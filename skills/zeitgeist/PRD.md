# PRD — Zeitgeist: Dynamic Temporal Awareness Engine

**Project:** Hermes Skill `zeitgeist`  
**Version:** 1.2.0  
**Date:** 2026-08-15  
**Status:** Approved & Implemented  
**Purpose:** Fully self-contained specification document for developers, agents, and contributors.

---

## 1. Executive Summary

Zeitgeist gives autonomous AI agents and LLMs 100% reliable, zero-hallucination temporal awareness. Large Language Models fail systematically on time: they treat "now" as a static training string, miscalculate relative temporal phrases (*"day after tomorrow in the morning"*, *"next week Friday"*), hallucinate daily weather forecasts for far-future dates (> 16 days out), and confuse user device timezones with destination timezones.

Zeitgeist solves this through six deterministic pillars:
1. **Stratum-1 Atomic Clock & Timezone Cascade:** Real-time atomic time via SNTP UDP 123 + HTTP Date fallback with clock drift offset compensation.
2. **Temporal Horizon Matrix:** Multi-tier query classification (Micro / Meso / Macro / Clima) with mandatory reliability tags (`[forecast]`, `[trend]`, `[climatology]`).
3. **Deterministic NL/EN Normalizer:** Converts relative expressions into exact ISO 8601 windows with confidence scoring.
4. **National & Cultural Holiday Grounding:** Dynamic holiday detection for NL, ID, AT, DE, BE, GB, and US.
5. **Recurring Intervals & Schedules:** Resolves recurring patterns (*"every Saturday morning"*, *"weekdays"*) into the next concrete occurrence.
6. **Solar & Activity Context:** Astronomical solar calculations (sunrise, sunset, golden hour, twilight) via `astral`.

**Core Rule (Zero-Hallucination):** The LLM never calculates time or invents forecasts mentally. All temporal math, timezone conversions, solar phases, and weather retrievals run through `zeitgeist.py`.

---

## 2. Goals & Non-Goals

### 2.1 Goals (v1.2.0)
- **G1:** Determine the correct timezone deterministically via the cascade (Contextual Location ➔ Host/OS ➔ Config Default ➔ UTC).
- **G2:** Normalize Dutch & English relative phrases to ISO 8601 windows with confidence scores.
- **G3:** Classify queries into Micro (0–36h), Meso (36h–7d), Macro (8–30d), and Clima (>30d).
- **G4:** Query appropriate Open-Meteo endpoints per horizon; automatically switch to climatology for dates > 16 days out.
- **G5:** Enforce mandatory reliability tagging on every response (`[forecast]`, `[trend]`, `[climatology]`).
- **G6:** Correctly handle Daylight Saving Time (DST) transitions, non-existent hours, and ambiguous fold hours.
- **G7:** Comprehensive test coverage: golden test suite, DST edge cases, horizon thresholds, and reference scenarios (29/29 passing).

### 2.2 Non-Goals
- User personal calendar integration (handled by dedicated calendar skills).
- Maritime ocean wave modeling (reserved for future Marine API adapter).
- Graphical UI (Zeitgeist is a pure backend agent skill & CLI).

---

## 3. Architecture

### 3.1 Component Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Hermes Agent                        │
│  (LLM; invokes tools, NEVER calculates time mentally)   │
└───────────────┬─────────────────────────┬───────────────┘
                │ pre-prompt injection    │ tool calls
                ▼                         ▼
┌───────────────────────┐   ┌─────────────────────────────┐
│  Context Injector     │   │  zeitgeist.py (CLI / Lib)   │
│  (atomic now context) │   │  ├─ AtomicTimeSource        │
└───────────────────────┘   │  ├─ TimezoneResolver        │
                            │  ├─ NaturalLanguageNormalizer│
                            │  ├─ HorizonClassifier       │
                            │  ├─ HolidayResolver         │
                            │  ├─ SolarCalculator         │
                            │  └─ SemanticDuration        │
                            └──────────┬──────────────────┘
                                       │ interfaces
                        ┌──────────────┴──────────────┐
                        ▼                             ▼
              ┌──────────────────┐          ┌──────────────────┐
              │ TimeSource       │          │ WeatherProvider  │
              │ ├─ Atomic (SNTP) │          │ └─ OpenMeteo     │
              │ ├─ HTTP Date     │          │    (hourly/daily/│
              │ └─ Local Clock   │          │     climate)     │
              └──────────────────┘          └──────────────────┘
```

### 3.2 Prompt Injection vs. Tool Call

| Mechanism | Data | Trigger |
|---|---|---|
| **Pre-prompt Injection** | Current atomic date/time, user timezone, weekday, DST status | Every turn, automatically |
| **Tool Call (`zeitgeist.py`)** | Normalization, horizon classification, weather, solar, holidays | Whenever a query requires relative math or future data |

---

## 4. Temporal Horizon Matrix

| Horizon | Relative Window | Resolution | Data Strategy | Reliability Label | Required Output Phrasing |
|---|---|---|---|---|---|
| **1. Micro** | 0 – 36 hours | Hourly | Open-Meteo `hourly` | `[forecast]` | *"Forecast for [hour]: ..."* |
| **2. Meso** | 36 hours – 7 days | Dayparts + Min/Max | Open-Meteo `daily` | `[forecast]` (d1–4) / `[trend]` (d5–7) | *"Forecast / Trend for [day]: ..."* |
| **3. Macro** | 8 – 30 days | Weekly trends | Open-Meteo 16-day Ensemble | `[trend]` | *"Multi-day trend for [period]: ..."* |
| **4. Clima** | > 30 days | Monthly Normals | Open-Meteo Climate Archive | `[climatology]` | *"Climatology for [month] in [location]: ..."* |

---

## 5. Test Suite & Verification

The suite contains 29 automated tests verifying:
- **`test_atomic_clock.py`**: Stratum-1 SNTP UDP sync, HTTP fallback, drift calculation, deterministic clock injection.
- **`test_dst.py`**: Spring/autumn DST shifts in Europe/Amsterdam, fold handling, non-DST zones (Indonesia).
- **`test_horizon.py`**: Boundary conditions (35h, 37h, day 4/5, day 7/8, day 16/17, mixed multi-week spans).
- **`test_holidays.py`**: National and cultural holiday normalization (Koningsdag, Kerst, Pasen, Nyepi, Idul Fitri).
- **`test_recurring_and_solar_events.py`**: Recurring rhythms (*"every Saturday morning"*, *"weekdays"*) and solar events (*"during sunset"*, *"golden hour"*, *"before dark"*).
- **`test_normalizer_golden.py`**: 50+ golden phrases evaluated against frozen timestamps.
- **`test_e2e_scenarios.py`**: End-to-end integration scenarios.

---

## 6. License

MIT License © 2026 Matthijs van den Berg.
