# AGENTS.md

Guidance for AI coding agents working in this repository. Humans should read
[readme.md](readme.md) first; this file captures the conventions an agent needs
to make correct, idiomatic changes.

## What this project is

Spear is a single-user **CLI music library manager** written in Python. It plays
local audio via VLC, integrates with YouTube (download + metadata), and tracks
playlists and listen history in SQLite.

## Architecture (read before editing)

Modules live flat in the repo root and are organized into layers. **Dependencies
flow downward only** — an upper layer may import a lower one, never the reverse.

| Layer            | Modules                                                                 | Role |
|------------------|-------------------------------------------------------------------------|------|
| Foundation       | `constants`, `db_utils`                                                  | Config values & shared SQLite helpers |
| Config           | `reader`                                                                 | Reads `user_specs.yaml` |
| Pure logic       | `search`                                                                 | Fuzzy search, no I/O |
| Data/persistence | `song_metadata`, `listen_history`, `playlists`, `playback_timeline`, `export_to_csv` | Each owns one DB table; CRUD |
| YouTube          | `youtube_utils`, `youtube_downloader`, `youtube_integration`            | URL detection, download, DB/playlist orchestration |
| Playback         | `play_song`                                                             | VLC playback with keyboard controls |
| UI               | `cli_menu`                                                              | Interactive menu (widest fan-out) |
| Entry point      | `main`                                                                  | Bootstraps DBs, launches `cli_menu` |

When adding code, place it in the lowest layer that makes sense and respect the
downward-only import rule.

## Conventions

- **Database access**: always use the `get_connection()` context manager from
  `db_utils` (handles rollback + close). Generate IDs with `generate_uid()`
  (16-char alphanumeric, validated by `UID_PATTERN`). Do not open raw
  `sqlite3.connect` calls in feature modules.
- **Docstrings**: every public function has a docstring with `Args:` / `Returns:`
  sections (Google style). Match this format for new functions.
- **Type hints**: required on all function definitions (mypy runs with
  `disallow_untyped_defs = true`).
- **Pure logic stays pure**: `search` must remain free of I/O and DB calls.

## Commands

```bash
# Run the app
python main.py            # or run.bat (Windows) / run.sh — auto-creates .venv

# Install dev dependencies
pip install -r requirements-dev.txt

# Format & lint (run before finishing a change)
black .                   # line-length 88
isort .                   # black profile
flake8                    # config in .flake8
mypy .                    # strict-ish, config in pyproject.toml

# Tests
pytest                    # tests/ ; pythonpath="." set in pyproject.toml
```

## Testing notes

- Tests live in `tests/` and import modules by their flat name (e.g.
  `import playlists`), enabled by `pythonpath = ["."]` in `pyproject.toml`.
- When adding a feature to a data module, add a matching test file following the
  existing `tests/test_<module>.py` pattern.

## Do not touch / do not commit

- `user_specs.yaml` (user config — gitignored; `user_specs.example.yaml` is the template)
- `data/listen_history.db`, `data/exports/` (user data — gitignored)
- `_scratch/` (one-off migration scripts — gitignored)
- `.venv/`, `build/`, `__pycache__/`, cache folders

## Definition of done for a change

1. New/changed functions have type hints and Google-style docstrings.
2. `black`, `isort`, `flake8`, and `mypy` all pass.
3. Relevant tests added/updated and `pytest` passes.
4. Import direction still flows downward through the layers.
