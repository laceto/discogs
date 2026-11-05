"""Tests for discogs.client. No live network calls."""

import discogs_client
import pytest

from discogs.client import get_client


def test_get_client_returns_client_instance_when_token_set(monkeypatch):
    monkeypatch.setenv("DISCOGS_USER_TOKEN", "fake-token")

    client = get_client()

    assert isinstance(client, discogs_client.Client)


def test_get_client_raises_when_token_unset(monkeypatch):
    monkeypatch.delenv("DISCOGS_USER_TOKEN", raising=False)
    # get_client() calls load_dotenv(), which would otherwise pick up a real
    # DISCOGS_USER_TOKEN from this repo's own .env file and mask the case
    # under test — stub it out so this test only exercises "truly unset".
    monkeypatch.setattr("discogs.client.load_dotenv", lambda *a, **kw: False)

    with pytest.raises(RuntimeError):
        get_client()
