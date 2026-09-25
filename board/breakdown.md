# Breakdown: Discogs data-collection layer

Source: [board/brainstorm.md](brainstorm.md) — this breakdown assumes Phase 6's Next Steps
1–4 are in scope (auth, schema, release-detail collector, breadth collectors) and defers the
"full-catalog `search()` sweep" and "other users' collections" ideas as out of scope for now
(see brainstorm Phase 4/5 — those carry the highest strategic risk and need an explicit scope
decision first).

**Goal:** Build a reusable data-collection layer on `discogs_client` that pulls full release
detail (base fields, credits/producers, community, master link, marketplace stats, price
suggestions), plus breadth collectors (label → releases, artist → releases, master → versions),
and persists everything to `data/` in a queryable shape — without breaking the existing
`scripts/discogs_release_reader.py`.

This is planning only — no code written yet. Leaves are meant to be picked up and solved in
order, A1 → A5, confirming each before moving to the next.

```
Goal: Build a reusable Discogs data-collection layer (auth → schema → release detail →
      breadth collectors → persistence) on top of discogs_client.

A1  Authentication setup
  A1.1  Add `python3-discogs-client` to requirements.txt and pyproject.toml [project.dependencies]
  A1.2  Generate a Discogs personal user token (discogs.com developer settings, manual/user step);
        add DISCOGS_USER_TOKEN to .env.example as a documented placeholder
  A1.3  Write discogs/client.py: get_client() -> discogs_client.Client, reading
        DISCOGS_USER_TOKEN from the environment, raising a clear error if unset
  A1.4  tests/test_client.py: verify get_client() returns a Client instance; skip (not fail)
        the live client.identity() call when no token is present in the environment

A2  Minimal persisted schema
  A2.1  Decide storage shape: flat JSON per entity under data/<entity_type>/<id>.json
        (matches the existing data/ convention already in the repo; no DB dependency yet).
        Leaf: write the decision as a short note in docs/schemas.md
  A2.2  Define the release-record dict shape in docs/schemas.md: id, title, year, genres,
        styles, country, formats, tracklist, artists, credits, labels, community, master_id,
        marketplace_stats, price_suggestions
  A2.3  Write discogs/storage.py: save_json(entity_type: str, id, record: dict) -> writes to
        data/<entity_type>/<id>.json, creating parent dirs as needed

A3  Release-detail collector (the atomic unit everything else composes from)
  A3.1  discogs/collectors/release.py: collect_release(client, release_id) -> dict with base
        fields (title, year, genres, styles, country, formats, notes, images, url, tracklist)
  A3.2  Extend collect_release: artists + credits (extraartists), normalized to
        [{name, id, role}] — handle multi-artist "join" keyword per brainstorm Phase 2 note
  A3.3  Extend collect_release: labels (name, catno)
  A3.4  Extend collect_release: community (want, have, rating avg/count, submitter,
        contributors) — must not error when a release has zero community data
  A3.5  Extend collect_release: master_id + link via release.master — must handle None
        (standalone releases with no master)
  A3.6  discogs/collectors/release.py: collect_marketplace_stats(client, release_id) -> dict
        (num_for_sale, blocked_from_sale, lowest_price) as its own function (separate API call)
  A3.7  discogs/collectors/release.py: collect_price_suggestions(client, release_id) -> dict
        per condition grade (Poor..Mint) — requires auth, own function
  A3.8  tests/test_release_collector.py: unit tests against a fixture dict (no live API call)
        covering normal fields, missing-master case, and empty-community case
  A3.9  Extend scripts/discogs_release_reader.py with an optional "full detail" mode that calls
        collect_release + storage.save_json, behind a flag — existing default behavior unchanged

A4  Breadth collectors
  A4.1  discogs/collectors/label.py: collect_label_releases(client, label_id) -> paginates
        label.releases, yields release ids
  A4.2  discogs/collectors/artist.py: collect_artist_releases(client, artist_id) -> paginates
        artist.releases (MixedPaginatedList), yields release/master ids
  A4.3  discogs/collectors/master.py: collect_master_versions(client, master_id) -> paginates
        master.versions, yields release ids
  A4.4  discogs/collectors/_pagination.py: shared helper to iterate a PaginatedList page by
        page with rate-limit backoff, checkpointing "last page fetched" to resume an
        interrupted crawl (brainstorm Phase 5: rate-limit throttling is the top execution risk)
  A4.5  Wire each breadth collector to call collect_release (A3.1) per id found, persisting via
        storage.save_json (A2.3)
  A4.6  tests/test_pagination.py: mock a multi-page PaginatedList-like object, assert full
        iteration completes and resuming from a checkpoint skips already-fetched pages

A5  Verification / wrap-up
  A5.1  Manual run: collect_release() on the two releases already looked up this session
        (Me Sabe A Porro id 2303570, Price Tag EP id 2051210) — confirm credits/community/
        marketplace fields now populate that the old script never captured
  A5.2  Manual run: collect_label_releases() on one small label (e.g. Desolat) — confirm N
        release JSON files land under data/release/
  A5.3  Replace the placeholder text in docs/architecture.md with the real collector module
        layout (discogs/client.py, discogs/storage.py, discogs/collectors/*)
  A5.4  If a distinct task shape emerged, add a "DATA COLLECTION" category to CLAUDE.md's
        router pointing at coding-rules.md + docs/schemas.md
```

## Notes

- A1 → A2 → A3 are strictly sequential (auth blocks everything; schema decision blocks what
  the collector writes). A4 depends on A3.1 existing but its three sub-collectors (A4.1–A4.3)
  are independent of each other and can be built in any order once A4.4's pagination helper
  exists.
- Out of scope for this pass (per brainstorm Phase 3/5): the full-catalog `search()`-driven
  sweep (Alternative 5) and crawling other users' collections/wantlists (Alternative 3) — both
  carry Medium/Strategic risk and need an explicit go-ahead before building.
- Key open question carried over from the brainstorm: is the end goal a personal
  reference/archive tool or a bulk dataset-building crawl? A3 (release depth) serves either
  goal equally; A4 (breadth/volume) is only worth building if the answer leans toward "bulk."
