"""
Utility functions for YouTube URL handling and metadata extraction.

This module provides URL validation, metadata extraction using yt-dlp,
UID generation from URLs, duplicate checking, and filename sanitization.
"""

import json
import os
import re
import subprocess
from typing import Dict, Optional

import constants as cv
import song_metadata

# YouTube URL patterns
VIDEO_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})"
)
PLAYLIST_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=([a-zA-Z0-9_-]+)"
)


def is_video_url(url: str) -> bool:
    """Check if URL is a YouTube video URL

    Args:
        url: URL to check

    Returns:
        bool: True if valid YouTube video URL
    """
    return VIDEO_URL_PATTERN.search(url) is not None


def is_playlist_url(url: str) -> bool:
    """Check if URL is a YouTube playlist URL

    Args:
        url: URL to check

    Returns:
        bool: True if valid YouTube playlist URL
    """
    return PLAYLIST_URL_PATTERN.search(url) is not None


def detect_url_type(user_input: str) -> Optional[str]:
    """Detect if user input is a YouTube URL and what type

    Args:
        user_input: User input string

    Returns:
        str: "video" if video URL, "playlist" if playlist URL, None if not a URL
    """
    user_input = user_input.strip()

    if is_playlist_url(user_input):
        return "playlist"
    elif is_video_url(user_input):
        return "video"
    else:
        return None


def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube URL

    Args:
        url: YouTube video URL

    Returns:
        str: Video ID or None if not found
    """
    match = VIDEO_URL_PATTERN.search(url)
    return match.group(1) if match else None


def extract_playlist_id(url: str) -> Optional[str]:
    """Extract playlist ID from YouTube URL

    Args:
        url: YouTube playlist URL

    Returns:
        str: Playlist ID or None if not found
    """
    match = PLAYLIST_URL_PATTERN.search(url)
    return match.group(1) if match else None


def sanitize_filename(title: str) -> str:
    """Sanitize filename by removing/replacing illegal characters

    Removes or replaces: / \\ : * ? " < > |

    Args:
        title: Original filename/title

    Returns:
        str: Sanitized filename safe for filesystem
    """
    # Replace problematic characters with safe alternatives
    replacements = {
        "/": "-",
        "\\": "-",
        ":": "-",
        "*": "",
        "?": "",
        '"': "'",
        "<": "",
        ">": "",
        "|": "-",
    }

    sanitized = title
    for bad_char, replacement in replacements.items():
        sanitized = sanitized.replace(bad_char, replacement)

    # Remove multiple consecutive spaces or dashes
    sanitized = re.sub(r"[\s-]+", " ", sanitized).strip()

    # Limit length to avoid filesystem issues
    max_length = 200
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].strip()

    return sanitized


def get_video_metadata(url: str) -> Optional[Dict]:
    """Extract metadata from YouTube video without downloading

    Uses yt-dlp --dump-json to get video information.

    Args:
        url: YouTube video URL

    Returns:
        dict: Metadata dictionary with keys: title, duration, url, video_id
              Returns None if extraction fails
    """
    try:
        result = subprocess.run(
            [*cv.YT_DLP_CMD, "--dump-json", "--no-playlist", url],
            capture_output=True,
            text=True,
            check=True,
        )

        data = json.loads(result.stdout)

        return {
            "title": data.get("title", "Unknown"),
            "duration": data.get("duration", 0),  # in seconds
            "url": url,
            "video_id": data.get("id", ""),
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        print(f"Error extracting metadata from {url}: {e}")
        return None


def get_playlist_metadata(url: str) -> Optional[Dict]:
    """Extract playlist metadata including all video URLs

    Uses yt-dlp --dump-json to get playlist information.

    Args:
        url: YouTube playlist URL

    Returns:
        dict: Metadata dictionary with keys: title, video_urls
              Returns None if extraction fails
    """
    try:
        result = subprocess.run(
            [*cv.YT_DLP_CMD, "--dump-json", "--flat-playlist", url],
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse multiple JSON objects (one per line for each video)
        lines = result.stdout.strip().split("\n")
        videos = []
        playlist_title = None

        for line in lines:
            if not line.strip():
                continue
            data = json.loads(line)

            # First entry contains playlist info
            if playlist_title is None and "title" in data:
                playlist_title = data.get("playlist_title") or data.get("title")

            # Extract video URL
            if "id" in data:
                video_url = f"https://www.youtube.com/watch?v={data['id']}"
                videos.append(video_url)

        return {
            "title": playlist_title or "Unknown Playlist",
            "video_urls": videos,
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Error extracting playlist metadata from {url}: {e}")
        return None


def is_duplicate(url: str) -> bool:
    """Check if URL already exists in database

    Args:
        url: YouTube URL to check

    Returns:
        bool: True if URL already tracked in database
    """
    songs = song_metadata.get_all_songs()
    for song in songs:
        if song.get("url") == url:
            return True
    return False


def get_song_by_url(url: str) -> Optional[Dict]:
    """Get song from database by URL

    Args:
        url: YouTube URL

    Returns:
        dict: Song dictionary or None if not found
    """
    songs = song_metadata.get_all_songs()
    for song in songs:
        if song.get("url") == url:
            return song
    return None


def path_exists(file_path: str) -> bool:
    """Check if file path exists on filesystem

    Args:
        file_path: Path to check

    Returns:
        bool: True if path exists
    """
    return os.path.exists(file_path)
