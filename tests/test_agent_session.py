"""Tests for discogs.agent.session - human-approval flow with a scripted model."""

from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from discogs.agent import tools as agent_tools
from discogs.agent.agent import build_agent
from discogs.agent.session import run_turn
from discogs.agent.tools import RequestBudget


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def _crawl_call():
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "crawl_artist_releases", "args": {"artist_id": 1, "max_items": 2}, "id": "c1"}
        ],
    )


@pytest.fixture
def agent_and_budget(tmp_path, monkeypatch):
    fetched = []
    monkeypatch.setattr(
        agent_tools.artist,
        "collect_artist_releases",
        lambda c, aid: iter(fetched.append(1) or [10, 11]),
    )
    budget = RequestBudget(5)
    model = ScriptedModel(messages=iter([_crawl_call(), AIMessage(content="Fetched them.")]))
    agent = build_agent(SimpleNamespace(), model=model, budget=budget, repo_root=tmp_path)
    return agent, budget, fetched


def test_crawl_runs_only_after_approval(agent_and_budget):
    agent, budget, _ = agent_and_budget
    asked = []

    def approve(name, args):
        asked.append((name, args))
        return True

    reply = run_turn(agent, "crawl artist 1", "t1", approve)

    assert asked == [("crawl_artist_releases", {"artist_id": 1, "max_items": 2})]
    assert reply == "Fetched them."
    assert budget.used == 2


def test_rejected_crawl_makes_no_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(
        agent_tools.artist, "collect_artist_releases", lambda c, aid: iter([10, 11])
    )
    budget = RequestBudget(5)
    model = ScriptedModel(messages=iter([_crawl_call(), AIMessage(content="Okay, skipped.")]))
    agent = build_agent(SimpleNamespace(), model=model, budget=budget, repo_root=tmp_path)

    reply = run_turn(agent, "crawl artist 1", "t2", lambda name, args: False)

    assert reply == "Okay, skipped."
    assert budget.used == 0
