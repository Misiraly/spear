A custom agent instructions file lives at [../AGENTS.md](../AGENTS.md). Read it
before making changes — it is the source of truth for this repository's
architecture, conventions, commands, and definition of done.

Key reminders (see AGENTS.md for the full detail):

- Modules are flat in the repo root and layered; **imports flow downward only**
  (UI → playback/YouTube → data → pure logic → config → foundation).
- Use `db_utils.get_connection()` for all SQLite access and `generate_uid()` for
  IDs. Never open raw `sqlite3.connect` in feature modules.
- All functions need type hints (mypy `disallow_untyped_defs`) and Google-style
  docstrings (`Args:` / `Returns:`).
- `search.py` is pure logic — no I/O or DB calls.
- Before finishing: run `black .`, `isort .`, `flake8`, `mypy .`, and `pytest`
  (or the VS Code tasks: **format**, **lint**, **typecheck**, **test**, **check**).
- Never commit `user_specs.yaml`, `data/` databases, or `_scratch/`.
