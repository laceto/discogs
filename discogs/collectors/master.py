"""Breadth collector: a Master's `.versions` listing -> persisted release records.

`collect_master_versions` paginates a Master's `.versions` collection (every
release/pressing/reissue that belongs to this master) using the shared
`_pagination.iter_paginated` helper, calls `collect_release` (A3.1) for each
version's release id, persists the resulting record via
`storage.save_json('release', id, record)` (A2.3), and returns the list of
release ids processed.
"""

from typing import Any

from discogs.collectors._pagination import iter_paginated
from discogs.collectors.release import collect_release
from discogs.storage import save_json


def collect_master_versions(client: Any, master_id: int) -> list[int]:
    """Collect and persist every release version of `master_id`'s Master.

    Paginates `client.master(master_id).versions` page by page via
    `iter_paginated`. For every version found, calls
    `collect_release(client, version.id)` and persists the resulting record
    with `storage.save_json('release', version.id, record)`.

    Returns the list of release ids processed, in the order encountered.
    """
    master = client.master(master_id)
    processed_ids: list[int] = []

    for version in iter_paginated(master.versions):
        release_id = version.id
        record = collect_release(client, release_id)
        save_json("release", release_id, record)
        processed_ids.append(release_id)

    return processed_ids
