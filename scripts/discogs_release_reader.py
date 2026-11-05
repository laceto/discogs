"""Fetch and print Discogs release metadata for a DJ EP/release URL.

Discogs release pages are served behind a Cloudflare bot challenge, so a plain
HTTP fetch of the HTML page returns a 403 "Just a moment..." page instead of
content. This script instead extracts the release ID from the URL and calls
Discogs' public REST API (api.discogs.com), which returns the same
information (title, artists, label, year, genres/styles, tracklist) as JSON.

Usage:
    python discogs_release_reader.py [URL]
    python discogs_release_reader.py [URL] --full

If no URL is given, defaults to the MyMy & Emika "Price Tag EP" release. The
default behavior (no flag) is unauthenticated and unchanged: it fetches the
public REST API directly and prints a summary. Passing --full additionally
builds an authenticated client (discogs.client.get_client, requires
DISCOGS_USER_TOKEN), collects full release detail plus marketplace stats and
price suggestions (discogs.collectors.release), and persists the result to
data/release/<id>.json (discogs.storage.save_json).
"""

import argparse
import re
import sys

import requests

from discogs.client import get_client
from discogs.collectors.release import (
    collect_marketplace_stats,
    collect_price_suggestions,
    collect_release,
)
from discogs.storage import save_json

DEFAULT_URL = "https://www.discogs.com/it/release/2051210-MyMy-Emika-Price-Tag-EP"
API_BASE = "https://api.discogs.com/releases"
USER_AGENT = "djia-discogs-release-reader/1.0"


def extract_release_id(url: str) -> str:
    match = re.search(r"/release/(\d+)", url)
    if not match:
        raise ValueError(f"could not find a release ID in URL: {url}")
    return match.group(1)


def fetch_release(release_id: str) -> dict:
    response = requests.get(
        f"{API_BASE}/{release_id}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def format_release(data: dict) -> str:
    artists = ", ".join(a["name"] for a in data.get("artists", []))
    labels = ", ".join(
        f"{label['name']} ({label['catno']})" for label in data.get("labels", [])
    )
    genres = ", ".join(data.get("genres", []))
    styles = ", ".join(data.get("styles", []))

    lines = [
        f"{artists} - {data.get('title', '?')}",
        f"Label:   {labels or '?'}",
        f"Year:    {data.get('year', '?')}",
        f"Genres:  {genres or '?'}",
        f"Styles:  {styles or '?'}",
        "Tracklist:",
    ]
    for track in data.get("tracklist", []):
        position = track.get("position", "").strip()
        title = track.get("title", "")
        duration = track.get("duration", "")
        prefix = f"  {position}" if position else "  "
        suffix = f" ({duration})" if duration else ""
        lines.append(f"{prefix}\t{title}{suffix}")

    return "\n".join(lines)


def collect_full_release(release_id: str):
    """Build an authenticated client, collect full release detail + marketplace/
    price data, and persist it to data/release/<id>.json. Returns the path written to.
    """
    client = get_client()
    record = collect_release(client, release_id)
    record["marketplace_stats"] = collect_marketplace_stats(client, release_id)
    record["price_suggestions"] = collect_price_suggestions(client, release_id)
    return save_json("release", release_id, record)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="Discogs release URL")
    parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "also collect full detail via an authenticated client and persist it to "
            "data/release/<id>.json"
        ),
    )
    args = parser.parse_args()

    try:
        release_id = extract_release_id(args.url)
        data = fetch_release(release_id)
    except (ValueError, requests.RequestException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(format_release(data))

    if args.full:
        try:
            path = collect_full_release(release_id)
        except Exception as exc:  # noqa: BLE001 - surface any collector/auth failure clearly
            print(f"error collecting full detail: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"\nFull detail saved to {path}")


if __name__ == "__main__":
    main()
