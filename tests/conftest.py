import pytest

from b2a import config


@pytest.fixture(autouse=True)
def _no_clarity_check(monkeypatch):
    """Most tests fake one Claude answer; the clarity check has its own tests."""
    monkeypatch.setattr(config, "CLARITY_MIN", 0)
