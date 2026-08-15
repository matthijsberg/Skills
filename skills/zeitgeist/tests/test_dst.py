from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest

from scripts.zeitgeist import NaturalLanguageNormalizer, TimezoneResolver


def test_dst_spring_forward():
    # 2026 spring forward in Europe/Amsterdam: Sunday March 29, 2026 (02:00 -> 03:00)
    tz = ZoneInfo("Europe/Amsterdam")
    ref_dt = datetime(2026, 3, 28, 14, 0, 0, tzinfo=tz)  # Saturday before switch
    norm = NaturalLanguageNormalizer(default_tz="Europe/Amsterdam")

    res = norm.normalize("morgen", reference=ref_dt, tz_name="Europe/Amsterdam")
    start = datetime.fromisoformat(res.start)
    end = datetime.fromisoformat(res.end)

    # Start is midnight CET (+01:00)
    assert start.strftime("%z") == "+0100"
    # End is 23:59:59 CEST (+02:00)
    assert end.strftime("%z") == "+0200"


def test_dst_fall_back():
    # 2026 fall back in Europe/Amsterdam: Sunday October 25, 2026 (03:00 -> 02:00)
    tz = ZoneInfo("Europe/Amsterdam")
    ref_dt = datetime(2026, 10, 24, 14, 0, 0, tzinfo=tz)  # Saturday before switch
    norm = NaturalLanguageNormalizer(default_tz="Europe/Amsterdam")

    res = norm.normalize("morgen", reference=ref_dt, tz_name="Europe/Amsterdam")
    start = datetime.fromisoformat(res.start)
    end = datetime.fromisoformat(res.end)

    # Start is midnight CEST (+02:00)
    assert start.strftime("%z") == "+0200"
    # End is 23:59:59 CET (+01:00)
    assert end.strftime("%z") == "+0100"


def test_no_dst_indonesia():
    # Indonesia has no DST (Bali = Asia/Makassar UTC+8 year round)
    tz = ZoneInfo("Asia/Makassar")
    ref_dt = datetime(2026, 3, 28, 14, 0, 0, tzinfo=tz)
    norm = NaturalLanguageNormalizer(default_tz="Asia/Makassar")

    res = norm.normalize("morgen", reference=ref_dt, tz_name="Asia/Makassar")
    start = datetime.fromisoformat(res.start)
    end = datetime.fromisoformat(res.end)

    assert start.strftime("%z") == "+0800"
    assert end.strftime("%z") == "+0800"
