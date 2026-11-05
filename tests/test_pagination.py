"""Tests for discogs.collectors._pagination. No live API calls, no real sleeps.

`_FakePaginatedList` stands in for any `discogs_client.BasePaginatedResponse`
subclass (label releases, artist releases, master versions, ...): it exposes
the same `.pages` / `.page(index)` interface without any network layer.
"""

import itertools

from discogs_client.exceptions import AuthorizationError, HTTPError

from discogs.collectors._pagination import iter_paginated


class _FakePaginatedList:
    """Fake PaginatedList: `pages_data[i]` is the (1-indexed) item list for page i+1."""

    def __init__(self, pages_data: list[list[str]]):
        self._pages_data = pages_data
        self.pages = len(pages_data)
        self.page_calls: list[int] = []

    def page(self, index: int) -> list[str]:
        self.page_calls.append(index)
        return self._pages_data[index - 1]


class _FlakyPaginatedList(_FakePaginatedList):
    """Like `_FakePaginatedList`, but raises 429 on a page's first N attempts."""

    def __init__(self, pages_data: list[list[str]], fail_first_n_calls: dict[int, int]):
        super().__init__(pages_data)
        # page_index -> number of times to raise 429 before succeeding
        self._remaining_failures = dict(fail_first_n_calls)

    def page(self, index: int) -> list[str]:
        self.page_calls.append(index)
        remaining = self._remaining_failures.get(index, 0)
        if remaining > 0:
            self._remaining_failures[index] = remaining - 1
            raise HTTPError("Too Many Requests", 429)
        return self._pages_data[index - 1]


def _fake_sleep_recorder():
    calls: list[float] = []

    def sleep(seconds: float) -> None:
        calls.append(seconds)

    return sleep, calls


def test_full_iteration_yields_every_item_across_all_pages():
    paginated = _FakePaginatedList([["a", "b"], ["c"], ["d", "e", "f"]])

    items = list(iter_paginated(paginated))

    assert items == ["a", "b", "c", "d", "e", "f"]
    assert paginated.page_calls == [1, 2, 3]


def test_resuming_from_checkpoint_skips_consumed_pages_fetches_remainder():
    paginated = _FakePaginatedList([["a", "b"], ["c"], ["d", "e", "f"]])

    # Simulate a crawl that already fully consumed page 1 (checkpoint = 1);
    # resume from page 2 onward.
    items = list(iter_paginated(paginated, start_page=2))

    assert items == ["c", "d", "e", "f"]
    assert paginated.page_calls == [2, 3]
    assert 1 not in paginated.page_calls


def test_on_page_done_checkpoint_callback_fires_per_completed_page():
    paginated = _FakePaginatedList([["a"], ["b"], ["c"]])
    completed_pages: list[int] = []

    list(iter_paginated(paginated, on_page_done=completed_pages.append))

    assert completed_pages == [1, 2, 3]


def test_checkpoint_then_resume_round_trip_covers_every_item_with_no_gaps():
    pages_data = [["a", "b"], ["c"], ["d", "e", "f"]]
    paginated = _FakePaginatedList(pages_data)

    # First "run": pull only page 1's items, then stop (simulating a
    # crash/interrupt right as page 1 finishes) without ever touching page 2.
    first_run_items = list(itertools.islice(iter_paginated(paginated), len(pages_data[0])))

    assert first_run_items == ["a", "b"]
    assert paginated.page_calls == [1]  # page 2 was never fetched by the first run

    checkpoint = 1  # page 1 fully consumed

    # Second "run": resume from the page right after the checkpoint.
    second_run_items = list(iter_paginated(paginated, start_page=checkpoint + 1))

    assert second_run_items == ["c", "d", "e", "f"]
    assert paginated.page_calls == [1, 2, 3]  # page 1 was never re-fetched on resume
    assert first_run_items + second_run_items == ["a", "b", "c", "d", "e", "f"]


def test_rate_limit_429_retries_with_exponential_backoff_then_succeeds():
    paginated = _FlakyPaginatedList([["a"], ["b"]], fail_first_n_calls={2: 2})
    sleep, sleep_calls = _fake_sleep_recorder()

    items = list(iter_paginated(paginated, base_delay=1.0, sleep=sleep))

    assert items == ["a", "b"]
    # Page 2 failed twice (429) then succeeded: two backoff sleeps, doubling.
    assert sleep_calls == [1.0, 2.0]


def test_rate_limit_exhausts_max_retries_then_raises():
    paginated = _FlakyPaginatedList([["a"]], fail_first_n_calls={1: 10})
    sleep, sleep_calls = _fake_sleep_recorder()

    try:
        list(iter_paginated(paginated, max_retries=2, base_delay=0.1, sleep=sleep))
        raised = False
    except HTTPError as error:
        raised = True
        assert error.status_code == 429

    assert raised
    # 2 retries allowed -> 2 backoff sleeps before giving up.
    assert sleep_calls == [0.1, 0.2]


def test_non_rate_limit_error_propagates_immediately_without_retry():
    class _AlwaysUnauthorized(_FakePaginatedList):
        def page(self, index: int) -> list[str]:
            self.page_calls.append(index)
            raise AuthorizationError("Invalid token", 401, {})

    paginated = _AlwaysUnauthorized([["a"]])
    sleep, sleep_calls = _fake_sleep_recorder()

    try:
        list(iter_paginated(paginated, sleep=sleep))
        raised = False
    except AuthorizationError:
        raised = True

    assert raised
    assert sleep_calls == []
    assert paginated.page_calls == [1]


def test_start_page_less_than_one_raises_value_error():
    paginated = _FakePaginatedList([["a"]])

    try:
        list(iter_paginated(paginated, start_page=0))
        raised = False
    except ValueError:
        raised = True

    assert raised
