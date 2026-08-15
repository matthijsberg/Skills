---
name: zeitgeist
description: "Dynamic temporal awareness, atomic clock sync, relative time normalizer, horizon classifier, solar phases, and weather/climatology."
version: 1.0.0
author: Matthijs van den Berg & Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [time, temporal-awareness, atomic-clock, normalizer, horizon-matrix, weather, solar, climatology, anti-hallucination, date-math]
    related_skills: [homeassistant, dutch-public-transport]
---

# Zeitgeist: Dynamic Temporal Awareness Engine

Zeitgeist gives the agent 100% reliable, zero-hallucination temporal awareness.
It solves the core failure mode of LLMs around time: static "now" strings, broken date-math, hallucinated far-future weather forecasts, and timezone confusion.

---

## ⚡ Iron Rule (Anti-Hallucination)

> **THE MODEL NEVER CALCULATES TIME OR INVENTS FORECASTS MENTALLY.**  
> All time resolution, date calculations, relative offsets, solar phases, and weather retrieval MUST run through `zeitgeist.py`.

---

## 🧭 The 6 Core Pillars

1. **Stratum-1 Atomic Clock & Timezone Cascade:**
   - Real-time atomic time via SNTP (`time.cloudflare.com`, `time.google.com`) and HTTP Date fallback.
   - Automatic timezone resolving: Contextual location ➔ Host/OS ➔ Config Default (`Europe/Amsterdam`) ➔ UTC.
2. **Temporal Horizon Matrix & Reliability Labels:**
   - **Micro (0–36h):** Hourly forecast ➔ Label: `[forecast]`
   - **Meso (36h–7d):** Daily curves & min/max ➔ Label: `[forecast]` (d1–4) / `[trend]` (d5–7)
   - **Macro (8–30d):** 16-day ensemble trend ➔ Label: `[trend]`
   - **Clima (>30d):** Historical climate normals ➔ Label: `[climatology]` *(Never invent a daily forecast!)*
3. **Deterministic NL/EN Normalizer:**
   - Normalizes phrases like *"morgenochtend"*, *"over 3 dagen"*, *"volgende week vrijdag"*, *"eerste weekend van september"* into exact ISO 8601 windows with confidence scores.
4. **National & Cultural Holiday Grounding:**
   - Detects and normalizes official and cultural holidays (Koningsdag, Kerst, Pasen, Hemelvaart, Pinksteren, Oud & Nieuw, Nyepi, Idul Fitri) per country (NL, ID, AT, DE, BE, GB, US).
5. **Recurring Intervals & Schedules:**
   - Interprets recurring patterns like *"elke zaterdagochtend"*, *"iedere vrijdag om 08:30"*, *"doordeweeks"* into the next occurrence with schedule metadata.
6. **Solar Event-Anchored Relative Time:**
   - Automatically anchors queries like *"tijdens zonsondergang"*, *"tijdens golden hour"*, *"voor het donker"*, *"bij zonsopgang"* to the exact astronomical event window for any location on Earth.

## 🌐 Universal Domain Applications

Zeitgeist grounds any temporal query across 6 core domains:
- 🚆 **Public Transit & Commutes:** Holiday schedules, weekday vs. weekend train tables (`06:59` commute).
- ⚡ **Energy & Smart Grid:** Day-ahead hourly EPEX electricity pricing, solar battery charging, heat pump heating buffers.
- 🏋️ **Fitness & Routines:** Recurring CrossFit schedules (`Wed/Fri 08:30`, `Sun 09:30`), daylight-safe outdoor training.
- 🏡 **Smart Home & Automations:** Solar lighting (`sunset`), quiet hours (`22:00–08:00`), vacation heating setpoints.
- 📊 **Business & Planning:** Fiscal quarters, ISO-week sprint planning, market trading hours, deadlines.
- 🌤️ **Weather & Climatology:** Hourly micro-forecasts ➔ weekly meso-trends ➔ long-term climate normals.

---

## 🛠️ CLI & Library Usage

### 1. All-in-One Query (Recommended)
Run the complete pipeline (Normalizer ➔ Timezone ➔ Horizon ➔ Solar ➔ Weather):
```bash
python3 /config/.hermes/profiles/matthijs/skills/time/zeitgeist/scripts/zeitgeist.py query "morgen om 10:00 ferry naar Gili" --loc "Gili Trawangan" --json
```

### 2. Live Atomic Time Context (Pre-Turn Grounding)
```bash
python3 /config/.hermes/profiles/matthijs/skills/time/zeitgeist/scripts/zeitgeist.py now --loc "Bali" --json
```

### 3. Relative Phrase Normalization
```bash
python3 /config/.hermes/profiles/matthijs/skills/time/zeitgeist/scripts/zeitgeist.py normalize "overmorgenochtend" --tz "Europe/Amsterdam" --json
```

### 4. Solar Daylight & Golden Hour
```bash
python3 /config/.hermes/profiles/matthijs/skills/time/zeitgeist/scripts/zeitgeist.py solar "2026-08-15" --loc "Amsterdam" --json
```

---

## 📋 Response Phrasing Guide

1. **Include Reliability Label:**
   - 🟢 `[forecast]`: *"Verwachting voor morgen 10:00 [forecast]: 29 °C, wind 3 Bft O, geen neerslag."*
   - 🟡 `[trend]`: *"Trend voor volgende week [trend]: aanhoudend zonnig rond 28-31 °C."*
   - 🔵 `[climatology]`: *"Klimatologie voor januari in Gerlos [climatology]: historische gemiddelde dagtemperatuur rond -3 °C met hoge sneeuwzekerheid."*
2. **Ambiguity Handling:**
   - Confidence $\ge 0.80$: Proceed immediately and briefly state the date assumption in 1 sentence.
   - Confidence $< 0.80$: Ask 1 single targeted clarification question via `clarify`.
