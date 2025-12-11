"""
Playlist management module for organizing songs.

This module provides functionality to create, manage, and query playlists
stored in SQLite alongside the listen history.
"""

import os
import random
from datetime import datetime

import constants as cv
from db_utils import ensure_playlist_exists as _ensure_playlist_exists
from db_utils import generate_uid as _generate_uid
from db_utils import get_connection as _get_connection
from db_utils import get_next_position as _get_next_position
from db_utils import row_to_playlist_dict as _row_to_playlist_dict
from db_utils import row_to_playlist_item_dict as _row_to_playlist_item_dict
from db_utils import validate_uid as _validate_uid

# Constants
DB_PATH = os.path.join(os.path.dirname(__file__), cv.DB_PATH)


def init_database(db_path=DB_PATH):
    """Create playlist tables if they don't exist"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys = ON")

        # Create playlists table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS playlists (
                uid TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL,
                last_modified TEXT NOT NULL
            )
        """
        )

        # Create playlist_items table with foreign key constraint
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS playlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_uid TEXT NOT NULL,
                song_uid TEXT NOT NULL,
                position INTEGER NOT NULL,
                added_at TEXT NOT NULL,
                FOREIGN KEY (playlist_uid) REFERENCES playlists(uid) ON DELETE CASCADE
            )
        """
        )

        # Create indexes for faster queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_playlist_position 
            ON playlist_items(playlist_uid, position)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_song_uid 
            ON playlist_items(song_uid)
        """
        )

        conn.commit()

    return db_path


def _renumber_positions(
    playlist_uid, conn=None, max_position_before_delete=None, db_path=DB_PATH
):
    """Renumber playlist positions to be consecutive starting from 1"""
    should_close = conn is None
    if conn is None:
        conn = _get_connection(db_path).__enter__()

    try:
        cursor = conn.cursor()

        # Get all items in order
        cursor.execute(
            """
            SELECT id FROM playlist_items
            WHERE playlist_uid = ?
            ORDER BY position, id
        """,
            (playlist_uid,),
        )

        items = cursor.fetchall()

        # Optimization: if max_position_before_delete is provided and equals item count + 1,
        # the deleted item was at the end, so no renumbering needed
        if (
            max_position_before_delete is not None
            and max_position_before_delete == len(items) + 1
        ):
            if should_close:
                conn.commit()
            return

        # Batch renumber using executemany
        updates = [
            (new_position, item_id)
            for new_position, (item_id,) in enumerate(items, start=1)
        ]
        cursor.executemany(
            "UPDATE playlist_items SET position = ? WHERE id = ?", updates
        )

        if should_close:
            conn.commit()
    finally:
        if should_close:
            conn.__exit__(None, None, None)


def _update_modified_time(playlist_uid, conn=None, db_path=DB_PATH):
    """Update last_modified timestamp for a playlist"""
    should_close = conn is None
    if conn is None:
        conn = _get_connection(db_path).__enter__()

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE playlists
            SET last_modified = ?
            WHERE uid = ?
        """,
            (datetime.now().isoformat(), playlist_uid),
        )
        if should_close:
            conn.commit()
    finally:
        if should_close:
            conn.__exit__(None, None, None)


# ============================================================================
# PLAYLIST CRUD OPERATIONS
# ============================================================================


def create_playlist(name, description=None, song_uids=None, db_path=DB_PATH):
    """Create a new playlist

    Args:
        name: Playlist name (must be unique)
        description: Optional playlist description
        song_uids: Optional list of song UIDs to add initially
        db_path: Path to database

    Returns:
        The playlist UID

    Raises:
        ValueError: If playlist name already exists
    """
    if playlist_exists(name, db_path):
        raise ValueError(f"Playlist '{name}' already exists")

    uid = _generate_uid()
    now = datetime.now().isoformat()

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO playlists (uid, name, description, created_at, last_modified)
            VALUES (?, ?, ?, ?, ?)
        """,
            (uid, name, description, now, now),
        )
        conn.commit()

    # Add initial songs if provided
    if song_uids:
        add_multiple_to_playlist(uid, song_uids, db_path)

    return uid


def rename_playlist(playlist_uid, new_name, db_path=DB_PATH):
    """Rename an existing playlist"""
    _validate_uid(playlist_uid, "playlist_uid")

    # Check if new name is already in use by a different playlist
    existing = get_playlist_by_name(new_name, db_path)
    if existing and existing["uid"] != playlist_uid:
        raise ValueError(f"Playlist '{new_name}' already exists")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE playlists
            SET name = ?, last_modified = ?
            WHERE uid = ?
        """,
            (new_name, datetime.now().isoformat(), playlist_uid),
        )

        if cursor.rowcount == 0:
            return False

        conn.commit()
        return True


def update_playlist_description(playlist_uid, description, db_path=DB_PATH):
    """Update playlist description"""
    _validate_uid(playlist_uid, "playlist_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE playlists
            SET description = ?, last_modified = ?
            WHERE uid = ?
        """,
            (description, datetime.now().isoformat(), playlist_uid),
        )

        if cursor.rowcount == 0:
            return False

        conn.commit()
        return True


def delete_playlist(playlist_uid, db_path=DB_PATH):
    """Delete a playlist and all its items"""
    _validate_uid(playlist_uid, "playlist_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys = ON")

        # Delete the playlist (items cascade automatically)
        cursor.execute(
            """
            DELETE FROM playlists
            WHERE uid = ?
        """,
            (playlist_uid,),
        )

        conn.commit()


def get_playlist(playlist_uid, db_path=DB_PATH):
    """Get playlist metadata, returns dict or None"""
    _validate_uid(playlist_uid, "playlist_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT uid, name, description, created_at, last_modified
            FROM playlists WHERE uid = ?
        """,
            (playlist_uid,),
        )
        row = cursor.fetchone()

        if row:
            return _row_to_playlist_dict(row)
        return None


def get_all_playlists(db_path=DB_PATH):
    """Get all playlists ordered by name"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT uid, name, description, created_at, last_modified
            FROM playlists
            ORDER BY name
        """
        )

        return [_row_to_playlist_dict(row) for row in cursor.fetchall()]


def get_playlist_count(db_path=DB_PATH):
    """Return total number of playlists"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM playlists")
        return cursor.fetchone()[0]


def playlist_exists(name, db_path=DB_PATH):
    """Check if playlist name already exists"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM playlists WHERE name = ?
        """,
            (name,),
        )
        return cursor.fetchone()[0] > 0


def get_playlist_by_name(name, db_path=DB_PATH):
    """Retrieve playlist by name, returns dict or None"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT uid, name, description, created_at, last_modified
            FROM playlists WHERE name = ?
        """,
            (name,),
        )
        row = cursor.fetchone()

        if row:
            return _row_to_playlist_dict(row)
        return None


# ============================================================================
# ADDING SONGS
# ============================================================================


def add_to_playlist(playlist_uid, song_uid, db_path=DB_PATH):
    """Add a single song to the end of a playlist"""
    _validate_uid(playlist_uid, "playlist_uid")
    _validate_uid(song_uid, "song_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Check playlist exists
        _ensure_playlist_exists(cursor, playlist_uid)

        # Get next position
        next_position = _get_next_position(cursor, playlist_uid)

        # Insert song
        cursor.execute(
            """
            INSERT INTO playlist_items (playlist_uid, song_uid, position, added_at)
            VALUES (?, ?, ?, ?)
        """,
            (playlist_uid, song_uid, next_position, datetime.now().isoformat()),
        )

        _update_modified_time(playlist_uid, conn, db_path)
        conn.commit()


def add_multiple_to_playlist(playlist_uid, song_uids, db_path=DB_PATH):
    """Bulk add songs to a playlist"""
    _validate_uid(playlist_uid, "playlist_uid")
    for song_uid in song_uids:
        _validate_uid(song_uid, "song_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Check playlist exists
        _ensure_playlist_exists(cursor, playlist_uid)

        # Get next position
        next_position = _get_next_position(cursor, playlist_uid)

        # Insert all songs using executemany
        now = datetime.now().isoformat()
        inserts = [
            (playlist_uid, song_uid, next_position + i, now)
            for i, song_uid in enumerate(song_uids)
        ]
        cursor.executemany(
            """
            INSERT INTO playlist_items (playlist_uid, song_uid, position, added_at)
            VALUES (?, ?, ?, ?)
        """,
            inserts,
        )

        _update_modified_time(playlist_uid, conn, db_path)
        conn.commit()


def insert_at_position(playlist_uid, song_uid, position, db_path=DB_PATH):
    """Insert a song at a specific position (1-based)"""
    _validate_uid(playlist_uid, "playlist_uid")
    _validate_uid(song_uid, "song_uid")

    if position < 1:
        raise ValueError("Position must be >= 1")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Check playlist exists
        _ensure_playlist_exists(cursor, playlist_uid)

        # Get current max position
        cursor.execute(
            """
            SELECT MAX(position) FROM playlist_items WHERE playlist_uid = ?
        """,
            (playlist_uid,),
        )
        max_pos = cursor.fetchone()[0] or 0

        # Validate position (allow inserting at end + 1)
        if position > max_pos + 1:
            raise ValueError(
                f"Position {position} is out of range (max: {max_pos + 1})"
            )

        # Shift songs down
        cursor.execute(
            """
            UPDATE playlist_items
            SET position = position + 1
            WHERE playlist_uid = ? AND position >= ?
        """,
            (playlist_uid, position),
        )

        # Insert the new song
        cursor.execute(
            """
            INSERT INTO playlist_items (playlist_uid, song_uid, position, added_at)
            VALUES (?, ?, ?, ?)
        """,
            (playlist_uid, song_uid, position, datetime.now().isoformat()),
        )

        _update_modified_time(playlist_uid, conn, db_path)
        conn.commit()


# ============================================================================
# REMOVING SONGS
# ============================================================================


def remove_by_position(playlist_uid, position, db_path=DB_PATH):
    """Remove song at a specific position"""
    _validate_uid(playlist_uid, "playlist_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Get the max position before deletion for optimization
        cursor.execute(
            """
            SELECT position, MAX(position) OVER () as max_pos
            FROM playlist_items
            WHERE playlist_uid = ? AND position = ?
        """,
            (playlist_uid, position),
        )
        result = cursor.fetchone()

        if not result:
            return False

        pos_to_delete, max_position = result

        # Delete the item
        cursor.execute(
            """
            DELETE FROM playlist_items
            WHERE playlist_uid = ? AND position = ?
        """,
            (playlist_uid, position),
        )

        # Renumber positions (optimized for end-deletions)
        _renumber_positions(playlist_uid, conn, max_position, db_path)
        _update_modified_time(playlist_uid, conn, db_path)
        conn.commit()
        return True


def remove_by_uid(playlist_uid, song_uid, db_path=DB_PATH):
    """Remove all instances of a song from a playlist"""
    _validate_uid(playlist_uid, "playlist_uid")
    _validate_uid(song_uid, "song_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM playlist_items
            WHERE playlist_uid = ? AND song_uid = ?
        """,
            (playlist_uid, song_uid),
        )

        # Renumber positions and update timestamp
        _renumber_positions(playlist_uid, conn, None, db_path)
        _update_modified_time(playlist_uid, conn, db_path)
        conn.commit()


def remove_from_all_playlists(song_uid, db_path=DB_PATH):
    """Remove a song from every playlist"""
    _validate_uid(song_uid, "song_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Get all affected playlists
        cursor.execute(
            """
            SELECT DISTINCT playlist_uid FROM playlist_items WHERE song_uid = ?
        """,
            (song_uid,),
        )
        affected_playlists = [row[0] for row in cursor.fetchall()]

        # Delete all instances
        cursor.execute(
            """
            DELETE FROM playlist_items WHERE song_uid = ?
        """,
            (song_uid,),
        )

        # Renumber and update timestamps for all affected playlists in single transaction
        for playlist_uid in affected_playlists:
            _renumber_positions(playlist_uid, conn, None, db_path)
            _update_modified_time(playlist_uid, conn, db_path)

        conn.commit()


def clear_playlist(playlist_uid, db_path=DB_PATH):
    """Remove all songs from playlist but keep the playlist"""
    _validate_uid(playlist_uid, "playlist_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM playlist_items WHERE playlist_uid = ?
        """,
            (playlist_uid,),
        )
        _update_modified_time(playlist_uid, conn, db_path)
        conn.commit()


# ============================================================================
# REORDERING
# ============================================================================


def move_song(playlist_uid, from_position, to_position, db_path=DB_PATH):
    """Move a song from one position to another"""
    _validate_uid(playlist_uid, "playlist_uid")

    if from_position == to_position:
        return True

    if from_position < 1 or to_position < 1:
        return False

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Get current max position
        cursor.execute(
            """
            SELECT MAX(position) FROM playlist_items WHERE playlist_uid = ?
        """,
            (playlist_uid,),
        )
        max_pos = cursor.fetchone()[0]

        if not max_pos:
            return False

        if from_position > max_pos or to_position > max_pos:
            return False

        # Get the item to move
        cursor.execute(
            """
            SELECT id FROM playlist_items
            WHERE playlist_uid = ? AND position = ?
        """,
            (playlist_uid, from_position),
        )
        item = cursor.fetchone()

        if not item:
            return False

        item_id = item[0]

        # Temporarily set to a negative position
        cursor.execute(
            """
            UPDATE playlist_items SET position = -1 WHERE id = ?
        """,
            (item_id,),
        )

        # Shift other items
        if from_position < to_position:
            # Moving down: shift items up
            cursor.execute(
                """
                UPDATE playlist_items
                SET position = position - 1
                WHERE playlist_uid = ? AND position > ? AND position <= ?
            """,
                (playlist_uid, from_position, to_position),
            )
        else:
            # Moving up: shift items down
            cursor.execute(
                """
                UPDATE playlist_items
                SET position = position + 1
                WHERE playlist_uid = ? AND position >= ? AND position < ?
            """,
                (playlist_uid, to_position, from_position),
            )

        # Set final position
        cursor.execute(
            """
            UPDATE playlist_items SET position = ? WHERE id = ?
        """,
            (to_position, item_id),
        )

        _update_modified_time(playlist_uid, conn, db_path)
        conn.commit()
        return True


def shuffle_playlist(playlist_uid, db_path=DB_PATH):
    """Randomize the order of songs in a playlist"""
    _validate_uid(playlist_uid, "playlist_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Get all item IDs
        cursor.execute(
            """
            SELECT id FROM playlist_items WHERE playlist_uid = ?
        """,
            (playlist_uid,),
        )
        item_ids = [row[0] for row in cursor.fetchall()]

        # Shuffle the list
        random.shuffle(item_ids)

        # Assign new positions using executemany
        updates = [
            (new_position, item_id)
            for new_position, item_id in enumerate(item_ids, start=1)
        ]
        cursor.executemany(
            """
            UPDATE playlist_items SET position = ? WHERE id = ?
        """,
            updates,
        )

        _update_modified_time(playlist_uid, conn, db_path)
        conn.commit()


# ============================================================================
# QUERY FUNCTIONS
# ============================================================================


def get_playlist_songs(playlist_uid, db_path=DB_PATH):
    """Get all songs in a playlist with their titles"""
    _validate_uid(playlist_uid, "playlist_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                pi.position,
                pi.song_uid,
                s.title,
                s.duration,
                pi.added_at
            FROM playlist_items pi
            LEFT JOIN songs s ON pi.song_uid = s.uid
            WHERE pi.playlist_uid = ?
            ORDER BY pi.position
        """,
            (playlist_uid,),
        )

        return [_row_to_playlist_item_dict(row) for row in cursor.fetchall()]


def find_playlists_for_song(song_uid, db_path=DB_PATH):
    """Find all playlists containing a specific song"""
    _validate_uid(song_uid, "song_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                p.uid,
                p.name,
                pi.position
            FROM playlist_items pi
            JOIN playlists p ON pi.playlist_uid = p.uid
            WHERE pi.song_uid = ?
            ORDER BY p.name, pi.position
        """,
            (song_uid,),
        )

        # Group by playlist
        playlists_dict = {}
        for row in cursor.fetchall():
            playlist_uid = row[0]
            playlist_name = row[1]
            position = row[2]

            if playlist_uid not in playlists_dict:
                playlists_dict[playlist_uid] = {
                    "playlist_uid": playlist_uid,
                    "playlist_name": playlist_name,
                    "positions": [],
                }

            playlists_dict[playlist_uid]["positions"].append(position)

        return list(playlists_dict.values())


def get_empty_playlists(db_path=DB_PATH):
    """List playlists with no songs

    Returns:
        List of playlist dictionaries
    """
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.uid, p.name, p.description, p.created_at, p.last_modified
            FROM playlists p
            LEFT JOIN playlist_items pi ON p.uid = pi.playlist_uid
            WHERE pi.id IS NULL
            ORDER BY p.name
        """
        )

        return [_row_to_playlist_dict(row) for row in cursor.fetchall()]


def search_playlists(query, db_path=DB_PATH):
    """Search playlists by name

    Args:
        query: Search string
        db_path: Path to database

    Returns:
        List of matching playlists
    """
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT uid, name, description, created_at, last_modified
            FROM playlists
            WHERE name LIKE ?
            ORDER BY name
        """,
            (f"%{query}%",),
        )

        return [_row_to_playlist_dict(row) for row in cursor.fetchall()]


# ============================================================================
# STATISTICS & METADATA
# ============================================================================


def get_playlist_stats(playlist_uid, db_path=DB_PATH):
    """Get comprehensive statistics for a playlist

    Args:
        playlist_uid: Playlist unique identifier
        db_path: Path to database

    Returns:
        Dict with name, description, song_count, unique_songs,
        total_duration, created_at, last_modified, or None if not found
    """
    _validate_uid(playlist_uid, "playlist_uid")

    playlist = get_playlist(playlist_uid, db_path)
    if not playlist:
        return None

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Count total and unique songs
        cursor.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT song_uid)
            FROM playlist_items
            WHERE playlist_uid = ?
        """,
            (playlist_uid,),
        )
        song_count, unique_songs = cursor.fetchone()

        # Calculate total duration
        cursor.execute(
            """
            SELECT SUM(s.duration)
            FROM playlist_items pi
            LEFT JOIN songs s ON pi.song_uid = s.uid
            WHERE pi.playlist_uid = ?
        """,
            (playlist_uid,),
        )
        total_duration = cursor.fetchone()[0] or 0

    return {
        "name": playlist["name"],
        "description": playlist["description"],
        "song_count": song_count,
        "unique_songs": unique_songs,
        "total_duration": total_duration,
        "created_at": playlist["created_at"],
        "last_modified": playlist["last_modified"],
    }


def merge_playlists(source_uid, target_uid, db_path=DB_PATH):
    """Append all songs from source playlist to target playlist

    Args:
        source_uid: Source playlist UID
        target_uid: Target playlist UID
        db_path: Path to database

    Raises:
        ValueError: If either playlist doesn't exist
    """
    _validate_uid(source_uid, "source_uid")
    _validate_uid(target_uid, "target_uid")

    # Get songs from source playlist
    songs = get_playlist_songs(source_uid, db_path)

    if not songs:
        return

    # Add them to target playlist
    song_uids = [song["uid"] for song in songs]
    add_multiple_to_playlist(target_uid, song_uids, db_path)


def duplicate_playlist(playlist_uid, new_name, db_path=DB_PATH):
    """Create a copy of a playlist with a new name

    Args:
        playlist_uid: Playlist to duplicate
        new_name: Name for the new playlist
        db_path: Path to database

    Returns:
        The new playlist UID, or None if source not found

    Raises:
        ValueError: If new name already exists
    """
    _validate_uid(playlist_uid, "playlist_uid")

    # Get original playlist
    original = get_playlist(playlist_uid, db_path)
    if not original:
        return None

    # Get songs from original
    songs = get_playlist_songs(playlist_uid, db_path)
    song_uids = [song["uid"] for song in songs]

    # Create new playlist
    new_uid = create_playlist(
        new_name,
        description=original["description"],
        song_uids=song_uids,
        db_path=db_path,
    )

    return new_uid
