"""Tests for discogs.collectors.search. No live API calls.

`client.search(...)` is mocked as a fake paginated list (same shape as
tests/test_artist_collector.py's fixture) mixing real `discogs_client`
`Release`/`Master` instances. `collect_release` / `storage.save_json` are
monkeypatched so the wiring - including the `limit` stop condition and
`type='release'` forcing - can be verified without touching the network or
the filesystem.
"""

from types import SimpleNamespace

import pytest
from discogs_client.models import Master, Release

import discogs.collectors.search as search_module
from discogs.collectors.search import collect_search_releases

_STUB_CLIENT = SimpleNamespace(_base_url="https://api.discogs.com")


def _release(id):
    return Release(_STUB_CLIENT, {"id": id, "title": f"Release {id}"})


def _master(id):
    return Master(_STUB_CLIENT, {"id": id, "title": f"Master {id}"})


class _FakePaginatedList:
    """Fake PaginatedList matching `_pagination.SupportsPagination`."""

    def __init__(self, pages_data):
        self._pages_data = pages_data
        self.pages = len(pages_data)

    def page(self, index):
        return self._pages_data[index - 1]


class _FakeClient:
    """Stands in for discogs_client.Client: .search(**fields) returns a canned list
    and records every call's kwargs."""

    def __init__(self, results):
        self._results = results
        self.search_calls: list[dict] = []

    def search(self, **fields):
        self.search_calls.append(fields)
        return self._results


@pytest.fixture
def collect_release_calls(monkeypatch):
    calls: list[tuple[object, int]] = []

    def fake_collect_release(client, release_id):
        calls.append((client, release_id))
        return {"id": release_id, "title": f"Release {release_id}"}

    monkeypatch.setattr(search_module, "collect_release", fake_collect_release)
    return calls


@pytest.fixture
def save_json_calls(monkeypatch):
    calls: list[tuple[str, int, dict]] = []

    def fake_save_json(entity_type, id, record):
        calls.append((entity_type, id, record))

    monkeypatch.setattr(search_module.storage, "save_json", fake_save_json)
    return calls


def test_collects_up_to_limit_and_yields_release_ids(collect_release_calls, save_json_calls):
    results = _FakePaginatedList([[_release(1), _release(2), _release(3)]])
    client = _FakeClient(results)

    result = list(collect_search_releases(client, limit=2, style="Minimal"))

    assert result == [1, 2]
    assert [release_id for _, release_id in collect_release_calls] == [1, 2]
    assert [id_ for _, id_, _ in save_json_calls] == [1, 2]


def test_forces_type_release_overriding_any_caller_supplied_type(
    collect_release_calls, save_json_calls
):
    results = _FakePaginatedList([[_release(1)]])
    client = _FakeClient(results)

    list(collect_search_releases(client, limit=5, style="Minimal", type="master"))

    assert client.search_calls == [{"style": "Minimal", "type": "release"}]


def test_skips_master_entries_without_crashing(collect_release_calls, save_json_calls):
    results = _FakePaginatedList([[_master(100), _release(1), _master(200), _release(2)]])
    client = _FakeClient(results)

    result = list(collect_search_releases(client, limit=10, style="Minimal"))

    assert result == [1, 2]
    assert [id_ for _, id_, _ in save_json_calls] == [1, 2]


def test_empty_results_yields_nothing():
    client = _FakeClient(_FakePaginatedList([]))

    result = list(collect_search_releases(client, limit=5, style="Minimal"))

    assert result == []


def test_limit_less_than_one_raises_value_error():
    client = _FakeClient(_FakePaginatedList([]))

    with pytest.raises(ValueError):
        list(collect_search_releases(client, limit=0, style="Minimal"))


def test_stops_before_fetching_a_second_page_when_limit_is_reached_within_the_first(
    collect_release_calls, save_json_calls
):
    # A single page holding more items than `limit`: reaching `limit` here
    # never requires the iterator to ask for a next page, so page 2 must
    # never be fetched. (A limit landing exactly on a page boundary would
    # still fetch one page ahead - `for x in gen: ... break` has to call
    # next() to get `x` before the loop body can decide to break - so this
    # test deliberately avoids that boundary case.)
    class _CountingFakePaginatedList(_FakePaginatedList):
        def __init__(self, pages_data):
            super().__init__(pages_data)
            self.page_fetches: list[int] = []

        def page(self, index):
            self.page_fetches.append(index)
            return super().page(index)

    results = _CountingFakePaginatedList(
        [[_release(1), _release(2), _release(3)], [_release(4)]]
    )
    client = _FakeClient(results)

    result = list(collect_search_releases(client, limit=2, style="Minimal"))

    assert result == [1, 2]
    assert results.page_fetches == [1]
