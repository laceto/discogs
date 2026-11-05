"""Repo-wide test safety net.

A collector test that forgets to monkeypatch `storage.save_json` doesn't just
fail loudly - it silently writes its fake fixture data into the real repo's
`data/` directory (this happened once, from tests/test_search_collector.py).
This autouse fixture closes that hole for every test by redirecting
`discogs.storage`'s default base directory to a per-test temp directory, so a
missed mock can never touch the real `data/` folder, regardless of which test
file it's in or what gets added later.

Tests that explicitly want to exercise the *default-path* behavior (e.g.
tests/test_storage.py's `test_default_base_dir_resolves_under_repo_root`)
still monkeypatch `_REPO_ROOT` themselves afterward, which simply overrides
this fixture's value for that test - no conflict.
"""

import pytest

import discogs.storage as storage


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_REPO_ROOT", tmp_path)
