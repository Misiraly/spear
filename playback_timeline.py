"""
Playback timeline management for tracking song playback history and queue.

This module maintains a cursor-based registry of songs that have been played
and are queued to play next. It allows bidirectional navigation (skip back/forward)
and persists the timeline across application restarts.

The timeline is distinct from listen history - it tracks opened songs,
while listen history only records songs where >=70% of duration was played.
"""

import os
import random
from datetime import datetime

import constants as cv
from db_utils import get_connection as _get_connection
from db_utils import row_to_timeline_dict as _row_to_timeline_dict
from db_utils import validate_uid as _validate_uid
from song_metadata import get_song as _get_song

# Constants
DB_PATH = cv.DB_PATH
MAX_PAST_ENTRIES = 100


def init_database(db_path=DB_PATH):
    """Create playback timeline tables if they don't exist"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Create timeline table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS playback_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_uid TEXT NOT NULL,
                position INTEGER NOT NULL,
                added_at TEXT NOT NULL
            )
        """
        )

        # Create cursor table (singleton)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS playback_cursor (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                position INTEGER NOT NULL,
                resume_ms INTEGER NOT NULL DEFAULT 0
            )
        """
        )

        # Migrate: add resume_ms column if it doesn't exist (for existing databases)
        try:
            cursor.execute(
                "ALTER TABLE playback_cursor ADD COLUMN resume_ms INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # Column already exists

        # Create index for position-based queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_timeline_position
            ON playback_timeline(position)
        """
        )

        # Initialize cursor if it doesn't exist
        cursor.execute(
            """
            INSERT OR IGNORE INTO playback_cursor (id, position)
            VALUES (1, -1)
        """
        )

        conn.commit()

    return db_path


def get_cursor(db_path=DB_PATH):
    """Get the current cursor position"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT position FROM playback_cursor WHERE id = 1")
        row = cursor.fetchone()
        return row[0] if row else -1


def _set_cursor(position, db_path=DB_PATH):
    """Set the cursor position (internal use). Resets resume_ms to 0."""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE playback_cursor SET position = ?, resume_ms = 0 WHERE id = 1
        """,
            (position,),
        )
        conn.commit()


def get_resume_ms(db_path=DB_PATH):
    """Return the saved resume position (ms) for the current song, or 0."""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT resume_ms FROM playback_cursor WHERE id = 1")
        row = cursor.fetchone()
        return row[0] if row else 0


def set_resume_ms(ms, db_path=DB_PATH):
    """Save a resume position (ms) for the current cursor song."""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE playback_cursor SET resume_ms = ? WHERE id = 1",
            (int(ms),),
        )
        conn.commit()


def get_current_song(db_path=DB_PATH):
    """Get the song_uid at the current cursor position, or None if empty/invalid"""
    cursor_pos = get_cursor(db_path)
    if cursor_pos < 0:
        return None

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT song_uid FROM playback_timeline
            WHERE position = ?
        """,
            (cursor_pos,),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def get_timeline(db_path=DB_PATH):
    """Get the full timeline as a list of dicts with position, song_uid, added_at"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT position, song_uid, added_at
            FROM playback_timeline
            ORDER BY position
        """
        )
        return [_row_to_timeline_dict(row) for row in cursor.fetchall()]


def clear_timeline(db_path=DB_PATH):
    """Delete all timeline entries and reset cursor to -1"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM playback_timeline")
        cursor.execute("UPDATE playback_cursor SET position = -1 WHERE id = 1")
        conn.commit()


def skip_back(db_path=DB_PATH):
    """
    Skip to the previous song in the timeline.

    Decrements cursor if > 0 and auto-skips deleted songs.
    Returns song_uid or None if at start or all past songs deleted.
    """
    cursor_pos = get_cursor(db_path)
    if cursor_pos <= 0:
        return None

    # Try to find a valid song going backwards
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        for new_pos in range(cursor_pos - 1, -1, -1):
            cursor.execute(
                """
                SELECT song_uid FROM playback_timeline
                WHERE position = ?
            """,
                (new_pos,),
            )
            row = cursor.fetchone()

            if row and _get_song(row[0], db_path) is not None:
                _set_cursor(new_pos, db_path)
                return row[0]

    # No valid song found
    return None


def _shuffle_future(cursor_pos, db_path=DB_PATH):
    """Shuffle all future timeline entries (positions > cursor_pos)"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT song_uid, position FROM playback_timeline
            WHERE position > ?
            ORDER BY position
        """,
            (cursor_pos,),
        )
        future_entries = cursor.fetchall()

        # Extract song_uids and shuffle them
        song_uids = [row[0] for row in future_entries]
        random.shuffle(song_uids)

        # Update positions with shuffled song_uids
        for idx, (_, position) in enumerate(future_entries):
            cursor.execute(
                """
                UPDATE playback_timeline
                SET song_uid = ?
                WHERE position = ?
            """,
                (song_uids[idx], position),
            )
        conn.commit()


def skip_forward(shuffle=False, db_path=DB_PATH):
    """
    Skip to the next song in the timeline.

    If no future exists, select a random song and append it.
    If shuffle=True, re-shuffle the future before advancing.
    Auto-skips deleted songs.

    Returns song_uid or None if no songs exist in database.
    """
    cursor_pos = get_cursor(db_path)

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Check if future exists
        cursor.execute(
            """
            SELECT COUNT(*) FROM playback_timeline
            WHERE position > ?
        """,
            (cursor_pos,),
        )
        future_count = cursor.fetchone()[0]

        # If no future, add a random song
        if future_count == 0:
            # Import here to avoid circular dependency
            from song_metadata import get_random_song

            random_uid = get_random_song(db_path)
            if random_uid is None:
                return None  # No songs in database

            # Append the random song
            new_pos = cursor_pos + 1
            cursor.execute(
                """
                INSERT INTO playback_timeline (song_uid, position, added_at)
                VALUES (?, ?, ?)
            """,
                (random_uid, new_pos, datetime.now().isoformat()),
            )
            conn.commit()
            _set_cursor(new_pos, db_path)
            return random_uid

        # If shuffle is on, re-shuffle the future
        if shuffle:
            _shuffle_future(cursor_pos, db_path)

        # Find next valid song
        cursor.execute(
            """
            SELECT position, song_uid FROM playback_timeline
            WHERE position > ?
            ORDER BY position
        """,
            (cursor_pos,),
        )

        for row in cursor.fetchall():
            pos, song_uid = row
            if _get_song(song_uid, db_path) is not None:
                _set_cursor(pos, db_path)
                return song_uid

    # No valid songs in future
    return None


def _delete_future(cursor_pos, db_path=DB_PATH):
    """Delete all timeline entries with position > cursor_pos"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM playback_timeline WHERE position > ?
        """,
            (cursor_pos,),
        )
        conn.commit()


def _renumber_positions(db_path=DB_PATH):
    """Renumber all positions to be contiguous starting from 0, update cursor"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Get current cursor position and song_uid at that position
        current_cursor = get_cursor(db_path)
        current_song = None

        if current_cursor >= 0:
            cursor.execute(
                """
                SELECT song_uid FROM playback_timeline
                WHERE position = ?
            """,
                (current_cursor,),
            )
            row = cursor.fetchone()
            current_song = row[0] if row else None

        # Get all entries ordered by position
        cursor.execute(
            """
            SELECT id, song_uid, added_at FROM playback_timeline
            ORDER BY position
        """
        )
        entries = cursor.fetchall()

        # Clear and reinsert with new positions
        cursor.execute("DELETE FROM playback_timeline")

        new_cursor = -1
        for new_pos, (_, song_uid, added_at) in enumerate(entries):
            cursor.execute(
                """
                INSERT INTO playback_timeline (song_uid, position, added_at)
                VALUES (?, ?, ?)
            """,
                (song_uid, new_pos, added_at),
            )

            # Track where the cursor song ends up
            if song_uid == current_song:
                new_cursor = new_pos

        # Update cursor position
        cursor.execute(
            """
            UPDATE playback_cursor SET position = ? WHERE id = 1
        """,
            (new_cursor,),
        )

        conn.commit()


def _prune_past(limit=MAX_PAST_ENTRIES, db_path=DB_PATH):
    """Delete oldest past entries if count exceeds limit, then renumber"""
    cursor_pos = get_cursor(db_path)

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Count past entries
        cursor.execute(
            """
            SELECT COUNT(*) FROM playback_timeline
            WHERE position < ?
        """,
            (cursor_pos,),
        )
        past_count = cursor.fetchone()[0]

        if past_count > limit:
            # Get positions to delete (oldest ones)
            to_delete = past_count - limit
            cursor.execute(
                """
                SELECT position FROM playback_timeline
                WHERE position < ?
                ORDER BY position
                LIMIT ?
            """,
                (cursor_pos, to_delete),
            )

            positions_to_delete = [row[0] for row in cursor.fetchall()]

            # Delete them
            for pos in positions_to_delete:
                cursor.execute(
                    """
                    DELETE FROM playback_timeline WHERE position = ?
                """,
                    (pos,),
                )

            conn.commit()

    # Renumber to keep positions contiguous
    _renumber_positions(db_path)


def append_song(song_uid, db_path=DB_PATH):
    """
    Append a song to the timeline, replacing the future.

    Deletes all future entries, appends the song, advances cursor.
    """
    _validate_uid(song_uid, "song_uid")

    cursor_pos = get_cursor(db_path)
    _delete_future(cursor_pos, db_path)

    new_pos = cursor_pos + 1

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO playback_timeline (song_uid, position, added_at)
            VALUES (?, ?, ?)
        """,
            (song_uid, new_pos, datetime.now().isoformat()),
        )
        conn.commit()

    _set_cursor(new_pos, db_path)
    _prune_past(MAX_PAST_ENTRIES, db_path)


def append_song_list(song_uids, db_path=DB_PATH):
    """
    Append a list of song UIDs to the timeline as a queue, replacing the future.

    Deletes all future entries, appends all songs in order, advances cursor
    to the first song in the list. Used for ad-hoc queues and playlist playback.
    """
    if not song_uids:
        return

    for uid in song_uids:
        _validate_uid(uid, "song_uid")

    cursor_pos = get_cursor(db_path)
    _delete_future(cursor_pos, db_path)

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        for idx, song_uid in enumerate(song_uids):
            new_pos = cursor_pos + 1 + idx
            cursor.execute(
                """
                INSERT INTO playback_timeline (song_uid, position, added_at)
                VALUES (?, ?, ?)
            """,
                (song_uid, new_pos, datetime.now().isoformat()),
            )
        conn.commit()

    # Advance cursor to first song
    _set_cursor(cursor_pos + 1, db_path)
    _prune_past(MAX_PAST_ENTRIES, db_path)


def advance_cursor(db_path=DB_PATH):
    """Advance the cursor one position forward (used during sequential playlist playback)"""
    current = get_cursor(db_path)
    _set_cursor(current + 1, db_path)


def append_playlist(playlist_uid, db_path=DB_PATH):
    """
    Append all songs from a playlist to the timeline, replacing the future.

    Fetches songs from playlist, deletes future, appends all in order,
    advances cursor to first song.
    """
    _validate_uid(playlist_uid, "playlist_uid")

    # Import here to avoid circular dependency
    from playlists import get_playlist_songs

    playlist_songs = get_playlist_songs(playlist_uid, db_path)

    if not playlist_songs:
        return  # Empty playlist, nothing to do

    song_uids = [entry["song_uid"] for entry in playlist_songs]
    append_song_list(song_uids, db_path)
