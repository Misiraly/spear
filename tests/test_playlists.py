"""Tests for playlists module - focused on core functionality"""

import os
import sqlite3
import tempfile
import unittest

import playlists


class TestPlaylists(unittest.TestCase):
    """Base test class with setup/teardown"""

    def setUp(self):
        """Create temporary database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db_path = self.temp_db.name
        playlists.init_database(self.db_path)

        # Create songs table (needed for JOINs in queries)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS songs (
                uid TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                duration INTEGER,
                add_date TEXT,
                path TEXT
            )
        """
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)


class TestDatabaseInitialization(TestPlaylists):
    """Tests for database setup"""

    def test_init_creates_tables(self):
        """Test that init_database creates both tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('playlists', 'playlist_items')"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        self.assertIn("playlists", tables)
        self.assertIn("playlist_items", tables)

    def test_init_creates_indexes(self):
        """Test that necessary indexes are created"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        self.assertIn("idx_playlist_position", indexes)
        self.assertIn("idx_song_uid", indexes)


class TestPlaylistCRUD(TestPlaylists):
    """Tests for create, read, update, delete operations"""

    def test_create_playlist_basic(self):
        """Test creating a basic playlist"""
        uid = playlists.create_playlist("My Playlist", db_path=self.db_path)

        self.assertIsNotNone(uid)
        self.assertEqual(len(uid), 16)

        playlist = playlists.get_playlist(uid, self.db_path)
        self.assertEqual(playlist["name"], "My Playlist")
        self.assertIsNone(playlist["description"])

    def test_create_playlist_with_description(self):
        """Test creating playlist with description"""
        uid = playlists.create_playlist(
            "Test Playlist", description="A test playlist", db_path=self.db_path
        )

        playlist = playlists.get_playlist(uid, self.db_path)
        self.assertEqual(playlist["description"], "A test playlist")

    def test_create_duplicate_name_raises_error(self):
        """Test that duplicate playlist names raise error"""
        playlists.create_playlist("Duplicate", db_path=self.db_path)

        with self.assertRaises(ValueError):
            playlists.create_playlist("Duplicate", db_path=self.db_path)

    def test_get_playlist_not_found(self):
        """Test getting non-existent playlist returns None"""
        result = playlists.get_playlist("abcd1234EFGH5678", self.db_path)
        self.assertIsNone(result)

    def test_rename_playlist(self):
        """Test renaming a playlist"""
        uid = playlists.create_playlist("Old Name", db_path=self.db_path)
        success = playlists.rename_playlist(uid, "New Name", self.db_path)

        self.assertTrue(success)
        playlist = playlists.get_playlist(uid, self.db_path)
        self.assertEqual(playlist["name"], "New Name")

    def test_update_description(self):
        """Test updating playlist description"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        success = playlists.update_playlist_description(
            uid, "Updated description", self.db_path
        )

        self.assertTrue(success)
        playlist = playlists.get_playlist(uid, self.db_path)
        self.assertEqual(playlist["description"], "Updated description")

    def test_delete_playlist(self):
        """Test deleting a playlist"""
        uid = playlists.create_playlist("To Delete", db_path=self.db_path)
        playlists.delete_playlist(uid, self.db_path)

        result = playlists.get_playlist(uid, self.db_path)
        self.assertIsNone(result)

    def test_get_all_playlists(self):
        """Test getting all playlists"""
        playlists.create_playlist("Playlist A", db_path=self.db_path)
        playlists.create_playlist("Playlist B", db_path=self.db_path)
        playlists.create_playlist("Playlist C", db_path=self.db_path)

        all_playlists = playlists.get_all_playlists(self.db_path)

        self.assertEqual(len(all_playlists), 3)
        names = [p["name"] for p in all_playlists]
        self.assertEqual(names, ["Playlist A", "Playlist B", "Playlist C"])

    def test_playlist_exists(self):
        """Test checking if playlist name exists"""
        playlists.create_playlist("Existing", db_path=self.db_path)

        self.assertTrue(playlists.playlist_exists("Existing", self.db_path))
        self.assertFalse(playlists.playlist_exists("Not Existing", self.db_path))

    def test_get_playlist_by_name(self):
        """Test retrieving playlist by name"""
        playlists.create_playlist("Find Me", db_path=self.db_path)

        result = playlists.get_playlist_by_name("Find Me", self.db_path)
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Find Me")

        result = playlists.get_playlist_by_name("Not Found", self.db_path)
        self.assertIsNone(result)


class TestAddingSongs(TestPlaylists):
    """Tests for adding songs to playlists"""

    def test_add_single_song(self):
        """Test adding one song to playlist"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        playlists.add_to_playlist(uid, "song1234ABCD5678", self.db_path)

        songs = playlists.get_playlist_songs(uid, self.db_path)
        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0]["uid"], "song1234ABCD5678")
        self.assertEqual(songs[0]["position"], 1)

    def test_add_multiple_songs(self):
        """Test adding multiple songs at once"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        song_uids = ["song1111AAAA1111", "song2222BBBB2222", "song3333CCCC3333"]

        playlists.add_multiple_to_playlist(uid, song_uids, self.db_path)

        songs = playlists.get_playlist_songs(uid, self.db_path)
        self.assertEqual(len(songs), 3)
        self.assertEqual(songs[0]["position"], 1)
        self.assertEqual(songs[2]["position"], 3)

    def test_insert_at_position(self):
        """Test inserting song at specific position"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        playlists.add_multiple_to_playlist(
            uid, ["songAAAA11112222", "songBBBB33334444"], self.db_path
        )

        playlists.insert_at_position(uid, "songNEW000000000", 2, self.db_path)

        songs = playlists.get_playlist_songs(uid, self.db_path)
        self.assertEqual(len(songs), 3)
        self.assertEqual(songs[1]["uid"], "songNEW000000000")
        self.assertEqual(songs[1]["position"], 2)


class TestRemovingSongs(TestPlaylists):
    """Tests for removing songs from playlists"""

    def test_remove_by_position(self):
        """Test removing song by position"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        playlists.add_multiple_to_playlist(
            uid,
            ["song1111AAAA1111", "song2222BBBB2222", "song3333CCCC3333"],
            self.db_path,
        )

        success = playlists.remove_by_position(uid, 2, self.db_path)

        self.assertTrue(success)
        songs = playlists.get_playlist_songs(uid, self.db_path)
        self.assertEqual(len(songs), 2)
        self.assertEqual(songs[0]["position"], 1)
        self.assertEqual(songs[1]["position"], 2)

    def test_remove_by_uid(self):
        """Test removing all instances of a song"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        playlists.add_multiple_to_playlist(
            uid,
            ["songAAAA11112222", "songBBBB33334444", "songAAAA11112222"],
            self.db_path,
        )

        playlists.remove_by_uid(uid, "songAAAA11112222", self.db_path)

        songs = playlists.get_playlist_songs(uid, self.db_path)
        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0]["uid"], "songBBBB33334444")

    def test_clear_playlist(self):
        """Test clearing all songs from playlist"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        playlists.add_multiple_to_playlist(
            uid, ["song1111AAAA1111", "song2222BBBB2222"], self.db_path
        )

        playlists.clear_playlist(uid, self.db_path)

        songs = playlists.get_playlist_songs(uid, self.db_path)
        self.assertEqual(len(songs), 0)


class TestReordering(TestPlaylists):
    """Tests for reordering songs"""

    def test_move_song_down(self):
        """Test moving song to later position"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        playlists.add_multiple_to_playlist(
            uid,
            ["songA111AAAA1111", "songB222BBBB2222", "songC333CCCC3333"],
            self.db_path,
        )

        success = playlists.move_song(uid, 1, 3, self.db_path)

        self.assertTrue(success)
        songs = playlists.get_playlist_songs(uid, self.db_path)
        self.assertEqual(songs[0]["uid"], "songB222BBBB2222")
        self.assertEqual(songs[2]["uid"], "songA111AAAA1111")

    def test_move_song_up(self):
        """Test moving song to earlier position"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        playlists.add_multiple_to_playlist(
            uid,
            ["songA111AAAA1111", "songB222BBBB2222", "songC333CCCC3333"],
            self.db_path,
        )

        success = playlists.move_song(uid, 3, 1, self.db_path)

        self.assertTrue(success)
        songs = playlists.get_playlist_songs(uid, self.db_path)
        self.assertEqual(songs[0]["uid"], "songC333CCCC3333")

    def test_shuffle_playlist(self):
        """Test shuffling playlist (just verify count stays same)"""
        uid = playlists.create_playlist("Test", db_path=self.db_path)
        song_uids = [f"song{i:04d}AAAA{i:04d}" for i in range(10)]
        playlists.add_multiple_to_playlist(uid, song_uids, self.db_path)

        playlists.shuffle_playlist(uid, self.db_path)

        songs = playlists.get_playlist_songs(uid, self.db_path)
        self.assertEqual(len(songs), 10)
        # Verify all songs still present
        shuffled_uids = {s["uid"] for s in songs}
        self.assertEqual(shuffled_uids, set(song_uids))


class TestQueryFunctions(TestPlaylists):
    """Tests for playlist query functions"""

    def test_get_playlist_count(self):
        """Test counting total playlists"""
        self.assertEqual(playlists.get_playlist_count(self.db_path), 0)

        playlists.create_playlist("Playlist 1", db_path=self.db_path)
        playlists.create_playlist("Playlist 2", db_path=self.db_path)

        self.assertEqual(playlists.get_playlist_count(self.db_path), 2)

    def test_search_playlists(self):
        """Test searching playlists by name/description"""
        playlists.create_playlist("Rock Classics", db_path=self.db_path)
        playlists.create_playlist("Jazz Favorites", db_path=self.db_path)
        playlists.create_playlist(
            "Classical", description="Rock-inspired classical", db_path=self.db_path
        )

        results = playlists.search_playlists("Rock", self.db_path)
        # Should match "Rock Classics" by name and "Classical" by description
        self.assertGreaterEqual(len(results), 1)

    def test_get_empty_playlists(self):
        """Test finding playlists with no songs"""
        _ = playlists.create_playlist("Empty", db_path=self.db_path)
        uid2 = playlists.create_playlist("Not Empty", db_path=self.db_path)
        playlists.add_to_playlist(uid2, "song1234ABCD5678", self.db_path)

        empty = playlists.get_empty_playlists(self.db_path)
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty[0]["name"], "Empty")


class TestInputValidation(TestPlaylists):
    """Tests for input validation"""

    def test_invalid_uid_format(self):
        """Test that invalid UID format raises ValueError"""
        with self.assertRaises(ValueError):
            playlists.get_playlist("invalid", self.db_path)

    def test_add_to_nonexistent_playlist(self):
        """Test adding to non-existent playlist raises error"""
        with self.assertRaises(ValueError):
            playlists.add_to_playlist(
                "abcd1234EFGH5678", "song1234ABCD5678", self.db_path
            )


if __name__ == "__main__":
    unittest.main()
