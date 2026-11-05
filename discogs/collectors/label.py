"""Label collector: the label's own profile, plus its releases.

`collect_label` fetches a label's own profile data (name, bio, links, parent
label, sublabels) as a plain dict - the atomic unit, mirroring
`collectors.release.collect_release`. `collect_label_releases` persists that
profile once via `storage.save_json`, then walks `client.label(label_id).releases`
page by page via the shared `iter_paginated` helper, calling `collect_release`
for every release id found and persisting each one too, yielding the release
ids as they're processed.

See docs/schemas.md for the persisted record shapes.
"""

from collections.abc import Iterator
from typing import Any

from discogs import storage
from discogs.collectors._pagination import iter_paginated
from discogs.collectors.release import collect_release


def _normalize_label_ref(label: Any) -> dict[str, Any]:
    return {"id": getattr(label, "id", None), "name": getattr(label, "name", None)}


def _collect_label_fields(label: Any, label_id: int) -> dict[str, Any]:
    parent_label = getattr(label, "parent_label", None)

    return {
        "id": label_id,
        "name": getattr(label, "name", None),
        "profile": getattr(label, "profile", None),
        "urls": list(getattr(label, "urls", None) or []),
        "images": list(getattr(label, "images", None) or []),
        "contact_info": getattr(label, "contact_info", None),
        "data_quality": getattr(label, "data_quality", None),
        "url": getattr(label, "url", None),
        "parent_label": _normalize_label_ref(parent_label) if parent_label else None,
        "sublabels": [_normalize_label_ref(sub) for sub in getattr(label, "sublabels", None) or []],
    }


def collect_label(client: Any, label_id: int) -> dict[str, Any]:
    """Collect a label's own profile detail into a plain dict.

    Covers name, profile (bio text), urls, images, contact_info, data_quality,
    url, parent_label (as `{id, name}`, or None for a label with no parent),
    and sublabels (as a list of `{id, name}`). Does NOT include the label's
    releases - that's `collect_label_releases`'s job, kept separate since
    walking releases is a much larger, paginated operation.
    """
    label = client.label(label_id)
    return _collect_label_fields(label, label_id)


def collect_label_releases(client: Any, label_id: int) -> Iterator[int]:
    """Collect + persist `label_id`'s own profile, then paginate + collect its releases.

    Fetches the label once, collects + persists its own profile via
    `storage.save_json('label', label_id, record)` - once, regardless of how
    many releases follow - then reuses that same label object to paginate its
    `.releases` collection (fetching it a second time via a fresh object would
    re-fetch the label's own JSON, since `.releases` needs `releases_url` off
    the label resource). For every release found, calls
    `collect_release(client, release_id)` for the full record and persists it
    via `storage.save_json('release', ...)`. Yields each release id right
    after it's processed, so a caller can stream progress or stop early
    without waiting for the whole label to finish.
    """
    label = client.label(label_id)
    label_record = _collect_label_fields(label, label_id)
    storage.save_json("label", label_id, label_record)

    for release_stub in iter_paginated(label.releases):
        release_id = release_stub.id
        record = collect_release(client, release_id)
        storage.save_json("release", release_id, record)
        yield release_id
