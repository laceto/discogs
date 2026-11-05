"""Tests for discogs.collectors.label. No live API calls.

Mocks `collect_release` and `storage.save_json` (as imported into
`discogs.collectors.label`) plus a fake paginated `.releases` list, so this
exercises the wiring: collect the label's own profile once -> save_json ->
paginate -> collect_release -> save_json -> yield release id. Pagination
itself is covered by tests/test_pagination.py, `collect_release`'s
field-collection logic by tests/test_release_collector.py.
"""

from types import SimpleNamespace

import discogs.collectors.label as label_module
from discogs.collectors.label import collect_label, collect_label_releases


class _FakePaginatedReleases:
    """Fake PaginatedList: `pages_data[i]` is the (1-indexed) item list for page i+1."""

    def __init__(self, pages_data: list[list[SimpleNamespace]]):
        self._pages_data = pages_data
        self.pages = len(pages_data)

    def page(self, index: int) -> list[SimpleNamespace]:
        return self._pages_data[index - 1]


def _label_ref(id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=id, name=name)


def _fake_label(releases: _FakePaginatedReleases, **profile_fields) -> SimpleNamespace:
    """A fake Label: `releases` plus whatever profile attrs a test cares about.
    Fields left unset simply aren't present, matching getattr(..., None)'s
    handling of a real Label object where the API omitted that field.
    """
    return SimpleNamespace(releases=releases, **profile_fields)


class _FakeClient:
    """Stands in for discogs_client.Client: .label(id) returns a canned object,
    and always returns the SAME instance for a given id (matching the real
    client's per-call-but-consistent-data behavior enough for these tests)."""

    def __init__(self, label: SimpleNamespace):
        self._label = label
        self.label_calls: list[int] = []

    def label(self, label_id):
        self.label_calls.append(label_id)
        return self._label


def _release_stub(id: int) -> SimpleNamespace:
    return SimpleNamespace(id=id)


def test_collect_label_normal_fields():
    label = _fake_label(
        _FakePaginatedReleases([]),
        id=93611,
        name="Desolat",
        profile="Label founded in 2007 by Loco Dice and Martin Buttrich in Düsseldorf, Germany.",
        urls=["https://desolat.com", "https://desolatmusicgroup.de"],
        images=[{"type": "primary", "uri": "http://example.com/logo.jpg"}],
        contact_info=None,
        data_quality="Correct",
        url="https://www.discogs.com/label/93611-Desolat",
        parent_label=_label_ref(999, "Desolat Music Group"),
        sublabels=[],
    )
    client = _FakeClient(label)

    record = collect_label(client, 93611)

    assert record == {
        "id": 93611,
        "name": "Desolat",
        "profile": "Label founded in 2007 by Loco Dice and Martin Buttrich in Düsseldorf, Germany.",
        "urls": ["https://desolat.com", "https://desolatmusicgroup.de"],
        "images": [{"type": "primary", "uri": "http://example.com/logo.jpg"}],
        "contact_info": None,
        "data_quality": "Correct",
        "url": "https://www.discogs.com/label/93611-Desolat",
        "parent_label": {"id": 999, "name": "Desolat Music Group"},
        "sublabels": [],
    }


def test_collect_label_no_parent_label_is_none():
    label = _fake_label(_FakePaginatedReleases([]), name="Standalone Label", parent_label=None)
    client = _FakeClient(label)

    record = collect_label(client, 1)

    assert record["parent_label"] is None


def test_collect_label_missing_fields_default_to_none_or_empty():
    label = _fake_label(_FakePaginatedReleases([]))
    client = _FakeClient(label)

    record = collect_label(client, 1)

    assert record == {
        "id": 1,
        "name": None,
        "profile": None,
        "urls": [],
        "images": [],
        "contact_info": None,
        "data_quality": None,
        "url": None,
        "parent_label": None,
        "sublabels": [],
    }


def test_collect_label_with_sublabels():
    label = _fake_label(
        _FakePaginatedReleases([]),
        name="Desolat Music Group",
        sublabels=[_label_ref(93611, "Desolat"), _label_ref(200, "Life and Death")],
    )
    client = _FakeClient(label)

    record = collect_label(client, 999)

    assert record["sublabels"] == [
        {"id": 93611, "name": "Desolat"},
        {"id": 200, "name": "Life and Death"},
    ]


def test_collect_label_releases_persists_label_profile_once(monkeypatch):
    releases = _FakePaginatedReleases([[_release_stub(101)]])
    label = _fake_label(releases, name="Desolat", profile="Founded in 2007...")
    client = _FakeClient(label)

    save_json_calls: list[tuple] = []
    monkeypatch.setattr(label_module, "collect_release", lambda c, rid: {"id": rid})
    monkeypatch.setattr(
        label_module.storage,
        "save_json",
        lambda entity_type, id, record: save_json_calls.append((entity_type, id, record)),
    )

    list(collect_label_releases(client, label_id=93611))

    label_calls = [call for call in save_json_calls if call[0] == "label"]
    assert label_calls == [
        (
            "label",
            93611,
            {
                "id": 93611,
                "name": "Desolat",
                "profile": "Founded in 2007...",
                "urls": [],
                "images": [],
                "contact_info": None,
                "data_quality": None,
                "url": None,
                "parent_label": None,
                "sublabels": [],
            },
        )
    ]
    # Only fetched the label once, even though both the profile and .releases
    # need it - reusing one object instead of calling client.label() twice.
    assert client.label_calls == [93611]


def test_collect_label_releases_calls_collect_release_and_save_json_once_per_id(monkeypatch):
    release_ids = [101, 102, 103]
    releases = _FakePaginatedReleases(
        [[_release_stub(101), _release_stub(102)], [_release_stub(103)]]
    )
    client = _FakeClient(_fake_label(releases))

    collect_release_calls: list[tuple] = []
    save_json_calls: list[tuple] = []

    def fake_collect_release(client_arg, release_id):
        collect_release_calls.append((client_arg, release_id))
        return {"id": release_id}

    def fake_save_json(entity_type, id, record):
        save_json_calls.append((entity_type, id, record))

    monkeypatch.setattr(label_module, "collect_release", fake_collect_release)
    monkeypatch.setattr(label_module.storage, "save_json", fake_save_json)

    result = list(collect_label_releases(client, label_id=999))

    assert result == release_ids

    assert len(collect_release_calls) == len(release_ids)
    assert [call[1] for call in collect_release_calls] == release_ids
    assert all(call[0] is client for call in collect_release_calls)

    release_save_calls = [call for call in save_json_calls if call[0] == "release"]
    assert len(release_save_calls) == len(release_ids)
    assert [call[1] for call in release_save_calls] == release_ids
    assert [call[2] for call in release_save_calls] == [{"id": rid} for rid in release_ids]

    # Plus exactly one "label" save for the profile, alongside the per-release ones.
    assert sum(1 for call in save_json_calls if call[0] == "label") == 1


def test_collect_label_releases_empty_label_yields_nothing(monkeypatch):
    client = _FakeClient(_fake_label(_FakePaginatedReleases([])))

    collect_release_calls: list[int] = []
    monkeypatch.setattr(
        label_module,
        "collect_release",
        lambda client_arg, release_id: collect_release_calls.append(release_id),
    )
    monkeypatch.setattr(label_module.storage, "save_json", lambda *args: None)

    result = list(collect_label_releases(client, label_id=1))

    assert result == []
    assert collect_release_calls == []


def test_collect_label_releases_uses_label_id_to_look_up_label(monkeypatch):
    releases = _FakePaginatedReleases([[_release_stub(5)]])
    client = _FakeClient(_fake_label(releases))

    monkeypatch.setattr(label_module, "collect_release", lambda c, rid: {"id": rid})
    monkeypatch.setattr(label_module.storage, "save_json", lambda *args: None)

    list(collect_label_releases(client, label_id=42))

    assert client.label_calls == [42]
