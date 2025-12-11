"""Tests for song_metadata module"""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime

import song_metadata


class TestSongMetadata(unittest.TestCase):
    """Base test class with setup/teardown"""

    def setUp(self):
        """Create temporary database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db_path = self.temp_db.name
        song_metadata.init_database(self.db_path)

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)


class TestDatabaseInitialization(TestSongMetadata):
    """Tests for database setup"""

    def test_init_creates_table(self):
        """Test that init_database creates songs table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='songs'"
        )
        result = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "songs")

    def test_init_creates_indexes(self):
        """Test that necessary indexes are created"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        self.assertIn("idx_title", indexes)
        self.assertIn("idx_add_date", indexes)


class TestAddSong(TestSongMetadata):
    """Tests for adding songs"""

    def test_add_song_basic(self):
        """Test adding a song with minimal data"""
        uid = song_metadata.add_song(
            "song1234ABCD5678", "Test Song", "/path/to/song.mp3", db_path=self.db_path
        )

        self.assertEqual(uid, "song1234ABCD5678")

        song = song_metadata.get_song(uid, self.db_path)
        self.assertEqual(song["title"], "Test Song")
        self.assertEqual(song["path"], "/path/to/song.mp3")
        self.assertIsNone(song["url"])
        self.assertIsNone(song["duration"])

    def test_add_song_with_all_fields(self):
        """Test adding song with all optional fields"""
        uid = song_metadata.add_song(
            "songFULLABCD5678",
            "Complete Song",
            "/path/to/complete.mp3",
            url="http://example.com/song",
            duration=180,
            add_date="2025-01-01",
            db_path=self.db_path,
        )

        song = song_metadata.get_song(uid, self.db_path)
        self.assertEqual(song["url"], "http://example.com/song")
        self.assertEqual(song["duration"], 180)
        self.assertEqual(song["add_date"], "2025-01-01")

    def test_add_song_auto_date(self):
        """Test that add_date defaults to today"""
        uid = song_metadata.add_song(
            "songDATEABCD5678",
            "Auto Date Song",
            "/path/to/song.mp3",
            db_path=self.db_path,
        )

        song = song_metadata.get_song(uid, self.db_path)
        today = datetime.now().date().isoformat()
        self.assertEqual(song["add_date"], today)

    def test_add_song_updates_existing(self):
        """Test that adding with same UID updates existing song"""
        uid = "songUPDTABCD5678"

        song_metadata.add_song(
            uid, "Original Title", "/original/path", db_path=self.db_path
        )
        song_metadata.add_song(
            uid, "Updated Title", "/updated/path", db_path=self.db_path
        )

        song = song_metadata.get_song(uid, self.db_path)
        self.assertEqual(song["title"], "Updated Title")
        self.assertEqual(song["path"], "/updated/path")

    def test_add_song_invalid_uid(self):
        """Test that invalid UID format raises ValueError"""
        with self.assertRaises(ValueError):
            song_metadata.add_song("short", "Test", "/path", db_path=self.db_path)

        with self.assertRaises(ValueError):
            song_metadata.add_song(
                "invalid!@#$5678", "Test", "/path", db_path=self.db_path
            )


class TestGetSong(TestSongMetadata):
    """Tests for retrieving songs"""

    def test_get_song_exists(self):
        """Test getting an existing song"""
        uid = "songGETSABCD5678"
        song_metadata.add_song(uid, "Get Test", "/path", db_path=self.db_path)

        song = song_metadata.get_song(uid, self.db_path)
        self.assertIsNotNone(song)
        self.assertEqual(song["uid"], uid)
        self.assertEqual(song["title"], "Get Test")

    def test_get_song_not_found(self):
        """Test getting non-existent song returns None"""
        song = song_metadata.get_song("songNONEABCD5678", self.db_path)
        self.assertIsNone(song)

    def test_get_all_songs_empty(self):
        """Test getting all songs from empty database"""
        songs = song_metadata.get_all_songs(self.db_path)
        self.assertEqual(songs, [])

    def test_get_all_songs_ordered(self):
        """Test that get_all_songs returns songs ordered by add_date DESC"""
        song_metadata.add_song(
            "song1111AAAA1111",
            "Song 1",
            "/p1",
            add_date="2025-01-01",
            db_path=self.db_path,
        )
        song_metadata.add_song(
            "song2222BBBB2222",
            "Song 2",
            "/p2",
            add_date="2025-01-03",
            db_path=self.db_path,
        )
        song_metadata.add_song(
            "song3333CCCC3333",
            "Song 3",
            "/p3",
            add_date="2025-01-02",
            db_path=self.db_path,
        )

        songs = song_metadata.get_all_songs(self.db_path)
        self.assertEqual(len(songs), 3)
        # Most recent first
        self.assertEqual(songs[0]["uid"], "song2222BBBB2222")
        self.assertEqual(songs[1]["uid"], "song3333CCCC3333")
        self.assertEqual(songs[2]["uid"], "song1111AAAA1111")


class TestSearchSongs(TestSongMetadata):
    """Tests for searching songs"""

    def test_search_songs_by_title(self):
        """Test searching songs by title substring"""
        song_metadata.add_song(
            "song1111AAAA1111", "Rock Song", "/p1", db_path=self.db_path
        )
        song_metadata.add_song(
            "song2222BBBB2222", "Jazz Music", "/p2", db_path=self.db_path
        )
        song_metadata.add_song(
            "song3333CCCC3333", "Rock Anthem", "/p3", db_path=self.db_path
        )

        results = song_metadata.search_songs("Rock", self.db_path)
        self.assertEqual(len(results), 2)
        titles = [s["title"] for s in results]
        self.assertIn("Rock Song", titles)
        self.assertIn("Rock Anthem", titles)

    def test_search_songs_case_insensitive(self):
        """Test that search is case insensitive"""
        song_metadata.add_song(
            "songTESTABCD5678", "Test SONG", "/p", db_path=self.db_path
        )

        results = song_metadata.search_songs("test", self.db_path)
        self.assertEqual(len(results), 1)

    def test_search_songs_no_match(self):
        """Test searching with no matches returns empty list"""
        song_metadata.add_song(
            "song1111AAAA1111", "Song Title", "/p", db_path=self.db_path
        )

        results = song_metadata.search_songs("NoMatch", self.db_path)
        self.assertEqual(results, [])

    def test_search_songs_ordered_by_title(self):
        """Test that search results are ordered by title"""
        song_metadata.add_song(
            "song1111AAAA1111", "Zebra Track", "/p1", db_path=self.db_path
        )
        song_metadata.add_song(
            "song2222BBBB2222", "Alpha Track", "/p2", db_path=self.db_path
        )
        song_metadata.add_song(
            "song3333CCCC3333", "Beta Track", "/p3", db_path=self.db_path
        )

        results = song_metadata.search_songs("Track", self.db_path)
        titles = [s["title"] for s in results]
        self.assertEqual(titles, ["Alpha Track", "Beta Track", "Zebra Track"])


class TestUpdateSong(TestSongMetadata):
    """Tests for updating song data"""

    def test_update_song_path(self):
        """Test updating song path"""
        uid = "songPATHABCD5678"
        song_metadata.add_song(uid, "Test", "/old/path", db_path=self.db_path)

        song_metadata.update_song_path(uid, "/new/path", self.db_path)

        song = song_metadata.get_song(uid, self.db_path)
        self.assertEqual(song["path"], "/new/path")
        self.assertIsNotNone(song["last_modified"])


class TestDeleteSong(TestSongMetadata):
    """Tests for deleting songs"""

    def test_delete_song(self):
        """Test deleting a song"""
        uid = "songDELEABCD5678"
        song_metadata.add_song(uid, "Delete Me", "/path", db_path=self.db_path)

        song_metadata.delete_song(uid, self.db_path)

        song = song_metadata.get_song(uid, self.db_path)
        self.assertIsNone(song)

    def test_delete_nonexistent_song(self):
        """Test deleting non-existent song doesn't raise error"""
        song_metadata.delete_song("songNONEABCD5678", self.db_path)  # Should not raise


class TestGetSongsAlphabetically(TestSongMetadata):
    """Tests for alphabetical sorting"""

    def test_get_songs_alphabetically_ascending(self):
        """Test getting songs A-Z"""
        song_metadata.add_song("song1111AAAA1111", "Zebra", "/p1", db_path=self.db_path)
        song_metadata.add_song("song2222BBBB2222", "Alpha", "/p2", db_path=self.db_path)
        song_metadata.add_song("song3333CCCC3333", "Beta", "/p3", db_path=self.db_path)

        songs = song_metadata.get_songs_alphabetically(db_path=self.db_path)
        titles = [s["title"] for s in songs]
        self.assertEqual(titles, ["Alpha", "Beta", "Zebra"])

    def test_get_songs_alphabetically_descending(self):
        """Test getting songs Z-A"""
        song_metadata.add_song("song1111AAAA1111", "Zebra", "/p1", db_path=self.db_path)
        song_metadata.add_song("song2222BBBB2222", "Alpha", "/p2", db_path=self.db_path)
        song_metadata.add_song("song3333CCCC3333", "Beta", "/p3", db_path=self.db_path)

        songs = song_metadata.get_songs_alphabetically(
            reverse=True, db_path=self.db_path
        )
        titles = [s["title"] for s in songs]
        self.assertEqual(titles, ["Zebra", "Beta", "Alpha"])


class TestGetSongsWithListenCount(TestSongMetadata):
    """Tests for getting songs with listen counts"""

    def test_get_songs_with_listen_count(self):
        """Test getting songs with listen counts"""
        # Create listen_history table
        conn = sqlite3.connect(self.db_path)
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
        conn.commit()
        conn.close()

        # Add songs
        song_metadata.add_song(
            "song1111AAAA1111", "Popular", "/p1", db_path=self.db_path
        )
        song_metadata.add_song(
            "song2222BBBB2222", "Less Popular", "/p2", db_path=self.db_path
        )

        # Add listen history
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO listen_history (song_uid, listened_at) VALUES (?, ?)",
            ("song1111AAAA1111", "2025-01-01 10:00:00"),
        )
        cursor.execute(
            "INSERT INTO listen_history (song_uid, listened_at) VALUES (?, ?)",
            ("song1111AAAA1111", "2025-01-02 10:00:00"),
        )
        cursor.execute(
            "INSERT INTO listen_history (song_uid, listened_at) VALUES (?, ?)",
            ("song2222BBBB2222", "2025-01-03 10:00:00"),
        )
        conn.commit()
        conn.close()

        songs = song_metadata.get_songs_with_listen_count(db_path=self.db_path)
        self.assertEqual(len(songs), 2)
        self.assertEqual(songs[0]["listen_count"], 2)
        self.assertEqual(songs[1]["listen_count"], 1)

    def test_get_songs_with_listen_count_limit(self):
        """Test limiting results"""
        conn = sqlite3.connect(self.db_path)
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
        conn.commit()
        conn.close()

        song_metadata.add_song(
            "song1111AAAA1111", "Song 1", "/p1", db_path=self.db_path
        )
        song_metadata.add_song(
            "song2222BBBB2222", "Song 2", "/p2", db_path=self.db_path
        )
        song_metadata.add_song(
            "song3333CCCC3333", "Song 3", "/p3", db_path=self.db_path
        )

        songs = song_metadata.get_songs_with_listen_count(limit=2, db_path=self.db_path)
        self.assertEqual(len(songs), 2)


if __name__ == "__main__":
    unittest.main()
