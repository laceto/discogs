# Architecture

A Discogs data-collection layer built on top of `python3-discogs-client`. It authenticates once,
pulls full release detail as the atomic unit, composes that into breadth crawls (label/artist/master
→ many releases), and persists every collected entity as flat JSON under `data/`.

## Module layout

```
discogs/
  client.py                  Auth: builds the discogs_client.Client
  ratelimit.py               ThrottledFetcher: paces requests, pauses when budget low, retries 5xx
  storage.py                 Persistence: save_json / load_json / list_ids
  collectors/
    _pagination.py           Shared pagination + rate-limit backoff helper (no Discogs-entity knowledge)
    release.py                collect_release / collect_marketplace_stats / collect_price_suggestions
    label.py                   collect_label_releases   (label -> releases)
    artist.py                  collect_artist_releases  (artist -> releases, skipping mixed-in masters)
    master.py                  collect_master_versions  (master -> version releases)
  agent/
    tools.py                 LangChain tools wrapping the collectors + RequestBudget
    agent.py                 build_agent(): Deep Agents graph, memory, sandbox, checkpointer
    session.py               run_turn(): one chat turn incl. human-approval pauses
scripts/chat.py              CLI entry point for the agent
```

### `discogs/client.py`

`get_client() -> discogs_client.Client` reads `DISCOGS_USER_TOKEN` from the environment (see
`.env.example`) and returns an authenticated client. Raises `RuntimeError` with a clear message if
the token is unset — every other module in this layer takes a `client` object as a parameter rather
than constructing its own, so auth is wired up exactly once, at the call site (a script or a test
fixture).

### `discogs/storage.py`

`save_json(entity_type, id, record, base_dir=None) -> Path` writes `record` to
`<base_dir>/<entity_type>/<id>.json` (default `base_dir` is `data/` at the repo root), creating
parent directories as needed. `load_json(entity_type, id, base_dir=None) -> dict | None` reads a
record back, or returns `None` if it doesn't exist. `entity_type` is a plain string
(`"release"`, `"label"`, ...) — no schema migration needed to add a new one. See `docs/schemas.md`
for the storage-shape decision and the release-record field layout.

### `discogs/collectors/release.py` — the atomic unit

`collect_release(client, release_id) -> dict` fetches one `client.release(release_id)` and
normalizes it into the record shape documented in `docs/schemas.md`: base fields (title, year,
genres, styles, country, formats, notes, images, url), `tracklist`, `artists` (with `join`
keyword), `credits` (extraartists), `labels`, `community` (defaulting to zero/empty values rather
than erroring when a release has no community data), and `master_id` (`None` for standalone
releases). It does **not** call `storage.save_json` itself and does **not** include marketplace or
price data — those are separate, more volatile API calls, exposed as their own functions:

- `collect_marketplace_stats(client, release_id) -> dict` — `{num_for_sale, blocked_from_sale,
  lowest_price}`.
- `collect_price_suggestions(client, release_id) -> dict` — suggested price per condition grade
  (`"Poor (P)"` .. `"Mint (M)"`); requires an authenticated client (401s otherwise).

Every other collector in this package calls `collect_release` and persists the result itself —
`collect_release` stays a pure fetch-and-normalize function with no I/O side effect, so it's
reusable both for a single-release lookup and inside a multi-thousand-release breadth crawl.

### `discogs/collectors/_pagination.py` — shared crawl helper

`iter_paginated(paginated, *, start_page=1, on_page_done=None, max_retries=5, base_delay=1.0,
sleep=time.sleep) -> Iterator[Any]` walks any object exposing `.pages` / `.page(index)` (the shape
`discogs_client`'s `BasePaginatedResponse` gives label `.releases`, artist `.releases`, and master
`.versions`), yielding items one at a time. It knows nothing about releases, artists, or any other
Discogs entity — it only handles three generic concerns:

- **Resuming**: `start_page` lets a caller skip pages already fully consumed in a prior run.
- **Checkpointing**: `on_page_done(page_index)` fires once a page is fully yielded, so a caller can
  persist `page_index` and resume from `page_index + 1` after an interrupted crawl.
- **Rate-limit backoff**: a `429` `HTTPError` is retried up to `max_retries` times with exponential
  backoff (`base_delay * 2**attempt`); any other `DiscogsAPIError` propagates immediately.

### Breadth collectors — `label.py`, `artist.py`, `master.py`

Each breadth collector follows the same composition: look up the parent entity, walk its paginated
child collection via `iter_paginated`, and for every release id found call `collect_release` (A3.1)
then persist the record with `storage.save_json("release", release_id, record)`.

- `collect_label_releases(client, label_id) -> Iterator[int]` paginates `label.releases`.
- `collect_artist_profile(client, artist_id) -> dict` fetches the artist's own profile detail
  (name, real_name, profile bio, images, url, urls, name_variations, aliases and groups each
  normalized to `[{id, name}]`) — mirrors `collect_label`'s contract: a pure fetch-and-normalize
  function with no persistence side effect and no release walking.
- `collect_artist_releases(client, artist_id) -> Iterator[int]` paginates `artist.releases`, which
  is a *mixed* list of `Release` and `Master` entries (Discogs surfaces an artist's masters
  alongside releases in that feed); non-`Release` entries are skipped without erroring — expanding
  a master into its versions is `collect_master_versions`'s job, not this collector's.
- `collect_master_versions(client, master_id) -> list[int]` paginates `master.versions`.

Each yields (or returns, for `collect_master_versions`) the release ids it processed, so a caller
can stream progress, stop early, or just count how many releases a crawl touched.

## Data flow

```
scripts / caller
      |
      v
discogs.client.get_client()  ----------------------------+
      |                                                   |
      v                                                   |
breadth collector (label.py / artist.py / master.py)      |
  paginates via collectors._pagination.iter_paginated     |
      |                                                    (client passed through
      v                                                     every layer — built once)
collectors.release.collect_release(client, release_id) ---+
      |
      v
storage.save_json("release", release_id, record)
      |
      v
data/release/<id>.json
```

`collect_marketplace_stats` and `collect_price_suggestions` sit outside this default flow — they're
called explicitly by a caller that wants that (more volatile, auth-required) data too, as
`scripts/discogs_release_reader.py --full` does: it collects base detail, layers in marketplace
stats and price suggestions, and saves the combined record.

## Design invariants

- **`collect_release` is the atomic unit.** Every breadth collector composes from it and shares its
  normalization logic instead of re-implementing field extraction.
- **Collectors don't own auth.** `client` is always a parameter, built once via
  `discogs.client.get_client()` at the call site (script, notebook, or test fixture).
- **Collectors don't own persistence policy beyond calling `storage.save_json`.** Storage shape
  (flat JSON under `data/<entity_type>/<id>.json`) is centralized in `storage.py`; collectors never
  construct paths themselves.
- **`_pagination.py` is entity-agnostic.** It only depends on the `.pages` / `.page(index)`
  protocol, so it works unchanged for label, artist, and master feeds (and any future paginated
  Discogs collection) without modification.
- **Missing data degrades to zero/empty, not an error.** No community data, no master, no
  marketplace snapshot, no price suggestion for a grade — each is represented as a documented
  zero/empty/`None` value (see `docs/schemas.md`), since real Discogs releases routinely lack one
  or more of these.

## Agent (`discogs/agent/`)

A LangChain Deep Agents agent that drives the collectors through tools. Run it with
`python scripts/chat.py` (needs `OPENAI_API_KEY` and `DISCOGS_USER_TOKEN`; model via
`DISCOGS_AGENT_MODEL`, default `openai:gpt-5`).

- **Tools** (`tools.py`): one per collector function plus `remaining_budget`, `list_saved`,
  `load_saved`. API tools return short summaries; the full record is saved by `storage`.
- **Request budget**: every API tool charges a shared `RequestBudget` (default 100 per run,
  `DISCOGS_AGENT_BUDGET`) and errors once it is spent. Crawls are capped by `max_items` and the
  remaining budget. Per-minute pacing is separate and lives in `ratelimit.py` (about 54 requests/min).
- **Memory**: `docs/architecture.md` and `docs/schemas.md` are loaded read-only into the system
  prompt; `data/_agent/notes.md` is the agent's writable notes file. Conversations persist in a
  SQLite checkpointer (`data/_agent/checkpoints.sqlite`) keyed by `--thread`.
- **Sandbox**: the agent can read `docs/` and `data/`, write only `data/_agent/`, and is denied
  everything else. Dotfiles need explicit deny patterns because `**` does not match them; without
  them `.env` (API keys) would be readable. Covered by `tests/test_agent_agent.py`.
- **Human approval**: `crawl_*` and `search_releases` pause for a yes/no before running.
