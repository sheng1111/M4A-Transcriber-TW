# Coding Guidelines for Codex

- Do not modify `requirements.txt`.
- After modifying any Python files, run `python -m py_compile app.py gui_app.py` to ensure there are no syntax errors.
- Commit only if the compile step succeeds.
- Run `pytest -q` if tests are present and ensure they pass before committing.
