"""
Song metadata storage and management using SQLite.

This module stores permanent song information (title, URL, duration, etc.)
separate from the listen history tracking.
"""

import os
from datetime import datetime

import constants as cv
from db_utils import get_connection as _get_connection
from db_utils import row_to_song_dict as _row_to_song_dict
from db_utils import \
    row_to_song_dict_with_count as _row_to_song_dict_with_count
from db_utils import validate_uid as _validate_uid

# Constants
DB_PATH = os.path.join(os.path.dirname(__file__), cv.DB_PATH)


def init_database(db_path=DB_PATH):
    """Create the song metadata table if it doesn't exist"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS songs (
                uid TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT,
                duration INTEGER,
                add_date TEXT NOT NULL,
                path TEXT NOT NULL,
                last_modified TEXT
            )
        """
        )

        # Create indexes for faster queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_title 
            ON songs(title)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_add_date 
            ON songs(add_date)
        """
        )

        conn.commit()

    return db_path


def add_song(uid, title, path, url=None, duration=None, add_date=None, db_path=DB_PATH):
    """Add a new song to the database or update if it exists

    Args:
        uid: 16-character unique identifier
        title: Song title
        path: File path to the song
        url: YouTube URL (optional)
        duration: Duration in seconds (optional)
        add_date: Date added (defaults to now)
        db_path: Path to database

    Returns:
        The song UID

    Raises:
        ValueError: If UID format is invalid
    """
    _validate_uid(uid, "uid")

    if add_date is None:
        add_date = datetime.now().date().isoformat()

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO songs 
            (uid, title, url, duration, add_date, path, last_modified)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (uid, title, url, duration, add_date, path, datetime.now().isoformat()),
        )
        conn.commit()

    return uid


def get_song(uid, db_path=DB_PATH):
    """Get song metadata by UID, returns dict or None"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT uid, title, url, duration, add_date, path, last_modified
            FROM songs WHERE uid = ?
        """,
            (uid,),
        )
        row = cursor.fetchone()
        return _row_to_song_dict(row) if row else None


def get_all_songs(db_path=DB_PATH):
    """Get all songs ordered by add_date DESC"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT uid, title, url, duration, add_date, path, last_modified
            FROM songs
            ORDER BY add_date DESC
        """
        )
        return [_row_to_song_dict(row) for row in cursor.fetchall()]


def search_songs(query, db_path=DB_PATH):
    """Search songs by title (LIKE query), returns list"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT uid, title, url, duration, add_date, path, last_modified
            FROM songs
            WHERE title LIKE ?
            ORDER BY title
        """,
            (f"%{query}%",),
        )
        return [_row_to_song_dict(row) for row in cursor.fetchall()]


def update_song_path(uid, new_path, db_path=DB_PATH):
    """Update file path for a song"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE songs 
            SET path = ?, last_modified = ?
            WHERE uid = ?
        """,
            (new_path, datetime.now().isoformat(), uid),
        )
        conn.commit()


def update_song_title(uid, new_title, db_path=DB_PATH):
    """Update song title (database only, does not rename file)
    
    Args:
        uid: Song UID
        new_title: New title for the song
        db_path: Path to database
    """
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE songs 
            SET title = ?, last_modified = ?
            WHERE uid = ?
        """,
            (new_title, datetime.now().isoformat(), uid),
        )
        conn.commit()


def update_song_duration(uid, new_duration, db_path=DB_PATH):
    """Update song duration
    
    Args:
        uid: Song UID
        new_duration: New duration in seconds
        db_path: Path to database
    """
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE songs 
            SET duration = ?, last_modified = ?
            WHERE uid = ?
        """,
            (new_duration, datetime.now().isoformat(), uid),
        )
        conn.commit()


def delete_song(uid, db_path=DB_PATH):
    """Delete song by UID (does not delete listen history)"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM songs WHERE uid = ?", (uid,))
        conn.commit()


def get_songs_alphabetically(reverse=False, db_path=DB_PATH):
    """Get all songs sorted alphabetically by title"""
    order = "DESC" if reverse else "ASC"
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT uid, title, url, duration, add_date, path, last_modified
            FROM songs
            ORDER BY title {order}
        """
        )
        return [_row_to_song_dict(row) for row in cursor.fetchall()]


def get_songs_with_listen_count(limit=None, db_path=DB_PATH):
    """Get all songs with their total listen count"""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                s.uid, s.title, s.url, s.duration, s.add_date, s.path,
                COUNT(lh.id) as listen_count
            FROM songs s
            LEFT JOIN listen_history lh ON s.uid = lh.song_uid
            GROUP BY s.uid
            ORDER BY listen_count DESC
        """
        if limit:
            query += f" LIMIT {limit}"
        cursor.execute(query)
        return [_row_to_song_dict_with_count(row) for row in cursor.fetchall()]


def get_random_song(db_path=DB_PATH):
    """
    Get a random song_uid from the songs table.
    
    Returns song_uid or None if no songs exist.
    """
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT uid FROM songs 
            ORDER BY RANDOM() 
            LIMIT 1
        """
        )
        row = cursor.fetchone()
        return row[0] if row else None
