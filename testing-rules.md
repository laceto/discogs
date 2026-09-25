# Testing Rules

- Tests live in `tests/`, mirroring the `discogs/` package layout as it grows.
- Run the suite with `pytest` from the repo root (config in `pyproject.toml [tool.pytest.ini_options]`, testpaths = `tests`).
- Every new module in `discogs/` gets a corresponding `tests/test_<module>.py`.
- Keep tests independent of network/external services (e.g. the Discogs API) — mock or fixture external calls rather than hitting them live.
