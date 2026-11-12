#!/usr/bin/env python
"""Chat with the Discogs Deep Agents agent.

Run from the repo root with the venv active:

    python scripts/chat.py                      # new conversation thread
    python scripts/chat.py --thread my-session  # resume a previous thread
    python scripts/chat.py --budget 300         # allow more Discogs requests this run

Needs OPENAI_API_KEY and DISCOGS_USER_TOKEN (environment or .env). Override the model with
DISCOGS_AGENT_MODEL, e.g. "openai:gpt-5".
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

# Let `python scripts/chat.py` find the `discogs` package without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from discogs.agent.agent import DEFAULT_BUDGET, build_agent  # noqa: E402
from discogs.agent.session import run_turn  # noqa: E402
from discogs.agent.tools import RequestBudget  # noqa: E402


def _ask_approval(tool_name: str, args: dict) -> bool:
    answer = input(f"\n  Agent wants to run {tool_name}({json.dumps(args)}). Allow? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--thread", default=f"chat-{uuid.uuid4().hex[:8]}")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="max Discogs requests")
    args = parser.parse_args()

    budget = RequestBudget(args.budget)
    agent = build_agent(budget=budget)
    print(f"Thread: {args.thread}  (resume with --thread {args.thread}). Empty line to quit.")

    while True:
        text = input("\nyou> ").strip()
        if not text:
            break
        print("\nagent>", run_turn(agent, text, args.thread, _ask_approval))
        print(f"[requests used: {budget.used}/{budget.limit}]")


if __name__ == "__main__":
    main()
