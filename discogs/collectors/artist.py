"""Artist collector: the artist's own profile, plus the releases they're credited on.

`collect_artist_profile` fetches an artist's own profile data (real name,
bio, links, name variations, aliases, groups) as a plain dict - the atomic
unit, mirroring `collectors.label.collect_label`. It does not persist the
record itself and does not touch releases.

`collect_artist_releases` paginates an Artist's `.releases` collection - a
`MixedPaginatedList` that mixes actual `Release` entries with `Master`
entries (Discogs surfaces an artist's masters alongside their releases in
that same feed) - using the shared pagination helper (`_pagination`). For
every real `Release` entry found it calls `collect_release` (the atomic
release-detail collector, A3.1) and persists the result via
`storage.save_json`. `Master` entries are skipped: they carry no release id
of their own to fetch - `collect_master_versions` (leaf A4.3) is the
collector that expands a master into its release versions.

See docs/schemas.md for the persisted record shapes.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from discogs_client.models import Release

from discogs import storage
from discogs.collectors._pagination import iter_paginated
from discogs.collectors.release import collect_release


def _normalize_artist_ref(artist: Any) -> dict[str, Any]:
    return {"id": getattr(artist, "id", None), "name": getattr(artist, "name", None)}


def collect_artist_profile(client: Any, artist_id: int) -> dict[str, Any]:
    """Collect an artist's own profile detail into a plain dict.

    Covers name, real_name, profile (bio text), images, url, urls,
    name_variations, aliases (as `[{id, name}]`), and groups (as
    `[{id, name}]`). Does NOT include the artist's releases - that's
    `collect_artist_releases`'s job, kept separate since walking releases is
    a much larger, paginated operation. Missing fields degrade to
    zero/empty values rather than erroring - see docs/schemas.md.
    """
    artist = client.artist(artist_id)

    return {
        "id": artist_id,
        "name": getattr(artist, "name", None),
        "real_name": getattr(artist, "real_name", None),
        "profile": getattr(artist, "profile", None),
        "images": list(getattr(artist, "images", None) or []),
        "url": getattr(artist, "url", None),
        "urls": list(getattr(artist, "urls", None) or []),
        "name_variations": list(getattr(artist, "name_variations", None) or []),
        "aliases": [_normalize_artist_ref(a) for a in getattr(artist, "aliases", None) or []],
        "groups": [_normalize_artist_ref(g) for g in getattr(artist, "groups", None) or []],
    }


def collect_artist_releases(client: Any, artist_id: int) -> Iterator[int]:
    """Paginate `artist_id`'s releases, collecting + persisting each real release.

    Walks the artist's (mixed) releases collection page by page via
    `_pagination.iter_paginated`. For every entry that is an actual `Release`
    (not a `Master`), calls `collect_release(client, release_id)` and writes
    the result with `storage.save_json('release', release_id, record)`.
    `Master` entries in the mix are skipped without erroring.

    Yields each processed release id as it's collected, so a caller can
    consume this lazily (e.g. `for release_id in collect_artist_releases(...)`)
    or materialize it eagerly with `list(...)`.
    """
    artist = client.artist(artist_id)
    for entry in iter_paginated(artist.releases):
        if not isinstance(entry, Release):
            continue

        release_id = entry.id
        record = collect_release(client, release_id)
        storage.save_json("release", release_id, record)
        yield release_id
