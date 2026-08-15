from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

from scripts.zeitgeist import Zeitgeist


@pytest.fixture
def engine():
    return Zeitgeist()


def test_scenario_1_ferry_gili(engine):
    # 1. "morgen om 10:00 tijdens de ferry naar Gili" -> Micro, hour, Asia/Makassar, [forecast]
    ref_dt = datetime(2026, 8, 14, 9, 12, 0, tzinfo=ZoneInfo("Asia/Makassar"))
    res = engine.query("morgen om 10:00", location_name="Gili Trawangan", reference=ref_dt)

    assert res["location"]["timezone_name"] == "Asia/Makassar"
    assert res["primary_horizon"]["horizon"] == "micro"
    assert res["primary_horizon"]["reliability"] == "forecast"
    assert res["reliability_tag"] == "[forecast]"
    assert res["window"]["granularity"] == "hour"
    assert "wind_bft" in res["weather"]


def test_scenario_2_gerlos_ski_clima(engine):
    # 2. "Kunnen we in januari skiën in Gerlos?" -> Clima, [climatology]
    ref_dt = datetime(2026, 8, 14, 9, 12, 0, tzinfo=ZoneInfo("Europe/Vienna"))
    res = engine.query("in januari", location_name="Gerlos", reference=ref_dt)

    assert res["primary_horizon"]["horizon"] == "clima"
    assert res["primary_horizon"]["reliability"] == "climatology"
    assert res["reliability_tag"] == "[climatology]"
    assert "climatology_note" in res["weather"]


def test_scenario_3_crossfit_overmorgen(engine):
    # 3. "Overmorgenochtend crossfit?" -> daypart, micro/meso
    ref_dt = datetime(2026, 8, 14, 9, 12, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.query("overmorgenochtend", location_name="Culemborg", reference=ref_dt)

    assert res["window"]["granularity"] == "daypart"
    assert res["window"]["start"].endswith("T06:00:00+02:00")
    assert res["window"]["end"].endswith("T12:00:00+02:00")


def test_scenario_5_solar_sunset_temple(engine):
    # 5. "Om 18:30 foto's bij de tempel op Bali?" -> Solar calculation for Bali
    ref_dt = datetime(2026, 8, 14, 18, 30, 0, tzinfo=ZoneInfo("Asia/Makassar"))
    solar = engine.solar_calc.compute(ref_dt, engine.tz_resolver.resolve("Bali"))

    assert solar.sunset is not None
    # In Bali in August, sunset is around 18:15 WITA, so at 18:30 daylight is False
    assert solar.is_daylight_now is False


def test_scenario_7_volgende_week_vrijdag(engine):
    # 7. "Volgende week vrijdag" on Wednesday Aug 12 -> Friday Aug 21
    ref_dt = datetime(2026, 8, 12, 10, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.normalizer.normalize("volgende week vrijdag", reference=ref_dt, tz_name="Europe/Amsterdam")

    assert res.start.startswith("2026-08-21")
    assert res.ambiguity_note is not None
    assert res.confidence >= 0.85


def test_scenario_10_eerste_weekend_september(engine):
    # 10. "Eerste weekend van september"
    ref_dt = datetime(2026, 8, 14, 9, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    res = engine.normalizer.normalize("eerste weekend van september", reference=ref_dt, tz_name="Europe/Amsterdam")

    # In 2026, Sept 1 is Tuesday, so first Saturday is Sept 5, Sunday is Sept 6
    assert res.start.startswith("2026-09-05")
    assert res.end.startswith("2026-09-06")
