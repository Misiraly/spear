"""Tests for export_to_csv module"""

import csv
import os
import sqlite3
import tempfile
from datetime import datetime

import pytest

import export_to_csv


@pytest.fixture
def temp_db():
    """Create a temporary test database"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".db") as f:
        db_path = f.name

    # Create and populate test database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create test tables
    cursor.execute(
        """
        CREATE TABLE songs (
            uid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT,
            duration INTEGER,
            add_date TEXT,
            path TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE listen_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song_uid TEXT NOT NULL,
            listened_at TIMESTAMP NOT NULL
        )
    """
    )

    # Insert test data
    cursor.execute(
        """
        INSERT INTO songs (uid, title, url, duration, add_date, path)
        VALUES ('abc123', 'Test Song 1', 'http://example.com/1', 180, '2025-01-01', '/path/1')
    """
    )
    cursor.execute(
        """
        INSERT INTO songs (uid, title, url, duration, add_date, path)
        VALUES ('def456', 'Test Song 2', 'http://example.com/2', 240, '2025-01-02', '/path/2')
    """
    )

    cursor.execute(
        """
        INSERT INTO listen_history (song_uid, listened_at)
        VALUES ('abc123', '2025-01-01 10:00:00')
    """
    )
    cursor.execute(
        """
        INSERT INTO listen_history (song_uid, listened_at)
        VALUES ('abc123', '2025-01-02 11:00:00')
    """
    )
    cursor.execute(
        """
        INSERT INTO listen_history (song_uid, listened_at)
        VALUES ('def456', '2025-01-03 12:00:00')
    """
    )

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir

    # Cleanup
    import shutil

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


def test_export_table_to_csv(temp_db, temp_output_dir, monkeypatch):
    """Test exporting a single table to CSV"""
    # Mock the DB_PATH
    monkeypatch.setattr(export_to_csv, "DB_PATH", temp_db)

    output_path = os.path.join(temp_output_dir, "songs_test.csv")

    # Export the songs table
    export_to_csv.export_table_to_csv("songs", output_path)

    # Verify CSV file was created
    assert os.path.exists(output_path)

    # Read and verify CSV contents
    with open(output_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Check header
    assert rows[0] == ["uid", "title", "url", "duration", "add_date", "path"]

    # Check data rows (2 songs inserted)
    assert len(rows) == 3  # header + 2 data rows
    assert rows[1][0] == "abc123"
    assert rows[1][1] == "Test Song 1"
    assert rows[2][0] == "def456"
    assert rows[2][1] == "Test Song 2"


def test_export_listen_history_to_csv(temp_db, temp_output_dir, monkeypatch):
    """Test exporting listen_history table to CSV"""
    monkeypatch.setattr(export_to_csv, "DB_PATH", temp_db)

    output_path = os.path.join(temp_output_dir, "listen_history_test.csv")

    # Export the listen_history table
    export_to_csv.export_table_to_csv("listen_history", output_path)

    # Verify CSV file was created
    assert os.path.exists(output_path)

    # Read and verify CSV contents
    with open(output_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Check header
    assert rows[0] == ["id", "song_uid", "listened_at"]

    # Check data rows (3 listens inserted)
    assert len(rows) == 4  # header + 3 data rows
    assert rows[1][1] == "abc123"
    assert rows[3][1] == "def456"


def test_export_empty_table(temp_db, temp_output_dir, monkeypatch):
    """Test exporting an empty table"""
    monkeypatch.setattr(export_to_csv, "DB_PATH", temp_db)

    # Create empty table
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE empty_table (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    output_path = os.path.join(temp_output_dir, "empty_test.csv")
    export_to_csv.export_table_to_csv("empty_table", output_path)

    # Verify CSV file was created with header only
    assert os.path.exists(output_path)

    with open(output_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    assert len(rows) == 1  # header only
    assert rows[0] == ["id", "name"]


def test_export_all_tables(temp_db, temp_output_dir, monkeypatch):
    """Test exporting all tables at once"""
    monkeypatch.setattr(export_to_csv, "DB_PATH", temp_db)
    monkeypatch.setattr(export_to_csv, "OUTPUT_DIR", temp_output_dir)

    # Export all tables
    export_to_csv.export_all_tables()

    # Check that both CSV files were created
    files = os.listdir(temp_output_dir)
    csv_files = [f for f in files if f.endswith(".csv")]

    assert len(csv_files) == 2

    # Check for expected file patterns
    listen_history_files = [f for f in csv_files if f.startswith("listen_history_")]
    songs_files = [f for f in csv_files if f.startswith("songs_")]

    assert len(listen_history_files) == 1
    assert len(songs_files) == 1

    # Verify timestamp format in filenames
    for filename in csv_files:
        # Extract timestamp part (format: YYYYMMDD_HHMMSS)
        if "listen_history_" in filename:
            timestamp_str = filename.replace("listen_history_", "").replace(".csv", "")
        else:
            timestamp_str = filename.replace("songs_", "").replace(".csv", "")

        # Verify timestamp is valid format
        try:
            datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        except ValueError:
            pytest.fail(f"Invalid timestamp format in filename: {filename}")


def test_csv_encoding_with_unicode(temp_db, temp_output_dir, monkeypatch):
    """Test that CSV export handles unicode characters correctly"""
    monkeypatch.setattr(export_to_csv, "DB_PATH", temp_db)

    # Add song with unicode characters
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO songs (uid, title, url, duration, add_date, path)
        VALUES ('xyz789', 'Café ☕ 日本語', 'http://example.com/3', 200, '2025-01-03', '/path/3')
    """
    )
    conn.commit()
    conn.close()

    output_path = os.path.join(temp_output_dir, "unicode_test.csv")
    export_to_csv.export_table_to_csv("songs", output_path)

    # Read and verify unicode is preserved
    with open(output_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Find the unicode song
    unicode_row = [row for row in rows if "xyz789" in row]
    assert len(unicode_row) == 1
    assert "Café ☕ 日本語" in unicode_row[0][1]


def test_output_directory_creation(temp_db, monkeypatch):
    """Test that export_all_tables creates output directory if it doesn't exist"""
    monkeypatch.setattr(export_to_csv, "DB_PATH", temp_db)

    # Use a non-existent directory
    with tempfile.TemporaryDirectory() as temp_dir:
        new_output_dir = os.path.join(temp_dir, "new_exports", "subdir")
        monkeypatch.setattr(export_to_csv, "OUTPUT_DIR", new_output_dir)

        assert not os.path.exists(new_output_dir)

        export_to_csv.export_all_tables()

        # Verify directory was created
        assert os.path.exists(new_output_dir)

        # Verify files were created
        files = os.listdir(new_output_dir)
        assert len([f for f in files if f.endswith(".csv")]) == 2
