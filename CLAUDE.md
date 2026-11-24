# PRINTYZ Clicker Studio — guidance for Claude Code

- Answer the user in **Hebrew**. Code, identifiers and commit messages in English.
- Spec: `docs/SPEC.md` (the user's full requirements, Hebrew; section numbers 1–55 are referenced in code/docs).
  Architecture + status per spec section: `docs/ARCHITECTURE.md`.
- Run tests: `.venv/bin/python -m pytest -q`. On the user's Windows machine the venv lives outside OneDrive:
  `$env:LOCALAPPDATA\PRINTYZ\ClickerV2\.venv` (Python 3.13; 3.14 unsupported by OCP).
- Build a sample: `python -m printyz_clicker build --text "שלום" --out out`.

## Non-negotiable rules
1. One data model (`model/project.py`) and one layout engine (`layout/engine.py`). Preview and
   export consume the same `BuildResult`; never compute positions/counts twice.
2. A feature is done only when it changes the REAL geometry and a test proves it
   (e.g. grooved body has less volume than smooth). Never fake a feature in the preview.
3. Mechanical values live in `config/mechanical.py` (developer-only). Values marked VERIFY
   are unconfirmed; never change MEASURED values (e.g. plate hole 13.90) without a physical test.
4. Never truncate a name silently; max 10 keys is reported as an error.
5. Every printable part must pass `validation/checks.py` (valid solid, watertight mesh).
6. Look at the rendered PNGs (`render/preview.py`) after geometry changes.
