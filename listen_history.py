import sqlite3
from datetime import datetime, timedelta
import os
from contextlib import contextmanager
import constants as cv
import re

# Constants
DB_PATH = os.path.join(os.path.dirname(__file__), cv.DB_PATH)


# Helper functions
@contextmanager
def _get_connection(db_path=DB_PATH):
    """Context manager for database connections"""
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def _execute_aggregation_query(where_clause, params, limit, reverse, db_path):
    """Execute a common aggregation query pattern
    
    Args:
        where_clause: SQL WHERE clause (e.g., "WHERE listened_at >= ?") or empty string
        params: Tuple of parameters for the query
        limit: Maximum number of results (None for all)
        reverse: If True, sort ascending (least played first)
        db_path: Path to database file
        
    Returns:
        List of tuples: [(song_uid, listen_count), ...]
    """
    order = 'ASC' if reverse else 'DESC'
    
    query = f'''
        SELECT song_uid, COUNT(*) as listen_count
        FROM listen_history
        {where_clause}
        GROUP BY song_uid
        ORDER BY listen_count {order}
    '''
    
    if limit:
        if not isinstance(limit, int) or limit < 0:
            raise ValueError(f"limit must be a non-negative integer, got: {limit}")
        query += f' LIMIT {limit}'
    
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()


def _get_start_of_week():
    """Calculate the start of the current week (Monday at 00:00:00)"""
    now = datetime.now()
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _get_start_of_month():
    """Calculate the start of the current month (1st day at 00:00:00)"""
    now = datetime.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _get_start_of_year():
    """Calculate the start of the current year (Jan 1st at 00:00:00)"""
    now = datetime.now()
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


def init_database(db_path=DB_PATH):
    """Create the database and table if they don't exist"""
    # Ensure the data directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS listen_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_uid TEXT NOT NULL,
                listened_at TIMESTAMP NOT NULL
            )
        ''')
        
        # Create indexes for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_song_uid 
            ON listen_history(song_uid)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_listened_at 
            ON listen_history(listened_at)
        ''')
        
        conn.commit()
    
    return db_path


def log_listen(song_uid, db_path=DB_PATH):
    """Record that a song was just listened to"""
    # Validate UID
    if not isinstance(song_uid, str) or not re.match(r'^[a-zA-Z0-9]{16}$', song_uid):
        raise ValueError(f"Invalid song_uid format: {song_uid}")
    
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO listen_history (song_uid, listened_at) VALUES (?, ?)',
            (song_uid, datetime.now())
        )
        conn.commit()


def get_top_songs_last_n_days(days, limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count in the last N days
    
    Args:
        days: Number of days to look back
        limit: Maximum number of results to return (None for all)
        reverse: If True, sort ascending (least played first)
        db_path: Path to the database file
        
    Returns:
        List of tuples: [(song_uid, listen_count), ...]
    """
    cutoff_date = datetime.now() - timedelta(days=days)
    
    return _execute_aggregation_query(
        'WHERE listened_at >= ?',
        (cutoff_date,),
        limit,
        reverse,
        db_path
    )


def get_top_songs_this_week(limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count in the current week (Monday-Sunday)
    
    Args:
        limit: Maximum number of results to return (None for all)
        reverse: If True, sort ascending (least played first)
        db_path: Path to the database file
        
    Returns:
        List of tuples: [(song_uid, listen_count), ...]
    """
    start_of_week = _get_start_of_week()
    
    return _execute_aggregation_query(
        'WHERE listened_at >= ?',
        (start_of_week,),
        limit,
        reverse,
        db_path
    )


def get_top_songs_this_month(limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count in the current month
    
    Args:
        limit: Maximum number of results to return (None for all)
        reverse: If True, sort ascending (least played first)
        db_path: Path to the database file
        
    Returns:
        List of tuples: [(song_uid, listen_count), ...]
    """
    start_of_month = _get_start_of_month()
    
    return _execute_aggregation_query(
        'WHERE listened_at >= ?',
        (start_of_month,),
        limit,
        reverse,
        db_path
    )


def get_top_songs_this_year(limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count in the current year
    
    Args:
        limit: Maximum number of results to return (None for all)
        reverse: If True, sort ascending (least played first)
        db_path: Path to the database file
        
    Returns:
        List of tuples: [(song_uid, listen_count), ...]
    """
    start_of_year = _get_start_of_year()
    
    return _execute_aggregation_query(
        'WHERE listened_at >= ?',
        (start_of_year,),
        limit,
        reverse,
        db_path
    )


def get_top_songs_all_time(limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count for all time
    
    Args:
        limit: Maximum number of results to return (None for all)
        reverse: If True, sort ascending (least played first)
        db_path: Path to the database file
        
    Returns:
        List of tuples: [(song_uid, listen_count), ...]
    """
    return _execute_aggregation_query(
        '',
        (),
        limit,
        reverse,
        db_path
    )


def get_top_songs_for_week(year, week, limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count for a specific week
    
    Args:
        year: Year (e.g., 2025)
        week: ISO week number (1-53)
        limit: Maximum number of results to return (None for all)
        reverse: If True, sort ascending (least played first)
        db_path: Path to the database file
        
    Returns:
        List of tuples: [(song_uid, listen_count), ...]
    """
    if not (1 <= week <= 53):
        raise ValueError(f"Week must be between 1 and 53, got: {week}")
    
    return _execute_aggregation_query(
        "WHERE strftime('%Y', listened_at) = ? AND strftime('%W', listened_at) = ?",
        (str(year), f'{week:02d}'),
        limit,
        reverse,
        db_path
    )


def get_top_songs_for_month(year, month, limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count for a specific month
    
    Args:
        year: Year (e.g., 2025)
        month: Month number (1-12)
        limit: Maximum number of results to return (None for all)
        reverse: If True, sort ascending (least played first)
        db_path: Path to the database file
        
    Returns:
        List of tuples: [(song_uid, listen_count), ...]
    """
    if not (1 <= month <= 12):
        raise ValueError(f"Month must be between 1 and 12, got: {month}")
    
    return _execute_aggregation_query(
        "WHERE strftime('%Y', listened_at) = ? AND strftime('%m', listened_at) = ?",
        (str(year), f'{month:02d}'),
        limit,
        reverse,
        db_path
    )


def get_top_songs_for_year(year, limit=None, reverse=False, db_path=DB_PATH):
    """Get songs sorted by listen count for a specific year
    
    Args:
        year: Year (e.g., 2025)
        limit: Maximum number of results to return (None for all)
        reverse: If True, sort ascending (least played first)
        db_path: Path to the database file
        
    Returns:
        List of tuples: [(song_uid, listen_count), ...]
    """
    if not isinstance(year, int) or year < 1900 or year > 2100:
        raise ValueError(f"Invalid year: {year}")
    
    return _execute_aggregation_query(
        "WHERE strftime('%Y', listened_at) = ?",
        (str(year),),
        limit,
        reverse,
        db_path
    )
