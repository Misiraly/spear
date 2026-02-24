# Spear — Personal Music Library Manager

A CLI music player and library manager with YouTube integration, playlist
management, listen history tracking, and VLC-based playback.

## Architecture

```
Layer              Module(s)                          Role
─────────────────  ─────────────────────────────────  ──────────────────────────────────────
Foundation         constants, db_utils                Config values & shared DB helpers
Config             reader                             Reads user_specs.yaml (library path…)
Pure logic         search                             Fuzzy search algorithm (no I/O)
Data / persistence song_metadata, listen_history,     Each owns a DB table; CRUD operations
                   playlists, playback_timeline,
                   export_to_csv
YouTube            youtube_utils,                     URL detection, downloading, and
                   youtube_downloader,                orchestrating DB + playlist updates
                   youtube_integration
Playback           play_song                          VLC playback with keyboard controls
UI                 cli_menu                           Interactive menu (widest fan-out)
Entry point        main                               Bootstraps DBs & launches cli_menu
```

Dependencies flow **downward only** — upper layers import lower ones, never
the reverse.

## Quick start

```
run.bat
```

On first run, `run.bat` automatically creates a `.venv` virtual environment
and installs dependencies from `requirements.txt`. To use an existing venv
instead, set the `SPEAR_VENV` environment variable to its path.

Or manually:

```
python main.py
```

## Development

Install dev dependencies:

```
pip install -r requirements-dev.txt
```

### Tools and config

| Tool | Config location | Purpose |
|------|----------------|---------|
| black | `pyproject.toml` `[tool.black]` | Code formatting |
| isort | `pyproject.toml` `[tool.isort]` | Import sorting |
| flake8 | `.flake8` | Linting |
| mypy | `pyproject.toml` `[tool.mypy]` | Static type checking |
| pytest | `pyproject.toml` `[tool.pytest.ini_options]` | Tests |
| vulture | — | Dead code detection |
| radon | — | Complexity metrics |

### Duplicate-code detection (jscpd)

[jscpd](https://github.com/kucherenko/jscpd) is a Node.js tool used for
copy-paste detection. It is **not** a Python package and therefore not listed
in `requirements-dev.txt`. Install it separately if needed:

```
npm install -g jscpd
```

Run against the project:

```
jscpd . --ignore "**/__pycache__/**,**/.venv/**,**/build/**"
```
