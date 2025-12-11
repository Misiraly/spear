import os
from datetime import datetime, timedelta

import constants as cv
from db_utils import get_connection as _get_connection
from db_utils import validate_uid as _validate_uid

# Constants
DB_PATH = os.path.join(os.path.dirname(__file__), cv.DB_PATH)


def _execute_aggregation_query(where_clause, params, limit, reverse, db_path):
    """Execute aggregation query with song titles joined from songs table"""
    order = "ASC" if reverse else "DESC"

    query = f"""
        SELECT lh.song_uid, s.title, COUNT(*) as listen_count
        FROM listen_history lh
        LEFT JOIN songs s ON lh.song_uid = s.uid
        {where_clause}
        GROUP BY lh.song_uid
        ORDER BY listen_count {order}
    """

    if limit is not None:
        if not isinstance(limit, int) or limit < 0:
            raise ValueError(f"limit must be a non-negative integer, got: {limit}")
        query += f" LIMIT {limit}"

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [
            {"uid": row[0], "title": row[1], "listen_count": row[2]}
            for row in cursor.fetchall()
        ]


def _get_start_of_week():
    """Calculate start of current week (Monday at 00:00:00)"""
    now = datetime.now()
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _get_start_of_month():
    """Calculate start of current month (1st day at 00:00:00)"""
    now = datetime.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _get_start_of_year():
    """Calculate start of current year (Jan 1st at 00:00:00)"""
    now = datetime.now()
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


def init_database(db_path=DB_PATH):
    """Create database and tables if they don't exist"""
    # Ensure the data directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS listen_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_uid TEXT NOT NULL,
                listened_at TIMESTAMP NOT NULL
            )
        """
        )

        # Create songs table for metadata (needed for JOINs in query functions)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS songs (
                uid TEXT PRIMARY KEY,
                title TEXT
            )
        """
        )

        # Create indexes for faster queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_song_uid 
            ON listen_history(song_uid)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_listened_at 
            ON listen_history(listened_at)
        """
        )

        conn.commit()

    return db_path


def log_listen(song_uid, db_path=DB_PATH):
    """Record that a song was just listened to"""
    _validate_uid(song_uid, "song_uid")

    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO listen_history (song_uid, listened_at) VALUES (?, ?)",
            (song_uid, datetime.now().isoformat()),
        )
        conn.commit()


def get_top_songs_last_n_days(days, limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count in the last N days"""
    cutoff_date = datetime.now() - timedelta(days=days)

    return _execute_aggregation_query(
        "WHERE lh.listened_at >= ?", (cutoff_date.isoformat(),), limit, reverse, db_path
    )


def get_top_songs_this_week(limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count in current week (Monday-Sunday)"""
    start_of_week = _get_start_of_week()

    return _execute_aggregation_query(
        "WHERE lh.listened_at >= ?",
        (start_of_week.isoformat(),),
        limit,
        reverse,
        db_path,
    )


def get_top_songs_this_month(limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count in current month"""
    start_of_month = _get_start_of_month()

    return _execute_aggregation_query(
        "WHERE lh.listened_at >= ?",
        (start_of_month.isoformat(),),
        limit,
        reverse,
        db_path,
    )


def get_top_songs_this_year(limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count in current year"""
    start_of_year = _get_start_of_year()

    return _execute_aggregation_query(
        "WHERE lh.listened_at >= ?",
        (start_of_year.isoformat(),),
        limit,
        reverse,
        db_path,
    )


def get_top_songs_all_time(limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count for all time"""
    return _execute_aggregation_query("", (), limit, reverse, db_path)


def get_top_songs_for_week(year, week, limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count for a specific week"""
    if not (1 <= week <= 53):
        raise ValueError(f"Week must be between 1 and 53, got: {week}")

    return _execute_aggregation_query(
        "WHERE strftime('%Y', lh.listened_at) = ? AND strftime('%W', lh.listened_at) = ?",
        (str(year), f"{week:02d}"),
        limit,
        reverse,
        db_path,
    )


def get_top_songs_for_month(year, month, limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count for a specific month"""
    if not (1 <= month <= 12):
        raise ValueError(f"Month must be between 1 and 12, got: {month}")

    return _execute_aggregation_query(
        "WHERE strftime('%Y', lh.listened_at) = ? AND strftime('%m', lh.listened_at) = ?",
        (str(year), f"{month:02d}"),
        limit,
        reverse,
        db_path,
    )


def get_top_songs_for_year(year, limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count for a specific year"""
    if not isinstance(year, int) or year < 1900 or year > 2100:
        raise ValueError(f"Invalid year: {year}")

    return _execute_aggregation_query(
        "WHERE strftime('%Y', lh.listened_at) = ?",
        (str(year),),
        limit,
        reverse,
        db_path,
    )
