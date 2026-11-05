"""Proactive rate limiting for the Discogs API (authenticated limit: 60 requests/minute).

`discogs_client` only reacts after a 429. `ThrottledFetcher` also (a) spaces requests at least
`min_interval` seconds apart, (b) pauses for the rest of the minute window when the
`X-Discogs-Ratelimit-Remaining` header says the budget is nearly spent, and (c) retries 5xx
responses, which Discogs returns intermittently on large listings.
"""

import time
from collections.abc import Callable
from typing import Any

from discogs_client.fetchers import UserTokenRequestsFetcher

MIN_INTERVAL = 1.1  # seconds between requests -> ~54/min, headroom under the 60/min limit
LOW_REMAINING = 2  # pause once this few requests are left in the window
WINDOW_SECONDS = 60.0
SERVER_ERROR_RETRIES = 4
SERVER_ERROR_BASE_DELAY = 5.0


class ThrottledFetcher(UserTokenRequestsFetcher):  # type: ignore[misc]  # discogs_client is untyped
    """User-token fetcher that paces its own requests and retries 5xx errors."""

    def __init__(
        self,
        user_token: str,
        *,
        min_interval: float = MIN_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(user_token)
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None

    def _wait_turn(self) -> None:
        if self._last_request_at is not None:
            wait = self.min_interval - (self._clock() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._clock()

    def _pause_if_nearly_spent(self, response: Any) -> None:
        remaining = response.headers.get("X-Discogs-Ratelimit-Remaining")
        if remaining is not None and int(remaining) <= LOW_REMAINING:
            self._sleep(WINDOW_SECONDS)
            self._last_request_at = self._clock()

    def request(self, method: str, url: str, data: Any, headers: Any, params: Any = None) -> Any:
        for attempt in range(SERVER_ERROR_RETRIES + 1):
            self._wait_turn()
            response = super().request(method, url, data, headers, params)
            self._pause_if_nearly_spent(response)
            if response.status_code < 500 or attempt == SERVER_ERROR_RETRIES:
                return response
            self._sleep(SERVER_ERROR_BASE_DELAY * (attempt + 1))
        return response  # unreachable; keeps type-checkers satisfied
