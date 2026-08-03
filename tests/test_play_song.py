"""Tests for play_song module - pure formatting helpers"""

import unittest

import play_song


class TestFormatTime(unittest.TestCase):
    """Tests for format_time"""

    def test_zero_and_negative(self):
        """Test non-positive values collapse to 0:00"""
        self.assertEqual(play_song.format_time(0), "0:00")
        self.assertEqual(play_song.format_time(-1), "0:00")
        self.assertEqual(play_song.format_time(-3600), "0:00")

    def test_under_one_minute(self):
        """Test seconds are zero-padded"""
        self.assertEqual(play_song.format_time(5), "0:05")
        self.assertEqual(play_song.format_time(59), "0:59")

    def test_minutes_and_seconds(self):
        """Test M:SS formatting below one hour"""
        self.assertEqual(play_song.format_time(60), "1:00")
        self.assertEqual(play_song.format_time(243), "4:03")
        self.assertEqual(play_song.format_time(3599), "59:59")

    def test_hours(self):
        """Test H:MM:SS formatting from one hour up"""
        self.assertEqual(play_song.format_time(3600), "1:00:00")
        self.assertEqual(play_song.format_time(4043), "1:07:23")
        self.assertEqual(play_song.format_time(36000), "10:00:00")

    def test_float_input_truncates(self):
        """Test fractional seconds are truncated, not rounded"""
        self.assertEqual(play_song.format_time(125.7), "2:05")
        self.assertEqual(play_song.format_time(59.9), "0:59")


if __name__ == "__main__":
    unittest.main()
