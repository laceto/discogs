"""Search-driven collector: pull releases matching a Discogs search query.

`collect_search_releases` walks `client.search(type='release', **search_fields)`
- a `MixedPaginatedList`, same shape `iter_paginated` already handles for the
breadth collectors - and collects + persists full detail for up to `limit`
matching releases. Unlike the label/artist/master collectors (which crawl a
bounded, known entity), a search can match the entire Discogs catalog, so
`limit` is required and enforced here rather than left to the caller to
remember to bound.

See docs/schemas.md for the persisted record shape, and board/brainstorm.md
(Alternative 5 / Phase 5) for why this is scoped to an explicit, bounded
`limit` rather than an unbounded full-catalog sweep.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from discogs_client.models import Release

from discogs import storage
from discogs.collectors._pagination import iter_paginated
from discogs.collectors.release import collect_release


def collect_search_releases(client: Any, limit: int, **search_fields: Any) -> Iterator[int]:
    """Search for releases matching `search_fields`, collecting + persisting up to `limit`.

    `search_fields` are passed straight through to `client.search(...)` as
    query parameters (e.g. `style="Minimal"`, `genre="Electronic"`,
    `year="2010"`) - see the Discogs API search endpoint for the full field
    list. `type="release"` is always forced, overriding any `type` passed in,
    since this collector only knows how to process `Release` entries.

    Stops as soon as `limit` releases have been collected, even if more pages
    of results remain - this deliberately does not do full-catalog crawling.
    Any non-`Release` entry in the results (masters, artists, labels) is
    skipped without erroring, matching `collect_artist_releases`'s handling of
    mixed result types.

    Yields each collected release id as it's processed.

    Raises:
        ValueError: if `limit` is not a positive integer.
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")

    search_fields = {**search_fields, "type": "release"}
    results = client.search(**search_fields)

    collected = 0
    for entry in iter_paginated(results):
        if collected >= limit:
            break
        if not isinstance(entry, Release):
            continue

        release_id = entry.id
        record = collect_release(client, release_id)
        storage.save_json("release", release_id, record)
        collected += 1
        yield release_id
