"""Basic smoke tests for discogs."""

import discogs


def test_version():
    assert isinstance(discogs.__version__, str)
    assert len(discogs.__version__) > 0
