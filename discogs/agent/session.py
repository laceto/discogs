"""Run one user turn against the agent, handling human-approval pauses.

Tools listed in `agent.APPROVAL_REQUIRED_TOOLS` pause the graph before running. `run_turn`
shows each pending call to `approve` (a callback returning True/False) and resumes the graph
with the decisions until the agent produces a final answer.
"""

from collections.abc import Callable
from typing import Any

from langgraph.types import Command

Approver = Callable[[str, dict[str, Any]], bool]


def _final_text(result: dict[str, Any]) -> str:
    content = result["messages"][-1].content
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if isinstance(part, dict))


def run_turn(agent: Any, text: str, thread_id: str, approve: Approver) -> str:
    """Send `text` on conversation `thread_id`; return the agent's final reply."""
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke({"messages": [("user", text)]}, config)

    while result.get("__interrupt__"):
        decisions: list[dict[str, Any]] = []
        for interrupt in result["__interrupt__"]:
            for request in interrupt.value["action_requests"]:
                ok = approve(request["name"], request["args"])
                decisions.append(
                    {"type": "approve"}
                    if ok
                    else {"type": "reject", "message": "The user declined this call."}
                )
        result = agent.invoke(Command(resume={"decisions": decisions}), config)

    return _final_text(result)
