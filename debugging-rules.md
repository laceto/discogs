# Debugging Rules

- Confirm the venv is active (`venv\Scripts\activate` on Windows) before diagnosing import or dependency errors — most "module not found" issues are an inactive/missing venv.
- Reproduce with `pytest -k <name> -v --tb=short` for a failing test rather than re-running the whole suite.
- If behavior looks wrong with no test covering it yet, write the failing test first, then fix.
