"""LangChain tools that expose the repo's Discogs collectors to an agent.

`build_tools(client, budget)` returns the tool list. Design rules:

- Every API-backed tool charges a shared `RequestBudget` and refuses once it is spent, so an
  agent cannot run away with the rate limit. Cost is counted in entity fetches (one release,
  one profile, ...); page-listing calls inside a crawl are not counted individually.
- Tools return SHORT summaries, never the full record: the full JSON is already persisted by
  `discogs.storage` and can be read back with `load_saved`, keeping the agent's context small.
- Errors surface as text to the agent (`handle_tool_error=True`) instead of crashing the run.
"""

import functools
import re
from collections.abc import Callable, Iterable
from itertools import islice
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, ToolException

from discogs import storage
from discogs.collectors import artist, label, master, release, search

_ENTITY_TYPE = re.compile(r"^[a-z_]+$")


class BudgetExhausted(Exception):
    """Raised when a tool needs more requests than the run's budget has left."""


class RequestBudget:
    """Counts Discogs requests for one agent run and refuses to go over `limit`."""

    def __init__(self, limit: int) -> None:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit}")
        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def charge(self, cost: int = 1) -> None:
        if cost > self.remaining:
            raise BudgetExhausted(
                f"Request budget exhausted: needs {cost}, only {self.remaining} of "
                f"{self.limit} left. Stop calling Discogs and report what you have."
            )
        self.used += cost


def summarize_release(record: dict[str, Any]) -> dict[str, Any]:
    """Compact view of a release record (the full JSON stays on disk)."""
    return {
        "id": record.get("id"),
        "title": record.get("title"),
        "year": record.get("year"),
        "genres": record.get("genres"),
        "styles": record.get("styles"),
        "labels": [lab.get("name") for lab in record.get("labels", [])],
        "tracks": len(record.get("tracklist", [])),
        "master_id": record.get("master_id"),
    }


def _summarize_profile(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "real_name": record.get("real_name"),
        "aliases": [a.get("name") for a in record.get("aliases", [])],
        "groups": [g.get("name") for g in record.get("groups", [])],
        "urls": record.get("urls", []),
    }


def _as_tool_error(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Re-raise any exception as ToolException so the agent sees it as text and can adapt."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            raise ToolException(f"{type(exc).__name__}: {exc}") from exc

    return wrapper


def _check_entity_type(entity_type: str) -> None:
    if not _ENTITY_TYPE.match(entity_type):
        raise ValueError(f"Invalid entity_type {entity_type!r}: use lowercase letters/underscores.")


def build_tools(client: Any, budget: RequestBudget) -> list[BaseTool]:
    """Build all agent tools bound to `client` and sharing `budget`."""

    def remaining_budget() -> dict[str, int]:
        """How many Discogs requests this run may still make."""
        return {"used": budget.used, "remaining": budget.remaining, "limit": budget.limit}

    def get_artist_profile(artist_id: int) -> dict[str, Any]:
        """Fetch an artist's profile (name, aliases, groups, links) and save it. 1 request."""
        budget.charge()
        record = artist.collect_artist_profile(client, artist_id)
        storage.save_json("artist", artist_id, record)
        return _summarize_profile(record)

    def get_label(label_id: int) -> dict[str, Any]:
        """Fetch a label's profile and save it to data/label. 1 request."""
        budget.charge()
        record = label.collect_label(client, label_id)
        storage.save_json("label", label_id, record)
        return {k: record.get(k) for k in ("id", "name", "profile", "contact_info", "url")}

    def get_release(release_id: int) -> dict[str, Any]:
        """Fetch a full release (genres, styles, tracklist, credits) and save it. 1 request.

        Needs a RELEASE id. A master id is a different thing: use a master's main_release.
        """
        budget.charge()
        record = release.collect_release(client, release_id)
        storage.save_json("release", release_id, record)
        return summarize_release(record)

    def get_marketplace_stats(release_id: int) -> dict[str, Any]:
        """Live marketplace stats (num for sale, lowest price) for a release. 1 request."""
        budget.charge()
        return release.collect_marketplace_stats(client, release_id)

    def get_price_suggestions(release_id: int) -> dict[str, Any]:
        """Suggested price per condition grade for a release. 1 request."""
        budget.charge()
        return release.collect_price_suggestions(client, release_id)

    def _run_crawl(ids: Iterable[int], max_items: int) -> dict[str, Any]:
        cap = min(max_items, budget.remaining)
        if cap < 1:
            raise BudgetExhausted("No request budget left for a crawl.")
        collected: list[int] = []
        for release_id in islice(ids, cap):
            budget.charge()
            collected.append(release_id)
        return {"collected": len(collected), "release_ids": collected, "cap_applied": cap}

    def crawl_artist_releases(artist_id: int, max_items: int = 20) -> dict[str, Any]:
        """Fetch + save up to max_items of an artist's releases (masters are skipped)."""
        return _run_crawl(artist.collect_artist_releases(client, artist_id), max_items)

    def crawl_label_releases(label_id: int, max_items: int = 20) -> dict[str, Any]:
        """Fetch + save up to max_items of a label's releases."""
        return _run_crawl(label.collect_label_releases(client, label_id), max_items)

    def crawl_master_versions(master_id: int) -> dict[str, Any]:
        """Fetch + save every version of a master. Refuses if it would exceed the budget."""
        count = client.master(master_id).versions.count
        budget.charge(count)
        ids = master.collect_master_versions(client, master_id)
        return {"collected": len(ids), "release_ids": ids}

    def search_releases(
        limit: int = 10,
        genre: str | None = None,
        style: str | None = None,
        year: str | None = None,
        country: str | None = None,
        label_name: str | None = None,
        artist_name: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Search Discogs releases, then fetch + save up to `limit` matches."""
        fields = {
            "genre": genre,
            "style": style,
            "year": year,
            "country": country,
            "label": label_name,
            "artist": artist_name,
            "q": query,
        }
        given = {k: v for k, v in fields.items() if v}
        cap = min(limit, budget.remaining)
        if cap < 1:
            raise BudgetExhausted("No request budget left for a search.")
        return _run_crawl(search.collect_search_releases(client, cap, **given), cap)

    def list_saved(entity_type: str) -> dict[str, Any]:
        """List ids already saved locally for an entity type (release, artist, label, ...)."""
        _check_entity_type(entity_type)
        ids = storage.list_ids(entity_type)
        return {"entity_type": entity_type, "count": len(ids), "ids": ids[:200]}

    def load_saved(entity_type: str, entity_id: str) -> dict[str, Any]:
        """Read a saved record from local data/ with no API call. Prefer this over refetching."""
        _check_entity_type(entity_type)
        record = storage.load_json(entity_type, entity_id)
        if record is None:
            return {"found": False}
        record.pop("community", None)  # contributor lists are long and rarely useful
        return {"found": True, "record": record}

    functions: list[Callable[..., Any]] = [
        remaining_budget,
        get_artist_profile,
        get_label,
        get_release,
        get_marketplace_stats,
        get_price_suggestions,
        crawl_artist_releases,
        crawl_label_releases,
        crawl_master_versions,
        search_releases,
        list_saved,
        load_saved,
    ]
    return [
        StructuredTool.from_function(_as_tool_error(fn), handle_tool_error=True, name=fn.__name__)
        for fn in functions
    ]
