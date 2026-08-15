from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest

from scripts.zeitgeist import HorizonClassifier, ResolvedWindow


@pytest.fixture
def classifier():
    return HorizonClassifier(micro_hours=36.0, meso_days=7.0, macro_days=30.0)


def test_micro_horizon(classifier):
    ref_dt = datetime(2026, 8, 14, 9, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    # Tomorrow 10:00 (25 hours ahead -> <= 36h = micro)
    win = ResolvedWindow(
        input_phrase="morgen om 10:00",
        reference_iso=ref_dt.isoformat(),
        timezone="Europe/Amsterdam",
        start="2026-08-15T10:00:00+02:00",
        end="2026-08-15T11:00:00+02:00",
        granularity="hour",
        confidence=0.95
    )
    segments = classifier.classify(win, reference=ref_dt)
    assert len(segments) == 1
    assert segments[0].horizon == "micro"
    assert segments[0].reliability == "forecast"


def test_meso_horizon(classifier):
    ref_dt = datetime(2026, 8, 14, 9, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    # In 4 days (96 hours ahead -> >36h and <=7d = meso)
    win = ResolvedWindow(
        input_phrase="over 4 dagen",
        reference_iso=ref_dt.isoformat(),
        timezone="Europe/Amsterdam",
        start="2026-08-18T00:00:00+02:00",
        end="2026-08-18T23:59:59+02:00",
        granularity="day",
        confidence=0.95
    )
    segments = classifier.classify(win, reference=ref_dt)
    assert len(segments) == 1
    assert segments[0].horizon == "meso"
    assert segments[0].reliability == "forecast"


def test_macro_horizon(classifier):
    ref_dt = datetime(2026, 8, 14, 9, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    # In 14 days -> macro
    win = ResolvedWindow(
        input_phrase="over 2 weken",
        reference_iso=ref_dt.isoformat(),
        timezone="Europe/Amsterdam",
        start="2026-08-28T00:00:00+02:00",
        end="2026-08-28T23:59:59+02:00",
        granularity="day",
        confidence=0.90
    )
    segments = classifier.classify(win, reference=ref_dt)
    assert len(segments) == 1
    assert segments[0].horizon == "macro"
    assert segments[0].reliability == "trend"


def test_clima_horizon(classifier):
    ref_dt = datetime(2026, 8, 14, 9, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    # In 6 months -> clima
    win = ResolvedWindow(
        input_phrase="in januari",
        reference_iso=ref_dt.isoformat(),
        timezone="Europe/Amsterdam",
        start="2027-01-01T00:00:00+01:00",
        end="2027-01-31T23:59:59+01:00",
        granularity="month",
        confidence=0.90
    )
    segments = classifier.classify(win, reference=ref_dt)
    assert len(segments) == 1
    assert segments[0].horizon == "clima"
    assert segments[0].reliability == "climatology"


def test_mixed_trip_horizon(classifier):
    ref_dt = datetime(2026, 8, 14, 9, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    # 3 weeks trip starting tomorrow
    win = ResolvedWindow(
        input_phrase="reis van 3 weken",
        reference_iso=ref_dt.isoformat(),
        timezone="Europe/Amsterdam",
        start="2026-08-15T00:00:00+02:00",
        end="2026-09-05T23:59:59+02:00",
        granularity="custom",
        confidence=0.95
    )
    segments = classifier.classify(win, reference=ref_dt)
    assert len(segments) == 3
    assert segments[0].horizon == "micro"
    assert segments[1].horizon == "meso"
    assert segments[2].horizon == "macro"
