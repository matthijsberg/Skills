import json
from datetime import datetime
from pathlib import Path
import pytest
from zoneinfo import ZoneInfo

from scripts.zeitgeist import NaturalLanguageNormalizer

GOLDEN_FILE = Path(__file__).parent / "golden" / "nl_phrases.json"


@pytest.fixture
def normalizer():
    return NaturalLanguageNormalizer(default_tz="Europe/Amsterdam")


def test_golden_phrases(normalizer):
    with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)

    for case in cases:
        inp = case["input"]
        ref_dt = datetime.fromisoformat(case["ref"])
        tz_name = case.get("tz", "Europe/Amsterdam")

        res = normalizer.normalize(inp, reference=ref_dt, tz_name=tz_name)

        assert res.start == case["expected_start"], f"Failed start for '{inp}': got {res.start}, expected {case['expected_start']}"
        assert res.end == case["expected_end"], f"Failed end for '{inp}': got {res.end}, expected {case['expected_end']}"
        assert res.granularity == case["granularity"], f"Failed granularity for '{inp}': got {res.granularity}, expected {case['granularity']}"
        assert res.confidence >= case["min_confidence"], f"Confidence too low for '{inp}': got {res.confidence}, expected >= {case['min_confidence']}"
