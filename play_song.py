"""
Music playback using VLC with keyboard controls and progress display.

This module provides playback functionality for local files and streaming
from URLs, with real-time keyboard controls and a visual progress bar.
"""

import msvcrt
import os
import subprocess
import sys
import threading
import time
from typing import Optional

import vlc  # type: ignore[import-untyped]

import constants as cv
import listen_history
import playback_timeline


class MusicPlayer:
    """VLC-based music player with keyboard controls"""

    def __init__(self):
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.is_playing = False
        self.is_stopped = False
        self.should_exit = False
        self.pending_song_uid = None  # Set by G/H navigation for caller to pick up
        self.exit_reason = "ended"  # "ended", "skip" (Q), "abort" (X), "navigate" (G/H)
        self.loop_mode = False  # When True, restart song on natural end
        self.loop_count = 0  # Number of completed loop iterations
        self.current_song_uid = None
        self.start_time = None
        self.total_played_time = 0  # Track cumulative playback time
        self.last_duration = 0  # Store duration for display when stopped
        self.listen_log_count = 0  # Track how many times we've logged this song
        self.last_position_ms = 0  # Position (ms) captured when playback exits

    def play(
        self,
        path_or_url: str,
        song_uid: Optional[str] = None,
        title: Optional[str] = None,
        loop_mode: bool = False,
        start_ms: int = 0,
    ):
        """Play a song from local file or URL

        Args:
            path_or_url: Local file path or URL to play
            song_uid: Optional song UID for listen history logging
            title: Optional song title for display
            loop_mode: When True, restart song automatically on natural end
            start_ms: Start playback from this position in milliseconds (0 = from beginning)
        """
        self.current_song_uid = song_uid
        self.should_exit = False
        self.is_stopped = False
        self.pending_song_uid = None  # Reset for each new song
        self.exit_reason = "ended"  # Reset; overwritten by keyboard or _on_song_end
        self.loop_mode = loop_mode
        self.loop_count = 0
        self.total_played_time = 0
        self.listen_log_count = 0  # Reset log count for new song

        # Create media
        media = self.instance.media_new(path_or_url)
        self.player.set_media(media)

        # Start playback
        self.player.play()
        self.is_playing = True
        self.start_time = time.time()

        # Wait for media to parse
        time.sleep(0.5)

        # Seek to resume position if provided
        if start_ms > 0:
            self.player.set_time(start_ms)

        # Get title if not provided
        if title is None:
            title = (
                os.path.basename(path_or_url)
                if os.path.exists(path_or_url)
                else path_or_url
            )

        # Display UI and handle controls
        self._display_and_control(title)

    def _display_and_control(self, title: str):
        """Display playback UI and handle keyboard controls

        Args:
            title: Song title to display
        """
        # Start keyboard listener thread
        keyboard_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
        keyboard_thread.start()

        # Display UI
        self._display_header(title)

        # Main playback loop
        while not self.should_exit:
            if self.player.get_state() == vlc.State.Ended:
                # Song finished naturally
                self._on_song_end()
                if self.loop_mode:
                    # Restart for next loop iteration
                    self.loop_count += 1
                    self.total_played_time = 0
                    self.listen_log_count = 0
                    self.player.set_time(0)
                    self.player.play()
                    self.is_playing = True
                    self.start_time = time.time()
                    print(
                        f"\n{'[Loop ' + str(self.loop_count + 1) + ']':^{cv.SCREEN_WIDTH}}"
                    )
                    continue
                break

            # Check if we should log a listen (every 70% of duration played)
            self._check_and_log_listen()

            # Update progress bar
            self._update_progress()

            time.sleep(0.1)

        # Capture playback position for resume (0 when song ended naturally)
        if self.exit_reason in ("skip", "abort", "navigate"):
            self.last_position_ms = self.player.get_time()
        else:
            self.last_position_ms = 0

        # Clean up
        self.player.stop()
        print("\n")  # Move to new line after progress bar

    def _display_header(self, title: str):
        """Display centered song title and controls

        Args:
            title: Song title
        """
        width = cv.SCREEN_WIDTH

        # Center and wrap title
        title_lines = self._wrap_text(title, width)
        for line in title_lines:
            print(line.center(width))

        print()

        # Display controls (centered)
        controls = [
            "Space: Play/Pause  S: Stop  R: Restart  G: Prev  H: Next  Q/X: Exit",
            "A/a: -30s/-5s   D/d: +30s/+5s   0-9: Jump to %",
        ]
        for line in controls:
            print(line.center(width))

        print()

    def _wrap_text(self, text: str, width: int) -> list:
        """Wrap text to multiple lines if needed

        Args:
            text: Text to wrap
            width: Maximum width per line

        Returns:
            list: Lines of wrapped text
        """
        if len(text) <= width:
            return ["-" * width, text]

        lines = ["-" * width]
        words = text.split()
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            if len(test_line) <= width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines

    def _check_and_log_listen(self):
        """Check if we've crossed a 70% threshold and log if so"""
        if not self.current_song_uid:
            return

        # Get current total played time (including current session if playing)
        current_total = self.total_played_time
        if self.is_playing and self.start_time:
            current_total += time.time() - self.start_time

        # Get duration
        duration = (
            self.last_duration
            if self.last_duration > 0
            else self.player.get_length() / 1000
        )
        if duration <= 0:
            return

        # Check if we've crossed the next 70% threshold
        next_threshold = (self.listen_log_count + 1) * 0.7 * duration
        if current_total >= next_threshold:
            listen_history.log_listen(self.current_song_uid)
            self.listen_log_count += 1

    def _update_progress(self):
        """Update progress bar with format: (icon) time====v---- time"""
        # Get duration (use stored if stopped, otherwise from player)
        if self.is_stopped:
            duration = self.last_duration
            position = 0
            icon = "([]) "
        else:
            duration = self.player.get_length() / 1000  # ms to seconds
            position = self.player.get_time() / 1000  # ms to seconds

            if duration > 0:
                self.last_duration = duration  # Store for later use

            # Determine status icon
            if self.is_playing:
                icon = "(>)  "
            else:
                icon = "(||) "

        if duration <= 0:
            return

        # Calculate progress
        progress = min(position / duration, 1.0)

        # Format time with fixed width (M:SS format, pad to 4 chars)
        pos_str = self._format_time(position)
        dur_str = self._format_time(duration)

        # Calculate bar width based on fixed total width
        # Total: icon(5) + pos_time(4) + bar + dur_time(4) = 80
        bar_width = cv.SCREEN_WIDTH - 5 - len(pos_str) - len(dur_str)
        filled = min(
            int(bar_width * progress), bar_width - 1
        )  # ensure v + dashes always fit

        # Build bar with cursor: ===v---
        bar = "=" * filled + "v" + "-" * (bar_width - filled - 1)

        # Print with carriage return (overwrite same line); \033[K clears to end of line
        sys.stdout.write(f"\r{icon}{pos_str}{bar}{dur_str}\033[K")
        sys.stdout.flush()

    def _format_time(self, seconds: float) -> str:
        """Format seconds as M:SS with consistent width

        Args:
            seconds: Time in seconds

        Returns:
            str: Formatted time string (always 4 chars for times < 10 min)
        """
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    def _keyboard_listener(self):
        """Listen for keyboard input in separate thread"""
        key_actions = {
            b" ": self._toggle_play_pause,  # Space - play/pause
            b"s": self._stop,  # Stop (reset to beginning)
            b"S": self._stop,
            b"r": self._restart,  # Restart
            b"R": self._restart,
            b"g": self._previous_song,  # Previous song
            b"G": self._previous_song,
            b"h": self._next_song,  # Next song
            b"H": self._next_song,
            b"a": lambda: self._seek(-5000),  # Seek back 5s
            b"A": lambda: self._seek(-30000),  # Seek back 30s
            b"d": lambda: self._seek(5000),  # Seek forward 5s
            b"D": lambda: self._seek(30000),  # Seek forward 30s
        }
        exit_keys = {
            b"q": "skip",  # Skip to next in queue
            b"Q": "skip",
            b"x": "abort",  # Abort entire queue
            b"X": "abort",
        }

        while not self.should_exit:
            if msvcrt.kbhit():
                char = msvcrt.getch()

                if char in key_actions:
                    key_actions[char]()
                elif char in exit_keys:
                    self.exit_reason = exit_keys[char]
                    self.should_exit = True
                elif char.isdigit():  # Jump to decile
                    self._jump_to_percent(int(char) * 10)

            time.sleep(0.01)

    def _toggle_play_pause(self):
        """Toggle between play and pause"""
        # Don't allow resume if stopped
        if self.is_stopped:
            return

        if self.is_playing:
            # Track time before pausing
            if self.start_time:
                self.total_played_time += time.time() - self.start_time
                self.start_time = None
            self.player.pause()
            self.is_playing = False
        else:
            self.player.play()
            self.is_playing = True
            self.start_time = time.time()

    def _stop(self):
        """Stop playback and reset to beginning"""
        self.player.stop()
        self.is_playing = False
        self.is_stopped = True
        if self.start_time:
            self.total_played_time += time.time() - self.start_time
            self.start_time = None
        # Force immediate display update to show stop icon and cursor at start
        self._update_progress()

    def _restart(self):
        """Restart current song from beginning"""
        self.player.set_time(0)
        if not self.is_playing:
            self.player.play()
            self.is_playing = True
            self.is_stopped = False
            self.start_time = time.time()

    def _previous_song(self):
        """Skip to previous song in playback timeline"""
        prev_song = playback_timeline.skip_back()
        if prev_song:
            self.pending_song_uid = prev_song
            self.exit_reason = "navigate"
            self.should_exit = True

    def _next_song(self):
        """Skip to next song in playback timeline"""
        next_song = playback_timeline.skip_forward(shuffle=False)
        if next_song:
            self.pending_song_uid = next_song
            self.exit_reason = "navigate"
            self.should_exit = True

    def _seek(self, milliseconds: int):
        """Seek forward or backward

        Args:
            milliseconds: Amount to seek (positive = forward, negative = backward)
        """
        current_time = self.player.get_time()
        duration = self.player.get_length()
        new_time = max(0, current_time + milliseconds)
        if duration > 0:
            new_time = min(new_time, duration - 1000)  # 1 second buffer before end
        self.player.set_time(new_time)

    def _jump_to_percent(self, percent: int):
        """Jump to specific percentage of song

        Args:
            percent: Percentage (0-100)
        """
        duration = self.player.get_length()
        if duration > 0:
            new_time = int(duration * percent / 100)
            # Ensure we don't seek past the end (leave 1 second buffer)
            max_time = duration - 1000  # 1 second before end
            new_time = min(new_time, max_time)
            self.player.set_time(new_time)

    def _on_song_end(self):
        """Handle song ending naturally"""
        # Track final play time
        if self.start_time:
            self.total_played_time += time.time() - self.start_time
            self.start_time = None

        # Final check for any remaining log threshold
        self._check_and_log_listen()

        self.exit_reason = "ended"


# Global player instance
_player = MusicPlayer()


def play_song(
    path: str,
    song_uid: Optional[str] = None,
    title: Optional[str] = None,
    loop_mode: bool = False,
    start_ms: int = 0,
):
    """Play a song from local file

    Args:
        path: Local file path
        song_uid: Optional song UID for listen history
        title: Optional song title for display
        loop_mode: When True, restart song automatically on natural end
        start_ms: Start playback from this position in milliseconds (0 = from beginning)
    """
    _player.play(path, song_uid, title, loop_mode, start_ms=start_ms)


def get_pending_song() -> Optional[str]:
    """Return and clear any pending song UID set by G/H navigation.

    Returns the UID of the song the user navigated to via G (prev) or H (next),
    then clears it so subsequent calls return None.
    Returns None if no navigation occurred.
    """
    uid = _player.pending_song_uid
    _player.pending_song_uid = None
    return uid


def get_exit_reason() -> str:
    """Return the exit reason of the most recently completed song.

    Values:
        "ended"    Song finished playing naturally
        "skip"     User pressed Q (skip to next in queue)
        "abort"    User pressed X (abort entire queue)
        "navigate" User pressed G/H (navigated via timeline)
    """
    return _player.exit_reason


def get_last_position_ms() -> int:
    """Return the playback position (ms) captured when the last song exited.

    Non-zero when the user interrupted playback (Q/X/navigate).  Zero when
    the song ended naturally.  Use this to save a resume point.
    """
    return _player.last_position_ms


def stream_from_url(url: str):
    """Stream and play from URL without database interaction

    Uses yt-dlp to extract direct stream URL to avoid VLC YouTube parsing issues.

    Args:
        url: URL to stream from
    """
    # Use yt-dlp to get the direct stream URL
    try:
        result = subprocess.run(
            ["yt-dlp", "-f", "bestaudio", "--get-url", url],
            capture_output=True,
            text=True,
            check=True,
        )
        direct_url = result.stdout.strip()

        # Get title for display
        title_result = subprocess.run(
            ["yt-dlp", "--get-title", url],
            capture_output=True,
            text=True,
            check=True,
        )
        title = title_result.stdout.strip()

        # Play the direct stream URL
        _player.play(direct_url, song_uid=None, title=title)

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Failed to extract stream URL: {e}")
        if e.stderr:
            print(f"Error: {e.stderr}")
        input("\nPress Enter to continue...")
