# Brainstorm: What can we collect from Discogs?

Seed: use `discogs_client` (joalla fork) to pull as much structured data as possible out of
Discogs — release detail, producer/artist info, label info, credits, community stats,
marketplace pricing, master/version history, user collections — for this project.

## Phase 1 — Reframe & Clarify

**Problem statement:** How might we build a data-collection layer on top of `discogs_client`
that captures the full breadth of what Discogs exposes, not just the bare release metadata the
current `scripts/discogs_release_reader.py` grabs?

**Goal statement:** The desired outcome is a reusable set of collectors that can pull, for a
given seed (a release, an artist, a label, or a search query), the full graph of related
Discogs data — release detail, credits/producers, label catalog, master version history,
community reception, and marketplace pricing — and persist it in a form we can query later
(not just print to stdout).

**Constraint statement:** The boundaries are: (1) Discogs API rate limits (60 req/min
authenticated, 25/min unauthenticated) and a required User-Agent; (2) `search()` requires an
authenticated user token; (3) the raw HTML release pages are Cloudflare-gated, so everything
must go through the REST API / `discogs_client`, never scraping HTML; (4) we don't yet know the
end use (personal crate-digging archive? a dataset for analysis? a recommendation feed?) — the
brainstorm assumes "collect broadly now, decide the use later" per the user's own framing.

**Assumed interpretation:** "The client" = `discogs_client` (joalla/discogs_client), already
scoped in the prior conversation. "As much as possible" is taken literally: enumerate every
object type and field the library exposes, not just the obviously-useful ones.

## Phase 2 — Angles & Dimensions

### Data & Information — what's actually collectible

- **Release-level**: title, year, country, format(s), genres, styles, notes, images, videos,
  full tracklist (position/title/duration), all artist credits including `extraartists` (this
  is where producer, mixed-by, mastered-by, remix, engineer credits live — the richest and most
  underused field), label + catalog number, community want/have counts, community rating
  (avg + count), community contributors and submitter, master link, marketplace stats
  (# for sale, blocked-from-sale), price suggestions per condition grade (Poor → Mint).
- **Artist-level**: profile bio, name variations, aliases, group memberships (is this alias of
  / member of), URLs (Bandcamp, SoundCloud, Discogs forum, etc. if populated), full discography
  via `artist.releases` (paginated, can be thousands of entries for prolific producers/labels).
- **Label-level**: profile, sublabels, parent label, contact info, full release catalog via
  `label.releases` — this is the backbone for "collect everything on label X" style crawls.
- **Master-level**: canonical grouping of a release, `main_release`, and `versions` — every
  pressing/reissue/regional variant of the same recording, which is gold for tracking a track's
  release history across years/countries/formats.
- **Community/reputation signal**: want/have ratio (proxy for rarity vs. desirability),
  average rating, who submitted/edited the entry (contributor network — could map prolific
  data-quality contributors).
- **Marketplace/economic signal**: live listings (price, condition, seller, location),
  price suggestions by grade, historical order data (if authenticated as the account that
  made the order) — this is the only "money" data source Discogs offers short of full sales
  history (which isn't public).
- **Personal/user-graph data**: if authenticated, our own wantlist, collection folders +
  per-item notes/ratings/date-added, collection value estimate, and (read-only, no auth needed)
  *any public user's* inventory — meaning we could, in principle, crawl other diggers'
  collections/wantlists as a signal of taste clusters.

### Technical — what it takes to build

- All access goes through one `discogs_client.Client`, instantiated once, reused across
  collectors (rate-limit state lives on the fetcher).
- Every collector is "seed in, object graph out" — e.g. `label(id).releases` returns a lazy
  `ObjectCollection` you must paginate; nothing is bulk-exported by the API itself.
- Persisting requires flattening `PrimaryAPIObject`/`SecondaryAPIObject` trees (nested
  Artist/Label/Track/Price objects) into rows — a serialization layer is unavoidable if we want
  anything queryable later (see `data/` convention already in the repo).
- Auth: user-token auth is enough for search + read; only OAuth is needed for anything that
  writes (listings, wantlist edits) — we don't need OAuth for a pure collector.

### Business / Value

- No monetary cost to Discogs API itself (free with a token), but "collecting a lot" costs
  *time* — rate limits mean a full label or prolific-artist discography can take minutes to
  hours to crawl exhaustively.
- Value split: crate-digging/discovery value (surfacing rare or highly-wanted releases),
  archival value (a personal dataset immune to Discogs UI/API changes), and potential
  analytical value (price trend / genre trend analysis) if pricing + timestamps are captured
  over repeated runs (Discogs itself doesn't give historical price series — we'd have to build
  one ourselves by re-polling over time).

### Time & Sequencing

- Release-by-release detail (what the existing script does) is the cheapest, must-have-first
  building block — everything else (label crawl, artist crawl, master version crawl) is just
  "call that same detail fetch across many seeds."
- Marketplace/pricing data is volatile — if it matters, it needs *repeated* collection over
  time, not a one-shot pull; this should be sequenced after the core catalog collector exists,
  as a "run periodically" job.
- Auth (user token) is a blocking prerequisite for anything using `search()` — get that sorted
  before building the search-driven bulk collector.

### Failure & Edge Cases

- Multi-artist releases: `artists` is *always* a list, join keywords ("feat", "vs") live on
  the `join` field of each Artist entry inside that list — easy to mis-render as a single
  artist if not handled.
- Master `main_release` and `versions` can be `None` for standalone releases with no master —
  must not assume every release has a master.
- Community data (want/have/rating) can be zero/empty for obscure releases — don't treat
  absence as an error.
- Rate-limit exhaustion mid-crawl (large label/artist discography) — needs resumable
  pagination (store last-page-fetched), not "restart from scratch."
- Public user inventories/wantlists can be empty, private, or huge (thousands of items) —
  treat every "collect a user's X" as unbounded until proven otherwise.

### Analogies

- This is structurally identical to crawling any faceted e-commerce/catalog API (think
  Goodreads for books, IMDb for film): entity graph (work → contributors → publisher →
  editions) + a marketplace layer (listings/prices) + a community layer (ratings/wants). Prior
  art from "IMDb dataset" or "MusicBrainz dump" projects on how to normalize a
  entity-with-many-editions model directly transfers to release ↔ master ↔ versions.

### Second-order effects

- Once release + credits data is normalized, "producer/engineer network" becomes queryable —
  e.g. "every release Rashad Becker mastered" — which is a distinct, high-value dataset beyond
  simple release lookup, but only if `extraartists` credits are parsed and role-tagged
  consistently (roles are free-text strings from Discogs, e.g. "Mixed By", "Mastered By" —
  will need normalization/mapping, not exact-match).
- Repeated marketplace polling turns a "static collector" into a de facto price-tracking
  service — raises the question of how long to retain snapshots and whether that's in scope.

## Phase 3 — Alternatives & Variations

1. **Depth-first (single release, maximal detail)** — pull everything the API offers for one
   release (credits, community, marketplace, price suggestions, master + all versions) before
   ever crawling a second release. Rationale: matches the existing script's pattern, cheapest
   to extend, good for "look up this record I just found" workflows.
2. **Breadth-first (seed = label or artist, minimal per-release detail)** — crawl every release
   ID under a label/artist first (title/year/format only), then backfill detail lazily.
   Rationale: gets a catalog map fast, defers the expensive part, good for "how big is this
   label's catalog" questions.
3. **Invert it — collect from the *demand* side, not the supply side** — instead of crawling
   releases, crawl `user.wantlist` / `user.collection_folders` across a set of usernames to
   build a taste-graph ("who wants what"), then join back to release detail only for items that
   show up. Rationale: prioritizes collection effort by what real diggers care about instead of
   exhaustively cataloging everything.
4. **Simplify radically — credits-only extractor** — ignore genres/styles/community entirely
   and build a single-purpose tool that only extracts `extraartists`/`credits` role data across
   a producer's name, to answer "what did this producer touch." Rationale: smallest slice that
   still delivers the single most differentiated dataset (Discogs credit data isn't easily
   available elsewhere in structured form).
5. **Scale wildly — genre/style/year faceted full crawl via `search()`** — drive `client.search()`
   across every combination of `genre`/`style`/`year`/`country` filters, paginating each facet
   to enumerate essentially the whole catalog. Rationale: this is the "as much as possible"
   literal reading — but at real scale (Discogs has ~millions of releases) this is a
   multi-week job even at the authenticated rate limit, so it's really a research question
   ("is full-catalog collection actually the goal?") disguised as a technical one.
6. **Steal from another domain — snapshot + diff, like a price-tracking bot** — treat
   marketplace/price-suggestion data the way stock-price scrapers treat tickers: poll on a
   schedule, append-only log with timestamps, and derive trend data ourselves since Discogs
   doesn't expose price history natively.

## Phase 4 — Hidden Assumptions

> We are assuming that **a user token is available or easy to obtain**, but if
> **the user hasn't generated a Discogs developer token yet**, we would need to add that as an
> explicit setup step (and store it via `.env`, which the scaffold already supports) before any
> collector beyond the current unauthenticated single-release reader can run.

> We are assuming that **the goal is breadth across data *types*** (release, artist, label,
> credits, community, marketplace), but if **the real goal is breadth across *volume*** (as many
> releases as possible, e.g. a whole label or genre), the collector design changes from
> "maximize fields per object" to "maximize objects crawled, minimize per-object cost."

> We are assuming that **persisted output matters** (something queryable later), but if
> **this is just ad-hoc lookups** (like the current script), then no storage/schema layer is
> needed at all — just richer per-call output.

> We are assuming that **rate limits are the binding constraint**, but if **Discogs applies
> additional anti-scraping heuristics beyond documented rate limits** (as it already does for
> the HTML pages via Cloudflare), a large `search()`-driven crawl could get token-limited or
> soft-blocked in ways the documented 60/min doesn't predict.

> We are assuming that **credit/role strings ("Mixed By", "Producer", "Written-By") are usable
> as-is**, but if **they're inconsistent free text** (which Discogs is known for — community
> edited), any "find everything a producer touched" feature needs a normalization/alias layer,
> not exact string matching.

> We are assuming **one Discogs account/token is enough**, but if **we later want to collect
> from multiple users' collections/wantlists** (Alternative 3 above), we're reading *other*
> people's data — worth a beat on whether that's within Discogs' API terms of use for how it
> gets stored/used downstream.

> We are assuming **the current single-release script's pattern (stdout, no persistence)** is
> just a stepping stone, but if **the user actually wants to keep it that way per-release** and
> only batch/persist at a higher level, the architecture should keep "fetch+format" and
> "collect+store" as separate layers rather than merging them.

## Phase 5 — Risks & Constraints

| Risk | Category | Rating | Mitigation |
|---|---|---|---|
| Rate-limit throttling stalls large crawls (label/artist/full-catalog) | Execution | High | Build pagination as resumable from the start (persist cursor/last-page); enable `backoff_enabled` on the client |
| No user token configured yet, blocking `search()` | Execution | Medium | Add token setup as the first concrete breakdown step; store in `.env` per existing scaffold convention |
| Credit/role free-text inconsistency undermines "producer network" use case | Adoption | Medium | Ship a small role-normalization map (e.g. "Mastered By" ~ "Mastering") as part of the credits collector, expand as edge cases appear |
| Full-catalog / wide `search()` crawling looks like large-scale scraping and could trip Discogs' abuse detection or ToS boundaries | Strategic | Medium | Prefer targeted seeds (a label, an artist, a set of releases) over unbounded full-catalog sweeps; keep request volume proportionate to actual need |
| Marketplace/price data is volatile — a one-shot pull gives a false sense of "the price," and no persistence means no trend data ever accumulates | Strategic | Low | Treat pricing as a periodic-poll concern from day one if it's wanted at all, not a one-off field to bolt on |
| Storing other users' public collection/wantlist data raises data-handling questions later (even though it's public) | Strategic | Low | Scope any "crawl other users" idea (Alternative 3) as explicitly opt-in/future, not default behavior |

## Phase 6 — Recommended Next Steps

1. **Confirm the actual goal and scope** — decide, with the user, which alternative from Phase 3
   is the real target (single-release depth, label/artist breadth, credits-only, full-catalog
   search sweep, or demand-side/user-collection crawl) — this determines almost everything
   downstream. *Deliverable: a one-line scope decision.*
2. **Set up authentication** — generate a Discogs user token, wire it into `.env` /
   `.env.example`, and confirm `discogs_client.Client(..., user_token=...)` works end-to-end.
   *Deliverable: a working authenticated client, verified with one `search()` call.*
3. **Design the minimal persisted schema** — decide what "collected data" is stored as
   (flat JSON per object type? SQLite tables mirroring Release/Artist/Label/Credit?) before
   writing collectors, so every collector writes into the same shape.
   *Deliverable: a schema sketch in `docs/schemas.md` (or the equivalent once real code exists).*
4. **Build the release-detail collector first** (superset of what `discogs_release_reader.py`
   already does — add credits/extraartists, community, master link, marketplace stats, price
   suggestions) — this is the reusable atomic unit every other collector (label, artist, master)
   composes from. *Deliverable: one function `collect_release(id) -> dict` covering every
   Release field.*
5. **Layer breadth collectors on top** (label → releases, artist → releases, master →
   versions), each just iterating seeds into step 4's function with pagination + rate-limit
   handling. *Deliverable: `collect_label(id)`, `collect_artist(id)`, `collect_master_versions(id)`.*

**Key open question:** Is the end goal a *personal reference/archive tool* (look up records as
you go, moderate volume) or a *bulk dataset-building crawl* (as many releases as possible,
label/genre/catalog scale)? That single answer decides whether we need pagination/rate-limit
engineering and persistence at all, or whether the existing single-release script just needs
richer field coverage.
