import yaml
import constants as cv


USER_SPECS_DATA = cv.USER_SPECS_DATA


def load_user_specs():
    with open(USER_SPECS_DATA, 'r') as file:
        user_specs = yaml.safe_load(file)
    return user_specs


def get_music_library_path():
    user_specs = load_user_specs()
    return user_specs.get('library', '')