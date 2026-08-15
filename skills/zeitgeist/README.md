# ⏳ Zeitgeist: Dynamic Temporal Awareness & Grounding Engine

[![Tests](https://img.shields.io/badge/pytest-29%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)]()

**Zeitgeist** is a deterministic, production-grade temporal awareness and grounding skill for **Hermes Agent**, LLMs, and autonomous AI systems. 

It eliminates the foundational time-handling failures of LLMs:
- ❌ Static "now" strings and broken relative date math (*"morgenochtend"*, *"volgende week vrijdag"*).
- ❌ Hallucinated daily weather forecasts for far-future dates (> 16 days out).
- ❌ Timezone confusion between user device, chat context, and remote travel destinations.
- ❌ Unawareness of local daylight, sunset, and national/cultural holidays.

---

## 🧭 The 6 Core Pillars

```
┌────────────────────────────────────────────────────────────────────────┐
│                     ZEITGEIST ENGINE ARCHITECTURE                      │
├─────────────────────────┬──────────────────────────────────────────────┤
│ 1. Atomic Clock Sync    │ Stratum-1 SNTP (UDP 123) + HTTP Date Header  │
│    & Timezone Cascade   │ Local OS Clock drift compensation (<30ms)    │
├─────────────────────────┼──────────────────────────────────────────────┤
│ 2. Horizon Matrix       │ Micro (0–36h) ➔ Meso (36h–7d) ➔              │
│    & Reliability Tags   │ Macro (8–30d) ➔ Clima (>30d, Climatology)    │
├─────────────────────────┼──────────────────────────────────────────────┤
│ 3. NL/EN Normalizer     │ Deterministic ISO 8601 parsing + confidence  │
│                         │ Dayparts, ISO-weeks, relative offsets        │
├─────────────────────────┼──────────────────────────────────────────────┤
│ 4. Holiday Grounding    │ Official & cultural holidays (NL, ID, AT, DE)│
│                         │ Koningsdag, Kerst, Pasen, Nyepi, Idul Fitri  │
├─────────────────────────┼──────────────────────────────────────────────┤
│ 5. Recurring Schedules  │ "elke zaterdagochtend", "doordeweeks"        │
├─────────────────────────┼──────────────────────────────────────────────┤
│ 6. Solar Event Context  │ Astral solar calculation: sunset, sunrise,   │
│                         │ golden hour, dusk, dawn across the globe     │
└─────────────────────────┴──────────────────────────────────────────────┘
```

---

## 🌐 Universal Multi-Domain Use Cases

While weather is a prominent example of horizon-based degradation (hourly vs. climate averages), **time grounds almost every autonomous agent task**. Zeitgeist provides the universal temporal backbone across 6 key domains:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ZEITGEIST UNIVERSAL DOMAINS                          │
├──────────────────────┬──────────────────────────────────────────────────┤
│ 🚆 Public Transport  │ Train departures ("next Friday 06:59"), holiday  │
│    & Commutes        │ schedules (Sunday vs. weekday timetable changes) │
├──────────────────────┼──────────────────────────────────────────────────┤
│ ⚡ Dynamic Energy    │ EPEX hourly day-ahead power prices, heat pump    │
│    & Smart Grids     │ buffer heating during solar hours vs. winter     │
├──────────────────────┼──────────────────────────────────────────────────┤
│ 🏋️ Habits, Sports   │ CrossFit WOD schedules ("every Wednesday 08:30"),│
│    & Routines        │ daylight-safe outdoor training, rest days        │
├──────────────────────┼──────────────────────────────────────────────────┤
│ 🏡 Smart Home        │ Solar-anchored triggers: sunset lighting, quiet  │
│    & Automations     │ hours (22:00–08:00), holiday heating profiles    │
├──────────────────────┼──────────────────────────────────────────────────┤
│ 📊 Business, Finance │ Fiscal quarters (Q1–Q4), ISO-week sprint planning│
│    & Deadlines       │ market open/close, month-end reconciliations     │
├──────────────────────┼──────────────────────────────────────────────────┤
│ 🌤️ Weather & Clima  │ Micro hourly forecasts, Meso weekly trends, and  │
│                      │ historical climate averages (skiing / holidays)  │
└──────────────────────┴──────────────────────────────────────────────────┘
```

### Domain Examples in Action:
- **Energy / Heat Pump:** *"Should I charge the battery tomorrow afternoon?"* ➔ Zeitgeist resolves `start: 12:00, end: 18:00` in the user's timezone and supplies the exact solar generation window.
- **Commute / Public Transit:** *"Will the 06:59 train run on King's Day?"* ➔ Zeitgeist detects `holiday: Koningsdag (NL)` on April 27 and warns that Sunday timetables apply.
- **CrossFit / Gym:** *"Plan my workouts for next week"* ➔ Expands recurring intervals (`Wed/Fri 08:30`, `Sun 09:30`) into exact ISO dates.
- **Photography & Travel:** *"When is the best light at Ubud temple tomorrow?"* ➔ Anchors to `golden_hour_start` (`17:33 WITA`).

---

## 🚀 Quickstart & Demo

### 1. Installation
```bash
bash scripts/setup.sh
```

### 2. Run All-in-One Query
```bash
python3 scripts/zeitgeist.py query "morgen om 10:00 ferry naar Gili" --loc "Gili Trawangan" --json
```

**JSON Output:**
```json
{
  "query": "morgen om 10:00 ferry naar Gili",
  "reference": "2026-08-15T10:26:57+08:00",
  "location": {
    "name": "Gili Trawangan",
    "latitude": -8.3503,
    "longitude": 116.039,
    "timezone_name": "Asia/Makassar"
  },
  "window": {
    "input_phrase": "morgen om 10:00 ferry naar Gili",
    "start": "2026-08-16T10:00:00+08:00",
    "end": "2026-08-16T11:00:00+08:00",
    "granularity": "hour",
    "confidence": 0.95
  },
  "primary_horizon": {
    "horizon": "micro",
    "reliability": "forecast",
    "hours_from_now": 23.5
  },
  "solar": {
    "sunrise": "2026-08-16T06:28:45+08:00",
    "sunset": "2026-08-16T18:18:22+08:00",
    "is_daylight_now": true
  },
  "weather": {
    "temperature_c": 29.4,
    "wind_bft": 3,
    "wind_direction": "O",
    "precipitation_prob": 0.05,
    "weather_description": "Overwegend helder"
  },
  "reliability_tag": "[forecast]",
  "prompt_guidance": "Gebruik betrouwbaarheidslabel FORECAST. Formuleer conform MICRO horizon."
}
```

---

## 📊 Temporal Horizon Matrix (Anti-Hallucination)

| Horizon | Relative Time Window | Resolution | Data Strategy | Reliability Label | Required Output Phrasing |
|---|---|---|---|---|---|
| **1. Micro** | 0 – 36 hours | Hourly | Open-Meteo `hourly` | `[forecast]` | *"Verwachting voor [uur]: ..."* |
| **2. Meso** | 36 hours – 7 days | Dayparts + Min/Max | Open-Meteo `daily` | `[forecast]` (d1–4) / `[trend]` (d5–7) | *"Verwachting / Trend voor [dag]: ..."* |
| **3. Macro** | 8 – 30 days | Weekly trends | Open-Meteo 16-day Ensemble | `[trend]` | *"Meerdaagse trend voor [periode]: ..."* |
| **4. Clima** | > 30 days | Monthly Normals | Open-Meteo Climate Archive | `[climatology]` | *"Klimatologie voor [maand] in [locatie]: ..."* |

---

## 🛠️ CLI Reference

```bash
# 1. Atomic Clock Sync & Drift Check
python3 scripts/zeitgeist.py atomic-sync --json

# 2. Instant Pre-Turn Grounding
python3 scripts/zeitgeist.py now --loc "Bali" --json

# 3. Relative Phrase Normalization
python3 scripts/zeitgeist.py normalize "volgende week vrijdag" --tz "Europe/Amsterdam" --json

# 4. Solar & Golden Hour Calculations
python3 scripts/zeitgeist.py solar "2026-08-15" --loc "Amsterdam" --json

# 5. Full Query with Weather & Holiday Context
python3 scripts/zeitgeist.py query "met Koningsdag in Amsterdam" --json
```

---

## 🧪 Automated Test Suite (29/29 Passing)

Zeitgeist includes a comprehensive, deterministic test suite:

```bash
python3 -m pytest tests/ -v
```

### Coverage:
- `test_atomic_clock.py`: Stratum-1 SNTP, HTTP fallback, drift compensation, deterministic clock injection.
- `test_dst.py`: European spring/autumn DST transitions, invalid times, double hours, non-DST zones (Indonesia).
- `test_horizon.py`: Micro/Meso/Macro/Clima boundaries and multi-segment mixed windows.
- `test_normalizer_golden.py`: 50+ golden phrases covering NL & EN relative date patterns.
- `test_holidays.py`: Official & religious holidays for NL, ID, AT, DE, US.
- `test_recurring_and_solar_events.py`: Recurring schedules (*"elke zaterdagochtend"*, *"doordeweeks"*) and solar anchors (*"tijdens zonsondergang"*, *"golden hour"*, *"voor het donker"*).
- `test_e2e_scenarios.py`: Complete PRD reference scenarios.

---

## 📄 License

MIT License © 2026 Matthijs van den Berg.
