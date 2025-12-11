"""Export database tables to CSV files"""

import csv
import os
import sqlite3
from datetime import datetime

import constants as cv

DB_PATH = os.path.join(os.path.dirname(__file__), cv.DB_PATH)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "exports")


def export_table_to_csv(table_name, output_path):
    """Export a database table to CSV

    Args:
        table_name: Name of the table to export
        output_path: Path where CSV file should be saved
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all rows from the table
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    # Get column names
    column_names = [description[0] for description in cursor.description]

    # Write to CSV
    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(column_names)
        writer.writerows(rows)

    conn.close()
    print(f"Exported {len(rows)} rows from {table_name} to {output_path}")


def export_all_tables():
    """Export all tables to CSV files with timestamp"""
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Export listen_history table
    listen_history_path = os.path.join(OUTPUT_DIR, f"listen_history_{timestamp}.csv")
    export_table_to_csv("listen_history", listen_history_path)

    # Export songs table
    songs_path = os.path.join(OUTPUT_DIR, f"songs_{timestamp}.csv")
    export_table_to_csv("songs", songs_path)

    print(f"\nExport complete! Files saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    export_all_tables()
