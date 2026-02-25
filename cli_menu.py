"""
CLI menu for song selection and playback.

This module provides a unified interactive interface for browsing songs,
playing music, and downloading from YouTube URLs.
"""

import os
import random
import re
import sys

import constants as cv
import listen_history
import play_song
import playback_timeline
import playlists
import reader
import search
import song_metadata
import youtube_integration
import youtube_utils

# Track last played song for replay function
_last_played_uid = None


def _try_num_command(arg, name, handler):
    """Parse a numeric argument and invoke *handler*, or print an error."""
    try:
        num = int(arg.strip())
        handler(num)
    except ValueError:
        print(f"Invalid {name} command. Usage: {name} <number>")


def _handle_input_fallback(user_input, songs):
    """Handle URL, ad-hoc queue, song number, or fuzzy search.

    Returns:
        bool: True if the library should be refreshed afterwards.
    """
    url_type = youtube_utils.detect_url_type(user_input)

    if url_type == "video":
        _handle_video_download(user_input)
        return True

    if url_type == "playlist":
        _handle_playlist_download(user_input)
        return True

    # Ad-hoc queue: 2+ numbers separated by commas/spaces
    tokens = user_input.replace(",", " ").split()
    if len(tokens) >= 2 and all(t.isdigit() for t in tokens):
        _handle_adhoc_queue(tokens, songs)
        return True

    # Plain number → play that song, anything else → search
    limit, query = _parse_search_limit(user_input)
    try:
        choice = int(query)
        _handle_song_selection(str(choice), songs)
        return True
    except ValueError:
        _handle_search(query, songs, limit)
        return False


def _dispatch_command(user_input, songs):
    """Route a single user command to its handler.

    Returns:
        bool: True if the library should be refreshed and reprinted.
    """
    cmd = user_input.lower()

    # --- exact-match commands (dict lookup) ---
    exact_handlers = {
        "h": (lambda: _show_help(), False),
        "help": (lambda: _show_help(), False),
        "r": (lambda: _handle_replay(), True),
        "p": (lambda: _playlist_menu(), True),
        "t": (lambda: _display_timeline(), False),
        "shuffle": (lambda: _handle_shuffle_all(songs), True),
        "sh": (lambda: _handle_shuffle_all(songs), True),
        "rand": (lambda: _handle_random_offer(user_input, songs), True),
        "date": (lambda: _display_by_date(songs, reverse=False), False),
        "date r": (lambda: _display_by_date(songs, reverse=True), False),
        "top": (lambda: _display_by_play_count(songs, user_input), False),
        "--update-ytdlp": (lambda: _handle_update_ytdlp(), False),
    }
    if cmd in exact_handlers:
        handler, refresh = exact_handlers[cmd]
        handler()
        return refresh

    # --- prefix commands (table-driven iteration) ---
    prefix_handlers = [
        (
            "del ",
            lambda arg: _try_num_command(
                arg, "del", lambda n: _handle_delete(n, songs)
            ),
            True,
        ),
        (
            "ren ",
            lambda arg: _try_num_command(
                arg, "ren", lambda n: _handle_rename(n, songs)
            ),
            True,
        ),
        (
            "re ",
            lambda arg: _try_num_command(
                arg, "re", lambda n: _handle_redownload(n, songs)
            ),
            True,
        ),
        ("s ", lambda arg: _handle_stream(arg), True),
        ("loop ", lambda arg: _handle_loop(user_input, songs), True),
        ("rand ", lambda arg: _handle_random_offer(user_input, songs), True),
        ("top ", lambda arg: _display_by_play_count(songs, user_input), False),
        ("mode ", lambda arg: _handle_mode_command(arg), False),
    ]
    for prefix, handler, refresh in prefix_handlers:
        if cmd.startswith(prefix):
            handler(cmd[len(prefix) :])
            return refresh

    # --- quick-add (case-sensitive "+") ---
    if user_input.startswith("+"):
        _handle_quick_add(user_input[1:].strip(), songs)
        return False

    # --- fallback: URL / ad-hoc queue / number / search ---
    return _handle_input_fallback(user_input, songs)


def _print_current_song_status():
    """Print a one-line current/up-next status above the prompt."""
    current_uid = playback_timeline.get_current_song()
    if not current_uid:
        return
    song = song_metadata.get_song(current_uid)
    if not song:
        return
    resume_ms = playback_timeline.get_resume_ms()
    title = _truncate_title(song.get("title", "Unknown"), cv.SCREEN_WIDTH - 32)
    dur_str = _format_duration(song.get("duration", 0))
    if resume_ms > 0:
        pos_str = _format_duration(resume_ms // 1000)
        print(f"  \u266a {title}  [{pos_str} / {dur_str}]  \u2014 Enter to resume")
    else:
        print(f"  \u266a {title}  [{dur_str}]  \u2014 Enter to play")


def _handle_resume_current():
    """Play (or resume) the current song from its saved position."""
    current_uid = playback_timeline.get_current_song()
    if not current_uid:
        print("\nNo current song — play something first.")
        return
    song = song_metadata.get_song(current_uid)
    if not song:
        print("\nCurrent song not found in library.")
        return
    resume_ms = playback_timeline.get_resume_ms()
    _play_song(song, _from_timeline=True, _start_ms=resume_ms)


def display_menu():
    """Display interactive menu with two-column song list and unified input handling.

    The library is printed once on startup and only again when the user explicitly
    types 'l'.  All other commands operate against the in-memory ``songs`` list;
    that list is silently refreshed (without reprinting) after any operation that
    modifies the library so that song indices always stay correct.
    """
    songs = song_metadata.get_songs_alphabetically()
    _print_library(songs)

    while True:
        _print_current_song_status()
        user_input = input("> ").strip()
        cmd = user_input.lower()

        # Empty Enter → resume / play the current song
        if not user_input:
            _handle_resume_current()
            songs = song_metadata.get_songs_alphabetically()
            _print_library(songs)
            continue

        if cmd in ("q", "x"):
            print("-" * cv.SCREEN_WIDTH)
            break

        if cmd == "l":
            songs = song_metadata.get_songs_alphabetically()
            _print_library(songs)
            continue

        refresh = _dispatch_command(user_input, songs)

        if refresh:
            songs = song_metadata.get_songs_alphabetically()
            _print_library(songs)


def _print_library(songs):
    """Print song library in two columns

    Args:
        songs: List of song dictionaries
    """
    width = cv.SCREEN_WIDTH
    print("=" * width)
    print("SPEAR MUSIC LIBRARY".center(width))
    print("=" * width)

    if not songs:
        print("\nNo songs in library yet. Add songs by entering a YouTube URL.")
        print("\nCommands: [URL] download | s [URL] stream | r/h/q\n")
        return

    # Print songs in two columns
    col_width = width // 2
    half = (len(songs) + 1) // 2  # Round up for odd numbers

    for i in range(half):
        left_idx = i
        right_idx = i + half

        # Left column
        left_song = songs[left_idx]
        left_num = left_idx + 1
        title_w = (
            col_width - 11
        )  # 4 (num) + 1 (sp) + title + 1 (sp) + 5 (dur) = col_width
        left_title = _truncate_title(left_song["title"], title_w)
        left_duration = _format_duration(left_song.get("duration", 0))
        left_text = f"{left_num:<4} {left_title:<{title_w}} {left_duration:>5}"

        # Right column (if exists)
        if right_idx < len(songs):
            right_song = songs[right_idx]
            right_num = right_idx + 1
            right_title = _truncate_title(right_song["title"], title_w)
            right_duration = _format_duration(right_song.get("duration", 0))
            right_text = f"{right_num:<4} {right_title:<{title_w}} {right_duration:>5}"

            # Print both columns
            print(f"{left_text}  {right_text}")
        else:
            # Only left column
            print(left_text)

    # Command strip
    print(
        "[ shuffle : rand <N> : loop <num> : t (timeline) : date : top : del/ren/re <num> ]".center(
            width
        )
    )
    print("[ + <num> <pl> : p (playlists) : l (library) : r (replay) : h (help) : q (quit) ]".center(width))


def _truncate_title(title, max_length):
    """Truncate title with ellipsis if too long

    Args:
        title: Song title
        max_length: Maximum length

    Returns:
        str: Truncated title
    """
    if len(title) <= max_length:
        return title
    return title[: max_length - 3] + "..."


def _format_duration(seconds):
    """Format duration in seconds as MM:SS

    Args:
        seconds: Duration in seconds

    Returns:
        str: Formatted duration string
    """
    if seconds <= 0:
        return "0:00"

    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


def _handle_song_selection(user_input, songs):
    """Handle song number selection

    Args:
        user_input: User input string
        songs: List of songs
    """
    if not songs:
        print("No songs available.")
        return

    try:
        choice = int(user_input)
        if 1 <= choice <= len(songs):
            selected_song = songs[choice - 1]
            _play_song(selected_song)
        else:
            print(f"Invalid choice. Please enter a number between 1 and {len(songs)}")
    except ValueError:
        print("Invalid input. Please enter a song number, URL, or 'q' to quit")


def _handle_video_download(url):
    """Download video, add to library, and play immediately

    Args:
        url: YouTube video URL
    """
    uid = youtube_integration.download_and_add_video(url)

    if uid:
        # Get the newly added song and play it
        song = song_metadata.get_song(uid)
        if song:
            print(f"\n▶ Now playing: {song['title']}\n")
            _play_song(song)
    else:
        print("\n✗ Download failed")
        input("\nPress Enter to continue...")


def _handle_playlist_download(url):
    """Confirm and download playlist

    Args:
        url: YouTube playlist URL
    """
    # Get playlist info first
    playlist_metadata = youtube_utils.get_playlist_metadata(url)

    if not playlist_metadata:
        print("\n✗ Failed to fetch playlist information")
        input("\nPress Enter to continue...")
        return

    playlist_title = playlist_metadata["title"]
    video_count = len(playlist_metadata["video_urls"])

    # Confirm with user
    print(f"\nPlaylist: {playlist_title}")
    print(f"Videos: {video_count}")
    confirm = input(f"\nDownload {video_count} videos? (y/n): ").strip().lower()

    if confirm == "y":
        print("\n📥 Downloading playlist...")
        playlist_uid = youtube_integration.download_and_add_playlist(url)

        if playlist_uid:
            print("\n✓ Playlist download complete!")
        else:
            print("\n✗ Playlist download failed")
            input("\nPress Enter to continue...")
    else:
        print("\nPlaylist download cancelled")


def _play_song(song, _from_timeline=False, _single_nav=False, _start_ms=0, _in_playlist=False):
    """Play the selected song, following G/H navigation chains.

    Args:
        song: Song dictionary from database
        _from_timeline: True when the song was pre-loaded into the timeline
                        (e.g. playlist mode) — skips re-appending to avoid
                        overwriting the queued future.
        _single_nav: When True, return immediately after a single G/H press
                     instead of chaining.  The pending song is NOT played;
                     the caller is expected to handle it (e.g. to print a
                     playlist counter before playing the next song).
        _start_ms: Start playback from this offset in milliseconds (0 = beginning).
                   Only applied to the first song in a navigation chain.
        _in_playlist: When True, suppresses auto-advance after natural song end —
                      _play_playlist manages cursor advancement itself.

    Returns:
        bool: True if the user navigated away via G/H at any point.
    """
    global _last_played_uid

    path = song.get("path")
    uid = song.get("uid")
    title = song.get("title", "Unknown")

    if not path:
        print(f"\nError: No file path for song '{title}'")
        return False

    # Resolve filename to full path via library directory
    full_path = song_metadata.resolve_path(path)
    navigated = False

    # While loop handles chained G/H navigation without recursion depth risk
    while True:
        _last_played_uid = uid

        # Record in playback timeline (browser-history model).
        # Skip when navigating via G/H — the timeline cursor was already moved by
        # skip_back() / skip_forward() so we must not append again.
        if uid and not _from_timeline:
            playback_timeline.append_song(uid)

        play_song.play_song(full_path, song_uid=uid, title=title, start_ms=_start_ms)
        _start_ms = 0  # Only the first play in the chain gets the resume offset

        # Check whether the user pressed G or H to navigate to a different song
        pending_uid = play_song.get_pending_song()
        if not pending_uid:
            # Playback ended without a navigation event — persist position.
            _exit_reason = play_song.get_exit_reason()
            if _exit_reason != "ended":
                # Interrupted (Q / X) — save resume point
                playback_timeline.set_resume_ms(play_song.get_last_position_ms())
            elif not _in_playlist:
                # Song finished naturally in standalone mode → advance current song
                _pick_next_current()
            break

        pending = song_metadata.get_song(pending_uid)
        if not pending or not pending.get("path"):
            # Navigation target vanished — save position and stop
            _exit_reason = play_song.get_exit_reason()
            if _exit_reason != "ended":
                playback_timeline.set_resume_ms(play_song.get_last_position_ms())
            break

        # G/H navigation occurred — cursor already moved, resume_ms already reset
        navigated = True

        # In single-nav mode, return immediately so the caller can
        # print the playlist counter before the next song plays.
        # Do NOT save position here: cursor has already moved to the new song.
        if _single_nav:
            break

        # Chain: update for next iteration
        _from_timeline = True  # All subsequent songs come from the timeline
        full_path = song_metadata.resolve_path(pending["path"])
        uid = pending.get("uid")
        title = pending.get("title", "Unknown")

    return navigated


def _show_help():
    """Display help information for all commands"""
    help_text = """
================================================================================
                              SPEAR - HELP
================================================================================

PLAYBACK COMMANDS:
  <number>              Play song by number (e.g., "5")
  2,5,3  or  2 5 3      Play songs as ad-hoc queue (Q=next, X=abort all)
  shuffle  /  sh        Shuffle and play entire library once
  rand [N]              Suggest N random songs to pick from (default: 5)
  loop <number>         Loop a song on repeat until Q or X
  r                     Replay last played song
  s <url>               Stream from URL without downloading

SEARCH:
  <text>                Fuzzy search song titles  (e.g. "dark side")
  <text> /N             Limit results to N  (e.g. "dark side /20")
  (Typo-tolerant: "darck syde" still finds "Dark Side of the Moon")

DISPLAY COMMANDS:
  t                     Show playback timeline (±10 around current position)
  date                  List all songs by date added (newest first)
  date r                List all songs by date added (oldest first)
  top                   Most played songs, all time
  top r                 Least played songs, all time
  top w  /  top wr      Most / least played this week
  top m  /  top mr      Most / least played this month
  top y  /  top yr      Most / least played this year
  top <N>  /  top <N>r  Most / least played in last N days  (e.g. top 30)

LIBRARY MANAGEMENT:
  <url>                 Download YouTube video and add to library
  del <number>          Delete song from library and disk
  ren <number>          Rename song (database only, file unchanged)
  re <number>           Re-download song (updates file and duration)

PLAYLIST COMMANDS:
  p                     Open playlist menu
  + <num> <name>        Quick-add song to playlist (e.g., "+ 5 Favorites")

PLAYLIST MENU (inside 'p'):
  <number>              View playlist details
  c                     Create new playlist
  del <number>          Delete playlist
  ren <number>          Rename playlist
  dup <number>          Duplicate playlist
  merge <src> <dest>    Merge playlists (append src to dest)
  q                     Back to main menu

PLAYLIST DETAIL (inside playlist):
  <number>              Play song at position
  play / play shuffle   Play all songs / shuffled
  add <song_num>        Add song from library by number
  rm <position>         Remove song at position
  mv <from> <to>        Move song to new position
  clear                 Remove all songs from playlist
  q                     Back to playlist menu

PLAYBACK CONTROLS (while playing):
  Space                 Play/Pause
  S                     Stop (reset to beginning)
  R                     Restart from beginning
  G                     Previous song
  H                     Next song
  A / a                 Seek backward 30s / 5s
  D / d                 Seek forward 30s / 5s
  0-9                   Jump to percentage (0=0%, 9=90%)
  Q                     Skip to next song in queue (or exit if no queue)
  X                     Abort entire queue and exit playback

OTHER COMMANDS:
  l                     Reprint the song library
  mode r                Next-song mode: Random (default)
  mode a                Next-song mode: Alphabetical
  mode h                Next-song mode: History (forward in timeline)
  mode hr               Next-song mode: History (reverse / backwards)
  <Enter>               Resume current song (or play it from beginning)
  --update-ytdlp          Update yt-dlp and restart (only works when launched via run.bat)
  h or help             Show this help message
  q or x                Quit program

================================================================================
"""
    print(help_text)


def _handle_update_ytdlp():
    """Exit with code 100 so run.bat updates yt-dlp and restarts the app.

    Only meaningful when the application was launched via run.bat; if run
    directly from the terminal the user will simply be told to update manually.
    """
    print("\nThis will close Spear, update yt-dlp, then restart automatically.")
    print("(Only works when launched via run.bat — otherwise update manually.)")
    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm == "y":
        print("\nExiting to update yt-dlp...")
        sys.exit(100)


def _handle_stream(url):
    """Stream from URL without downloading

    Args:
        url: URL to stream from
    """
    print(f"\n▶ Streaming from: {url}\n")
    play_song.stream_from_url(url)


def _handle_mode_command(arg):
    """Handle the 'mode' command: switch the next-song selection mode.

    Valid arguments: r/random, a/alpha, h/history, hr/history_r
    """
    mapping = {
        "r": "random",
        "random": "random",
        "a": "alpha",
        "alpha": "alpha",
        "h": "history",
        "history": "history",
        "hr": "history_r",
        "history_r": "history_r",
    }
    mode = mapping.get(arg.strip().lower())
    if not mode:
        print(
            f"Unknown mode '{arg.strip()}'.  Use: "
            "mode r (random) | a (alpha) | h (history) | hr (history reverse)"
        )
        return
    reader.set_next_song_mode(mode)
    labels = {
        "random": "Random",
        "alpha": "Alphabetical",
        "history": "History (forward)",
        "history_r": "History (reverse)",
    }
    print(f"✓ Next-song mode set to: {labels[mode]}")


def _handle_replay():
    """Replay the last played song"""
    if not _last_played_uid:
        print("\nNo song played yet")
        return

    song = song_metadata.get_song(_last_played_uid)
    if song:
        print(f"\n▶ Replaying: {song['title']}\n")
        _play_song(song)
    else:
        print("\nLast played song not found in library")


def _handle_delete(num, songs):
    """Delete a song from library and disk

    Args:
        num: Song number (1-indexed)
        songs: List of songs
    """
    if not songs or num < 1 or num > len(songs):
        print(f"Invalid song number: {num}")
        return

    song = songs[num - 1]
    title = song.get("title", "Unknown")
    path = song.get("path")
    uid = song.get("uid")

    # Confirm deletion
    confirm = (
        input(f"\nDelete '{title}' from library and disk? (y/n): ").strip().lower()
    )

    if confirm == "y":
        # Delete from database
        song_metadata.delete_song(uid)

        # Delete file from disk
        full_path = song_metadata.resolve_path(path)
        if full_path and os.path.exists(full_path):
            try:
                os.remove(full_path)
                print("✓ Deleted from library and disk")
            except OSError as e:
                print(f"✓ Deleted from library (file deletion failed: {e})")
        else:
            print("✓ Deleted from library (file not found)")
    else:
        print("Delete cancelled")


def _handle_rename(num, songs):
    """Rename a song in the database only

    Args:
        num: Song number (1-indexed)
        songs: List of songs
    """
    if not songs or num < 1 or num > len(songs):
        print(f"Invalid song number: {num}")
        return

    song = songs[num - 1]
    old_title = song.get("title", "Unknown")
    uid = song.get("uid")

    print(f"\nCurrent title: {old_title}")
    new_title = input("New title: ").strip()

    if not new_title:
        print("Rename cancelled (empty title)")
        return

    # Update title in database
    song_metadata.update_song_title(uid, new_title)
    print(f"✓ Renamed to: {new_title}")


def _handle_redownload(num, songs):
    """Re-download a song to update file and duration

    Args:
        num: Song number (1-indexed)
        songs: List of songs
    """
    if not songs or num < 1 or num > len(songs):
        print(f"Invalid song number: {num}")
        return

    song = songs[num - 1]
    uid = song.get("uid")

    # Re-download
    success = youtube_integration.redownload_song(uid)

    if not success:
        input("\nPress Enter to continue...")


# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

_SEARCH_LIMIT_RE = re.compile(r"\s*/(?P<n>\d+)\s*$")


def _parse_search_limit(user_input: str) -> tuple[int, str]:
    """Parse an optional /N suffix from the end of a search query.

    Returns:
        (limit, query_without_suffix)
    """
    m = _SEARCH_LIMIT_RE.search(user_input)
    if m:
        limit = int(m.group("n"))
        query = user_input[: m.start()].strip()
        return limit, query
    return cv.DEFAULT_SEARCH_RESULTS, user_input.strip()


def _handle_search(query: str, songs: list, limit: int) -> None:
    """Run fuzzy search and display results."""
    if not query:
        return
    results = search.fuzzy_search(query, songs, limit=limit)
    _display_search_results(query, results, songs)


def _display_search_results(query: str, results: list, alpha_songs: list) -> None:
    """Print fuzzy search results with alphabetical #indices.

    Args:
        query:       The raw search string (for the header).
        results:     Ordered list of matching song dicts.
        alpha_songs: The full alphabetical song list (for index lookup).
    """
    alpha_index = {s["uid"]: i + 1 for i, s in enumerate(alpha_songs)}
    width = cv.SCREEN_WIDTH
    print("=" * width)
    print(f'SEARCH: "{query}"'.center(width))
    print("=" * width)

    if not results:
        print("  No matches found.")
        print()
        return

    for song in reversed(results):
        uid = song["uid"]
        idx = alpha_index.get(uid, "?")
        title = _truncate_title(song["title"], width - 16)
        duration = _format_duration(song.get("duration", 0))
        print(f"  {idx:<4}  {title:<{width - 16}} {duration:>5}")

    print()


def _display_timeline():
    """Print the playback timeline window: ±10 entries around the current cursor."""
    timeline = playback_timeline.get_timeline()
    cursor = playback_timeline.get_cursor()

    if not timeline or cursor < 0:
        print("\nTimeline is empty — play some songs first.")
        return

    # Build a dict keyed by position for fast lookup
    by_pos = {entry["position"]: entry["song_uid"] for entry in timeline}

    lo = cursor - 10
    hi = cursor + 10
    positions = sorted(pos for pos in by_pos if lo <= pos <= hi)

    width = cv.SCREEN_WIDTH
    print("=" * width)
    print("PLAYBACK TIMELINE".center(width))
    print("=" * width)

    for pos in positions:
        uid = by_pos[pos]
        song = song_metadata.get_song(uid)

        if song:
            title = _truncate_title(song["title"], width - 20)
            duration = _format_duration(song.get("duration", 0))
            meta = f"{title} {duration:>5}"
        else:
            meta = "[deleted]"

        offset = pos - cursor
        if offset == 0:
            marker = "►"
            label = f"  {marker} now   {meta}"
        elif offset < 0:
            label = f"  {'':2}  {offset:+d}   {meta}"
        else:
            label = f"  {'':2}  +{offset}   {meta}"

        print(label)


def _display_by_date(songs, reverse=False):
    """Print all songs sorted by date added.

    Args:
        songs: Alphabetical song list (used to derive #indices for playback).
        reverse: False = newest first (default), True = oldest first.
    """
    # get_all_songs() returns ORDER BY add_date DESC already
    dated = song_metadata.get_all_songs()
    if reverse:
        dated = list(reversed(dated))

    if not dated:
        print("\nNo songs in library.")
        return

    # Build uid → 1-based alphabetical index map
    alpha_index = {s["uid"]: i + 1 for i, s in enumerate(songs)}

    direction = "oldest first" if reverse else "newest first"
    width = cv.SCREEN_WIDTH
    print("=" * width)
    print(f"SONGS BY DATE ADDED  ({direction})".center(width))
    print("=" * width)

    for song in reversed(dated):
        uid = song["uid"]
        idx = alpha_index.get(uid, "?")
        title = _truncate_title(song["title"], width - 28)
        duration = _format_duration(song.get("duration", 0))
        add_date = song.get("add_date", "")[:10]  # YYYY-MM-DD
        print(f"  {idx:<4}  {title:<{width - 28}} {duration:>5}  {add_date}")

    print()


def _display_by_play_count(songs, user_input):
    """Print songs ranked by play count for a chosen time period.

    Supported sub-commands after 'top':
        (empty)      all-time, descending
        r            all-time, ascending (least played)
        w / wr       this week desc / asc
        m / mr       this month desc / asc
        y / yr       this year desc / asc
        <N> / <N>r   last N days desc / asc  (e.g. "top 30", "top 30r")

    Args:
        songs: Alphabetical song list (used to derive #indices for playback).
        user_input: Raw command string from the user (e.g. "top m").
    """
    parts = user_input.strip().split(maxsplit=1)
    sub = parts[1].strip() if len(parts) > 1 else ""

    reverse = sub.endswith("r") and sub != "r"  # 'r' alone = all-time reverse
    # Strip trailing 'r' for period lookup
    period_key = sub.rstrip("r").strip()

    # Dispatch
    if sub == "" or sub == "r":
        period_label = "ALL TIME"
        ranked = listen_history.get_top_songs_all_time(reverse=(sub == "r"))
    elif period_key == "w":
        period_label = "THIS WEEK"
        ranked = listen_history.get_top_songs_this_week(reverse=reverse)
    elif period_key == "m":
        period_label = "THIS MONTH"
        ranked = listen_history.get_top_songs_this_month(reverse=reverse)
    elif period_key == "y":
        period_label = "THIS YEAR"
        ranked = listen_history.get_top_songs_this_year(reverse=reverse)
    elif period_key.isdigit():
        days = int(period_key)
        period_label = f"LAST {days} DAYS"
        ranked = listen_history.get_top_songs_last_n_days(days, reverse=reverse)
    else:
        print(
            f"Unknown top command: '{user_input}'  (try: top / top w / top m / top y / top 30)"
        )
        return

    direction = "LEAST PLAYED" if reverse else "MOST PLAYED"
    header = f"{direction} — {period_label}"

    if not ranked:
        print(f"\nNo listen history for {period_label.lower()}.")
        return

    # Build uid → 1-based alphabetical index map
    alpha_index = {s["uid"]: i + 1 for i, s in enumerate(songs)}

    width = cv.SCREEN_WIDTH
    print("=" * width)
    print(header.center(width))
    print("=" * width)

    for entry in reversed(list(ranked)):
        uid = entry["uid"]
        idx = alpha_index.get(uid)
        if idx is None:
            continue  # Song deleted from library — skip
        title = _truncate_title(entry["title"], width - 22)
        count = entry["listen_count"]
        plays = "play" if count == 1 else "plays"
        print(f"  {idx:<4}  {title:<{width - 22}}  {count} {plays}")


# ============================================================================
# QUEUE / PLAYBACK HELPER FUNCTIONS
# ============================================================================


def _pick_next_alpha_song_uid():
    """Return the UID of the next song alphabetically after the current one."""
    current_uid = playback_timeline.get_current_song()
    songs = song_metadata.get_songs_alphabetically()
    if not songs:
        return None
    if not current_uid:
        return songs[0].get("uid")
    for i, s in enumerate(songs):
        if s.get("uid") == current_uid:
            return songs[(i + 1) % len(songs)].get("uid")
    return songs[0].get("uid")  # Fallback


def _pick_next_current():
    """Pick the next current song based on the configured mode.

    Appends the chosen song to the timeline and advances the cursor to it.
    Called after a song ends naturally (standalone) or after a playlist finishes.
    Returns the chosen song UID, or None if no songs are available.
    """
    mode = reader.get_next_song_mode()

    if mode == "history":
        uid = playback_timeline.skip_forward(shuffle=False)
        return uid

    if mode == "history_r":
        uid = playback_timeline.skip_back()
        return uid

    if mode == "alpha":
        uid = _pick_next_alpha_song_uid()
    else:  # random (default)
        uid = song_metadata.get_random_song()

    if uid:
        playback_timeline.append_song(uid)
    return uid


def _handle_adhoc_queue(tokens, songs):
    """Play songs by index list as an ad-hoc queue (not saved as a playlist).

    Args:
        tokens: List of digit strings representing 1-based song indices
        songs: Current full song list
    """
    indices = []
    for t in tokens:
        idx = int(t)
        if idx < 1 or idx > len(songs):
            print(f"Invalid song number: {idx} (must be 1-{len(songs)})")
            return
        indices.append(idx)

    queue = [{"uid": songs[i - 1]["uid"]} for i in indices]
    titles = ", ".join(songs[i - 1]["title"][:20] for i in indices[:3])
    ellipsis = "..." if len(indices) > 3 else ""
    print(f"\n▶ Ad-hoc queue: {titles}{ellipsis}  ({len(indices)} songs)")
    _play_playlist(queue, shuffle=False)


def _handle_shuffle_all(songs):
    """Shuffle and play all songs in the library once."""
    if not songs:
        print("\nNo songs in library")
        return
    print(f"\n▶ Shuffling all {len(songs)} songs...")
    queue = [{"uid": s["uid"]} for s in songs]
    _play_playlist(queue, shuffle=True)


def _handle_random_offer(user_input, songs):
    """Display N random songs and let the user pick one to play.

    Args:
        user_input: Raw input string (e.g. "rand" or "rand 10")
        songs: Current full song list
    """
    if not songs:
        print("\nNo songs in library")
        return

    parts = user_input.strip().split()
    n = cv.DEFAULT_RANDOM_OFFER_COUNT
    if len(parts) > 1:
        try:
            n = int(parts[1])
            if n < 1:
                raise ValueError
        except ValueError:
            print("Invalid count. Usage: rand [number]")
            return

    n = min(n, len(songs))
    offered = random.sample(songs, n)

    width = cv.SCREEN_WIDTH
    print("=" * width)
    print("RANDOM SUGGESTIONS".center(width))
    print("=" * width)
    for i, s in enumerate(offered, 1):
        title = _truncate_title(s["title"], width - 15)
        duration = _format_duration(s.get("duration", 0))
        print(f"  {i:<3} {title:<{width - 15}} {duration:>5}")
    print()

    choice_str = input("Pick a number to play, or Enter to go back: ").strip()
    if not choice_str:
        return
    try:
        choice = int(choice_str)
        if 1 <= choice <= len(offered):
            _play_song(offered[choice - 1])
        else:
            print(f"Invalid choice. Enter 1-{len(offered)}")
    except ValueError:
        print("Invalid input")


def _handle_loop(user_input, songs):
    """Loop a single song on repeat until Q or X is pressed.

    Args:
        user_input: Raw input string (e.g. "loop 5")
        songs: Current full song list
    """
    parts = user_input.strip().split()
    if len(parts) < 2:
        print("Usage: loop <number>")
        return
    try:
        num = int(parts[1])
    except ValueError:
        print("Usage: loop <number>")
        return

    if not songs or num < 1 or num > len(songs):
        print(f"Invalid song number: {num} (must be 1-{len(songs)})")
        return

    song = songs[num - 1]
    path = song.get("path")
    uid = song.get("uid")
    title = song.get("title", "Unknown")

    if not path:
        print(f"\nError: No file path for song '{title}'")
        return

    # Resolve filename to full path via library directory
    full_path = song_metadata.resolve_path(path)

    global _last_played_uid
    _last_played_uid = uid

    if uid:
        playback_timeline.append_song(uid)

    print(f"\n[Loop] {title}  —  Q: skip next / X: stop")
    play_song.play_song(full_path, song_uid=uid, title=title, loop_mode=True)

    # If G/H was pressed to escape loop mode, follow through to that song
    pending_uid = play_song.get_pending_song()
    if pending_uid:
        pending = song_metadata.get_song(pending_uid)
        if pending:
            _play_song(pending, _from_timeline=True)


# ============================================================================
# PLAYLIST MENU FUNCTIONS
# ============================================================================


def _playlist_menu():
    """Display playlist management menu"""
    while True:
        all_playlists = playlists.get_all_playlists()
        _display_playlists(all_playlists)

        user_input = input("> ").strip()

        # Back to main menu
        if user_input.lower() in ["q", "x", "b"]:
            break

        # Create playlist
        if user_input.lower() == "c":
            _handle_create_playlist()
            continue

        # Delete playlist
        if user_input.lower().startswith("del "):
            try:
                num = int(user_input[4:].strip())
                _handle_delete_playlist(num, all_playlists)
            except ValueError:
                print("Invalid command. Usage: del <number>")
            continue

        # Rename playlist
        if user_input.lower().startswith("ren "):
            try:
                num = int(user_input[4:].strip())
                _handle_rename_playlist(num, all_playlists)
            except ValueError:
                print("Invalid command. Usage: ren <number>")
            continue

        # Duplicate playlist
        if user_input.lower().startswith("dup "):
            try:
                num = int(user_input[4:].strip())
                _handle_duplicate_playlist(num, all_playlists)
            except ValueError:
                print("Invalid command. Usage: dup <number>")
            continue

        # Merge playlists
        if user_input.lower().startswith("merge "):
            parts = user_input[6:].strip().split()
            if len(parts) == 2:
                try:
                    src = int(parts[0])
                    dest = int(parts[1])
                    _handle_merge_playlists(src, dest, all_playlists)
                except ValueError:
                    print("Invalid command. Usage: merge <src_num> <dest_num>")
            else:
                print("Invalid command. Usage: merge <src_num> <dest_num>")
            continue

        # Enter playlist detail view
        try:
            num = int(user_input)
            if 1 <= num <= len(all_playlists):
                _playlist_detail_menu(all_playlists[num - 1])
            else:
                print(f"Invalid choice. Enter 1-{len(all_playlists)}")
        except ValueError:
            print("Invalid input")


def _display_playlists(all_playlists):
    """Display all playlists with song counts"""
    width = cv.SCREEN_WIDTH
    print("=" * width)
    print("PLAYLISTS".center(width))
    print("=" * width)

    if not all_playlists:
        print("\nNo playlists yet. Press 'c' to create one.")
        print("\nCommands: c create | q back\n")
        return

    col_width = width // 2
    half = (len(all_playlists) + 1) // 2

    for i in range(half):
        left_idx = i
        right_idx = i + half

        # Left column
        pl = all_playlists[left_idx]
        stats = playlists.get_playlist_stats(pl["uid"])
        count = stats["song_count"] if stats else 0
        empty_tag = " (empty)" if count == 0 else ""
        left_text = f"{left_idx + 1}  {_truncate_title(pl['name'], col_width - 18)} ({count} songs){empty_tag}"

        # Right column
        if right_idx < len(all_playlists):
            pl_r = all_playlists[right_idx]
            stats_r = playlists.get_playlist_stats(pl_r["uid"])
            count_r = stats_r["song_count"] if stats_r else 0
            empty_tag_r = " (empty)" if count_r == 0 else ""
            right_text = f"{right_idx + 1}  {_truncate_title(pl_r['name'], col_width - 18)} ({count_r} songs){empty_tag_r}"
            print(f"{left_text:<{col_width}}{right_text}")
        else:
            print(left_text)

    print("\n[num] view | c create | del/ren/dup [num] | merge [src] [dest] | q back\n")


def _playlist_detail_menu(playlist):
    """Display and manage a single playlist's contents"""
    playlist_uid = playlist["uid"]

    while True:
        songs = playlists.get_playlist_songs(playlist_uid)
        pl_data = playlists.get_playlist(playlist_uid)

        if not pl_data:
            print("Playlist not found")
            break

        _display_playlist_songs(pl_data, songs)

        user_input = input("> ").strip()

        # Back to playlist menu
        if user_input.lower() in ["q", "x", "b"]:
            break

        # Play all
        if user_input.lower() == "play":
            if not songs:
                print("Playlist is empty")
            else:
                _play_playlist(songs, shuffle=False)
            continue

        # Play shuffled
        if user_input.lower() == "play shuffle":
            if not songs:
                print("Playlist is empty")
            else:
                _play_playlist(songs, shuffle=True)
            continue

        # Add song from library
        if user_input.lower().startswith("add "):
            try:
                song_num = int(user_input[4:].strip())
                _handle_add_song_to_playlist(playlist_uid, song_num)
            except ValueError:
                print("Invalid command. Usage: add <song_number>")
            continue

        # Remove song at position
        if user_input.lower().startswith("rm "):
            try:
                pos = int(user_input[3:].strip())
                _handle_remove_from_playlist(playlist_uid, pos, songs)
            except ValueError:
                print("Invalid command. Usage: rm <position>")
            continue

        # Move song
        if user_input.lower().startswith("mv "):
            parts = user_input[3:].strip().split()
            if len(parts) == 2:
                try:
                    from_pos = int(parts[0])
                    to_pos = int(parts[1])
                    _handle_move_song(playlist_uid, from_pos, to_pos, songs)
                except ValueError:
                    print("Invalid command. Usage: mv <from> <to>")
            else:
                print("Invalid command. Usage: mv <from> <to>")
            continue

        # Clear playlist
        if user_input.lower() == "clear":
            _handle_clear_playlist(playlist_uid, pl_data["name"])
            continue

        # Play song at position
        try:
            pos = int(user_input)
            if 1 <= pos <= len(songs):
                song_item = songs[pos - 1]
                song = song_metadata.get_song(song_item["uid"])
                if song:
                    _play_song(song)
                else:
                    print("Song not found in library")
            else:
                print(f"Invalid position. Enter 1-{len(songs)}")
        except ValueError:
            print("Invalid input")


def _display_playlist_songs(playlist, songs):
    """Display songs in a playlist"""
    width = cv.SCREEN_WIDTH
    print("=" * width)
    print(f"PLAYLIST: {playlist['name']}".center(width))
    print("=" * width)

    if not songs:
        print("\n(empty playlist)")
        print("\nCommands: add <num> | play | q back\n")
        return

    # Show songs with positions
    for song in songs:
        pos = song["position"]
        title = _truncate_title(song.get("title") or "Unknown", width - 15)
        duration = _format_duration(song.get("duration") or 0)
        print(f"  {pos:<4} {title:<{width - 15}} {duration:>5}")

    # Stats
    stats = playlists.get_playlist_stats(playlist["uid"])
    if stats:
        total_dur = _format_duration(stats["total_duration"])
        print(f"\n  Total: {stats['song_count']} songs, {total_dur}")

    print("\n[pos] play | play [shuffle] | add/rm [num] | mv [from] [to] | clear | q\n")


def _play_playlist(songs, shuffle=False):
    """Play all songs in a playlist sequentially"""
    global _last_played_uid

    song_list = list(songs)  # Copy to avoid modifying original
    if shuffle:
        random.shuffle(song_list)

    print(f"\n▶ Playing {len(song_list)} songs" + (" (shuffled)" if shuffle else ""))

    # Load the entire queue into the timeline upfront so the full session is
    # recorded as a browsing-history block (G/H navigation is aware of it too).
    valid_uids = [s["uid"] for s in song_list if s.get("uid")]
    if valid_uids:
        playback_timeline.append_song_list(valid_uids)

    # Record the timeline base so we can map cursor position → playlist index.
    # append_song_list places song_list[0] at base+1, [1] at base+2, etc.
    # The cursor is now at base+1 (first song).
    timeline_base = playback_timeline.get_cursor() - 1

    aborted = False
    navigated_away = False
    i = 0
    while i < len(song_list):
        song_item = song_list[i]
        song = song_metadata.get_song(song_item["uid"])
        if not song:
            print("Skipping: song not found in library")
            # Keep cursor in sync even for skipped entries
            if i < len(song_list) - 1:
                playback_timeline.advance_cursor()
            i += 1
            continue

        print(f"\n[{i + 1}/{len(song_list)}]")
        _last_played_uid = song["uid"]
        # _play_song returns True if the user navigated away via G/H.
        # _single_nav ensures it returns after one press without playing
        # the pending song, so the loop can print the counter first.
        navigated = _play_song(song, _from_timeline=True, _single_nav=True, _in_playlist=True)

        if navigated:
            # G/H was used — figure out where the cursor landed and resume
            # from there if it's still within the playlist range.
            current_cursor = playback_timeline.get_cursor()
            landed_index = current_cursor - timeline_base - 1

            # Check for X/abort press during the navigation
            if play_song.get_exit_reason() == "abort":
                aborted = True
                break

            # Landed outside the playlist range — user navigated away entirely
            if landed_index < 0 or landed_index >= len(song_list):
                navigated_away = True
                break

            # Resume: play the song the user navigated to (cursor is already
            # at its position, so no advance_cursor needed).
            i = landed_index
            continue

        exit_reason = play_song.get_exit_reason()

        # X = abort the entire queue
        if exit_reason == "abort":
            aborted = True
            break

        # Q ("skip") or natural end — advance cursor and continue to next song
        if i < len(song_list) - 1:
            playback_timeline.advance_cursor()
        i += 1

    # After the playlist finishes normally (not aborted, not navigated away),
    # pick the next current song so the menu shows what's up next.
    if not aborted and not navigated_away:
        _pick_next_current()


def _handle_quick_add(args, songs):
    """Quick-add a song to a playlist from main menu"""
    parts = args.split(maxsplit=1)
    if len(parts) != 2:
        print("Usage: + <song_number> <playlist_name>")
        return

    try:
        song_num = int(parts[0])
    except ValueError:
        print("Invalid song number")
        return

    playlist_name = parts[1].strip()

    if not songs or song_num < 1 or song_num > len(songs):
        print(f"Invalid song number: {song_num}")
        return

    song = songs[song_num - 1]

    # Find or create playlist
    pl = playlists.get_playlist_by_name(playlist_name)
    if not pl:
        confirm = (
            input(f"Create new playlist '{playlist_name}'? (y/n): ").strip().lower()
        )
        if confirm == "y":
            try:
                playlist_uid = playlists.create_playlist(playlist_name)
                print(f"✓ Created playlist: {playlist_name}")
            except ValueError as e:
                print(f"✗ {e}")
                return
        else:
            print("Cancelled")
            return
    else:
        playlist_uid = pl["uid"]

    # Add song
    playlists.add_to_playlist(playlist_uid, song["uid"])
    print(f"✓ Added '{song['title']}' to '{playlist_name}'")


def _handle_create_playlist():
    """Create a new playlist"""
    name = input("\nPlaylist name: ").strip()
    if not name:
        print("Cancelled (empty name)")
        return

    try:
        playlists.create_playlist(name)
        print(f"✓ Created playlist: {name}")
    except ValueError as e:
        print(f"✗ {e}")
        input("\nPress Enter to continue...")


def _handle_delete_playlist(num, all_playlists):
    """Delete a playlist"""
    if num < 1 or num > len(all_playlists):
        print(f"Invalid playlist number: {num}")
        return

    pl = all_playlists[num - 1]
    confirm = input(f"\nDelete playlist '{pl['name']}'? (y/n): ").strip().lower()

    if confirm == "y":
        playlists.delete_playlist(pl["uid"])
        print(f"✓ Deleted playlist: {pl['name']}")
    else:
        print("Cancelled")


def _handle_rename_playlist(num, all_playlists):
    """Rename a playlist"""
    if num < 1 or num > len(all_playlists):
        print(f"Invalid playlist number: {num}")
        return

    pl = all_playlists[num - 1]
    print(f"\nCurrent name: {pl['name']}")
    new_name = input("New name: ").strip()

    if not new_name:
        print("Cancelled (empty name)")
        return

    try:
        playlists.rename_playlist(pl["uid"], new_name)
        print(f"✓ Renamed to: {new_name}")
    except ValueError as e:
        print(f"✗ {e}")
        input("\nPress Enter to continue...")


def _handle_duplicate_playlist(num, all_playlists):
    """Duplicate a playlist"""
    if num < 1 or num > len(all_playlists):
        print(f"Invalid playlist number: {num}")
        return

    pl = all_playlists[num - 1]
    default_name = f"{pl['name']} (copy)"
    new_name = input(f"\nNew playlist name [{default_name}]: ").strip()

    if not new_name:
        new_name = default_name

    try:
        playlists.duplicate_playlist(pl["uid"], new_name)
        print(f"✓ Duplicated to: {new_name}")
    except ValueError as e:
        print(f"✗ {e}")
        input("\nPress Enter to continue...")


def _handle_merge_playlists(src_num, dest_num, all_playlists):
    """Merge source playlist into destination"""
    if src_num < 1 or src_num > len(all_playlists):
        print(f"Invalid source playlist number: {src_num}")
        return
    if dest_num < 1 or dest_num > len(all_playlists):
        print(f"Invalid destination playlist number: {dest_num}")
        return

    src = all_playlists[src_num - 1]
    dest = all_playlists[dest_num - 1]

    confirm = (
        input(f"\nAppend all songs from '{src['name']}' to '{dest['name']}'? (y/n): ")
        .strip()
        .lower()
    )

    if confirm == "y":
        playlists.merge_playlists(src["uid"], dest["uid"])
        print(f"✓ Merged '{src['name']}' into '{dest['name']}'")
    else:
        print("Cancelled")


def _handle_add_song_to_playlist(playlist_uid, song_num):
    """Add a song from library to playlist"""
    songs = song_metadata.get_songs_alphabetically()

    if not songs or song_num < 1 or song_num > len(songs):
        print(f"Invalid song number: {song_num}")
        return

    song = songs[song_num - 1]
    playlists.add_to_playlist(playlist_uid, song["uid"])
    print(f"✓ Added: {song['title']}")


def _handle_remove_from_playlist(playlist_uid, position, songs):
    """Remove song at position from playlist"""
    if position < 1 or position > len(songs):
        print(f"Invalid position: {position}")
        return

    song_item = songs[position - 1]
    playlists.remove_by_position(playlist_uid, position)
    print(f"✓ Removed: {song_item.get('title', 'Unknown')}")


def _handle_move_song(playlist_uid, from_pos, to_pos, songs):
    """Move song from one position to another"""
    if from_pos < 1 or from_pos > len(songs):
        print(f"Invalid from position: {from_pos}")
        return
    if to_pos < 1 or to_pos > len(songs):
        print(f"Invalid to position: {to_pos}")
        return

    if playlists.move_song(playlist_uid, from_pos, to_pos):
        print(f"✓ Moved song from position {from_pos} to {to_pos}")
    else:
        print("✗ Move failed")
        input("\nPress Enter to continue...")


def _handle_clear_playlist(playlist_uid, name):
    """Clear all songs from playlist"""
    confirm = input(f"\nRemove all songs from '{name}'? (y/n): ").strip().lower()

    if confirm == "y":
        playlists.clear_playlist(playlist_uid)
        print("✓ Cleared playlist")
    else:
        print("Cancelled")


if __name__ == "__main__":
    display_menu()
