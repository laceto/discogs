# Discogs — Agent Router

A Python library project (fresh scaffold, no application code yet). This file routes you to the right context — don't load everything, load what your task needs.

## Identify Your Task

**CODING (Python)** — Adding a module to `discogs/`, writing a script, fixing a bug
→ READ: `coding-rules.md`
→ ALSO READ: `docs/architecture.md` for data flow context

**DATA COLLECTION** — Adding/changing a Discogs collector (`discogs/collectors/`), the client, or
the storage/schema shape of a persisted entity
→ READ: `coding-rules.md`
→ ALSO READ: `docs/schemas.md` for the persisted storage shape (where entities land under `data/`,
  the release-record field layout) and `docs/architecture.md` for how the collectors compose

**AGENT** — Changing the Deep Agents agent, its tools, memory, sandbox permissions or rate limiting
(`discogs/agent/`, `discogs/ratelimit.py`, `scripts/chat.py`)
→ READ: `coding-rules.md`
→ ALSO READ: `docs/architecture.md` (the Agent section)

**TESTING** — Writing new tests or expanding coverage
→ READ: `testing-rules.md`

**DEBUGGING** — A script errored, a test failed, or output looks wrong
→ READ: `debugging-rules.md`

## Repo Layout

```
discogs/        Python package — application code
scripts/        Utility / CLI scripts (not part of the package)
data/           Data files (gitignored by default)
tests/          pytest test suite, mirrors discogs/
venv/           Virtual environment (gitignored)
docs/           Reference docs (facts about the project)
```

Root holds only: config files (`pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`), `README.md`, `CLAUDE.md`, and the rule files (`coding-rules.md`, `testing-rules.md`, `debugging-rules.md`).

## Reference Docs (load only what your task requires)

| File | Contents |
|---|---|
| `docs/architecture.md` | Data flow, module responsibilities, design invariants |
| `docs/schemas.md` | Storage shape decision + the persisted release-record field layout |

## Instructions

1. Identify your task above
2. Load the rule file for that task
3. Load only the reference docs the task actually requires
4. Do not load all docs — load what you need
5. If unsure which category fits, ask — do not guess
