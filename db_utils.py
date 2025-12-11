"""
Shared database utilities for SQLite operations.

This module provides common database connection management, UID generation,
and helper functions used across playlists, listen_history, and song_metadata modules.
"""

import re
import secrets
import sqlite3
import string
from contextlib import contextmanager

# Constants
UID_PATTERN = re.compile(r"^[a-zA-Z0-9]{16}$")


@contextmanager
def get_connection(db_path):
    """Context manager for database connections with automatic rollback on error

    Args:
        db_path: Path to SQLite database file

    Yields:
        sqlite3.Connection: Database connection

    Note:
        Automatically rolls back transaction on exception and closes connection
    """
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def generate_uid():
    """Generate a 16-character alphanumeric UID

    Returns:
        str: Random 16-character UID using letters and digits
    """
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(16))


def validate_uid(uid, uid_type="UID"):
    """Validate UID format

    Args:
        uid: UID string to validate
        uid_type: Type description for error message

    Raises:
        ValueError: If UID format is invalid
    """
    if not isinstance(uid, str) or not UID_PATTERN.match(uid):
        raise ValueError(f"Invalid {uid_type} format: {uid}")


def row_to_playlist_dict(row):
    """Convert database row to playlist dictionary

    Args:
        row: Tuple from database query (uid, name, description, created_at, last_modified)

    Returns:
        dict: Playlist data dictionary
    """
    return {
        "uid": row[0],
        "name": row[1],
        "description": row[2],
        "created_at": row[3],
        "last_modified": row[4],
    }


def ensure_playlist_exists(cursor, playlist_uid):
    """Check if playlist exists, raise ValueError if not

    Args:
        cursor: Database cursor
        playlist_uid: Playlist UID to check

    Raises:
        ValueError: If playlist not found
    """
    cursor.execute("SELECT uid FROM playlists WHERE uid = ?", (playlist_uid,))
    if not cursor.fetchone():
        raise ValueError(f"Playlist not found: {playlist_uid}")


def row_to_song_dict(row):
    """Convert song row to dict with fields: uid, title, url, duration, add_date, path, last_modified"""
    return {
        "uid": row[0],
        "title": row[1],
        "url": row[2],
        "duration": row[3],
        "add_date": row[4],
        "path": row[5],
        "last_modified": row[6],
    }


def row_to_song_dict_with_count(row):
    """Convert song row to dict including listen_count instead of last_modified"""
    return {
        "uid": row[0],
        "title": row[1],
        "url": row[2],
        "duration": row[3],
        "add_date": row[4],
        "path": row[5],
        "listen_count": row[6],
    }


def row_to_playlist_item_dict(row):
    """Convert playlist item row to dict with fields: position, uid, title, duration, added_at"""
    return {
        "position": row[0],
        "uid": row[1],
        "title": row[2],
        "duration": row[3],
        "added_at": row[4],
    }


def row_to_history_dict(row):
    """Convert listen history row to dict with fields: id, song_uid, listen_date, listen_time, source"""
    return {
        "id": row[0],
        "song_uid": row[1],
        "listen_date": row[2],
        "listen_time": row[3],
        "source": row[4],
    }


def get_next_position(cursor, playlist_uid):
    """Get next available position for playlist item"""
    cursor.execute(
        "SELECT MAX(position) FROM playlist_items WHERE playlist_uid = ?",
        (playlist_uid,),
    )
    max_pos = cursor.fetchone()[0]
    return (max_pos or 0) + 1
