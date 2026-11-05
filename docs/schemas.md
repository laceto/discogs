# Schemas

## Storage decision (A2.1)

Collected data is persisted as **flat JSON, one file per entity, under
`data/<entity_type>/<id>.json`** (relative to the repo root). For example, a release with id
`2303570` is written to `data/release/2303570.json`.

Rationale:

- Matches the existing `data/` convention already present in the repo (gitignored, per-entity
  files) — no new convention to learn.
- No database dependency for this stage of the project. The `discogs/collectors/` modules
  produce plain dicts; a flat JSON file is the simplest thing that can store one without adding
  a DB layer, migrations, or an ORM before there's a real need for querying across entities.
- `entity_type` is a plain string (`"release"`, `"artist"`, `"label"`, `"master"`, ...) so new
  entity types need no schema change — just a new subdirectory, created on demand.
- One file per entity keeps writes independent (no partial-file corruption across unrelated
  entities) and makes it trivial to inspect, diff, or re-fetch a single record by id.

If a query layer is needed later (e.g. "every release a given producer mastered"), it can be
built by reading these JSON files into a database or dataframe — the flat-file layer doesn't
need to anticipate that now.

## Release record shape (A2.2)

A release record, as produced by `discogs/collectors/release.py` (`collect_release`) and stored
at `data/release/<id>.json`, is a dict with the following top-level fields:

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Discogs release id. |
| `title` | `str` | Release title. |
| `year` | `int \| None` | Release year, if known. |
| `genres` | `list[str]` | Top-level genre tags (e.g. `["Electronic"]`). |
| `styles` | `list[str]` | Finer-grained style tags (e.g. `["Techno", "Deep House"]`). |
| `country` | `str \| None` | Country of release/pressing. |
| `formats` | `list[dict]` | Physical/digital format info (e.g. `[{"name": "Vinyl", "qty": "2", "descriptions": ["12\"", "33 ⅓ RPM"]}]`). |
| `tracklist` | `list[dict]` | Ordered tracks, each `{position, title, duration}`. |
| `artists` | `list[dict]` | Main release artists, normalized to `[{id, name, role, join}]` — `join` carries the keyword ("feat", "vs", ",") linking this artist to the next one in the list. |
| `credits` | `list[dict]` | Extra artist credits (`extraartists`: producer, mixed-by, mastered-by, remix, engineer, etc.), normalized to `[{id, name, role}]`. |
| `labels` | `list[dict]` | Labels this release is on, `[{name, catno}]`. |
| `community` | `dict` | Community reception: `{want, have, rating_avg, rating_count, submitter, contributors}`. Absent/zero data (obscure releases) is represented as zero/empty values, never omitted or treated as an error. |
| `master_id` | `int \| None` | Id of the master release this belongs to, or `None` for standalone releases with no master. |
| `marketplace_stats` | `dict` | Live marketplace snapshot: `{num_for_sale, blocked_from_sale, lowest_price}`. Collected separately (own API call) since it's volatile. |
| `price_suggestions` | `dict` | Suggested price per condition grade, keyed `"Poor"`..`"Mint"` (e.g. `{"Mint (M)": 12.5, ...}`). Requires an authenticated client; collected separately from the base fields. |

Notes:

- `marketplace_stats` and `price_suggestions` are populated by their own collector functions
  (`collect_marketplace_stats`, `collect_price_suggestions`) rather than `collect_release`
  itself, since they're separate, more volatile API calls — a caller may choose to skip them.
- Multi-artist releases always represent `artists`/`credits` as a list, even for a single
  artist, so callers never have to special-case "one artist vs. many."

## Artist profile record shape (A5.1)

A profile record, as produced by `discogs/collectors/artist.py` (`collect_artist_profile`), is a
dict with the following top-level fields:

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Discogs artist id. |
| `name` | `str \| None` | Display name. |
| `real_name` | `str \| None` | Artist's real name, if known. |
| `profile` | `str \| None` | Free-text bio/profile description. |
| `images` | `list[dict]` | Artist images, as returned by the API. |
| `url` | `str \| None` | Discogs page URL for this artist. |
| `urls` | `list[str]` | External site links (homepage, Bandcamp, social profiles, ...). |
| `name_variations` | `list[str]` | Alternate spellings/renderings of the artist's name. |
| `aliases` | `list[dict]` | Other artist identities for the same person, `[{id, name}]`. |
| `groups` | `list[dict]` | Bands/collectives this artist is a member of, `[{id, name}]`. |

Notes:

- This function does not persist the record itself (mirrors `collect_release`'s contract) — a
  caller writes it via `storage.save_json("artist", artist_id, record)`.
- Missing data degrades to zero/empty values, not an error: absent `urls`, `name_variations`,
  `aliases`, or `groups` become `[]`; absent `real_name`/`profile`/`url` become `None`.

## Label record shape

A label record, as produced by `discogs/collectors/label.py` (`collect_label`) and stored at
`data/label/<id>.json`, is a dict with the following top-level fields:

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Discogs label id. |
| `name` | `str` | Label name. |
| `profile` | `str \| None` | Free-text bio/profile (e.g. "Label founded in 2007 by..."). |
| `urls` | `list[str]` | External links (official site, social media, etc.). |
| `images` | `list[dict]` | Label images, as returned by the API. |
| `contact_info` | `str \| None` | Free-text contact info, when present. |
| `data_quality` | `str \| None` | Discogs data-quality rating for this entry. |
| `url` | `str \| None` | Canonical Discogs page URL for the label. |
| `parent_label` | `dict \| None` | Parent label group, normalized to `{id, name}`, or `None` if this label has no parent (e.g. Desolat's parent is Desolat Music Group). |
| `sublabels` | `list[dict]` | Sublabels, normalized to `[{id, name}]`. |

Notes:

- `collect_label` does **not** include the label's releases — that's a much larger, paginated
  operation handled separately by `collect_label_releases`, which calls `collect_label` once for
  the profile and then walks releases into separate `release` records.

## Other files under `data/`

- `data/discography/<artist_id>.json` - the raw `/artists/{id}/releases` listing: a list of
  summary stubs (`id`, `type` = `release` or `master`, `title`, `year`, `role`, `label`, `format`,
  `main_release` for masters, `thumb`, `stats`). It has no genres, styles, tracklist or durations;
  those only exist in the full release records (`data/release/<id>.json`). Masters have no label
  in this listing. Not written by a collector yet (saved by hand so far).
- `data/_agent/notes.md` - the chat agent's writable notes, persisted across sessions.
- `data/_agent/checkpoints.sqlite` - the agent's saved conversations, one per `--thread`.
