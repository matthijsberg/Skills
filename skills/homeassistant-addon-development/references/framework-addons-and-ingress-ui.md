# Framework-First Home Assistant Add-ons & Ingress UI Architecture

When building extensible Home Assistant Add-ons (such as Energy Management Systems, Automation Engines, or Custom Controllers), avoid hardcoding site-specific hardware or assumptions into the core application. Instead, structure the add-on as a **pluggable framework with decoupled policies**.

---

## 1. The Clean-Slate Framework Pattern

1. **Zero Pre-Populated Assumptions:**
   - On fresh installation, the user should see a clean slate. No specific household hardware, fixed tariffs, or site-specific sensors are pre-loaded.
2. **Default Open Public APIs:**
   - The only pre-configured entities should be open, universally accessible APIs that work out-of-the-box:
     - Market prices: Public day-ahead & quarter-hourly spot price APIs (e.g. EPEX Spot via EnergyZero).
     - Weather & Solar: Global forecast APIs (e.g. Open-Meteo horizontal global radiation and temperature).
3. **Everything Else is a Dynamic Entity (Full CRUD):**
   - Users create and manage resources via standard CRUD interfaces:
     - **Tariffs / Energy Suppliers:** Dynamic spot markups, energy taxes, fixed monthly fees, and settlement intervals (15m vs 1h).
     - **Devices / Resources:** Grid meters, solar inverters, heat pumps, boilers, batteries, EV chargers, and baseload.

---

## 2. Dynamic Home Assistant Entity Discovery (Dropdown Selectors)

Never force users to manually type complex Home Assistant entity IDs (e.g., `sensor.zonnepanelen_power_avg_5_minutes`). Instead, query the Home Assistant Core REST API:

```python
# Querying Home Assistant Core REST API for available entities
import urllib.request, json, ssl

headers = {"Authorization": f"Bearer {ha_token}", "Content-Type": "application/json"}
req = urllib.request.Request(f"{ha_url}/api/states", headers=headers)
with urllib.request.urlopen(req, timeout=5) as r:
    states = json.loads(r.read().decode("utf-8"))

# Filter entities by domain and capabilities
power_sensors = [
    {"id": s["entity_id"], "name": s.get("attributes", {}).get("friendly_name", s["entity_id"])}
    for s in states
    if s["entity_id"].startswith("sensor.") and any(k in s["entity_id"] for k in ["power", "watt", "kw"])
]
```

Expose this through a local endpoint (e.g. `GET /api/ha/entities`) so modal form dropdowns in the Ingress UI populate with friendly names and IDs automatically.

---

## 3. Decoupling Policies from Physical Devices

**Core Architectural Rule:** Devices should NEVER determine their own policy.
- A **Device** is a physical resource with technical constraints (e.g., "I am a 10 kWh battery with 5 kW max charge power", "I am a 3 kW heat pump with 20 min minimum run time"). It has zero knowledge of market prices or overall site forecasts.
- A **Policy** is an independent orchestration rule that evaluates economics, forecasts, and guardrails across multiple resources.

### The Three Fundamental Policy Archetypes

```
┌─────────────────────────────────────────────────────────────┐
│                    1. DE POLICY ENGINE                      │
│                                                             │
│  • Type 1: ShiftableConsumerPolicy (Verbruik zonder opslag) │
│    - Vaatwasser, wasmachine, EV laden binnen tijdslot       │
│    - Parameters: window start/end, duration, watts, solar   │
│                                                             │
│  • Type 2: ThermalBufferPolicy (Buffer zonder teruggave)   │
│    - Warmtepomp, 350L SWW boiler, CV vloerbuffering         │
│    - 1-way storage with standby thermal leakage             │
│    - Guardrail Priority 1: Emergency < 38°C overrules all   │
│    - Economic deadband: No reheat if > 46°C without solar   │
│    - Lockouts: SG1 off during morning/evening grid peaks    │
│                                                             │
│  • Type 3: BatteryArbitragePolicy (Accu met teruggave)      │
│    - Thuisaccu (Deye), bidirectioneel laden/ontladen        │
│    - Economic Deadband (Dode Zone): If ΔP < €0.115/kWh,     │
│      battery enters HOLD/STANDBY (no loss-making cycling)   │
│    - Free solar surplus charges before grid arbitrage       │
│    - Peak shaving: Discharge if grid phase > 20A (3x25A)    │
└──────────────────────────────┬──────────────────────────────┘
                               │ Dispatches commands
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     2. DE DEVICE LAAG                       │
│  (Domme actuatoren en sensoren gekoppeld aan Home Assistant)│
└─────────────────────────────────────────────────────────────┘
```

### Bidirectional Device-to-Policy UI Mapping
In the UI, ensure full bidirectional clarity:
1. **Policy Modal Device Selector:** When creating or editing a policy, provide a multi-checkbox list of all configured HEMS devices so the user explicitly selects which devices the policy controls.
2. **Policy Badges:** Policy cards display friendly badges of connected devices (e.g. `[Daikin Altherma 3 H HT] [OEG 350L SWW]`).
3. **Device Cards:** Device cards display which policy currently governs that device (e.g. `Beleid: [350L SWW Boiler Buffer Beleid]`), or flag `Geen beleid gekoppeld (stand-by)`.

---

## 4. The Battery Economic Deadband (Dode Zone) Algorithm

Blind price arbitrage on small spreads results in financial loss due to two factors:
1. **Round-Trip Conversion Loss:** Battery inverters have typical round-trip efficiency of $\approx 87\%$ ($\eta = 0.87$), meaning $13\%$ of imported energy is lost.
2. **Levelized Cost of Storage (LCOS) Degradation:** Battery cell wear costs approximately **€0.0741 / kWh** throughput (e.g. €4,000 capital cost over 6,000 cycles).

### Minimum Price Spread Formula:
$$\Delta P_{\text{min}} = \left( \frac{P_{\text{import}}(h_{\text{laad}})}{\eta} \right) - P_{\text{export}}(h_{\text{ontlaad}}) + \text{LCOS} \approx €0.115\text{ / kWh}$$

**Operational Rules:**
- **$\Delta P < €0.115$ / kWh $\rightarrow$ STATUS: HOLD / STANDBY:** The battery does not trade with the grid.
- **$\Delta P \ge €0.115$ / kWh $\rightarrow$ STATUS: ARBITRAGE ACTIVE:** Charge in the cheapest valley hour; discharge in the peak hour.
- **Solar Surplus ($P_{\text{solar}} > P_{\text{baseload}}$) $\rightarrow$ STATUS: SOLAR BUFFERING:** Charges immediately from rooftop solar without grid taxes or high spreads.

---

## 5. Stacked 24-Hour Power & Energy Visualization (Chart.js)

To give users clear operational insight into their energy balance, plot a 24-hour (or 96-quarter-hour) stacked bar graph with dual Y-axes:

### Data Layout:
- **Left Y-Axis (Stacked Bars - kW or kWh):**
  - Dataset 1: Baseload (Blue, house idle consumption)
  - Dataset 2: Heat Pump / Thermal Storage (Pink, scheduled run slots)
  - Dataset 3: Battery Charging (Emerald, surplus absorption)
  - Dataset 4: EV Charging (Purple)
- **Overlay Curves (Lines):**
  - Solar Generation Curve (Warm Amber line, primary axis)
  - Dynamic Electricity Price Curve (Cyan dashed line, right Y-axis)
- **Dynamic Recommendation Callout Banners:**
  - Display actionable recommendation banners for the cheapest spot hours and peak solar moments.
  - Display the Battery Status Banner highlighting whether the battery is actively trading or in **Hold/Standby (Deadband)**.
