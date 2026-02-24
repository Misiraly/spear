import os

import yaml

import constants as cv

USER_SPECS_DATA = cv.USER_SPECS_DATA


def ensure_user_specs():
    """Ensure user_specs.yaml exists. Prompt to create it on first run."""
    if os.path.isfile(USER_SPECS_DATA):
        return

    print("Welcome to Spear! It looks like this is your first run.")
    print("We need to know where your music library lives.")
    print()
    library = input("Enter the full path to your music library: ").strip()

    if not library:
        print("No path provided — you can edit user_specs.yaml later.")
        library = ""

    specs = {"library": library}

    with open(USER_SPECS_DATA, "w", encoding="utf-8") as f:
        yaml.dump(specs, f, default_flow_style=False, allow_unicode=True)

    print(f"Saved to {USER_SPECS_DATA}")
    print()


def load_user_specs():
    with open(USER_SPECS_DATA, "r") as file:
        user_specs = yaml.safe_load(file)
    return user_specs


def get_music_library_path():
    user_specs = load_user_specs()
    return user_specs.get("library", "")
