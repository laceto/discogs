"""Tests for discogs.collectors.master. No live API calls.

`_FakeVersionsList` stands in for `Master.versions` (a
`discogs_client.models.PaginatedList` of `Release` objects): it exposes the
same `.pages` / `.page(index)` interface `_pagination.iter_paginated` needs,
without any network layer. Each fake "version" only needs an `.id` attribute
-- that's the only thing `collect_master_versions` reads off it directly.
`collect_release` and `storage.save_json` are mocked rather than exercised
for real, since they're already covered by their own test modules.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import call, patch

from discogs.collectors.master import collect_master_versions


class _FakeVersionsList:
    """Fake PaginatedList: `pages_data[i]` is the (1-indexed) item list for page i+1."""

    def __init__(self, pages_data: list[list[Any]]):
        self._pages_data = pages_data
        self.pages = len(pages_data)

    def page(self, index: int) -> list[Any]:
        return self._pages_data[index - 1]


def _version(release_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=release_id)


class _FakeMaster:
    def __init__(self, versions: _FakeVersionsList):
        self.versions = versions


class _FakeClient:
    """Stands in for discogs_client.Client: .master(id) returns a canned Master."""

    def __init__(self, master: _FakeMaster):
        self._master = master

    def master(self, master_id: int) -> _FakeMaster:
        return self._master


@patch("discogs.collectors.master.save_json")
@patch("discogs.collectors.master.collect_release")
def test_collect_master_versions_calls_collect_release_and_save_json_per_release(
    mock_collect_release, mock_save_json
):
    versions = _FakeVersionsList([[_version(101), _version(102)], [_version(103)]])
    client = _FakeClient(_FakeMaster(versions))

    fake_records = {101: {"id": 101}, 102: {"id": 102}, 103: {"id": 103}}
    mock_collect_release.side_effect = lambda _client, release_id: fake_records[release_id]

    result = collect_master_versions(client, 999)

    assert result == [101, 102, 103]
    assert mock_collect_release.call_args_list == [
        call(client, 101),
        call(client, 102),
        call(client, 103),
    ]
    assert mock_save_json.call_args_list == [
        call("release", 101, fake_records[101]),
        call("release", 102, fake_records[102]),
        call("release", 103, fake_records[103]),
    ]


@patch("discogs.collectors.master.save_json")
@patch("discogs.collectors.master.collect_release")
def test_collect_master_versions_empty_master_returns_empty_list(
    mock_collect_release, mock_save_json
):
    client = _FakeClient(_FakeMaster(_FakeVersionsList([])))

    result = collect_master_versions(client, 999)

    assert result == []
    mock_collect_release.assert_not_called()
    mock_save_json.assert_not_called()


@patch("discogs.collectors.master.save_json")
@patch("discogs.collectors.master.collect_release")
def test_collect_master_versions_single_page_single_version(
    mock_collect_release, mock_save_json
):
    client = _FakeClient(_FakeMaster(_FakeVersionsList([[_version(2303570)]])))
    mock_collect_release.return_value = {"id": 2303570}

    result = collect_master_versions(client, 42)

    assert result == [2303570]
    mock_collect_release.assert_called_once_with(client, 2303570)
    mock_save_json.assert_called_once_with("release", 2303570, {"id": 2303570})
