"""Fetch and print Discogs release metadata for a DJ EP/release URL.

Discogs release pages are served behind a Cloudflare bot challenge, so a plain
HTTP fetch of the HTML page returns a 403 "Just a moment..." page instead of
content. This script instead extracts the release ID from the URL and calls
Discogs' public REST API (api.discogs.com), which returns the same
information (title, artists, label, year, genres/styles, tracklist) as JSON.

Usage:
    python discogs_release_reader.py [URL]

If no URL is given, defaults to the MyMy & Emika "Price Tag EP" release.
"""

import argparse
import re
import sys

import requests

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="Discogs release URL")
    args = parser.parse_args()

    try:
        release_id = extract_release_id(args.url)
        data = fetch_release(release_id)
    except (ValueError, requests.RequestException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(format_release(data))


if __name__ == "__main__":
    main()
