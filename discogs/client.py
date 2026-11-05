"""Discogs API client factory.

Builds an authenticated `discogs_client.Client`, reading the user token from
the `DISCOGS_USER_TOKEN` environment variable.
"""

import os

import discogs_client
from dotenv import load_dotenv

from discogs.ratelimit import ThrottledFetcher

USER_AGENT = "discogs-data-collector/0.1"


def get_client() -> discogs_client.Client:
    """Return an authenticated Discogs API client.

    Reads the user token from the `DISCOGS_USER_TOKEN` environment variable,
    loading it from a `.env` file at the repo root if present (existing
    environment variables always take precedence over `.env`).

    Raises:
        RuntimeError: if `DISCOGS_USER_TOKEN` is unset or empty.
    """
    load_dotenv()
    token = os.environ.get("DISCOGS_USER_TOKEN")
    if not token:
        raise RuntimeError(
            "DISCOGS_USER_TOKEN is not set. Generate a personal token at "
            "https://www.discogs.com/settings/developers, then set it in your "
            "environment (see .env.example)."
        )
    client = discogs_client.Client(USER_AGENT, user_token=token)
    client._fetcher = ThrottledFetcher(token)  # paces requests + retries 5xx (see ratelimit.py)
    return client
