from datetime import datetime, timezone
import pytest

from scripts.zeitgeist import AtomicTimeSource, CacheManager


def test_atomic_clock_sync():
    cache = CacheManager()
    clock = AtomicTimeSource(cache)

    res = clock.sync(force=True)

    assert "utc_atomic" in res
    assert "source" in res
    assert res["synchronized"] is True
    assert res["stratum"] in (1, 2)
    assert isinstance(res["drift_seconds"], float)


def test_now_utc_deterministic():
    cache = CacheManager()
    clock = AtomicTimeSource(cache)

    utc_now = clock.now_utc()
    assert utc_now.tzinfo == timezone.utc
    assert utc_now.year >= 2026
