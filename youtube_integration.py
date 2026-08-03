"""
YouTube integration module for orchestrating download and database operations.

This module provides high-level functions to download YouTube videos/playlists
and automatically add them to the song database and playlists.
"""

import os
from typing import List, Optional

import playlists
import song_metadata
import youtube_downloader
import youtube_utils
from db_utils import generate_uid_from_url


def download_and_add_video(url: str) -> Optional[str]:
    """Download YouTube video and add to database

    Handles duplicate checking:
    - URL already in DB with file → skip, warn
    - Path exists on disk → skip, warn
    - URL in DB but missing data → download and update
    - New URL → download and add

    Args:
        url: YouTube video URL

    Returns:
        str: Song UID if successful, None otherwise
    """
    # Validate URL
    if not youtube_utils.is_video_url(url):
        print(f"Error: Invalid YouTube video URL: {url}")
        return None

    # Check for duplicates
    action = youtube_downloader.check_duplicate_before_download(url)

    if action == "skip_url":
        print(f"⚠ URL already in database with existing file, skipping: {url}")
        existing_song = song_metadata.get_song_by_url(url)
        return existing_song["uid"] if existing_song else None

    elif action == "skip_path":
        print(f"⚠ File already exists on disk, skipping download: {url}")
        return None

    elif action == "update":
        print("📝 URL tracked but missing data, downloading to update...")
        existing_song = song_metadata.get_song_by_url(url)
        if not existing_song:
            return None
        uid: str = existing_song["uid"]

        # Download
        download_info = youtube_downloader.download_video(url)
        if not download_info:
            print("✗ Download failed")
            return None

        # Update database
        song_metadata.add_song(
            uid=uid,
            title=download_info["title"],
            path=download_info["path"],
            url=url,
            duration=download_info["duration"],
        )

        print(f"✓ Updated: {download_info['title']}")
        return uid

    else:  # action == "download"
        # Generate UID
        uid = generate_uid_from_url(url)

        # Download
        print(f"📥 Downloading: {url}")
        download_info = youtube_downloader.download_video(url)

        if not download_info:
            print("✗ Download failed")
            return None

        # Add to database
        song_metadata.add_song(
            uid=uid,
            title=download_info["title"],
            path=download_info["path"],
            url=url,
            duration=download_info["duration"],
        )

        print(f"✓ Added to library: {download_info['title']}")
        return uid


def download_and_add_playlist(url: str) -> Optional[str]:
    """Download YouTube playlist and create corresponding playlist in database

    Downloads all videos sequentially, creates a playlist using the YouTube
    playlist title, and adds all successfully downloaded songs to the playlist.

    Args:
        url: YouTube playlist URL

    Returns:
        str: Playlist UID if successful, None otherwise
    """
    # Validate URL
    if not youtube_utils.is_playlist_url(url):
        print(f"Error: Invalid YouTube playlist URL: {url}")
        return None

    # Download playlist
    playlist_info = youtube_downloader.download_playlist(url)

    if not playlist_info or not playlist_info["downloaded_songs"]:
        print("✗ Playlist download failed or no songs downloaded")
        return None

    playlist_title = playlist_info["title"]
    downloaded_songs = playlist_info["downloaded_songs"]

    # Create playlist in database
    try:
        # Check if playlist name already exists
        existing_playlists = playlists.get_all_playlists()
        playlist_name = playlist_title
        counter = 1

        while any(p["name"] == playlist_name for p in existing_playlists):
            playlist_name = f"{playlist_title} ({counter})"
            counter += 1

        # Create playlist
        playlist_uid: str = playlists.create_playlist(
            name=playlist_name, description=f"Downloaded from YouTube: {url}"
        )

        print(f"\n✓ Created playlist: {playlist_name}")

        # Add songs to database and playlist
        song_uids = []
        for song_info in downloaded_songs:
            # Add to song database
            song_metadata.add_song(
                uid=song_info["uid"],
                title=song_info["title"],
                path=song_info["path"],
                url=song_info["url"],
                duration=song_info["duration"],
            )
            song_uids.append(song_info["uid"])

        # Add all songs to playlist at once
        if song_uids:
            playlists.add_multiple_to_playlist(playlist_uid, song_uids)
            print(f"✓ Added {len(song_uids)} songs to playlist")

        return playlist_uid

    except Exception as e:
        print(f"Error creating playlist: {e}")
        return None


def add_existing_url_to_playlist(url: str, playlist_uid: str) -> bool:
    """Add an already-downloaded YouTube video to a playlist

    Args:
        url: YouTube video URL
        playlist_uid: Target playlist UID

    Returns:
        bool: True if successful
    """
    # Check if URL exists in database
    existing_song = song_metadata.get_song_by_url(url)

    if not existing_song:
        print(f"Error: URL not found in database: {url}")
        return False

    song_uid = existing_song["uid"]

    # Add to playlist
    try:
        playlists.add_to_playlist(playlist_uid, song_uid)
        print(f"✓ Added '{existing_song['title']}' to playlist")
        return True
    except Exception as e:
        print(f"Error adding to playlist: {e}")
        return False


def batch_download_videos(urls: List[str]) -> List[str]:
    """Download multiple YouTube videos

    Args:
        urls: List of YouTube video URLs

    Returns:
        list: List of successfully added song UIDs
    """
    successful_uids = []

    print(f"\nBatch downloading {len(urls)} videos...\n")

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] Processing: {url}")
        uid = download_and_add_video(url)
        if uid:
            successful_uids.append(uid)
        print()

    print(f"Batch download complete: {len(successful_uids)}/{len(urls)} successful")
    return successful_uids


def redownload_song(uid: str) -> bool:
    """Re-download an existing song to update file and duration

    Preserves UID, title, add_date, and listen history.
    Updates file, duration, and path.

    Args:
        uid: Song UID to re-download

    Returns:
        bool: True if successful
    """
    # Get existing song
    existing_song = song_metadata.get_song(uid)

    if not existing_song:
        print(f"Error: Song not found with UID {uid}")
        return False

    url = existing_song.get("url")
    if not url:
        print(f"Error: No URL associated with song '{existing_song['title']}'")
        return False

    print(f"\nRe-downloading: {existing_song['title']}")

    # Delete old file if it exists
    old_path = existing_song.get("path")
    if old_path:
        full_old_path = song_metadata.resolve_path(old_path)
        if full_old_path and os.path.exists(full_old_path):
            try:
                os.remove(full_old_path)
                print("✓ Deleted old file")
            except OSError as e:
                print(f"⚠ Could not delete old file: {e}")

    # Download fresh
    download_info = youtube_downloader.download_video(url)

    if not download_info:
        print("\n✗ Re-download failed")
        return False

    # Update database (preserve title and add_date from original)
    song_metadata.add_song(
        uid=uid,
        title=existing_song["title"],  # Keep original title
        path=download_info["path"],
        url=url,
        duration=download_info["duration"],
        add_date=existing_song["add_date"],  # Preserve original add date
    )

    print("\n✓ Re-download complete")
    old_duration = existing_song.get("duration", 0)
    new_duration = download_info["duration"]
    print(f"Duration updated: {old_duration}s → {new_duration}s")

    return True
