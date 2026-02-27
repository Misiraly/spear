import os

USER_SPECS_DATA = "user_specs.yaml"
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_PROJECT_DIR, "data", "listen_history.db")

SCREEN_WIDTH = 80
DEFAULT_RANDOM_OFFER_COUNT = 5
DEFAULT_SEARCH_RESULTS = 10
YT_DLP_CMD = ["yt-dlp", "--config-location", os.path.join(_PROJECT_DIR, "yt-dlp.conf")]
