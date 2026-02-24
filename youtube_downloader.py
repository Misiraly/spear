"""
YouTube audio downloader using yt-dlp.

This module handles downloading audio from YouTube videos and playlists,
with duplicate checking, filename sanitization, and metadata tracking.
"""

import json
import os
import subprocess
from typing import Optional, Dict, List

import youtube_utils
import reader
import song_metadata


def _get_file_duration(file_path: str) -> Optional[int]:
    """Get actual duration of audio file in seconds using yt-dlp
    
    Args:
        file_path: Path to audio file
        
    Returns:
        int: Duration in seconds, or None if failed
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", file_path],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        return int(data.get("duration", 0))
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError):
        return None


def download_video(url: str, output_path: Optional[str] = None) -> Optional[Dict]:
    """Download audio from YouTube video as .ogg format
    
    Args:
        url: YouTube video URL
        output_path: Optional custom output directory (defaults to library path)
        
    Returns:
        dict: Downloaded file info with keys: path, title, duration, url, uid
              Returns None if download fails
    """
    # Get metadata first
    metadata = youtube_utils.get_video_metadata(url)
    if not metadata:
        print(f"Failed to extract metadata from {url}")
        return None
    
    # Sanitize filename
    safe_title = youtube_utils.sanitize_filename(metadata["title"])
    
    # Determine output directory
    if output_path is None:
        output_path = reader.get_music_library_path()
    
    # Ensure output directory exists
    os.makedirs(output_path, exist_ok=True)
    
    # Build output filename
    output_template = os.path.join(output_path, f"{safe_title}.%(ext)s")
    
    # Download with yt-dlp
    try:
        subprocess.run(
            [
                "yt-dlp",
                "-x",  # Extract audio
                "--audio-format", "vorbis",  # Convert to .ogg
                "--no-playlist",  # Don't download playlist if URL is part of one
                "-o", output_template,
                url,
            ],
            check=True,
        )
        
        # Construct expected file path
        file_path = os.path.join(output_path, f"{safe_title}.ogg")
        
        # Verify file was created
        if not os.path.exists(file_path):
            print(f"Download succeeded but file not found: {file_path}")
            return None
        
        # Get actual duration from downloaded file
        actual_duration = _get_file_duration(file_path)
        if actual_duration is None:
            # Fallback to YouTube metadata if we can't read file
            actual_duration = metadata["duration"]
        
        # Generate UID from URL
        from db_utils import generate_uid_from_url
        uid = generate_uid_from_url(url)
        
        return {
            "path": file_path,
            "title": metadata["title"],
            "duration": actual_duration,
            "url": url,
            "uid": uid,
        }
        
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Error downloading {url}: {e}")
        return None


def download_playlist(url: str, output_path: Optional[str] = None) -> Optional[Dict]:
    """Download all videos from YouTube playlist
    
    Downloads sequentially and returns metadata for each downloaded video.
    
    Args:
        url: YouTube playlist URL
        output_path: Optional custom output directory (defaults to library path)
        
    Returns:
        dict: Playlist info with keys: title, downloaded_songs (list of song dicts)
              Returns None if playlist extraction fails
    """
    # Get playlist metadata
    playlist_metadata = youtube_utils.get_playlist_metadata(url)
    if not playlist_metadata:
        print(f"Failed to extract playlist metadata from {url}")
        return None
    
    playlist_title = playlist_metadata["title"]
    video_urls = playlist_metadata["video_urls"]
    
    print(f"\nDownloading playlist: {playlist_title}")
    print(f"Found {len(video_urls)} videos\n")
    
    downloaded_songs = []
    
    for i, video_url in enumerate(video_urls, 1):
        print(f"[{i}/{len(video_urls)}] Downloading {video_url}...")
        
        # Check for duplicates before downloading
        if youtube_utils.is_duplicate(video_url):
            print(f"  ⚠ URL already in database, skipping")
            continue
        
        # Download the video
        song_info = download_video(video_url, output_path)
        
        if song_info:
            # Check if file already exists
            if youtube_utils.path_exists(song_info["path"]):
                print(f"  ✓ Downloaded: {song_info['title']}")
                downloaded_songs.append(song_info)
            else:
                print(f"  ✗ Download failed (file not found)")
        else:
            print(f"  ✗ Download failed")
    
    print(f"\nPlaylist download complete: {len(downloaded_songs)}/{len(video_urls)} songs downloaded")
    
    return {
        "title": playlist_title,
        "downloaded_songs": downloaded_songs,
    }


def check_duplicate_before_download(url: str) -> Optional[str]:
    """Check for duplicates and return appropriate action
    
    Args:
        url: YouTube URL to check
        
    Returns:
        str: Action to take - "skip_url", "skip_path", "download", or "update"
             None if no duplicate
    """
    # Check if URL already in database
    existing_song = youtube_utils.get_song_by_url(url)
    
    if existing_song:
        # URL is tracked in database
        stored_path = existing_song.get("path")
        full_path = song_metadata.resolve_path(stored_path) if stored_path else None
        if full_path and os.path.exists(full_path):
            # Path exists on disk
            if existing_song.get("title") and existing_song.get("duration"):
                # All data present
                return "skip_url"
            else:
                # Missing data, should update
                return "update"
        else:
            # Path missing or doesn't exist, should download
            return "download"
    
    # Not in database, check if path would collide
    metadata = youtube_utils.get_video_metadata(url)
    if metadata:
        safe_title = youtube_utils.sanitize_filename(metadata["title"])
        library_path = reader.get_music_library_path()
        expected_path = os.path.join(library_path, f"{safe_title}.ogg")

        if os.path.exists(expected_path):
            return "skip_path"
    
    return "download"
