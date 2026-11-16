# Layer 4: Analytics, Reporting & Monorepo Scoping Architecture

When designing advanced Home Assistant Add-ons and automation frameworks, user experience and software maintainability depend on two key structural decisions:
1. **The Inverted UI Hierarchy (4 down to 1):** Putting high-value analytical outcomes at the top of the interface.
2. **Contract-First Modular Monorepo Architecture:** Dividing complex engines into bounded layers with explicit AI agent scoping, avoiding redundant standalone control layers.

---

## 1. The Inverted 4-Layer UI Hierarchy

In energy management and automation systems, users interact most frequently with high-level operational results (financial savings, COP trends, daily performance) and least frequently with hardware drivers and database connections. 

### Navigation Order (Top to Bottom):
1. **Laag 4: Analyse & Rapportage (Top / Default Landing Tab):**
   - High-level KPIs: Financial savings today & this week (€), solar self-consumption ratio (%), heat pump seasonal COP (DHW & CV), and automated daily markdown digests.
2. **Laag 3: Optimalisatie & Beleid:**
   - 24-hour dispatch schedule waterfall, the 3 policy archetypes (Shiftable, Thermal Buffer, Battery Arbitrage with €0.115/kWh deadband), dynamic supplier tariffs, and **Systeembrede Multi-Device Beperkingen (3x25A main grid peak shaving & hydraulic backup heater interlocks)**.
3. **Laag 2: Zelflerend & Fysica:**
   - Empirical calibration: Solar angle matrix $K(h)$, building insulation $UA_{\text{base}}$, and sensor downtime exclusion windows.
4. **Laag 1: Data, Verbindingen & Apparaten (Bottom):**
   - Hardware entities, InfluxDB and MQTT multi-instance CRUD, open APIs, and **Apparaatspecifieke Beveiliging** (compressor dwell-time, max power, emergency comfort thresholds $<38^\circ\text{C}$, and physical RAM relay contacts S10S/S11S).

---

## 2. Real-Time Analytics & Financial Metrics Formulation

### 1. Dual-Polarity Power Producers Analytics (Grafana-Style Telemetry):
Visualize instantaneous household power balance using a dual-polarity time series:
- **Positive Axis ($> 0\text{ W}$ — Consumption & Import):**
  - **Grid Import (Afname):** Net power drawn from the grid (crimson area fill, e.g. `#EF4444`).
  - **Total Consumption (Totaal Verbruik):** Total instantaneous household load (bright orange line, e.g. `#F97316`):
    $$P_{\text{total\_verbruik}} = P_{\text{import}} + \max(0, P_{\text{solar}} - P_{\text{export}})$$
  - **Self-Consumption (Opgewekt Gebruikt):** Solar power consumed locally behind the meter (teal fill, e.g. `#14B8A6`):
    $$P_{\text{self\_consumed}} = \min(P_{\text{solar}}, P_{\text{total\_verbruik}})$$
- **Negative Axis ($< 0\text{ W}$ — Production & Export):**
  - **Solar Generation (Zonnepanelen):** Total rooftop PV power inverted below zero (yellow/olive area fill, e.g. `#EAB308`, plotted as $-P_{\text{solar}}$).
  - **Grid Export (Teruglevering):** Surplus electricity fed back to the grid (emerald green fill, e.g. `#10B981`, plotted as $-P_{\text{export}}$).
- **Home Assistant InfluxDB Schema Nuance:**
  - Home Assistant's default InfluxDB integration stores metrics under their unit measurement (`"kW"` for `power_consumption` and `power_production`, `"W"` for `zonnepanelen_power`), tagged by `entity_id`.
  - Always normalize units: multiply `"kW"` series by $1000$ in SQL queries (`SELECT mean("value") * 1000 as afname_w FROM "kW" WHERE "entity_id" = 'power_consumption' ...`) before combining with Watt series.
- **Interactive Legend Table:** Display paired metrics cards below the chart with live values formatted in W/kW: `Last *` (most recent interval), `Min` (valley), and `Max` (peak).

### 2. Load Shifting Financial Savings:
Compare actual dynamic costs against unoptimized flat average baseline:
$$\text{Savings} = \text{Actual Consumption} \times P_{\text{average}} - \text{Optimized Consumption} \times P_{\text{cheapest\_slots}}$$

### 3. Solar Self-Consumption Ratio:
Percentage of on-site solar generation utilized directly without grid export:
$$\text{Self-Consumption Ratio} = \min\left(100.0, \frac{P_{\text{solar}} - P_{\text{grid\_export}}}{P_{\text{solar}}} \times 100.0\right)$$

### 4. Forecast Accuracy Auditing:
Evaluate Day-Ahead EPEX and solar forecast models against verified InfluxDB hardware readings:
$$\text{MAE} = \frac{1}{n} \sum_{i=1}^{n} |F_i - A_i|, \quad \text{RMSE} = \sqrt{\frac{1}{n} \sum_{i=1}^{n} (F_i - A_i)^2}$$

---

## 3. Modular Monorepo & AI Agent Scoping Protocol

When using AI coding agents across a large codebase, monolithic task prompts lead to unintended side effects across layers. Enforce a **Contract-First Modular Monorepo** where each layer maintains an independent interface and an explicit `AGENT_SPEC.md`:

```
/config/projects/<project-name>/
├── models/                     # UNIVERSAL CONTRACT (Single Source of Truth)
│   └── canonical.py            # Shared schemas (Measurement, Policies, Commands)
│
├── layer1_data_collection/     # Network I/O, Line Protocol, MQTT, Device Source Adapters
│   ├── interfaces.py           # IDataCollector, ITimeSeriesStorage, IMqttBroker
│   └── AGENT_SPEC.md           # Scope: Ingestion & Device parameters (dwell-time, limits, SG relays)
│
├── layer2_calibration/         # Physics & Empirical Modeling
│   ├── interfaces.py           # IModelCalibrator, ISmoothedClamping
│   └── AGENT_SPEC.md           # Scope: Pure statistics & OLS. Forbidden: Network I/O
│
├── layer3_scheduling/          # Economic Dispatch, Policies & Peak Shaving
│   ├── interfaces.py           # IPolicyEvaluator, IDispatchOptimizer
│   └── AGENT_SPEC.md           # Scope: Solvers, deadband math, multi-device 3x25A grid limits
│
└── layer5_analytics/           # Analytics, Reporting & Audit (Layer 4 in UI)
    ├── interfaces.py           # IAnalyticsEngine, IReportGenerator
    └── AGENT_SPEC.md           # Scope: Read-only metrics & digests. Forbidden: Actuation
```

### Absorption of Hardware Actuation:
A standalone Layer 4 (Actuation) is absorbed:
- **Device-Specific Actuation & Safety** resides in `layer1_data_collection/` (device adapter parameters: compressor dwell-time, max power, local emergency comfort $<38^\circ\text{C}$, physical RAM relays S10S/S11S).
- **Multi-Device System Limits** resides in `layer3_scheduling/` (3-phase main grid peak shaving at 17.250 W / 3x25A, hydraulic BUH lockout, surplus priority waterfall).

### Delegation Rule:
When delegating work to an agent, always bound the prompt explicitly:  
*"Work strictly within `layer1_data_collection/` according to `layer1_data_collection/AGENT_SPEC.md`."* This guarantees that data-layer modifications never tamper with optimization models or hardware safety guardrails.
