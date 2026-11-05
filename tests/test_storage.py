"""Tests for discogs.storage: save_json / load_json round-trip."""

from pathlib import Path

import pytest

from discogs.storage import list_ids, load_json, save_json


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    """A temp directory standing in for data/, so tests never touch the repo's real data/."""
    return tmp_path / "data"


def test_save_json_writes_expected_file(base_dir: Path) -> None:
    record = {"id": 2303570, "title": "Me Sabe A Porro"}

    path = save_json("release", 2303570, record, base_dir=base_dir)

    expected_path = base_dir / "release" / "2303570.json"
    assert path == expected_path
    assert expected_path.exists()


def test_save_json_creates_parent_directories(base_dir: Path) -> None:
    assert not base_dir.exists()

    save_json("artist", 42, {"id": 42, "name": "Some Artist"}, base_dir=base_dir)

    assert (base_dir / "artist").is_dir()


def test_load_json_round_trip(base_dir: Path) -> None:
    record = {
        "id": 2051210,
        "title": "Price Tag EP",
        "genres": ["Electronic"],
        "styles": ["Techno", "Deep House"],
        "master_id": None,
        "community": {"want": 10, "have": 3, "rating_avg": 4.2, "rating_count": 5},
    }

    save_json("release", 2051210, record, base_dir=base_dir)
    loaded = load_json("release", 2051210, base_dir=base_dir)

    assert loaded == record


def test_load_json_missing_entity_returns_none(base_dir: Path) -> None:
    assert load_json("release", "does-not-exist", base_dir=base_dir) is None


def test_load_json_missing_entity_type_dir_returns_none(base_dir: Path) -> None:
    assert not base_dir.exists()

    assert load_json("label", 1, base_dir=base_dir) is None


def test_save_json_overwrites_existing_record(base_dir: Path) -> None:
    save_json("release", 1, {"title": "old"}, base_dir=base_dir)
    save_json("release", 1, {"title": "new"}, base_dir=base_dir)

    assert load_json("release", 1, base_dir=base_dir) == {"title": "new"}


def test_save_json_string_id(base_dir: Path) -> None:
    save_json("label", "desolat", {"name": "Desolat"}, base_dir=base_dir)

    assert load_json("label", "desolat", base_dir=base_dir) == {"name": "Desolat"}


def test_default_base_dir_resolves_under_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When base_dir is omitted, save_json/load_json fall back to <repo_root>/data."""
    import discogs.storage as storage

    fake_root = tmp_path / "fake_repo"
    monkeypatch.setattr(storage, "_REPO_ROOT", fake_root)

    path = save_json("release", 99, {"id": 99})

    assert path == fake_root / "data" / "release" / "99.json"
    assert storage.load_json("release", 99) == {"id": 99}


def test_list_ids_returns_sorted_saved_ids(tmp_path):
    save_json("release", 2, {"id": 2}, base_dir=tmp_path)
    save_json("release", 1, {"id": 1}, base_dir=tmp_path)
    assert list_ids("release", base_dir=tmp_path) == ["1", "2"]


def test_list_ids_missing_entity_type_returns_empty(tmp_path):
    assert list_ids("label", base_dir=tmp_path) == []
