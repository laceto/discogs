"""Tests for discogs.collectors.release. No live API calls.

Fixtures are minimal stand-ins (`types.SimpleNamespace`) that expose the same
attributes `python3-discogs-client`'s `Release`/`Artist`/`Track`/... objects
expose, rather than depending on the real library's network layer.
"""

from types import SimpleNamespace

from discogs_client.exceptions import HTTPError

from discogs.collectors.release import (
    collect_marketplace_stats,
    collect_price_suggestions,
    collect_release,
)


def _artist(id, name, role=None, join=None):
    return SimpleNamespace(id=id, name=name, role=role, join=join)


def _track(position, title, duration):
    return SimpleNamespace(position=position, title=title, duration=duration)


def _label(name, catno):
    return SimpleNamespace(name=name, catno=catno)


def _user(username):
    return SimpleNamespace(username=username)


def _rating(average, count):
    return SimpleNamespace(average=average, count=count)


def _community(want, have, rating, submitter, contributors):
    return SimpleNamespace(
        want=want, have=have, rating=rating, submitter=submitter, contributors=contributors
    )


def _master(id):
    return SimpleNamespace(id=id)


class _FakeClient:
    """Stands in for discogs_client.Client: .release(id) returns a canned object."""

    def __init__(self, release):
        self._release = release

    def release(self, release_id):
        assert release_id == self._release.id
        return self._release


def _full_release(*, id=2303570, master=None, community=None):
    return SimpleNamespace(
        id=id,
        title="Me Sabe A Porro",
        year=2019,
        genres=["Electronic"],
        styles=["Techno"],
        country="Spain",
        formats=[{"name": "Vinyl", "qty": "1", "descriptions": ['12"', "33 1/3 RPM"]}],
        notes="Test notes",
        images=[{"type": "primary", "uri": "http://example.com/img.jpg"}],
        url="https://www.discogs.com/release/2303570",
        tracklist=[_track("A1", "Track One", "5:30"), _track("A2", "Track Two", "4:15")],
        artists=[_artist(1, "DJ ABC", join="Feat"), _artist(2, "MC Z")],
        credits=[_artist(3, "Rashad Becker", role="Mastered By")],
        labels=[_label("Desolat", "DES001")],
        community=community,
        master=master,
    )


def test_collect_release_normal_fields():
    release = _full_release(
        master=_master(999),
        community=_community(
            want=42,
            have=10,
            rating=_rating(4.5, 8),
            submitter=_user("digger1"),
            contributors=[_user("digger1"), _user("digger2")],
        ),
    )
    client = _FakeClient(release)

    record = collect_release(client, 2303570)

    assert record["id"] == 2303570
    assert record["title"] == "Me Sabe A Porro"
    assert record["year"] == 2019
    assert record["genres"] == ["Electronic"]
    assert record["styles"] == ["Techno"]
    assert record["country"] == "Spain"
    assert record["formats"] == [
        {"name": "Vinyl", "qty": "1", "descriptions": ['12"', "33 1/3 RPM"]}
    ]
    assert record["notes"] == "Test notes"
    assert record["url"] == "https://www.discogs.com/release/2303570"
    assert record["tracklist"] == [
        {"position": "A1", "title": "Track One", "duration": "5:30"},
        {"position": "A2", "title": "Track Two", "duration": "4:15"},
    ]
    assert record["artists"] == [
        {"id": 1, "name": "DJ ABC", "role": "", "join": "Feat"},
        {"id": 2, "name": "MC Z", "role": "", "join": ""},
    ]
    assert record["credits"] == [
        {"id": 3, "name": "Rashad Becker", "role": "Mastered By"},
    ]
    assert record["labels"] == [{"name": "Desolat", "catno": "DES001"}]
    assert record["community"] == {
        "want": 42,
        "have": 10,
        "rating_avg": 4.5,
        "rating_count": 8,
        "submitter": "digger1",
        "contributors": ["digger1", "digger2"],
    }
    assert record["master_id"] == 999


def test_collect_release_missing_master_is_none():
    release = _full_release(master=None, community=_community(0, 0, None, None, []))
    client = _FakeClient(release)

    record = collect_release(client, 2303570)

    assert record["master_id"] is None


def test_collect_release_empty_community_defaults_to_zero_not_error():
    release = _full_release(master=None, community=None)
    client = _FakeClient(release)

    record = collect_release(client, 2303570)

    assert record["community"] == {
        "want": 0,
        "have": 0,
        "rating_avg": 0.0,
        "rating_count": 0,
        "submitter": None,
        "contributors": [],
    }


def test_collect_release_community_present_but_all_zero_fields():
    release = _full_release(
        master=None,
        community=_community(want=0, have=0, rating=None, submitter=None, contributors=[]),
    )
    client = _FakeClient(release)

    record = collect_release(client, 2303570)

    assert record["community"] == {
        "want": 0,
        "have": 0,
        "rating_avg": 0.0,
        "rating_count": 0,
        "submitter": None,
        "contributors": [],
    }


def test_collect_release_multi_artist_join_keyword_per_entry():
    release = _full_release(master=None, community=None)
    release.artists = [
        _artist(1, "DJ ABC", join="Feat"),
        _artist(2, "MC Z", join="Vs"),
        _artist(3, "DJ Third"),
    ]
    client = _FakeClient(release)

    record = collect_release(client, release.id)

    assert record["artists"] == [
        {"id": 1, "name": "DJ ABC", "role": "", "join": "Feat"},
        {"id": 2, "name": "MC Z", "role": "", "join": "Vs"},
        {"id": 3, "name": "DJ Third", "role": "", "join": ""},
    ]


def test_collect_marketplace_stats_normal():
    price = SimpleNamespace(value=12.5, currency="USD")
    stats = SimpleNamespace(num_for_sale=7, blocked_from_sale=1, lowest_price=price)
    release = SimpleNamespace(id=2303570, marketplace_stats=stats)
    client = _FakeClient(release)

    result = collect_marketplace_stats(client, 2303570)

    assert result == {"num_for_sale": 7, "blocked_from_sale": 1, "lowest_price": 12.5}


def test_collect_marketplace_stats_missing_returns_zeros():
    release = SimpleNamespace(id=2303570, marketplace_stats=None)
    client = _FakeClient(release)

    result = collect_marketplace_stats(client, 2303570)

    assert result == {"num_for_sale": 0, "blocked_from_sale": 0, "lowest_price": None}


def test_collect_price_suggestions_normal():
    suggestions = SimpleNamespace(
        poor=SimpleNamespace(value=1.0),
        fair=SimpleNamespace(value=2.0),
        good=SimpleNamespace(value=3.0),
        good_plus=SimpleNamespace(value=4.0),
        very_good=SimpleNamespace(value=5.0),
        very_good_plus=SimpleNamespace(value=6.0),
        near_mint=SimpleNamespace(value=7.0),
        mint=SimpleNamespace(value=8.0),
    )
    release = SimpleNamespace(id=2303570, price_suggestions=suggestions)
    client = _FakeClient(release)

    result = collect_price_suggestions(client, 2303570)

    assert result == {
        "Poor (P)": 1.0,
        "Fair (F)": 2.0,
        "Good (G)": 3.0,
        "Good Plus (G+)": 4.0,
        "Very Good (VG)": 5.0,
        "Very Good Plus (VG+)": 6.0,
        "Near Mint (NM or M-)": 7.0,
        "Mint (M)": 8.0,
    }


def test_collect_price_suggestions_missing_returns_empty_dict():
    release = SimpleNamespace(id=2303570, price_suggestions=None)
    client = _FakeClient(release)

    result = collect_price_suggestions(client, 2303570)

    assert result == {}


class _RaisingSuggestions:
    """Simulates python3-discogs-client's lazy PriceSuggestions field descriptor,
    which only makes its HTTP call (and can 404) when a grade attribute is read."""

    def __getattr__(self, name):
        raise HTTPError("You must fill out your seller settings first.", 404)


def test_collect_price_suggestions_api_error_degrades_to_empty_dict():
    # Real-world case: an authenticated account that isn't a configured
    # marketplace seller gets a 404 from Discogs on this endpoint. That's not
    # "no data available for this release" so much as "can't ask for this
    # account" — either way, callers should see {} rather than a crash.
    release = SimpleNamespace(id=2303570, price_suggestions=_RaisingSuggestions())
    client = _FakeClient(release)

    result = collect_price_suggestions(client, 2303570)

    assert result == {}
