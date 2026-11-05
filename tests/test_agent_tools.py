"""Tests for discogs.agent.tools - no network: collectors are monkeypatched."""

from types import SimpleNamespace

import pytest

from discogs import storage
from discogs.agent import tools as agent_tools
from discogs.agent.tools import BudgetExhausted, RequestBudget, build_tools

RELEASE = {
    "id": 7,
    "title": "Miracel Whop",
    "year": 2006,
    "genres": ["Electronic"],
    "styles": ["Techno"],
    "labels": [{"name": "Platzhirsch", "catno": "P08"}],
    "tracklist": [{"position": "A1", "title": "x", "duration": "8:02"}],
    "master_id": 31183,
    "community": {"have": 1, "contributors": ["a"]},
}


def _tool(tool_list, name):
    return next(t for t in tool_list if t.name == name)


@pytest.fixture
def tool_list(monkeypatch):
    monkeypatch.setattr(
        agent_tools.release, "collect_release", lambda c, rid: {**RELEASE, "id": rid}
    )
    monkeypatch.setattr(
        agent_tools.artist, "collect_artist_profile", lambda c, aid: {"id": aid, "name": "A"}
    )
    return build_tools(client=SimpleNamespace(), budget=RequestBudget(3))


def test_budget_charges_and_refuses():
    budget = RequestBudget(2)
    budget.charge()
    budget.charge()
    with pytest.raises(BudgetExhausted):
        budget.charge()
    assert budget.remaining == 0


def test_get_release_saves_full_record_returns_summary(tool_list):
    result = _tool(tool_list, "get_release").invoke({"release_id": 7})
    assert result["title"] == "Miracel Whop"
    assert result["tracks"] == 1
    assert "tracklist" not in result  # summary only
    assert storage.load_json("release", 7)["tracklist"]  # full record persisted


def test_tool_refuses_when_budget_spent_and_error_is_text(tool_list):
    get_release = _tool(tool_list, "get_release")
    for rid in (1, 2, 3):
        get_release.invoke({"release_id": rid})
    message = get_release.invoke({"release_id": 4})
    assert "budget exhausted" in message.lower()
    assert _tool(tool_list, "remaining_budget").invoke({})["remaining"] == 0


def test_crawl_is_capped_by_max_items_and_budget(tool_list, monkeypatch):
    monkeypatch.setattr(
        agent_tools.artist, "collect_artist_releases", lambda c, aid: iter(range(100, 200))
    )
    result = _tool(tool_list, "crawl_artist_releases").invoke({"artist_id": 1, "max_items": 50})
    assert result["collected"] == 3  # budget of 3 wins over max_items=50
    assert result["release_ids"] == [100, 101, 102]


def test_crawl_master_versions_refuses_when_count_exceeds_budget(tool_list):
    client = SimpleNamespace(master=lambda mid: SimpleNamespace(versions=SimpleNamespace(count=10)))
    local = build_tools(client=client, budget=RequestBudget(3))
    message = _tool(local, "crawl_master_versions").invoke({"master_id": 1})
    assert "budget exhausted" in message.lower()


def test_search_passes_only_given_fields(tool_list, monkeypatch):
    seen = {}

    def fake_search(client, limit, **fields):
        seen.update(fields, limit=limit)
        return iter([1, 2])

    monkeypatch.setattr(agent_tools.search, "collect_search_releases", fake_search)
    result = _tool(tool_list, "search_releases").invoke({"limit": 2, "style": "Techno"})
    assert seen == {"style": "Techno", "limit": 2}
    assert result["release_ids"] == [1, 2]


def test_list_and_load_saved_use_local_data_without_budget(tool_list):
    storage.save_json("release", 9, RELEASE)
    assert _tool(tool_list, "list_saved").invoke({"entity_type": "release"})["ids"] == ["9"]
    loaded = _tool(tool_list, "load_saved").invoke({"entity_type": "release", "entity_id": "9"})
    assert loaded["found"] and "community" not in loaded["record"]
    assert _tool(tool_list, "load_saved").invoke({"entity_type": "release", "entity_id": "x"}) == {
        "found": False
    }
    assert _tool(tool_list, "remaining_budget").invoke({})["used"] == 0


def test_entity_type_rejects_path_traversal(tool_list):
    message = _tool(tool_list, "list_saved").invoke({"entity_type": "../.."})
    assert "invalid entity_type" in message.lower()
