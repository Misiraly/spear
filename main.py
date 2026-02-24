"""
Spear - Personal Music Library Manager

Main entry point for the application. Launches unified interactive menu.
"""

import cli_menu
import reader
import song_metadata
import playlists
import playback_timeline
import listen_history


class Cabinet:
    def __init__(self):
        self.song = {}
        self.timeline = []
        self.pos = 0


if __name__ == "__main__":
    # Ensure user_specs.yaml exists (prompts on first run)
    reader.ensure_user_specs()

    # Initialize databases
    song_metadata.init_database()
    playlists.init_database()
    playback_timeline.init_database()
    listen_history.init_database()
    
    # Launch interactive menu
    cli_menu.display_menu()
