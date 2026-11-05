"""Shared resumable pagination + rate-limit backoff helper for breadth collectors.

Iterates any `discogs_client`-style paginated response - anything exposing
`.pages` (total page count) and `.page(index)` (1-indexed, returns the list of
items on that page), matching `discogs_client.models.BasePaginatedResponse` -
page by page, yielding items one at a time.

Generic on purpose: this module knows nothing about releases, artists, labels,
or any other Discogs entity. It only knows how to walk pages, survive
rate-limit errors, and let a caller checkpoint/resume a crawl.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from discogs_client.exceptions import DiscogsAPIError, HTTPError

_RATE_LIMIT_STATUS_CODE = 429
DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY = 1.0


class SupportsPagination(Protocol):
    """The subset of discogs_client's BasePaginatedResponse this helper needs."""

    @property
    def pages(self) -> int: ...

    def page(self, index: int) -> list[Any]: ...


def _is_rate_limit_error(error: DiscogsAPIError) -> bool:
    return isinstance(error, HTTPError) and error.status_code == _RATE_LIMIT_STATUS_CODE


def _fetch_page_with_backoff(
    paginated: SupportsPagination,
    page_index: int,
    *,
    max_retries: int,
    base_delay: float,
    sleep: Callable[[float], None],
) -> list[Any]:
    """Fetch one page, retrying with exponential backoff on 429 rate-limit errors.

    Any other `DiscogsAPIError` (auth failure, 404, etc.) propagates immediately
    - only a 429 `HTTPError` is treated as transient and retried.
    """
    attempt = 0
    while True:
        try:
            return paginated.page(page_index)
        except DiscogsAPIError as error:
            if not _is_rate_limit_error(error) or attempt >= max_retries:
                raise
            sleep(base_delay * (2**attempt))
            attempt += 1


def iter_paginated(
    paginated: SupportsPagination,
    *,
    start_page: int = 1,
    on_page_done: Callable[[int], None] | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[Any]:
    """Yield every item across all pages of `paginated`, resumably and with backoff.

    Resuming: pass `start_page` (1-indexed, default 1) to skip pages already
    fully consumed in a prior run instead of restarting the crawl from page 1.

    Checkpointing: `on_page_done(page_index)`, if given, is called once a
    page's items have all been yielded - a caller persists that `page_index`
    (e.g. via `discogs.storage.save_json`) and passes `page_index + 1` back in
    as `start_page` on the next run to resume an interrupted crawl.

    Rate-limit backoff: a 429 `HTTPError` from `discogs_client.exceptions` is
    retried up to `max_retries` times with exponential backoff
    (`base_delay * 2**attempt` seconds between attempts) before propagating.
    Any other `DiscogsAPIError` propagates immediately without retrying.

    `paginated` only needs to expose `.pages` (total page count) and
    `.page(index)` (1-indexed) - the interface `discogs_client`'s
    `BasePaginatedResponse` (and everything that subclasses it: label
    releases, artist releases, master versions, ...) already provides. This
    function never assumes anything about what the items themselves are.
    """
    if start_page < 1:
        raise ValueError(f"start_page must be >= 1, got {start_page}")

    total_pages = paginated.pages
    for page_index in range(start_page, total_pages + 1):
        items = _fetch_page_with_backoff(
            paginated,
            page_index,
            max_retries=max_retries,
            base_delay=base_delay,
            sleep=sleep,
        )
        yield from items
        if on_page_done is not None:
            on_page_done(page_index)
