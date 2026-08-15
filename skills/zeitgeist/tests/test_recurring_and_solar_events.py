from datetime import datetime, date
from zoneinfo import ZoneInfo
import pytest

from scripts.zeitgeist import NaturalLanguageNormalizer, Zeitgeist


@pytest.fixture
def engine():
    return Zeitgeist()


# ==========================================
# Test Idea 3: Recurring Intervals & Rhythms
# ==========================================

def test_recurring_elke_zaterdagochtend(engine):
    # Reference: Wednesday Aug 12, 2026 -> Next Saturday is Aug 15
    ref_dt = datetime(2026, 8, 12, 10, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.normalizer.normalize("elke zaterdagochtend", reference=ref_dt, tz_name="Europe/Amsterdam")

    assert res.start.startswith("2026-08-15T06:00:00")
    assert res.end.startswith("2026-08-15T12:00:00")
    assert res.granularity == "recurring"
    assert res.confidence >= 0.90
    assert "weekly" in str(res.ambiguity_note).lower()


def test_recurring_iedere_vrijdag_om_0830(engine):
    # Reference: Wednesday Aug 12, 2026 -> Next Friday is Aug 14
    ref_dt = datetime(2026, 8, 12, 10, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.normalizer.normalize("iedere vrijdag om 08:30", reference=ref_dt, tz_name="Europe/Amsterdam")

    assert res.start.startswith("2026-08-14T08:30:00")
    assert res.end.startswith("2026-08-14T09:30:00")
    assert res.granularity == "recurring"
    assert res.confidence >= 0.90


def test_recurring_doordeweeks(engine):
    # Reference: Saturday Aug 15, 2026 -> Next Monday-Friday is Aug 17 to Aug 21
    ref_dt = datetime(2026, 8, 15, 10, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.normalizer.normalize("doordeweeks", reference=ref_dt, tz_name="Europe/Amsterdam")

    assert res.start.startswith("2026-08-17T00:00:00")
    assert res.end.startswith("2026-08-21T23:59:59")
    assert res.granularity == "recurring"


# ==========================================
# Test Idea 4: Solar Event-Anchored Relative Time
# ==========================================

def test_solar_anchored_zonsondergang(engine):
    # Query "tijdens zonsondergang op Bali" for tomorrow
    ref_dt = datetime(2026, 8, 14, 10, 0, 0, tzinfo=ZoneInfo("Asia/Makassar"))
    res = engine.query("tijdens zonsondergang", location_name="Bali", reference=ref_dt)

    assert res["window"]["granularity"] == "solar_event"
    # Sunset on Bali is around 18:18 WITA; window should span sunset
    start_dt = datetime.fromisoformat(res["window"]["start"])
    end_dt = datetime.fromisoformat(res["window"]["end"])
    assert start_dt.hour == 17 or start_dt.hour == 18
    assert end_dt.hour == 18 or end_dt.hour == 19


def test_solar_anchored_golden_hour(engine):
    # Query "tijdens golden hour in Amsterdam"
    ref_dt = datetime(2026, 8, 14, 10, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.query("tijdens golden hour", location_name="Amsterdam", reference=ref_dt)

    assert res["window"]["granularity"] == "solar_event"
    assert "golden hour" in str(res["window"]["ambiguity_note"]).lower()


def test_solar_anchored_voor_het_donker(engine):
    # Query "voor het donker bij het hotel"
    ref_dt = datetime(2026, 8, 14, 12, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.query("voor het donker", location_name="Amsterdam", reference=ref_dt)

    assert res["window"]["granularity"] == "solar_event"
    assert "dusk" in str(res["window"]["ambiguity_note"]).lower() or "donker" in str(res["window"]["ambiguity_note"]).lower()
