"""
Spear - Personal Music Library Manager

Main entry point for the application. Launches unified interactive menu.
"""

import cli_menu
import listen_history
import playback_timeline
import playlists
import reader
import song_metadata

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
