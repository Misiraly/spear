"""
Shared database utilities for SQLite operations.

This module provides common database connection management, UID generation,
and helper functions used across playlists, listen_history, and song_metadata modules.
"""

import hashlib
import re
import secrets
import sqlite3
import string
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

# Constants
UID_PATTERN = re.compile(r"^[a-zA-Z0-9]{16}$")


@contextmanager
def get_connection(db_path: str) -> Iterator[sqlite3.Connection]:
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


def generate_uid() -> str:
    """Generate a 16-character alphanumeric UID

    Returns:
        str: Random 16-character UID using letters and digits
    """
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(16))


def generate_uid_from_url(url: str) -> str:
    """Generate deterministic 16-character alphanumeric UID from URL

    Uses SHA-256 hash of the URL, encoded to base62 (alphanumeric),
    truncated to 16 characters. Same URL always produces same UID.

    Args:
        url: YouTube or other URL to generate UID from

    Returns:
        str: Deterministic 16-character UID
    """
    # Hash the URL
    hash_bytes = hashlib.sha256(url.encode("utf-8")).digest()

    # Convert to base62 (alphanumeric only)
    chars = string.ascii_letters + string.digits
    hash_int = int.from_bytes(hash_bytes, byteorder="big")

    result: list[str] = []
    while hash_int > 0 and len(result) < 16:
        hash_int, remainder = divmod(hash_int, 62)
        result.append(chars[remainder])

    # Pad if needed
    while len(result) < 16:
        result.append(chars[0])

    return "".join(result[:16])


def validate_uid(uid: str, uid_type: str = "UID") -> None:
    """Validate UID format

    Args:
        uid: UID string to validate
        uid_type: Type description for error message

    Raises:
        ValueError: If UID format is invalid
    """
    if not isinstance(uid, str) or not UID_PATTERN.match(uid):
        raise ValueError(f"Invalid {uid_type} format: {uid}")


def row_to_playlist_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert database row to playlist dictionary

    Args:
        row: Tuple from database query
            (uid, name, description, created_at, last_modified)

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


def ensure_playlist_exists(cursor: sqlite3.Cursor, playlist_uid: str) -> None:
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


def row_to_song_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert song row to dict.

    Fields: uid, title, url, duration, add_date, path, last_modified.
    """
    return {
        "uid": row[0],
        "title": row[1],
        "url": row[2],
        "duration": row[3],
        "add_date": row[4],
        "path": row[5],
        "last_modified": row[6],
    }


def row_to_song_dict_with_count(row: tuple[Any, ...]) -> dict[str, Any]:
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


def row_to_playlist_item_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert playlist item row to dict.

    Fields: position, uid, title, duration, added_at.
    """
    return {
        "position": row[0],
        "uid": row[1],
        "title": row[2],
        "duration": row[3],
        "added_at": row[4],
    }


def row_to_timeline_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert playback timeline row to dict.

    Fields: position, song_uid, added_at.
    """
    return {
        "position": row[0],
        "song_uid": row[1],
        "added_at": row[2],
    }


def get_next_position(cursor: sqlite3.Cursor, playlist_uid: str) -> int:
    """Get next available position for playlist item"""
    cursor.execute(
        "SELECT MAX(position) FROM playlist_items WHERE playlist_uid = ?",
        (playlist_uid,),
    )
    max_pos = cursor.fetchone()[0]
    return (max_pos or 0) + 1
