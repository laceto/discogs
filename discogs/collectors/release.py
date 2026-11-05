"""Release-detail collector: the atomic unit other collectors compose from.

`collect_release` pulls the base release fields plus artists/credits, labels,
community stats, and the master link from a single `discogs_client.Release`
object. Marketplace stats and price suggestions are volatile/separate API
calls, so they're collected by their own functions (`collect_marketplace_stats`,
`collect_price_suggestions`) rather than folded into `collect_release`.

See docs/schemas.md for the persisted record shape.
"""

from typing import Any

from discogs_client.exceptions import DiscogsAPIError

# Discogs condition grades, in Poor -> Mint order, mapped to the attribute
# name `python3-discogs-client`'s PriceSuggestions object exposes for each.
_GRADE_ATTRS = {
    "Poor (P)": "poor",
    "Fair (F)": "fair",
    "Good (G)": "good",
    "Good Plus (G+)": "good_plus",
    "Very Good (VG)": "very_good",
    "Very Good Plus (VG+)": "very_good_plus",
    "Near Mint (NM or M-)": "near_mint",
    "Mint (M)": "mint",
}


def _normalize_tracklist(release: Any) -> list[dict[str, Any]]:
    tracks = getattr(release, "tracklist", None) or []
    return [
        {
            "position": getattr(track, "position", None),
            "title": getattr(track, "title", None),
            "duration": getattr(track, "duration", None),
        }
        for track in tracks
    ]


def _normalize_artist_entry(artist: Any, *, include_join: bool) -> dict[str, Any]:
    entry = {
        "id": getattr(artist, "id", None),
        "name": getattr(artist, "name", None),
        "role": getattr(artist, "role", None) or "",
    }
    if include_join:
        entry["join"] = getattr(artist, "join", None) or ""
    return entry


def _normalize_artists(release: Any) -> list[dict[str, Any]]:
    artists = getattr(release, "artists", None) or []
    return [_normalize_artist_entry(artist, include_join=True) for artist in artists]


def _normalize_credits(release: Any) -> list[dict[str, Any]]:
    credits_ = getattr(release, "credits", None) or []
    return [_normalize_artist_entry(artist, include_join=False) for artist in credits_]


def _normalize_labels(release: Any) -> list[dict[str, Any]]:
    labels = getattr(release, "labels", None) or []
    return [
        {
            "name": getattr(label, "name", None),
            "catno": getattr(label, "catno", None),
        }
        for label in labels
    ]


def _normalize_community(release: Any) -> dict[str, Any]:
    community = getattr(release, "community", None)
    if community is None:
        return {
            "want": 0,
            "have": 0,
            "rating_avg": 0.0,
            "rating_count": 0,
            "submitter": None,
            "contributors": [],
        }

    rating = getattr(community, "rating", None)
    submitter = getattr(community, "submitter", None)
    contributors = getattr(community, "contributors", None) or []

    return {
        "want": getattr(community, "want", None) or 0,
        "have": getattr(community, "have", None) or 0,
        "rating_avg": getattr(rating, "average", None) or 0.0 if rating else 0.0,
        "rating_count": getattr(rating, "count", None) or 0 if rating else 0,
        "submitter": getattr(submitter, "username", None) if submitter else None,
        "contributors": [
            getattr(user, "username", None)
            for user in contributors
            if getattr(user, "username", None) is not None
        ],
    }


def _extract_master_id(release: Any) -> int | None:
    master = getattr(release, "master", None)
    if master is None:
        return None
    return getattr(master, "id", None)


def collect_release(client: Any, release_id: int) -> dict[str, Any]:
    """Collect full release detail for `release_id` into a plain dict.

    Covers base fields (title, year, genres, styles, country, formats, notes,
    images, url, tracklist), artists + credits (extraartists), labels,
    community stats, and the master link. See docs/schemas.md for the exact
    shape. `marketplace_stats` and `price_suggestions` are NOT included here —
    fetch them separately with `collect_marketplace_stats` /
    `collect_price_suggestions`.
    """
    release = client.release(release_id)

    return {
        "id": release_id,
        "title": getattr(release, "title", None),
        "year": getattr(release, "year", None),
        "genres": list(getattr(release, "genres", None) or []),
        "styles": list(getattr(release, "styles", None) or []),
        "country": getattr(release, "country", None),
        "formats": list(getattr(release, "formats", None) or []),
        "notes": getattr(release, "notes", None),
        "images": list(getattr(release, "images", None) or []),
        "url": getattr(release, "url", None),
        "tracklist": _normalize_tracklist(release),
        "artists": _normalize_artists(release),
        "credits": _normalize_credits(release),
        "labels": _normalize_labels(release),
        "community": _normalize_community(release),
        "master_id": _extract_master_id(release),
    }


def collect_marketplace_stats(client: Any, release_id: int) -> dict[str, Any]:
    """Collect live marketplace stats for `release_id` in a separate API call.

    Returns `{num_for_sale, blocked_from_sale, lowest_price}`. `lowest_price`
    is the numeric price value (or None if there's no marketplace data at all).
    """
    release = client.release(release_id)
    stats = getattr(release, "marketplace_stats", None)
    if stats is None:
        return {"num_for_sale": 0, "blocked_from_sale": 0, "lowest_price": None}

    lowest_price = getattr(stats, "lowest_price", None)
    return {
        "num_for_sale": getattr(stats, "num_for_sale", None) or 0,
        "blocked_from_sale": getattr(stats, "blocked_from_sale", None) or 0,
        "lowest_price": getattr(lowest_price, "value", None) if lowest_price else None,
    }


def collect_price_suggestions(client: Any, release_id: int) -> dict[str, Any]:
    """Collect suggested price per condition grade (Poor..Mint) for `release_id`.

    Requires an authenticated client (see discogs.client.get_client) — the
    Discogs price-suggestions endpoint 401s for unauthenticated requests, and
    404s ("You must fill out your seller settings first") for an authenticated
    account that isn't configured as a marketplace seller. Both cases degrade
    to an empty dict rather than raising, consistent with how the rest of this
    collector treats unavailable data.

    Returns a dict keyed by grade label (e.g. "Mint (M)") with the numeric
    suggested price, or None where Discogs has no suggestion for that grade.
    """
    release = client.release(release_id)
    suggestions = getattr(release, "price_suggestions", None)
    if suggestions is None:
        return {}

    result: dict[str, float | None] = {}
    try:
        for grade_label, attr_name in _GRADE_ATTRS.items():
            price = getattr(suggestions, attr_name, None)
            result[grade_label] = getattr(price, "value", None) if price else None
    except DiscogsAPIError:
        return {}
    return result
