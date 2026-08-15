# PRD — Zeitgeist: Dynamic Temporal Awareness Engine

**Project:** Hermes-skill `zeitgeist`
**Versie:** 1.0 (concept)
**Datum:** 2026-08-14
**Status:** Ter review
**Doel van dit document:** Volledig zelfstandig leesbaar; elk model of elke ontwikkelaar moet hiermee de bouw kunnen overnemen zonder aanvullende context.

---

## 1. Samenvatting

Zeitgeist is een skill die de Hermes-agent 100% betrouwbaar tijdsbewustzijn geeft. AI-modellen falen structureel op tijd: ze behandelen "nu" als statische string, rekenen relatieve termen ("overmorgenochtend") fout om, en hallucineren weersberichten voor datums ver in de toekomst. Zeitgeist lost dit op met vier pijlers:

1. **Tijdbron-cascade** — deterministische bepaling van de relevante tijdzone en actuele tijd.
2. **Temporal Horizon Matrix** — classificatie van elke tijdsvraag in Micro/Meso/Macro/Clima, met per horizon een passende data-strategie en betrouwbaarheidslabel.
3. **Relative Natural Language Normalizer** — deterministische omzetting van Nederlandse (en Engelse) relatieve tijdsuitdrukkingen naar harde ISO 8601-vensters.
4. **Solar & Semantic Context** — daglichtfasen en activiteit-gebonden tijdsduren.

**Kernprincipe (anti-hallucinatie):** het model rekent nooit zelf met tijd. Alle tijdberekeningen lopen via deterministische tool calls naar `zeitgeist.py`. Prompt-injectie levert alleen de *nu-context*; alles wat rekenen vereist is een tool call.

---

## 2. Doelen en non-goals

### 2.1 Doelen (v1)

- G1: Elke tijdsvraag krijgt de juiste tijdzone via de cascade (locatie-in-vraag → device → profiel → UTC).
- G2: Relatieve NL/EN-tijdsuitdrukkingen worden deterministisch genormaliseerd naar ISO 8601-vensters, met confidence-score.
- G3: Elke vraag wordt geclassificeerd in een of meer tijdshorizonten; gemengde vragen leveren een lijst van (venster, horizon)-paren.
- G4: Weersdata wordt per horizon uit het juiste Open-Meteo-endpoint gehaald; boven de forecast-grens schakelt het systeem automatisch naar klimatologie en zegt dat er expliciet bij.
- G5: Elk antwoord draagt een betrouwbaarheidslabel: `forecast` / `trend` / `climatology`.
- G6: DST-overgangen (CET↔CEST en elders) worden correct afgehandeld, inclusief niet-bestaande en dubbele kloktijden.
- G7: Volledig getest: golden-test-suite voor de normalizer, DST-randgevallen, horizon-classificatie.

### 2.2 Non-goals (v1)

- Geen cultuur-/feestdagenkalender (Nyepi, Ramadan, zondagssluitingen) — fase 3; islamitische en Balinese kalenders zijn een project op zich.
- Geen kalender-integratie met agenda's van de gebruiker.
- Geen maritieme golfdata (Open-Meteo Marine API kan later als extra adapter).
- Geen UI; Zeitgeist is een backend-skill voor de Hermes-agent.

---

## 3. Architectuur

### 3.1 Componentoverzicht

```
┌─────────────────────────────────────────────────────────┐
│                     Hermes Agent                        │
│  (LLM; roept tools aan, rekent NOOIT zelf met tijd)     │
└───────────────┬─────────────────────────┬───────────────┘
                │ pre-prompt injectie     │ tool calls
                ▼                         ▼
┌───────────────────────┐   ┌─────────────────────────────┐
│  Context Injector     │   │  zeitgeist.py (CLI/lib)     │
│  (nu-context, licht)  │   │  ├─ TimezoneResolver        │
└───────────────────────┘   │  ├─ Normalizer (NL/EN)      │
                            │  ├─ HorizonClassifier       │
                            │  ├─ SolarCalculator         │
                            │  └─ SemanticDuration        │
                            └──────────┬──────────────────┘
                                       │ interfaces
                        ┌──────────────┴──────────────┐
                        ▼                             ▼
              ┌──────────────────┐          ┌──────────────────┐
              │ TimeSource       │          │ WeatherProvider  │
              │ ├─ HomeAssistant │          │ └─ OpenMeteo     │
              │ └─ SystemClock   │          │    (hourly/daily/│
              └──────────────────┘          │     climate)     │
                                            └──────────────────┘
```

### 3.2 Tool vs. injectie (kernregel)

| Mechanisme | Wat | Wanneer |
|---|---|---|
| **Pre-prompt injectie** | Actuele datum/tijd/tijdzone van gebruiker + weekdag + DST-status | Elke turn, altijd |
| **Tool call** | Normalisatie, horizonclassificatie, weer, solar, duurberekening | Zodra de vraag rekenen of externe data vereist |

Het model mag geïnjecteerde nu-context citeren, maar mag nooit zelf datums optellen, tijdzones converteren of forecasts formuleren zonder tool-resultaat.

### 3.3 Pijler 1 — Tijdbron-cascade

Prioriteitsvolgorde voor tijdzonebepaling:

1. **Contextuele locatie** — de vraag noemt een plek of reis (bijv. Bali → `Asia/Makassar`, UTC+8; Jakarta → `Asia/Jakarta`, UTC+7).
2. **Live device-locatie** — Home Assistant: `sensor.pixel_geocoded_location` / `zone.home`.
3. **Profiel-default** — thuistijdzone `Europe/Amsterdam` (CET/CEST).
4. **Fallback** — UTC, met expliciete melding in het antwoord.

**Dagdeel-regel bij reisvragen:** een dagdeel ("morgenochtend") volgt de tijdzone van de *besproken locatie* (cascade-stap 1), niet die van de gebruiker. Bij confidence < drempel (zie §3.5) vraagt de agent om bevestiging: "Bedoel je ochtend lokale tijd op Bali?"

Implementatie: Python `zoneinfo` (stdlib). Locatie→tijdzone via `timezonefinder` (offline, coördinaten→IANA-zone) gevoed door geocoding van de plaatsnaam (Open-Meteo Geocoding API, gratis, geen sleutel).

**DST-afhandeling (verplicht):**
- Alle interne tijden zijn timezone-aware `datetime` met IANA-zone; nooit naïef, nooit vaste offsets.
- Niet-bestaande tijd (voorjaarsovergang, bijv. 02:30 op de wisseldag): schuif naar het eerstvolgende geldige moment en meld dit.
- Dubbele tijd (najaarsovergang): gebruik `fold` en kies default `fold=0` (eerste voorkomen), meld ambiguïteit.
- Duurberekeningen over een DST-grens: reken in UTC, presenteer in lokale tijd.

### 3.4 Pijler 2 — Temporal Horizon Matrix

| # | Horizon | Venster | Resolutie | Databron (Open-Meteo) | Label |
|---|---|---|---|---|---|
| 1 | Micro | 0–36 uur | Uur | Forecast API, `hourly` | `forecast` |
| 2 | Meso | 36 uur – 7 dagen | Dagdelen + min/max | Forecast API, `daily` | `forecast` (d1–4), `trend` (d5–7) |
| 3 | Macro | 8–30 dagen | Weektrends | Forecast API `forecast_days=16` waar beschikbaar; daarboven klimatologie | `trend` / `climatology` |
| 4 | Clima | > 30 dagen | Maand-/seizoensgemiddelden | Historical Weather API (klimaatnormalen uit archief) | `climatology` |

**Grensregels (lost overlap uit het oorspronkelijke voorstel op):**
- De grens Micro/Meso ligt op 36 uur (niet 24), zodat "morgenavond" nog uur-precies kan.
- Classificatie gebeurt op het *eindpunt* van het gevraagde venster.
- **Gemengde vragen** ("weer voor de hele reis, vertrek morgen, terug over 3 weken") → de classifier retourneert een geordende lijst `[(venster₁, horizon₁), (venster₂, horizon₂), …]`; de agent beantwoordt per segment met het passende label.

**Anti-hallucinatie-gedrag per horizon:**
- Micro: exacte tijdvensters ("tussen 10:00 en 11:00: 24 °C, wind 4 Bft NO, 10% neerslagkans").
- Clima: uitsluitend klimatologie, altijd expliciet geformuleerd ("In januari ligt de gemiddelde dagtemperatuur in Gerlos rond −3 °C; historische sneeuwzekerheid ± 89%"). Nooit een "weersbericht" voor een specifieke dag > 16 dagen vooruit.

### 3.5 Pijler 3 — Relative Natural Language Normalizer

Deterministische parser (geen LLM) voor NL en EN. Input: frase + referentietijd + tijdzone. Output: JSON:

```json
{
  "input": "overmorgenochtend",
  "reference": "2026-08-14T09:12:00+02:00",
  "resolved": {
    "start": "2026-08-16T06:00:00+02:00",
    "end":   "2026-08-16T12:00:00+02:00"
  },
  "granularity": "daypart",
  "confidence": 0.95,
  "ambiguity": null
}
```

**Dagdeel-definities (configureerbaar in `config.yaml`):**
- ochtend 06:00–12:00 · middag 12:00–18:00 · avond 18:00–23:00 · nacht 23:00–06:00

**Ambiguïteitsregels (vastgelegd, niet aan het model overgelaten):**
- "volgende week vrijdag" → vrijdag in de *volgende ISO-week* (niet de eerstvolgende vrijdag). Confidence 0.7 → agent bevestigt bij twijfelgevoelige context.
- "dit weekend" → aanstaande za–zo; op za/zo zelf: het lopende weekend.
- "eerste weekend van september" → eerste za–zo die volledig in september valt.
- Weeknummering: ISO 8601 (week begint op maandag).
- Confidence < 0.8 → agent stelt één korte bevestigingsvraag; ≥ 0.8 → direct doorrekenen en de interpretatie kort benoemen in het antwoord.

**Bibliotheekkeuze:** basis op `dateparser` (NL-ondersteuning) + eigen regellaag voor dagdelen, weekends en ISO-weeklogica; golden tests borgen het gedrag (zie §6).

### 3.6 Pijler 4 — Solar Context

- Berekening via `astral` (offline, geen API): zonsopgang, zonsondergang, golden hour, civiele/nautische schemering, dag lengte.
- Gekoppeld aan de contextuele locatie uit de cascade.
- Voorbeeldgedrag: "Kunnen we om 18:30 nog foto's maken bij de tempel?" → zon onder ± 17:50 lokale tijd → antwoord: te donker, golden hour was 17:10–17:50.

### 3.7 Semantic Duration (activiteit → duur/dagdeel)

Configureerbare mapping in `references/activities.yaml`:

| Activiteit | Default venster | Extra factoren |
|---|---|---|
| Ferry-overtocht | uur-precies (opgegeven of gevraagd) | wind, windstoten; (golfslag: fase 2, Marine API) |
| CrossFit / sport buiten | 1 uur | temperatuur, neerslag, luchtvochtigheid |
| Dagtocht / tour | dagdeel middag 12:00–17:00 | UV-index, hittestress |
| Wintersport / strandvakantie | meerdaags | sneeuw-/seizoenscondities, klimatologie |

Onbekende activiteit → geen aanname; agent vraagt of gebruikt het letterlijk gevraagde venster.

---

## 4. Interfaces en datamodellen

### 4.1 Python-API (`scripts/zeitgeist.py`)

```python
def now(location: str | None = None) -> NowContext: ...
def resolve_timezone(query_location: str | None) -> TZResolution: ...
def normalize(phrase: str, reference: datetime, tz: str) -> ResolvedWindow: ...
def classify_horizon(window: ResolvedWindow, reference: datetime) -> list[HorizonSegment]: ...
def weather(window: ResolvedWindow, location: str) -> WeatherReport: ...
def solar(date: date, location: str) -> SolarContext: ...
def activity_window(activity: str, day: date, tz: str) -> ResolvedWindow | None: ...
```

**Determinisme-eis:** elke functie accepteert de referentietijd als parameter; nergens een verborgen `datetime.now()`. De CLI-wrapper injecteert de klok éénmalig bovenaan. Dit maakt de volledige suite testbaar met een bevroren klok.

CLI: `python zeitgeist.py normalize "overmorgenochtend" --tz Europe/Amsterdam --ref 2026-08-14T09:12:00+02:00 --json`

### 4.2 WeatherReport (kern-schema)

```json
{
  "location": {"name": "Gili Trawangan", "lat": -8.35, "lon": 116.04, "tz": "Asia/Makassar"},
  "window": {"start": "...", "end": "..."},
  "horizon": "micro",
  "reliability": "forecast",
  "data": {"temp_c": 29.4, "wind_bft": 4, "wind_dir": "NO", "precip_prob": 0.10, "uv_index": 9},
  "source": "open-meteo/forecast",
  "fetched_at": "...",
  "cache": "hit|miss"
}
```

### 4.3 Adapters (interfaces, wisselbaar)

```python
class TimeSource(Protocol):
    def device_timezone(self) -> str | None: ...
    def device_location(self) -> LatLon | None: ...

class WeatherProvider(Protocol):
    def hourly(self, loc, window) -> ...: ...
    def daily(self, loc, window) -> ...: ...
    def climatology(self, loc, month) -> ...: ...
```

Referentie-implementaties v1: `HomeAssistantTimeSource` (REST API, long-lived token uit env), `SystemClockTimeSource` (fallback), `OpenMeteoProvider` (geen API-sleutel nodig).

### 4.4 Caching & fallback

- Cache (lokale SQLite of JSON-file): hourly 15 min · daily 60 min · geocoding en klimatologie onbeperkt (klimaatnormalen wijzigen niet).
- API onbereikbaar → gebruik cache met leeftijdsmelding; geen cache → antwoord zonder weerdata, met expliciete melding. Nooit gokken.
- Rate-limit-respect: Open-Meteo gratis tier; batch-vensters per dag samennemen tot één request.

---

## 5. Skill-structuur

Locatie: `/config/.hermes/profiles/matthijs/skills/time/zeitgeist/`

```
zeitgeist/
├── SKILL.md                  # frontmatter (name, description) + gebruiksinstructies voor de agent
├── config.yaml               # dagdelen, drempels, cache-TTL's, profiel-default tz
├── scripts/
│   └── zeitgeist.py          # CLI + library (deterministisch, klok-injecteerbaar)
├── references/
│   ├── activities.yaml       # semantic-duration-mapping
│   ├── horizon-matrix.md     # naslag voor de agent (grensregels, labels)
│   └── ambiguity-rules.md    # normalisatieregels NL/EN
└── tests/
    ├── test_normalizer_golden.py
    ├── test_dst.py
    ├── test_horizon.py
    └── golden/nl_phrases.json
```

**SKILL.md-description (bewust "pushy" voor betrouwbare triggering):** de skill moet triggeren bij élke vraag met een tijdsdimensie — weer, planning, "hoe laat", "wanneer", zonsondergang, reisdata, relatieve termen — ook als de gebruiker niet expliciet om tijd vraagt.

**SKILL.md-body (kerninstructies aan de agent):**
1. Reken nooit zelf met tijd; roep altijd `zeitgeist.py` aan.
2. Benoem het betrouwbaarheidslabel in elk weer-antwoord (forecast/trend/klimatologie).
3. Bij confidence < 0.8 uit de normalizer: stel één bevestigingsvraag.
4. Bij fallback naar UTC of cache: meld dit.

---

## 6. Testplan

1. **Golden tests normalizer** — ≥ 50 NL-frases + ≥ 20 EN-frases → verwacht ISO-venster, bij vaste referentietijden (o.a. maandagochtend, vrijdagavond, zaterdag, oudjaarsdag, 29 februari-schrikkeljaarcontext). Dit is het meest foutgevoelige onderdeel; uitbreiden bij elk gevonden randgeval.
2. **DST-suite** — voorjaars- en najaarsovergang Europe/Amsterdam: niet-bestaande tijd, dubbele tijd, duur over de grens, vergelijking NL↔Bali (Indonesië kent geen DST).
3. **Horizon-classificatie** — grensgevallen: 35 u, 37 u, dag 7/8, dag 16/17, gemengde vensters.
4. **Adapter-tests** — Open-Meteo-responses als fixtures (geen live calls in CI); HA-adapter met mock.
5. **Integratietest** — 10 end-to-end-scenario's uit §8, met bevroren klok.

Acceptatie v1: alle golden tests groen; geen enkele codepath met verborgen `now()`; elk weer-antwoord bevat label + bron.

---

## 7. Fasering

| Fase | Inhoud | Deliverable |
|---|---|---|
| **1 (MVP)** | Tijdbron-cascade, normalizer NL/EN, horizon-classifier, Open-Meteo hourly/daily, cache, betrouwbaarheidslabels, volledige testsuite | Werkende skill + tests |
| **2** | Klimatologie-adapter, solar context (`astral`), semantic duration, Marine API (golfslag), 16-daagse trend | Uitbreiding + tests |
| **3** | Cultuur-/feestdagenkalender (`holidays`-pakket NL/ID als basis; religieuze kalenders apart onderzoeken), diepere HA-integratie (zones, personen), openingstijden | Onderzoeksnotitie + implementatie |

---

## 8. Referentiescenario's (voor tests én demo)

1. "Wat voor weer wordt het morgen om 10:00 tijdens de ferry naar Gili?" → Micro, uur-precies, `Asia/Makassar`, wind + neerslag, label `forecast`.
2. "Kunnen we in januari skiën in Gerlos?" → Clima, klimatologie, expliciete formulering, label `climatology`.
3. "Overmorgenochtend crossfit?" → normalizer → dagdeel → activiteit 1 u → Micro/Meso.
4. "Weer voor de hele reis (vertrek morgen, terug over 3 weken)?" → gemengde horizonten, gesegmenteerd antwoord.
5. "Om 18:30 nog foto's bij de tempel?" → solar context, zonsondergang lokaal.
6. Vraag gesteld op de dag van de klokwissel → correcte DST-afhandeling.
7. "Volgende week vrijdag" op een woensdag → ISO-weekregel + interpretatie benoemen.
8. API offline → cache-antwoord met leeftijd, of eerlijke melding.
9. Geen locatie bekend → profiel-default `Europe/Amsterdam`, expliciet benoemd.
10. "Eerste weekend van september" → volledig-in-septemberregel.

---

## 9. Open beslispunten

1. **Confidence-drempel** voor bevestigingsvragen: 0.8 (voorstel) — akkoord?
2. **Micro-grens op 36 u** i.p.v. 24 u — akkoord?
3. **Dagdeel-tijden** (ochtend 06–12 etc.) — aanpassen aan jouw ritme?
4. **Cache-backend**: SQLite (robuust) of JSON-file (simpel)? Voorstel: JSON in v1, SQLite bij behoefte.
5. **HA-koppeling in fase 1 of 2?** Voorstel: interface in fase 1, `SystemClock` als default; echte HA-adapter zodra token/endpoint beschikbaar is.
