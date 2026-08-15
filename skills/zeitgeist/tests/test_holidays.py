from datetime import datetime, date
from zoneinfo import ZoneInfo
import pytest

from scripts.zeitgeist import HolidayResolver, NaturalLanguageNormalizer, Zeitgeist


@pytest.fixture
def holiday_resolver():
    return HolidayResolver()


@pytest.fixture
def engine():
    return Zeitgeist()


def test_is_holiday_nl(holiday_resolver):
    # 2026-04-27 is Koningsdag in NL
    d = date(2026, 4, 27)
    hol = holiday_resolver.get_holiday(d, country_code="NL")
    assert hol is not None
    assert "Koningsdag" in hol


def test_is_holiday_id_nyepi(holiday_resolver):
    # 2026-03-19 is Nyepi in Indonesia
    d = date(2026, 3, 19)
    hol = holiday_resolver.get_holiday(d, country_code="ID")
    assert hol is not None
    assert "Nyepi" in hol or "Silence" in hol


def test_normalize_koningsdag(engine):
    # Reference: March 1, 2026 -> next Koningsdag is April 27, 2026
    ref_dt = datetime(2026, 3, 1, 10, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.normalizer.normalize("met Koningsdag", reference=ref_dt, tz_name="Europe/Amsterdam")

    assert res.start.startswith("2026-04-27T00:00:00")
    assert res.end.startswith("2026-04-27T23:59:59")
    assert res.confidence >= 0.90


def test_normalize_kerst(engine):
    # Reference: August 14, 2026 -> next Kerst is Dec 25-26, 2026
    ref_dt = datetime(2026, 8, 14, 10, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.normalizer.normalize("met Kerst", reference=ref_dt, tz_name="Europe/Amsterdam")

    assert res.start.startswith("2026-12-25T00:00:00")
    assert res.end.startswith("2026-12-26T23:59:59")
    assert res.granularity == "holiday"
    assert res.confidence >= 0.90


def test_normalize_oud_en_nieuw(engine):
    # Reference: August 14, 2026 -> Dec 31 18:00 to Jan 1 23:59:59
    ref_dt = datetime(2026, 8, 14, 10, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.normalizer.normalize("met Oud en Nieuw", reference=ref_dt, tz_name="Europe/Amsterdam")

    assert res.start.startswith("2026-12-31")
    assert res.end.startswith("2027-01-01")
    assert res.confidence >= 0.90


def test_query_with_holiday_context(engine):
    # Query for Koningsdag in Amsterdam
    ref_dt = datetime(2026, 3, 1, 10, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.query("met Koningsdag", location_name="Amsterdam", reference=ref_dt)

    assert res["holiday"] is not None
    assert "Koningsdag" in res["holiday"]["name"]
    assert res["window"]["start"].startswith("2026-04-27")
