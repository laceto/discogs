"""Tests for discogs.collectors.artist. No live API calls.

`client.artist(...).releases` is mocked as a fake paginated list (mirroring
`_pagination`'s own test fixtures) mixing real `discogs_client` `Release` and
`Master` instances. `collect_release` / `storage.save_json` are monkeypatched
so the wiring can be verified without touching the network or the filesystem.

`collect_artist_profile` is tested separately below with a fake Artist-like
object (`SimpleNamespace`), mirroring `tests/test_label_collector.py`'s style
for `collect_label`.
"""

from types import SimpleNamespace

import pytest
from discogs_client.models import Master, Release

import discogs.collectors.artist as artist_module
from discogs.collectors.artist import collect_artist_profile, collect_artist_releases

_STUB_CLIENT = SimpleNamespace(_base_url="https://api.discogs.com")


def _release(id):
    return Release(_STUB_CLIENT, {"id": id, "title": f"Release {id}"})


def _master(id):
    return Master(_STUB_CLIENT, {"id": id, "title": f"Master {id}"})


class _FakePaginatedList:
    """Fake PaginatedList matching `_pagination.SupportsPagination`.

    `pages_data[i]` is the (1-indexed) item list for page i+1, same shape as
    `tests/test_pagination.py`'s fixture.
    """

    def __init__(self, pages_data):
        self._pages_data = pages_data
        self.pages = len(pages_data)

    def page(self, index):
        return self._pages_data[index - 1]


class _FakeClient:
    """Stands in for discogs_client.Client: .artist(id) returns a canned artist."""

    def __init__(self, artist_id, releases):
        self._artist_id = artist_id
        self._artist = SimpleNamespace(releases=releases)

    def artist(self, artist_id):
        assert artist_id == self._artist_id
        return self._artist


@pytest.fixture
def collect_release_calls(monkeypatch):
    """Replace `collect_release` with a recorder; returns the list of calls."""
    calls: list[tuple[object, int]] = []

    def fake_collect_release(client, release_id):
        calls.append((client, release_id))
        return {"id": release_id, "title": f"Release {release_id}"}

    monkeypatch.setattr(artist_module, "collect_release", fake_collect_release)
    return calls


@pytest.fixture
def save_json_calls(monkeypatch):
    """Replace `storage.save_json` with a recorder; returns the list of calls."""
    calls: list[tuple[str, int, dict]] = []

    def fake_save_json(entity_type, id, record):
        calls.append((entity_type, id, record))

    monkeypatch.setattr(artist_module.storage, "save_json", fake_save_json)
    return calls


def test_calls_collect_release_and_save_json_once_per_release_id(
    collect_release_calls, save_json_calls
):
    releases = _FakePaginatedList([[_release(1), _release(2)], [_release(3)]])
    client = _FakeClient(42, releases)

    result = list(collect_artist_releases(client, 42))

    assert result == [1, 2, 3]
    assert [release_id for _, release_id in collect_release_calls] == [1, 2, 3]
    assert all(call_client is client for call_client, _ in collect_release_calls)
    assert [(entity_type, id_) for entity_type, id_, _ in save_json_calls] == [
        ("release", 1),
        ("release", 2),
        ("release", 3),
    ]
    assert [record for _, _, record in save_json_calls] == [
        {"id": 1, "title": "Release 1"},
        {"id": 2, "title": "Release 2"},
        {"id": 3, "title": "Release 3"},
    ]


def test_mixed_release_and_master_entries_skips_masters_without_crashing(
    collect_release_calls, save_json_calls
):
    releases = _FakePaginatedList([[_release(1), _master(100)], [_master(200), _release(2)]])
    client = _FakeClient(7, releases)

    result = list(collect_artist_releases(client, 7))

    assert result == [1, 2]
    assert [release_id for _, release_id in collect_release_calls] == [1, 2]
    assert [id_ for _, id_, _ in save_json_calls] == [1, 2]


def test_all_master_entries_yields_nothing_and_does_not_crash(
    collect_release_calls, save_json_calls
):
    releases = _FakePaginatedList([[_master(100), _master(200)]])
    client = _FakeClient(9, releases)

    result = list(collect_artist_releases(client, 9))

    assert result == []
    assert collect_release_calls == []
    assert save_json_calls == []


def test_empty_releases_collection_yields_nothing():
    releases = _FakePaginatedList([[]])
    client = _FakeClient(13, releases)

    result = list(collect_artist_releases(client, 13))

    assert result == []


def _artist_ref(id, name):
    return SimpleNamespace(id=id, name=name)


class _FakeProfileClient:
    """Stands in for discogs_client.Client for collect_artist_profile: .artist(id)
    returns a canned Artist-like object."""

    def __init__(self, artist):
        self._artist = artist
        self.artist_calls: list[int] = []

    def artist(self, artist_id):
        self.artist_calls.append(artist_id)
        return self._artist


def test_collect_artist_profile_normal_fields():
    artist = SimpleNamespace(
        name="Martin Buttrich",
        real_name="Martin Buttrich",
        profile="German DJ and producer, now based in Los Angeles, US.",
        images=[{"type": "primary", "uri": "http://example.com/photo.jpg"}],
        url="https://www.discogs.com/artist/12995-Martin-Buttrich",
        urls=["https://martinbuttrich.com", "https://soundcloud.com/martinbuttrich"],
        name_variations=["Butrich", "Buttrich", "M. Buttrich"],
        aliases=[_artist_ref(1, "Freak Sensation"), _artist_ref(2, "The Stoned Autopilot")],
        groups=[_artist_ref(100, "Desolat"), _artist_ref(101, "Rhythm Assault")],
    )
    client = _FakeProfileClient(artist)

    record = collect_artist_profile(client, 12995)

    assert record == {
        "id": 12995,
        "name": "Martin Buttrich",
        "real_name": "Martin Buttrich",
        "profile": "German DJ and producer, now based in Los Angeles, US.",
        "images": [{"type": "primary", "uri": "http://example.com/photo.jpg"}],
        "url": "https://www.discogs.com/artist/12995-Martin-Buttrich",
        "urls": ["https://martinbuttrich.com", "https://soundcloud.com/martinbuttrich"],
        "name_variations": ["Butrich", "Buttrich", "M. Buttrich"],
        "aliases": [
            {"id": 1, "name": "Freak Sensation"},
            {"id": 2, "name": "The Stoned Autopilot"},
        ],
        "groups": [{"id": 100, "name": "Desolat"}, {"id": 101, "name": "Rhythm Assault"}],
    }
    assert client.artist_calls == [12995]


def test_collect_artist_profile_missing_fields_default_to_none_or_empty():
    artist = SimpleNamespace()
    client = _FakeProfileClient(artist)

    record = collect_artist_profile(client, 1)

    assert record == {
        "id": 1,
        "name": None,
        "real_name": None,
        "profile": None,
        "images": [],
        "url": None,
        "urls": [],
        "name_variations": [],
        "aliases": [],
        "groups": [],
    }


def test_collect_artist_profile_no_aliases_or_groups_are_empty_lists():
    artist = SimpleNamespace(name="Solo Artist", aliases=[], groups=[])
    client = _FakeProfileClient(artist)

    record = collect_artist_profile(client, 2)

    assert record["aliases"] == []
    assert record["groups"] == []
