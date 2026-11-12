"""Deep Agents agent for the Discogs collectors.

`build_agent()` wires together:
- the collector tools (`tools.build_tools`) sharing one `RequestBudget`;
- `docs/architecture.md` + `docs/schemas.md` as read-only memory, plus a writable notes file
  (`data/_agent/notes.md`) that persists what the agent learned across sessions;
- a filesystem sandbox: the agent may read `docs/` and `data/`, write only `data/_agent/`,
  and can never touch anything else in the repo (notably `.env`, which holds API keys);
- a SQLite checkpointer so a conversation (thread) can be resumed after a restart;
- human approval before any tool that can trigger many API calls.
"""

import os
import sqlite3
from pathlib import Path
from typing import Any

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.sqlite import SqliteSaver

from discogs.agent.tools import RequestBudget, build_tools

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL = "openai:gpt-5"
DEFAULT_BUDGET = 100
MODEL_MAX_RETRIES = 6  # ride out transient connection errors during long runs
NOTES_PATH = "/data/_agent/notes.md"
MEMORY_FILES = ["/docs/architecture.md", "/docs/schemas.md", NOTES_PATH]
APPROVAL_REQUIRED_TOOLS = (
    "crawl_artist_releases",
    "crawl_label_releases",
    "crawl_master_versions",
    "search_releases",
)

SYSTEM_PROMPT = """\
You are a research assistant for a local Discogs data collection (see your memory for the \
architecture and storage schema).

Rules:
- Discogs allows ~60 requests/minute and this run has a hard request budget. Check \
`remaining_budget` before bulk work and never try to work around a budget error: stop and report.
- Prefer saved data: use `list_saved` / `load_saved` before any tool that calls the Discogs API.
- A master id is not a release id. To get a master's details, use its main_release.
- Full records are stored on disk by the tools; tool results are summaries. Read the JSON under \
/data when you need detail (tracklists, credits).
- You may read /docs and /data. Only /data/_agent/notes.md is writable: record durable facts \
there (what has been crawled, gaps, id mappings). Never store credentials anywhere.
- Plan multi-step work with write_todos, and report concisely what was fetched vs. already saved.
"""


def _permissions() -> list[FilesystemPermission]:
    """First match wins: notes are read/write, docs+data read-only, everything else denied."""
    return [
        FilesystemPermission(operations=["read", "write"], paths=["/data/_agent/**"]),
        FilesystemPermission(operations=["read"], paths=["/docs/**", "/data/**"]),
        # `**` does not match dotfiles (wcmatch default), so `/.env` and `/.git/...` need their
        # own patterns - a bare "/**" deny would silently leave secrets readable.
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/**", "/.*", "/.*/**", "/**/.*", "/**/.*/**"],
            mode="deny",
        ),
    ]


def _ensure_notes(repo_root: Path) -> None:
    notes = repo_root / NOTES_PATH.lstrip("/")
    if not notes.exists():
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text("# Agent notes\n\nDurable learnings about the Discogs data.\n", "utf-8")


def build_agent(
    client: Any | None = None,
    *,
    model: Any | None = None,
    budget: RequestBudget | None = None,
    repo_root: Path | None = None,
) -> Any:
    """Build the compiled Deep Agents graph.

    `model` is a LangChain model or "provider:name" string; it defaults to the
    `DISCOGS_AGENT_MODEL` env var, then `DEFAULT_MODEL`. OpenAI models read `OPENAI_API_KEY`.
    `budget` defaults to `DISCOGS_AGENT_BUDGET` env var, then `DEFAULT_BUDGET` requests.
    """
    load_dotenv()
    root = repo_root if repo_root is not None else _REPO_ROOT
    if client is None:
        from discogs.client import get_client  # deferred: needs DISCOGS_USER_TOKEN

        client = get_client()
    if budget is None:
        budget = RequestBudget(int(os.environ.get("DISCOGS_AGENT_BUDGET", DEFAULT_BUDGET)))
    if model is None:
        model = os.environ.get("DISCOGS_AGENT_MODEL", DEFAULT_MODEL)
    if isinstance(model, str):
        model = init_chat_model(model, max_retries=MODEL_MAX_RETRIES)

    _ensure_notes(root)
    checkpoint_db = root / "data" / "_agent" / "checkpoints.sqlite"
    checkpointer = SqliteSaver(sqlite3.connect(checkpoint_db, check_same_thread=False))

    return create_deep_agent(
        model=model,
        tools=build_tools(client, budget),
        system_prompt=SYSTEM_PROMPT,
        memory=MEMORY_FILES,
        backend=FilesystemBackend(root_dir=root, virtual_mode=True),
        permissions=_permissions(),
        interrupt_on={name: True for name in APPROVAL_REQUIRED_TOOLS},
        checkpointer=checkpointer,
        name="discogs-agent",
    )
