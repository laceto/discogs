"""Find releases by a Discogs artist on labels matching a pattern.

Uses MusicBrainz (public, no auth) to resolve the artist's Discogs ID,
then the public Discogs API to walk the artist's discography. Master
entries are expanded into their versions so every label is checked.
Set DISCOGS_TOKEN to raise the Discogs rate limit (25 -> 60 req/min).
"""
import argparse
import json
import os
import re
import sys
import time

import requests

UA = "laceto-discogs-check/1.0 (+https://github.com/laceto/discogs)"
DISCOGS = "https://api.discogs.com"
TOKEN = os.environ.get("DISCOGS_TOKEN") or None
DELAY = 1.1 if TOKEN else 2.5

session = requests.Session()
session.headers["User-Agent"] = UA


def discogs_get(path, **params):
    headers = {"Authorization": f"Discogs token={TOKEN}"} if TOKEN else {}
    for attempt in range(6):
        r = session.get(f"{DISCOGS}{path}", params=params, headers=headers, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        time.sleep(DELAY)
        return r.json()
    raise RuntimeError(f"rate limited on {path}")


def resolve_artist_id(name):
    if TOKEN:
        res = discogs_get("/database/search", q=name, type="artist")["results"]
        for hit in res:
            if hit["title"].lower() == name.lower():
                return hit["id"]
    r = session.get(
        "https://musicbrainz.org/ws/2/artist",
        params={"query": f'artist:"{name}"', "fmt": "json"},
        timeout=30,
    )
    r.raise_for_status()
    for art in r.json().get("artists", []):
        if art["name"].lower() != name.lower():
            continue
        time.sleep(1.1)
        d = session.get(
            f"https://musicbrainz.org/ws/2/artist/{art['id']}",
            params={"inc": "url-rels", "fmt": "json"},
            timeout=30,
        ).json()
        for rel in d.get("relations", []):
            m = re.search(r"discogs\.com/artist/(\d+)", rel.get("url", {}).get("resource", ""))
            if m:
                return int(m.group(1))
    sys.exit(f"Could not resolve a Discogs ID for {name!r}")


def paginate(path, key):
    page = 1
    while True:
        data = discogs_get(path, page=page, per_page=100)
        yield from data[key]
        if page >= data["pagination"]["pages"]:
            return
        page += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artist", required=True)
    ap.add_argument("--artist-id", type=int)
    ap.add_argument("--label-pattern", required=True, help="case-insensitive regex")
    ap.add_argument("--out", default="matches.json")
    args = ap.parse_args()
    pat = re.compile(args.label_pattern, re.I)

    artist_id = args.artist_id or resolve_artist_id(args.artist)
    artist = discogs_get(f"/artists/{artist_id}")
    print(f"Artist: {artist['name']} (Discogs ID {artist_id}) {artist.get('uri','')}")

    entries = list(paginate(f"/artists/{artist_id}/releases", "releases"))
    print(f"Discography entries: {len(entries)}")

    matches, labels_seen, errors = [], set(), []
    seen_keys = set()
    for e in entries:
        rows = []
        if e["type"] == "master":
            # Fall back to the main release's label if versions can't be fetched.
            rows.append((e.get("label", ""), "", e.get("main_release"), e.get("year", "")))
            try:
                for v in paginate(f"/masters/{e['id']}/versions", "versions"):
                    rows.append((v.get("label", ""), v.get("catno", ""), v.get("id"), v.get("released", "")))
            except Exception as exc:  # keep going; report at the end
                errors.append(f"master {e['id']} ({e['title']}): {exc}")
                print(f"WARN: {errors[-1]}")
        else:
            rows.append((e.get("label", ""), e.get("catno", ""), e["id"], e.get("year", "")))
        for label, catno, rid, year in rows:
            for lab in re.split(r",\s*", label or ""):
                labels_seen.add(lab)
                key = (rid, lab)
                if lab and pat.search(lab) and key not in seen_keys:
                    seen_keys.add(key)
                    matches.append({
                        "title": e["title"], "artist": e.get("artist"), "role": e.get("role"),
                        "label": lab, "catno": catno, "year": year,
                        "url": f"https://www.discogs.com/release/{rid}",
                    })

    with open(args.out, "w") as f:
        json.dump({"artist": artist["name"], "artist_id": artist_id,
                   "labels_seen": sorted(labels_seen), "matches": matches, "errors": errors}, f, indent=2)

    lines = [f"## {artist['name']} on labels matching `{args.label_pattern}`", ""]
    if matches:
        lines += ["| Title | Artist | Role | Label | Cat# | Year | Link |", "|---|---|---|---|---|---|---|"]
        for m in matches:
            lines.append(f"| {m['title']} | {m['artist']} | {m['role']} | {m['label']} | {m['catno']} | {m['year']} | {m['url']} |")
    else:
        lines.append("**No matching releases found.**")
    if errors:
        lines += ["", f"**{len(errors)} master(s) could not be expanded:**"] + [f"- {x}" for x in errors]
    lines += ["", f"All labels seen ({len(labels_seen)}): " + "; ".join(sorted(l for l in labels_seen if l))]
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
