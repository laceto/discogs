"""Tests for discogs.ratelimit - fake clock and fake HTTP, no sleeping, no network."""

from types import SimpleNamespace

import pytest
from discogs_client.fetchers import UserTokenRequestsFetcher

from discogs.ratelimit import ThrottledFetcher


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _response(status=200, remaining="50"):
    return SimpleNamespace(
        status_code=status, content=b"{}", headers={"X-Discogs-Ratelimit-Remaining": remaining}
    )


@pytest.fixture
def fake_time():
    return FakeTime()


def _fetcher(fake_time, monkeypatch, responses):
    """ThrottledFetcher whose underlying HTTP call returns `responses` in order."""
    fetcher = ThrottledFetcher("tok", clock=fake_time.clock, sleep=fake_time.sleep)
    calls = iter(responses)
    monkeypatch.setattr(UserTokenRequestsFetcher, "request", lambda self, *a, **kw: next(calls))
    return fetcher


def test_requests_are_spaced_by_min_interval(fake_time, monkeypatch):
    fetcher = _fetcher(fake_time, monkeypatch, [_response(), _response(), _response()])
    for _ in range(3):
        fetcher.request("GET", "u", None, {})
    # first call immediate, the next two each wait min_interval (clock advances only by sleeps)
    assert fake_time.sleeps == pytest.approx([fetcher.min_interval, fetcher.min_interval])


def test_pauses_a_full_window_when_remaining_is_low(fake_time, monkeypatch):
    fetcher = _fetcher(fake_time, monkeypatch, [_response(remaining="1"), _response()])
    fetcher.request("GET", "u", None, {})
    assert 60.0 in fake_time.sleeps


def test_retries_5xx_then_succeeds(fake_time, monkeypatch):
    fetcher = _fetcher(fake_time, monkeypatch, [_response(502), _response(503), _response(200)])
    assert fetcher.request("GET", "u", None, {}).status_code == 200
    assert 5.0 in fake_time.sleeps and 10.0 in fake_time.sleeps  # linear 5s, 10s backoff


def test_gives_up_after_retries_and_returns_last_5xx(fake_time, monkeypatch):
    fetcher = _fetcher(fake_time, monkeypatch, [_response(500)] * 5)
    assert fetcher.request("GET", "u", None, {}).status_code == 500


def test_get_client_uses_throttled_fetcher(monkeypatch):
    from discogs.client import get_client

    monkeypatch.setenv("DISCOGS_USER_TOKEN", "fake-token")
    assert isinstance(get_client()._fetcher, ThrottledFetcher)
