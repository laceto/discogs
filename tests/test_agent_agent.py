"""Tests for discogs.agent.agent - scripted fake model, no network, no API key."""

from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from discogs.agent.agent import MEMORY_FILES, NOTES_PATH, build_agent
from discogs.agent.tools import RequestBudget

SECRET = "sk-super-secret-value"


class ScriptedModel(GenericFakeChatModel):
    """Fake chat model that replays scripted AIMessages and tolerates bind_tools()."""

    def bind_tools(self, tools, **kwargs):
        return self


def _call(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "architecture.md").write_text("ARCH-MARKER", "utf-8")
    (tmp_path / "docs" / "schemas.md").write_text("SCHEMA-MARKER", "utf-8")
    (tmp_path / "data" / "release").mkdir(parents=True)
    (tmp_path / "data" / "release" / "1.json").write_text('{"id": 1}', "utf-8")
    (tmp_path / ".env").write_text(f"OPENAI_API_KEY={SECRET}", "utf-8")
    return tmp_path


def _run(repo, messages, thread="t"):
    agent = build_agent(
        SimpleNamespace(),
        model=ScriptedModel(messages=iter(messages)),
        budget=RequestBudget(5),
        repo_root=repo,
    )
    config = {"configurable": {"thread_id": thread}}
    return agent.invoke({"messages": [("user", "go")]}, config)


def _tool_outputs(result):
    return [str(m.content) for m in result["messages"] if m.type == "tool"]


def test_agent_cannot_read_env_secrets(repo):
    result = _run(repo, [_call("read_file", {"file_path": "/.env"}), AIMessage(content="done")])
    output = " ".join(_tool_outputs(result))
    assert SECRET not in output
    assert "permission" in output.lower() or "denied" in output.lower()


@pytest.mark.parametrize("secret_path", ["/.env", "/docs/.env", "/data/.env", "/.git/config"])
def test_dotfiles_anywhere_are_denied(repo, secret_path):
    target = repo / secret_path.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"KEY={SECRET}", "utf-8")
    result = _run(repo, [_call("read_file", {"file_path": secret_path}), AIMessage(content="ok")])
    assert SECRET not in " ".join(_tool_outputs(result))


def test_agent_can_read_data_but_not_write_docs(repo):
    result = _run(
        repo,
        [
            _call("read_file", {"file_path": "/data/release/1.json"}, "c1"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": "/docs/architecture.md", "content": "pwned"},
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(content="done"),
        ],
    )
    outputs = _tool_outputs(result)
    assert '"id": 1' in outputs[0]
    assert "denied" in outputs[1].lower() or "permission" in outputs[1].lower()
    assert (repo / "docs" / "architecture.md").read_text("utf-8") == "ARCH-MARKER"


def test_agent_can_write_its_notes_file(repo):
    new = "# Agent notes\n\nGabriel Ananda is id 20119\n"
    _run(
        repo,
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": "/data/_agent/other.md", "content": new},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="done"),
        ],
    )
    assert (repo / "data" / "_agent" / "other.md").read_text("utf-8") == new


def test_notes_file_is_created_and_listed_as_memory(repo):
    _run(repo, [AIMessage(content="hi")])
    assert (repo / NOTES_PATH.lstrip("/")).exists()
    assert NOTES_PATH in MEMORY_FILES and "/docs/schemas.md" in MEMORY_FILES


def test_collector_tools_are_registered(repo):
    agent = build_agent(SimpleNamespace(), model=ScriptedModel(messages=iter([])), repo_root=repo)
    tool_node = agent.get_graph().nodes["tools"].data
    names = set(tool_node.tools_by_name)
    assert {"get_release", "crawl_artist_releases", "load_saved", "remaining_budget"} <= names
