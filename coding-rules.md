# Coding Rules (Python)

- Package code lives in `discogs/`. One-off or CLI scripts live in `scripts/`, not inside the package.
- Import the package as `discogs`, not by relative path tricks — run scripts from the repo root with the venv active.
- Runtime dependencies go in `requirements.txt` and mirrored in `pyproject.toml [project.dependencies]`; dev-only tools (pytest, mypy, ruff) go in `[project.optional-dependencies].dev`.
- Format/lint with `ruff` (config in `pyproject.toml`, line-length 100). Type-check with `mypy --strict`.
- No secrets in code — read config from `.env` (see `.env.example`), never commit `.env`.
- Don't add abstractions, config layers, or error handling for cases that can't happen yet — this project is a fresh scaffold; build up structure as real modules land, not ahead of them.
