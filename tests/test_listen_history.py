import unittest
import sqlite3
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import listen_history


class TestListenHistory(unittest.TestCase):
    """Test suite for listen_history module"""
    
    def setUp(self):
        """Create a temporary database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        listen_history.init_database(self.db_path)
    
    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def _insert_test_data(self, data):
        """Helper to insert test data
        
        Args:
            data: List of tuples (song_uid, datetime_obj)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for song_uid, listened_at in data:
            cursor.execute(
                'INSERT INTO listen_history (song_uid, listened_at) VALUES (?, ?)',
                (song_uid, listened_at)
            )
        conn.commit()
        conn.close()


class TestDatabaseInitialization(TestListenHistory):
    """Tests for database initialization"""
    
    def test_init_database_creates_table(self):
        """Test that init_database creates the listen_history table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='listen_history'"
        )
        result = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 'listen_history')
    
    def test_init_database_creates_indexes(self):
        """Test that init_database creates necessary indexes"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        self.assertIn('idx_song_uid', indexes)
        self.assertIn('idx_listened_at', indexes)
    
    def test_init_database_creates_directory(self):
        """Test that init_database creates parent directory if needed"""
        nested_path = os.path.join(tempfile.gettempdir(), 'test_nested', 'subdir', 'test.db')
        
        try:
            listen_history.init_database(nested_path)
            self.assertTrue(os.path.exists(nested_path))
        finally:
            if os.path.exists(nested_path):
                os.unlink(nested_path)
            # Clean up directories
            parent = os.path.dirname(nested_path)
            if os.path.exists(parent):
                os.rmdir(parent)
            grandparent = os.path.dirname(parent)
            if os.path.exists(grandparent):
                os.rmdir(grandparent)


class TestLogListen(TestListenHistory):
    """Tests for log_listen function"""
    
    def test_log_listen_valid_uid(self):
        """Test logging a listen with valid song UID"""
        song_uid = 'abcd1234EFGH5678'
        listen_history.log_listen(song_uid, self.db_path)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT song_uid FROM listen_history WHERE song_uid = ?', (song_uid,))
        result = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(result)
        self.assertEqual(result[0], song_uid)
    
    def test_log_listen_invalid_uid_length(self):
        """Test that invalid UID length raises ValueError"""
        with self.assertRaises(ValueError):
            listen_history.log_listen('short', self.db_path)
        
        with self.assertRaises(ValueError):
            listen_history.log_listen('toolonguidmorethansixteen', self.db_path)
    
    def test_log_listen_invalid_uid_type(self):
        """Test that non-string UID raises ValueError"""
        with self.assertRaises(ValueError):
            listen_history.log_listen(1234567890123456, self.db_path)
        
        with self.assertRaises(ValueError):
            listen_history.log_listen(None, self.db_path)
    
    def test_log_listen_invalid_uid_format(self):
        """Test that UID with invalid characters raises ValueError"""
        with self.assertRaises(ValueError):
            listen_history.log_listen('abcd!@#$EFGH5678', self.db_path)
        
        with self.assertRaises(ValueError):
            listen_history.log_listen('abcd 123 EFG 567', self.db_path)
    
    def test_log_listen_timestamp(self):
        """Test that log_listen records current timestamp"""
        song_uid = 'test1234ABCD5678'
        before = datetime.now()
        listen_history.log_listen(song_uid, self.db_path)
        after = datetime.now()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT listened_at FROM listen_history WHERE song_uid = ?', (song_uid,))
        result = cursor.fetchone()
        conn.close()
        
        timestamp = datetime.fromisoformat(result[0])
        self.assertGreaterEqual(timestamp, before)
        self.assertLessEqual(timestamp, after)


class TestHelperFunctions(unittest.TestCase):
    """Tests for internal helper functions"""
    
    @patch('listen_history.datetime')
    def test_get_start_of_week_monday(self, mock_datetime):
        """Test _get_start_of_week on a Monday"""
        # Mock: Monday, Dec 8, 2025, 15:30:45
        mock_datetime.now.return_value = datetime(2025, 12, 8, 15, 30, 45)
        
        result = listen_history._get_start_of_week()
        expected = datetime(2025, 12, 8, 0, 0, 0)
        
        self.assertEqual(result, expected)
    
    @patch('listen_history.datetime')
    def test_get_start_of_week_friday(self, mock_datetime):
        """Test _get_start_of_week on a Friday"""
        # Mock: Friday, Dec 12, 2025, 23:59:59
        mock_datetime.now.return_value = datetime(2025, 12, 12, 23, 59, 59)
        
        result = listen_history._get_start_of_week()
        expected = datetime(2025, 12, 8, 0, 0, 0)  # Previous Monday
        
        self.assertEqual(result, expected)
    
    @patch('listen_history.datetime')
    def test_get_start_of_month_first_day(self, mock_datetime):
        """Test _get_start_of_month on the first day"""
        mock_datetime.now.return_value = datetime(2025, 12, 1, 12, 0, 0)
        
        result = listen_history._get_start_of_month()
        expected = datetime(2025, 12, 1, 0, 0, 0)
        
        self.assertEqual(result, expected)
    
    @patch('listen_history.datetime')
    def test_get_start_of_month_last_day(self, mock_datetime):
        """Test _get_start_of_month on the last day"""
        mock_datetime.now.return_value = datetime(2025, 12, 31, 23, 59, 59)
        
        result = listen_history._get_start_of_month()
        expected = datetime(2025, 12, 1, 0, 0, 0)
        
        self.assertEqual(result, expected)
    
    @patch('listen_history.datetime')
    def test_get_start_of_year_first_day(self, mock_datetime):
        """Test _get_start_of_year on January 1st"""
        mock_datetime.now.return_value = datetime(2025, 1, 1, 0, 0, 0)
        
        result = listen_history._get_start_of_year()
        expected = datetime(2025, 1, 1, 0, 0, 0)
        
        self.assertEqual(result, expected)
    
    @patch('listen_history.datetime')
    def test_get_start_of_year_last_day(self, mock_datetime):
        """Test _get_start_of_year on December 31st"""
        mock_datetime.now.return_value = datetime(2025, 12, 31, 23, 59, 59)
        
        result = listen_history._get_start_of_year()
        expected = datetime(2025, 1, 1, 0, 0, 0)
        
        self.assertEqual(result, expected)


class TestTopSongsQueries(TestListenHistory):
    """Tests for top songs aggregation functions"""
    
    def test_get_top_songs_all_time_basic(self):
        """Test getting all-time top songs"""
        test_data = [
            ('song1234ABCD5678', datetime.now()),
            ('song1234ABCD5678', datetime.now()),
            ('song1234ABCD5678', datetime.now()),
            ('song5678EFGH1234', datetime.now()),
            ('song5678EFGH1234', datetime.now()),
            ('songABCDEFGH0000', datetime.now()),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_all_time(db_path=self.db_path)
        
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ('song1234ABCD5678', 3))
        self.assertEqual(result[1], ('song5678EFGH1234', 2))
        self.assertEqual(result[2], ('songABCDEFGH0000', 1))
    
    def test_get_top_songs_all_time_with_limit(self):
        """Test getting top songs with limit"""
        test_data = [
            ('song1111AAAA1111', datetime.now()),
            ('song2222BBBB2222', datetime.now()),
            ('song2222BBBB2222', datetime.now()),
            ('song3333CCCC3333', datetime.now()),
            ('song3333CCCC3333', datetime.now()),
            ('song3333CCCC3333', datetime.now()),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_all_time(limit=2, db_path=self.db_path)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], 'song3333CCCC3333')
        self.assertEqual(result[1][0], 'song2222BBBB2222')
    
    def test_get_top_songs_all_time_reverse(self):
        """Test getting least played songs (reverse order)"""
        test_data = [
            ('song1111AAAA1111', datetime.now()),
            ('song2222BBBB2222', datetime.now()),
            ('song2222BBBB2222', datetime.now()),
            ('song3333CCCC3333', datetime.now()),
            ('song3333CCCC3333', datetime.now()),
            ('song3333CCCC3333', datetime.now()),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_all_time(reverse=True, db_path=self.db_path)
        
        self.assertEqual(result[0], ('song1111AAAA1111', 1))
        self.assertEqual(result[1], ('song2222BBBB2222', 2))
        self.assertEqual(result[2], ('song3333CCCC3333', 3))
    
    def test_get_top_songs_last_n_days(self):
        """Test getting top songs from last N days"""
        now = datetime.now()
        test_data = [
            ('songRECENT000001', now - timedelta(days=1)),
            ('songRECENT000001', now - timedelta(days=2)),
            ('songOLD0000000001', now - timedelta(days=10)),
            ('songOLD0000000001', now - timedelta(days=11)),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_last_n_days(7, db_path=self.db_path)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ('songRECENT000001', 2))
    
    @patch('listen_history.datetime')
    def test_get_top_songs_this_week(self, mock_datetime):
        """Test getting top songs from current week"""
        # Mock: Friday, Dec 12, 2025
        mock_now = datetime(2025, 12, 12, 12, 0, 0)
        mock_datetime.now.return_value = mock_now
        
        test_data = [
            ('songWEEK00000001', mock_now - timedelta(days=1)),  # Thursday
            ('songWEEK00000001', mock_now - timedelta(days=2)),  # Wednesday
            ('songOLDWEEK00001', mock_now - timedelta(days=7)),  # Previous Friday
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_this_week(db_path=self.db_path)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'songWEEK00000001')
    
    @patch('listen_history.datetime')
    def test_get_top_songs_this_month(self, mock_datetime):
        """Test getting top songs from current month"""
        mock_now = datetime(2025, 12, 15, 12, 0, 0)
        mock_datetime.now.return_value = mock_now
        
        test_data = [
            ('songMONTH0000001', datetime(2025, 12, 10)),
            ('songMONTH0000001', datetime(2025, 12, 14)),
            ('songOLDMONTH0001', datetime(2025, 11, 30)),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_this_month(db_path=self.db_path)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'songMONTH0000001')
    
    @patch('listen_history.datetime')
    def test_get_top_songs_this_year(self, mock_datetime):
        """Test getting top songs from current year"""
        mock_now = datetime(2025, 12, 15, 12, 0, 0)
        mock_datetime.now.return_value = mock_now
        
        test_data = [
            ('songYEAR00000001', datetime(2025, 6, 15)),
            ('songYEAR00000001', datetime(2025, 11, 30)),
            ('songOLDYEAR00001', datetime(2024, 12, 31)),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_this_year(db_path=self.db_path)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'songYEAR00000001')


class TestSpecificPeriodQueries(TestListenHistory):
    """Tests for queries targeting specific time periods"""
    
    def test_get_top_songs_for_week(self):
        """Test getting top songs for a specific week"""
        test_data = [
            ('songWEEK49_0001', datetime(2025, 12, 1)),   # Week 49
            ('songWEEK49_0001', datetime(2025, 12, 5)),   # Week 49
            ('songWEEK50_0001', datetime(2025, 12, 9)),   # Week 50
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_for_week(2025, 49, db_path=self.db_path)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ('songWEEK49_0001', 2))
    
    def test_get_top_songs_for_week_invalid_week(self):
        """Test that invalid week number raises ValueError"""
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_for_week(2025, 0, db_path=self.db_path)
        
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_for_week(2025, 54, db_path=self.db_path)
    
    def test_get_top_songs_for_month(self):
        """Test getting top songs for a specific month"""
        test_data = [
            ('songDEC00000001', datetime(2025, 12, 1)),
            ('songDEC00000001', datetime(2025, 12, 15)),
            ('songNOV00000001', datetime(2025, 11, 30)),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_for_month(2025, 12, db_path=self.db_path)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ('songDEC00000001', 2))
    
    def test_get_top_songs_for_month_invalid_month(self):
        """Test that invalid month number raises ValueError"""
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_for_month(2025, 0, db_path=self.db_path)
        
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_for_month(2025, 13, db_path=self.db_path)
    
    def test_get_top_songs_for_year(self):
        """Test getting top songs for a specific year"""
        test_data = [
            ('song2025_000001', datetime(2025, 1, 1)),
            ('song2025_000001', datetime(2025, 12, 31)),
            ('song2024_000001', datetime(2024, 12, 31)),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_for_year(2025, db_path=self.db_path)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ('song2025_000001', 2))
    
    def test_get_top_songs_for_year_invalid_year(self):
        """Test that invalid year raises ValueError"""
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_for_year(1899, db_path=self.db_path)
        
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_for_year(2101, db_path=self.db_path)
        
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_for_year("2025", db_path=self.db_path)


class TestInputValidation(TestListenHistory):
    """Tests for input validation and error handling"""
    
    def test_limit_validation_negative(self):
        """Test that negative limit raises ValueError"""
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_all_time(limit=-1, db_path=self.db_path)
    
    def test_limit_validation_non_integer(self):
        """Test that non-integer limit raises ValueError"""
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_all_time(limit="10", db_path=self.db_path)
        
        with self.assertRaises(ValueError):
            listen_history.get_top_songs_all_time(limit=10.5, db_path=self.db_path)
    
    def test_limit_zero_is_valid(self):
        """Test that limit=0 returns no results but doesn't raise error"""
        test_data = [
            ('songTEST00000001', datetime.now()),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_all_time(limit=0, db_path=self.db_path)
        self.assertEqual(len(result), 0)


class TestEdgeCases(TestListenHistory):
    """Tests for edge cases and boundary conditions"""
    
    def test_empty_database(self):
        """Test queries on empty database return empty results"""
        result = listen_history.get_top_songs_all_time(db_path=self.db_path)
        self.assertEqual(result, [])
    
    def test_single_song_multiple_listens(self):
        """Test aggregation with only one song"""
        test_data = [
            ('songSINGLE00001', datetime.now()),
            ('songSINGLE00001', datetime.now()),
            ('songSINGLE00001', datetime.now()),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_all_time(db_path=self.db_path)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ('songSINGLE00001', 3))
    
    def test_limit_larger_than_results(self):
        """Test that limit larger than available results returns all results"""
        test_data = [
            ('songLIMIT0000001', datetime.now()),
        ]
        self._insert_test_data(test_data)
        
        result = listen_history.get_top_songs_all_time(limit=100, db_path=self.db_path)
        
        self.assertEqual(len(result), 1)


class TestConnectionContextManager(unittest.TestCase):
    """Tests for database connection context manager"""
    
    def test_connection_closes_on_success(self):
        """Test that connection closes properly after successful operation"""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        db_path = temp_db.name
        
        try:
            listen_history.init_database(db_path)
            
            with listen_history._get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1')
            
            # Try to use connection - should fail if properly closed
            with self.assertRaises(sqlite3.ProgrammingError):
                cursor.execute('SELECT 1')
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_connection_closes_on_exception(self):
        """Test that connection closes even when exception occurs"""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        db_path = temp_db.name
        
        try:
            listen_history.init_database(db_path)
            
            with self.assertRaises(sqlite3.OperationalError):
                with listen_history._get_connection(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM nonexistent_table')
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


if __name__ == '__main__':
    unittest.main()
