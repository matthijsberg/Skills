# Layer 1: Data Collection, InfluxDB & MQTT Connectivity Architecture

When designing a Home Assistant Energy Management System (HEMS) or IoT controller, resist jumping ahead to high-level scheduling, arbitrage algorithms, or complex UI visuals before the data foundation is solid. **Layer 1 (Data Collection & Connectivity)** must be fully configurable, verifiable, and established first.

---

## 1. Core Principle: Solidify the Data Layer Before Orchestration & Decouple from HA

Without a verified pipeline for real-time telemetry ingestion and durable time-series storage, high-level policies operate on incomplete or unverified assumptions. Furthermore, a generic energy management framework must never assume that InfluxDB or MQTT are strictly local Home Assistant add-ons — they may be external cloud instances, remote dedicated servers, or third-party IoT gateways.

Layer 1 must provide:
1. **Multi-Instance CRUD for Infrastructure:** Complete CRUD management for multiple InfluxDB endpoints and MQTT brokers with user-definable default/active pointers.
2. **Interactive Verification:** Live connection-testing endpoints with immediate feedback in the UI (ping, database existence checks, socket handshakes, latency in ms).
3. **Canonical Normalization:** Ingestion of disparate raw telemetries (P1 DSMR, SunSpec Modbus, Daikin P1P2/SG, Deye hybrid inverter) into a unified `Measurement` model.
4. **Dual Dispatch:** Simultaneous persistence to InfluxDB (for historical regressions and calibration) and publication to MQTT (for real-time streaming to dashboards and external consumers).

---

## 2. InfluxDB Time-Series Engine: Multi-Instance & The Dual-Database Pattern

In real-world setups, an installation may utilize multiple InfluxDB instances:
- A local Home Assistant InfluxDB (1.8) on the internal docker network.
- A remote dedicated InfluxDB server (e.g. Synology NAS, dedicated VM, or InfluxDB Cloud 2.x with tokens and organization IDs).

Furthermore, within Home Assistant installations, InfluxDB often serves two distinct roles with different permission models:
1. **Home Assistant Historical Sensor Storage (`hassio`):** A read-heavy database containing thousands of registered entity series. Writing arbitrary custom schemas here may trigger `HTTP 403 Forbidden`.
2. **HEMS Engine Operational Storage (`hermes`):** A dedicated, write-accessible database optimized for high-frequency Line Protocol telemetry ingestion, 24h dispatch records, and model parameter checkpoints.

### Multi-Instance InfluxDB Schema (Full CRUD):
```json
{
  "influxdb_connections": [
    {
      "id": "local_ha_influxdb",
      "name": "Lokale Home Assistant InfluxDB (1.8)",
      "type": "influx_v1",
      "url": "http://a0d7b954-influxdb:8086",
      "database": "hermes",
      "read_database": "hassio",
      "username": "hermes",
      "password": "[REDACTED]",
      "retention_policy": "autogen",
      "is_default": true,
      "enabled": true
    },
    {
      "id": "remote_influx_cloud",
      "name": "Dedicated External InfluxDB Server / Cloud",
      "type": "influx_v2",
      "url": "https://influx.example.com:8086",
      "database": "energy_metrics",
      "username": "remote_user",
      "password": "[TOKEN_OR_PASS]",
      "retention_policy": "autogen",
      "is_default": false,
      "enabled": true
    }
  ]
}
```

### Verification & Testing Endpoint Recipe:
Expose `POST /api/infrastructure/influxdb/test` to ping any specific instance, enumerate available databases, and count existing measurements:
```python
import urllib.request, urllib.parse, base64, json, time

def test_influxdb_connection(url, database, username="", password=""):
    t0 = time.time()
    clean_url = url.rstrip("/")
    
    # 1. Ping
    ping_req = urllib.request.Request(f"{clean_url}/ping")
    with urllib.request.urlopen(ping_req, timeout=3) as r:
        if r.status not in (200, 204):
            return {"status": "error", "message": f"Ping failed with status {r.status}"}
            
    # 2. Query Databases
    q_url = f"{clean_url}/query?" + urllib.parse.urlencode({"q": "SHOW DATABASES"})
    req_q = urllib.request.Request(q_url)
    auth = base64.b64encode(f"{username}:{password}".encode()).decode() if (username and password) else None
    if auth:
        req_q.add_header("Authorization", f"Basic {auth}")
        
    with urllib.request.urlopen(req_q, timeout=4) as r:
        res = json.loads(r.read().decode("utf-8"))
        dbs = [v[0] for v in res.get("results", [{}])[0].get("series", [{}])[0].get("values", [])]
        
    # 3. Check target database measurement count
    series_count = 0
    target_db = database or "hermes"
    if target_db in dbs:
        q_meas = f"{clean_url}/query?" + urllib.parse.urlencode({"q": f"SHOW MEASUREMENTS ON {target_db}"})
        req_m = urllib.request.Request(q_meas)
        if auth:
            req_m.add_header("Authorization", f"Basic {auth}")
        with urllib.request.urlopen(req_m, timeout=4) as r:
            res_m = json.loads(r.read().decode("utf-8"))
            series_count = len(res_m.get("results", [{}])[0].get("series", [{}])[0].get("values", []))
            
    latency = round((time.time() - t0) * 1000, 1)
    return {
        "status": "success",
        "message": f"Connected to InfluxDB! Found database '{target_db}' with {series_count} measurements.",
        "databases": dbs,
        "series_count": series_count,
        "latency_ms": latency
    }
```

---

## 3. MQTT Broker Connectivity: Multi-Broker CRUD & Raw Socket Handshake

Just like storage, streaming brokers must not be constrained to a single local Home Assistant Mosquitto instance. Systems frequently stream to or from:
- A local Home Assistant Mosquitto add-on (`core-mosquitto:1883`).
- An external cloud broker (HiveMQ, EMQX, AWS IoT Core) via TLS/SSL.
- A dedicated micro-broker embedded in an EV charger, solar inverter, or heat pump bridge.

### Multi-Broker MQTT Schema (Full CRUD):
```json
{
  "mqtt_connections": [
    {
      "id": "local_mosquitto",
      "name": "Lokale Mosquitto Broker",
      "type": "standard",
      "host": "core-mosquitto",
      "port": 1883,
      "base_topic": "openhems",
      "client_id": "open-hems-collector",
      "username": "",
      "password": "",
      "tls": false,
      "is_default": true,
      "enabled": true
    },
    {
      "id": "external_cloud_mqtt",
      "name": "External Cloud Gateway",
      "type": "standard",
      "host": "broker.example.com",
      "port": 8883,
      "base_topic": "site/home",
      "client_id": "hems-edge-01",
      "username": "client_user",
      "password": "[PASS]",
      "tls": true,
      "is_default": false,
      "enabled": true
    }
  ]
}
```

### Raw Socket MQTT 3.1.1 Handshake Tester (Zero External Dependencies):
In minimal Alpine container images where `paho-mqtt` may not be installed, you can perform full MQTT 3.1.1 protocol validation using Python's standard `socket` library.
```python
import socket, time

def test_mqtt_connection(host, port, username="", password="", client_id="open-hems-test"):
    t0 = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect((host, int(port)))
        cid = client_id.encode("utf-8")
        clean_session = 0x02
        flags = clean_session
        if username: flags |= 0x80
        if password: flags |= 0x40

        payload = bytes([0, len(cid)]) + cid
        if username:
            ub = username.encode("utf-8")
            payload += bytes([0, len(ub)]) + ub
        if password:
            pb = password.encode("utf-8")
            payload += bytes([0, len(pb)]) + pb

        var_header = b"\x00\x04MQTT\x04" + bytes([flags, 0, 60]) # Protocol 3.1.1, keepalive 60s
        packet = bytes([0x10, len(var_header) + len(payload)]) + var_header + payload
        s.send(packet)
        resp = s.recv(10)
        s.close()
        latency = round((time.time() - t0) * 1000, 1)

        if len(resp) >= 4 and resp[0] == 0x20:
            rc = resp[3]
            rc_map = {
                0: ("success", f"Connected to MQTT broker ({host}:{port})! (RC 0: OK)"),
                1: ("error", "Protocol version rejected by broker (RC 1)"),
                2: ("error", "Client identifier rejected (RC 2)"),
                4: ("error", "Bad username or password (RC 4)"),
                5: ("error", "Not authorized: broker requires valid credentials (RC 5)")
            }
            st, msg = rc_map.get(rc, ("error", f"Broker return code: {rc}"))
            return {"status": st, "message": msg, "latency_ms": latency}
        return {"status": "error", "message": "Invalid MQTT CONNACK response received", "latency_ms": latency}
    except Exception as e:
        return {"status": "error", "message": str(e), "latency_ms": round((time.time() - t0) * 1000, 1)}
```

---

## 4. Realtime Ingestion & InfluxDB Line Protocol Pipeline

When streaming measurements arrive, format them immediately into InfluxDB Line Protocol to maintain high-throughput, low-latency writes:

```
hems_measurements,device_id=daikin_heat_pump,vector=electricity,flow=consumption power_w=3050.0,voltage=230.1 1725724800000000000
hems_measurements,device_id=dhw_tank,vector=heat,flow=storage temperature_c=52.8 1725724800000000000
```

### Line Protocol Writer Recipe:
```python
def write_to_influx(cfg, line_protocol_data: str):
    url = f"{cfg['url']}/write?db={cfg['database']}&precision=s"
    req = urllib.request.Request(url, data=line_protocol_data.encode("utf-8"), method="POST")
    if cfg.get("username") and cfg.get("password"):
        auth = base64.b64encode(f"{cfg['username']}:{cfg['password']}".encode()).decode()
        req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.status in (200, 204)
```

---

## 5. UI Presentation: Verbindingen & Opslag (Laag 1)

In the Add-on Ingress UI:
1. Place **Verbindingen & Opslag** prominently in the navigation menu before high-level optimization tabs.
2. Provide interactive test buttons (**"Test InfluxDB Verbinding"** and **"Test MQTT Verbinding"**) with visual spinners and badge indicators (`🟢 Verbonden` / `🔴 Niet bereikbaar`).
3. Display real-time telemetry counters (e.g. `Laatste meting: zojuist`, `Meetpunten/min: 48`).

---

## 6. Isolated Secrets Vault Architecture & Safe ID-Based Endpoint Testing

### The HTML Serialization Pitfall:
Never serialize credential-bearing configuration objects directly into HTML attributes, e.g.:
```html
<!-- DANGEROUS: Quotes and special characters (like §) break attribute parsing! -->
<button onclick='testSpecificInflux(${JSON.stringify(conn)})'>Testen</button>
```
When passwords contain quotes, section signs (`§`), or backslashes, browser HTML attribute tokenization corrupts the JSON string or strips characters. The frontend then sends an empty or truncated password (`""`), causing backend tests to fail with `401 Unauthorized` while initial server-side checks show green.

### The Isolated Secrets Vault Pattern:
1. **Dedicated Vault File (`/config/open_hems_secrets.json`):**
   - Store all credentials (passwords, tokens, API keys) in a dedicated secrets file with strict permissions `chmod 0600`.
   - Never store passwords in the public site configuration (`heatpump_config.json`).
   - Explicitly add `open_hems_secrets.json` to `.gitignore` and `.secret_patterns` in the pre-commit scanner.
2. **Masked API Responses:**
   - On `GET /api/infrastructure`, mask passwords: `"password": "••••••••"`, `"has_password": true`.
3. **Safe ID-Based Endpoint Testing:**
   - In the frontend UI, pass ONLY the clean string ID:
     ```javascript
     async function testSpecificInflux(connId) {
         const res = await fetch('./api/infrastructure/influxdb/test', {
             method: 'POST',
             headers: {'Content-Type': 'application/json'},
             body: JSON.stringify({ id: connId })
         });
     }
     ```
   - On `POST /api/infrastructure/influxdb/test`, the backend loads the connection metadata by ID and resolves the stored password directly from the local server vault.

---

## 7. Multi-Source Device Adapters vs. Contextual Feeds

Do not conflate physical resources, external context feeds, and transport buses:

1. **Transport Bus (MQTT Broker):**
   - Purely the transport medium (host, port, credentials, TLS). It handles sockets and packets, not Watts or temperatures.
2. **Physical Resources (Devices):**
   - Anything consuming, producing, storing, or measuring electricity or heat in the home (P1 DSMR meter, heat pump, battery, solar inverter).
   - Each device configures a **Data-Adapter (Source Type)**:
     - `source_type: "homeassistant"`: Polls or listens to Home Assistant entities (`ha_power_entity`, `ha_control_entity`).
     - `source_type: "mqtt"`: Direct real-time streaming subscriber (`mqtt_broker_id`, `mqtt_power_topic`, `mqtt_power_json_key`, `mqtt_control_topic`).
   - Device cards explicitly display their active data adapter (`🏠 Home Assistant (sensor.power_consumption)` vs `⚡ MQTT (dsmr/reading/power)`).
3. **External Context (Feeds / Providers):**
   - External market and atmospheric signals that provide situational context (EPEX Spot day-ahead/quarter-hourly electricity prices, Open-Meteo 48h solar irradiance and weather forecast).
   - Feeds live in their own dedicated catalog (`Open APIs & Feeds`), keeping the physical device list uncluttered.

---

## 8. Dedicated Canonical Datastore & Background Collector Engine

To ensure an energy management add-on can be published as a generic, standalone framework independent of Home Assistant's internal database quirks:

### The Dedicated Datastore Pattern:
- **Avoid Coupling to `hassio`:** Home Assistant's internal InfluxDB integration stores measurements named after raw units (`"W"`, `"kW"`, `"kWh"`) with entity IDs as tags. Never bind analytics or optimization engines to this schema.
- **Dedicated Database (`openhems`):** Deploy a dedicated database with an isolated user (`openhems`) and credentials stored in `/config/open_hems_secrets.json` (`chmod 0600`).
- **Canonical Schema:**
  - `energy_telemetry`:
    - Tags: `device_id`, `device_type`, `flow` (`IMPORT`, `EXPORT`, `GENERATION`, `CONSUMPTION`, `STORAGE`), `source_type`, `vector` (`ELECTRICITY`, `HEAT`)
    - Fields: `power_w` (float), `temperature_c` (float), `energy_kwh` (float)
  - `market_tariffs`:
    - Tags: `provider`, `tariff_type`, `resolution`
    - Fields: `price_eur` (float)
  - `weather_forecast`:
    - Tags: `provider`
    - Fields: `outdoor_temp_c` (float), `solar_irradiance_ghi_w_m2` (float)

### Background Collector Daemon Thread (`HemsBackgroundCollector`):
- Run a lightweight daemon thread in the add-on process (polling every 30s):
  1. Polls active devices and providers from the site configuration.
  2. Normalizes readings into canonical Line Protocol points.
  3. Writes batches to `openhems` via `HTTP POST /write?db=openhems`.

### Zero Legacy Fallbacks (100% Pure Canonical Datastore):
- **Never Rely on `hassio` Fallbacks:** Maintain zero queries, fallbacks, or backfill logic to Home Assistant's internal `hassio` database. An energy management framework intended for public release must be 100% standalone, validating exclusively against its own canonical schema.

### Heterogeneous Sampling Rates & Tumbling Window Accumulator (IEC 61850 / OpenADR):
- **The Pitfall of Raw Writes:** Writing raw heterogeneous points directly to InfluxDB creates unnecessary disk I/O, database bloat (86,400 points/day for a 1s P1 stream), and false optimization triggers caused by sub-second inductive switching spikes.
- **In-Memory Tumbling Window:** The background collector thread samples devices at high frequency (every 5–10s) into an in-memory accumulator (RAM), updating running sums and observation counts:
  $$\bar{P}_{60s} = \frac{1}{N} \sum_{i=1}^N P_i$$
- **Flush Interval (60 Seconds):** Exactly once per minute, flush the anti-spike, noise-filtered arithmetic mean as ONE Line Protocol point to the dedicated database at aligned wall-clock timestamps.
- **Downstream Aggregations:**
  - **1-minute (60s):** Telemetry storage standard (1,440 points/device/day) — smooths out high-frequency noise while preserving true heat pump compressor ramps and kitchen appliance cycles.
  - **15-minute (PT15M):** Market settlement and macro-dispatch schedule standard (matching European grid code, TenneT imbalance, and dynamic contract quarter-hourly intervals).

### Dual-Polarity Power Producers Visualizer & Dynamic Horizon Zooming:
- **Dual Polarity Charting:** Plot consumption and grid import above zero ($>0\text{ W}$), and solar generation and grid export below zero ($<0\text{ W}$), matching standard power engineer and Grafana conventions.
- **Interactive Timeframe Selector (1h, 6h, 24h, 48h, 7d):**
  - Expose a clean dropdown selector in the Ingress header dynamically tuning the group-by aggregation bucket and window:
    - `1h`: 1-minute resolution (high-frequency live monitoring)
    - `6h`: 2-minute resolution (afternoon/evening transition)
    - `24h`: 5-minute resolution (daily dispatch cycle)
    - `48h`: 15-minute resolution (Dutch market settlement standard)
    - `7d`: 1-hour resolution (multi-day trend analysis)
- **Timeframe Energy Totals Integration (kWh):**
  - Calculate discrete Riemann energy integrals across all sampled intervals: $\text{Total kWh} = \sum \frac{P_i \cdot \Delta t_{\text{hours}}}{1000}$.
  - Prominently display the exact timeframe total in kWh on all 6 metric cards below the visualizer alongside instantaneous power.
  - Verify energy conservation: $\text{Total Consumption} = \text{Grid Import} + \text{Self-Consumed Solar}$.

---

## 9. EPEX Spot Market Electricity Rates & Dual-Axis Solar Forecast Chart

A core requirement for modern smart energy dashboards is comparing volatile dynamic market electricity rates against the homeowner's fixed internal cost of rooftop solar power and expected solar generation:

### 1. Market Ingestion (EnergyZero / EPEX Spot):
- Fetch day-ahead all-in rates (including energy taxes and VAT) via public EnergyZero endpoints:
  - `INTERVAL_QUARTER`: 96 quarter-hourly intervals (Dutch standard for dynamic suppliers like Powerpeers).
  - `INTERVAL_HOUR`: 24 hourly intervals.
- Filter strictly for the current local calendar day (`datetime.now(AMS_TZ).date()`).

### 2. Dual-Axis Solar Forecast Integration:
- In addition to EPEX market prices, plot the **Verwachte Zonneproductie (kW)** on a secondary right Y-axis (`y1`, in kW) as an amber/gold glowing curve (`#F59E0B`).
- Sourced from Open-Meteo GHI shortwave radiation ($W/m^2$) for the installation's GPS coordinates:
  $$P_{\text{solar}} = \frac{\text{rad}}{1000.0} \cdot \text{kWp} \cdot \eta \cdot \text{tilt\_factor}$$
- Allows users to visually see solar generation peaks (e.g. 1.41 kW at 11:00-13:00) co-occurring with cheaper midday EPEX tariffs (€0.1935/kWh at 13:00).

### 3. Clean Mobile Header & Centralized Settings Architecture:
- *Pitfall:* Crowding chart card headers with text labels, numeric inputs, and unit labels causes messy multi-line wrapping on mobile screens (<768px).
- *Solution:* Keep analytical chart headers clean with only the title and the resolution dropdown (`Kwartiertarieven (15m)` / `Uurtarieven (1h)`).
- Move economic parameters to a dedicated settings card under **Tarieven & Leveranciers** (`Interne Opwek, Opslag & Woninginstellingen`):
  - **Zonnestroom Kostprijs / LCOE:** default **€0.060/kWh** (6 cent/kWh).
  - **Continue Basislast Woning:** default **300 Watt**.
  - Saved to `heatpump_config.json` via `POST /api/settings`.

### 4. Stepped Line Chart & Savings Margin Tooltip:
- Render EPEX rates as a stepped line chart (`stepped: 'before'`) filled with translucent blue.
- Overlay a dashed horizontal reference line at the configured solar cost (€0.060/kWh).
- Chart tooltips display the instantaneous delta: $\Delta = P_{\text{market}} - P_{\text{solar}}$, indicating the exact monetary benefit of consuming self-generated solar energy or battery discharge at that moment.
- Display 4 key analytical chips:
  - **Laagste Tarief (Min):** e.g. €0.1935/kWh (at 13:00)
  - **Hoogste Tarief (Max):** e.g. €0.4390/kWh (at 19:45)
  - **Piek Zonverwachting:** e.g. 1.41 kW (Open-Meteo GHI)
  - **Zon-Besparingsmarge:** e.g. +€0.2580/kWh average advantage over grid import.

---

## 10. 24-Hour Ahead Rolling Power Consumption Prediction Engine

A complete HEMS framework must project forward-looking power consumption at least 24 hours ahead, allowing homeowners and autonomous policy engines to anticipate heating loads and solar utilization:

### 1. Rolling 24-Hour Timeline:
- Generate a continuous 24-hour horizon starting from the current wall-clock hour (`Nu (HH:00)` through `Morgen (HH-1:00)`).
- Sourced from day-ahead EPEX prices (published daily at 13:00 CEST for tomorrow) and 48-hour Open-Meteo ambient temperature and GHI forecasts.

### 2. Stacked Consumption Components:
1. **Continue Basislast (kW):** `baseload_watts / 1000.0` (constant across all 24 hours from user settings, e.g. 0.30 kW).
2. **Warm Tapwater (SWW Boiler 350L) (kW):** Automatically scheduled on the optimal slot (highest solar surplus or lowest price window, e.g. 13:00 tomorrow) as a ~1.2 kW electrical heat pump boost (~3.6 kW thermal heat).
3. **Woningverwarming (CV) (kW):** Dynamically evaluated against ambient temperature ($T_{\text{out}} < 15.5^\circ\text{C}$) and building heat loss ($UA_{\text{base}} \cdot (19.5 - T_{\text{out}}) / \text{COP}$).
4. **Thuisaccu Laden (kW):** Scheduled during economic price arbitrage windows ($\Delta P \ge €0.115/\text{kWh}$) or surplus solar absorption.
5. **Overlays:** Solar generation forecast line (kW) and EPEX price line (€/kWh on secondary Y-axis).

### 3. Classic Dual-Polarity Energy Architecture (Power Producers & Netstromen Alignment):
Rather than complex floating baselines or offset bars, strictly adhere to the intuitive Power Producers standard:
- **Consumers Above the Horizontal Zero Axis ($>0\text{ kW}$, `stack: 'consumption'`):**
  - All electrical loads stack upward starting from zero:
    1. Continue Basislast (kW) (blue, `#3B82F6`)
    2. SWW Boiler 350L (kW) (pink, `#EC4899`)
    3. Space Heating / CV (kW) (indigo, `#6366F1`)
    4. Thuisaccu Laden (kW) (emerald, `#10B981`) — explicitly categorized as a consumer.
- **Generation & Sources Below the Horizontal Zero Axis ($<0\text{ kW}$, `stack: 'production'`):**
  - All local energy generation stacks downward starting from zero:
    1. Verwachte Zon Productie ($-kW$) (amber/gold, `#F59E0B`)
    2. Thuisaccu Ontladen ($-kW$) (teal/cyan, `#14B8A6`)
- **Net Grid Power Line Overlay (`net_power_kw`):**
  - A prominent continuous bold crimson red line (`#EF4444`, `borderWidth: 3`) drawn directly across the bar chart:
    - Line $>0$: Netto netafname (drawing power from the grid).
    - Line $<0$: Netto teruglevering (surplus power fed into the grid).
    - Line $=0$: 100% self-sufficient balance.
  - *Color Palette Rationale:* Red (`#EF4444`) provides instant visual contrast against blue (baseload), pink (SWW), indigo (CV), emerald (battery charge), amber (solar), and teal (battery discharge), preventing visual confusion with the orange total consumption line or amber solar bars.
- **Synchronized Zero Horizon Axis:**
  - Mathematically lock the zero grid line between the primary left Y-axis (Power in kW) and secondary right Y1-axis (Price in €/kWh):
    $$\text{zeroRatio} = \frac{|\text{minY}|}{\text{maxY} - \text{minY}}$$
    $$\text{syncdMinP} = -\left(\frac{\text{zeroRatio}}{1.0 - \text{zeroRatio}}\right) \cdot \text{maxP}$$
  - Guarantees $0\text{ kW}$ and $€0.00/\text{kWh}$ sit on the exact same horizontal grid line across the canvas.
- **Mobile Touch Tooltips & Zero Filtering:**
  - Attach a global `touchstart`/`click` listener to dismiss sticky tooltips when tapping outside canvas on mobile.
  - Apply a tooltip `filter` callback to suppress inactive devices with $0\text{ kW}$, keeping touch popups clean.
- **Non-Smart Appliance Solar Surplus Advice Window:**
  - Sum unallocated solar surplus ($\sum \max(0, P_{\text{solar}} - P_{\text{scheduled}})$) across the 24h horizon.
  - Display an actionable advice banner and summary badge (e.g. `🧺 Circa 5.0 kWh vrij overschot om 17:00`) so homeowners know the optimal window to manually trigger washing machines, dryers, dishwashers, or EV charging.

### 4. Solar-Prioritized Dispatch Rules for Heat Pump SWW & Battery:
- **Never Blindly Schedule SWW Boiler or Battery Charging Purely on Lowest Grid Tariff:**
  - When abundant solar production is forecast ($\ge 1.0$ kW), free self-generated rooftop electricity is economically and thermodynamically superior to any grid tariff.
  - **SWW Boiler Priority:** If peak daylight solar $\ge 1.0$ kW, schedule the 350L boiler run (1.2 kW electrical) at the hour of peak solar irradiance (e.g. 11:00-14:00) for 100% solar self-consumption. Fall back to the lowest EPEX tariff only on dark or heavily overcast days.
  - **Battery Charging Priority:** If daytime solar surplus exceeds baseload and SWW, prioritize charging the battery exclusively from free solar surplus rather than purchasing grid power.
  - **Battery Discharge Optimization:** Schedule battery discharge during evening peak tariff hours (€0.38 - €0.44/kWh) or high dinner-time loads to displace expensive grid import.

### 5. Chart Container Sizing, Legend Hygiene & Timestamp Normalization:
- **Canvas Vertical Sizing:** On dual-polarity charts spanning $-3$ kW to $+3$ kW, small continuous loads (e.g. 300 W baseload) appear crushed on standard 288px (`h-72`) canvases. Maintain a container height of at least `h-[420px]` / `sm:h-[460px]` with Y-axis tick intervals of `0.5 kW` for clear readability.
- **Single Legend Hygiene:** Disable Chart.js's built-in canvas legend (`plugins: { legend: { display: false } }`) to prevent duplicate legends, and display dedicated responsive HTML legend chips below the chart.
- **Open-Meteo ISO 'T' Timestamp Normalization:**
  - *Pitfall:* Open-Meteo hourly timestamps contain an ISO `'T'` separator (e.g. `"2026-09-08T13:00"`). Comparing against space-delimited timestamps (`"%Y-%m-%d %H:00"`) produces dictionary key mismatches, silently resulting in 0 kW solar forecasts across the entire 24h timeline.
  - *Solution:* Always normalize incoming timestamps with `t.replace("T", " ")[:13] + ":00"`.

### 6. Dynamic Dispatch & Recommendation Banner:
- Identifies the cheapest electricity window across the rolling horizon (e.g. *"Beste stroomtarief om 15:00 (€0.1823/kWh)"*).
- Displays actionable dispatch recommendations and battery state messages.

- **Dynamic Horizon Zooming on Young Databases:**
  - *Pitfall:* When querying a brand-new database (<24h old) with fixed 24h group-by queries (`GROUP BY time(1m) fill(none)`), 1,400+ leading intervals return null or 0. Chart.js squashes the active signal into the far-right edge, appearing blank.
  - *Solution:* Locate the first index with non-null data ($t_{\text{first}}$) and dynamically slice the returned time window to start from $\max(0, t_{\text{first}} - 5\text{m})$, displaying an immediate, informative zoomed view without waiting 24 hours.
- **Abolishing Artificial Blocks: `fill(none)` & Timestamp Alignment:**
  - *Pitfall:* Never use `fill(previous)` on a sparse or young time series. It extrapolates the last single recorded point across all future empty intervals, creating a fake, flat horizontal rectangle across the visualizer.
  - *Solution:* Use `fill(none)`. In Python, merge extracted series by timestamp into a dictionary (`ts_map`), sort by timestamp, and plot only verified intervals.
- **Dutch Local Timezone Alignment (CEST / CET vs UTC):**
  - *Pitfall:* InfluxDB timestamps are stored in UTC (`Z`). In Docker, Python's `.astimezone()` evaluates to the container's default UTC clock, causing a 2-hour lag against Dutch CEST time.
  - *Solution:* Explicitly pass `zoneinfo.ZoneInfo("Europe/Amsterdam")` to Python's `.astimezone(AMS_TZ)`, set `TZ: "Europe/Amsterdam"` in `config.yaml`, and export `TZ="Europe/Amsterdam"` in `run.sh`.
- **Add-on Core API Access & Output Unbuffering:**
  - *Pitfall:* Add-on background daemons fail to poll Home Assistant Core states if `homeassistant_api: true` is omitted from `config.yaml`, and stdout logs stay buffered indefinitely in 4KB memory blocks.
  - *Solution:* Declare `homeassistant_api: true`, read `os.environ.get("SUPERVISOR_TOKEN")`, and always execute container daemons with `exec python3 -u "$DAEMON_SCRIPT"` and `export PYTHONUNBUFFERED=1`.

---

## 11. Separation of Legacy Hermes Cronjobs vs. Modular Open HEMS Datastores

When migrating legacy automation scripts to a dedicated add-on, maintain strict operational and database separation:
1. **Legacy Standalone Scripts (`/config/predict_and_log_energy.py`, `job_id: df6ca8bf8984`):**
   - Read from Home Assistant InfluxDB (`hassio`) / SQLite (`home-assistant_v2.db`) as user `hermes`.
   - Write to InfluxDB (`hermes`) as user `hermes`.
   - Sync to Google Sheets / send daily Telegram briefings.
2. **Open HEMS Add-on (`/config/addons/open-hems`):**
   - Dedicated database: `openhems` in InfluxDB (`http://a0d7b954-influxdb:8086`), user `openhems`.
   - Complete self-contained background accumulator and REST APIs.
3. **Cronjob Output Hygiene:**
   - Standalone scripts triggered by Hermes cronjobs must never print raw database warnings or HTTP errors to `stdout`. Hermes treats `stdout` as the delivered message body sent to Telegram.
   - Route internal operational errors to `/config/logs/energy_data_collector.log`, keeping user briefings clean and concise.

---

## 12. Canonical 7×24 Unallocated Load Profile Modeling from Home Assistant SQLite

To model authentic household baseline demand across all 168 hours of the week:
1. **The Energy Balance Formula:**
   $$\text{Total Real Household Load} = (\text{P1 Import} - \text{P1 Export}) + \text{Solar Generation}$$
   $$\text{Direct Consumed Solar} = \max(0.0, \; \text{Solar Generation} - \text{P1 Export})$$
   $$\text{Unallocated Household Consumption} = \text{Total Household Load} - \text{Heat Pump} - \text{Battery Charging}$$
2. **Canonical SQLite Data Source:**
   - Query the `statistics` table in `/homeassistant/home-assistant_v2.db` across 180 days using delta sums (`sum - LAG(sum) OVER (...)`).
   - Sourced from: `sensor.daily_energy_consumption` (P1 import), `sensor.daily_energy_returned` (P1 export), `sensor.zonnepanelen_export_power` (solar), and `sensor.daily_energy_usage_sum_wp` (heat pump).
3. **Statistical Filtering:**
   - **Night (00:00–06:00):** Use the 25th percentile ($P_{25}$) to isolate pure standby (~295–320 W) and eliminate outliers (car charging, defrosts).
   - **Day & Evening (06:00–24:00):** Use 15% trimmed mean to capture authentic living patterns (morning coffee 560–740 W, daytime 600–860 W, Tuesday laundry peaks up to 990 W).

---

## 13. Same-Column Alignment & 15-Minute Dynamic Market Integration

1. **Chart.js Same-Column Alignment:**
   - Assign identical `stack: 'energy'` to all positive consumer bars and negative production bars. Chart.js stacks positive values upward and negative values downward in the exact same column without side-by-side splitting.
2. **15-Minute Resolution (`[ 1 Uur ] [ 15 Min ]` Toggle):**
   - Query EnergyZero with `interval=INTERVAL_QUARTER` for 96 quarter-hour slots per 24 hours.
   - Scale Riemann integrals with $\Delta t = 0.25\text{h}$ for 15-minute resolution ($E = \sum P_i \cdot 0.25$, $\text{Cost} = \sum P_{\text{net}} \cdot \text{price} \cdot 0.25$).
3. **Summer Lockout for Predictive CV Heating:**
   - Enforce 24h mean temperature $\ge 15^\circ\text{C}$ or max temperature $\ge 18^\circ\text{C}$ to strictly force CV space heating to 0.0 kW during summer, preventing artificial 550W nighttime bars.

---

## 14. Direct Inepro Modbus MQTT Streaming Ingestion & Background Subscriber Thread

1. **High-Frequency Ingestion Architecture:**
   - Energy meters streaming high-frequency Modbus data via an MBMD daemon or bridge directly publish to MQTT (e.g. `mbmd/inepro1-103/Power` for solar inverter, `mbmd/inepro1-102/Power` for heat pump).
   - Rather than waiting on Home Assistant entity polling cycles, spawn a dedicated background MQTT subscriber thread (`HemsMqttSubscriberThread`) connecting directly to Mosquitto (using dedicated credentials from `/config/open_hems_secrets.json`).
   - Maintains an in-memory zero-latency cache (`self.mqtt_sub.cache[topic]`) continuously refreshed on every incoming message.
2. **Layer 1 Accumulator Feed & Fallback:**
   - When sampling devices every 10 seconds:
     - If `source_type == "mqtt"`: read the live value directly from `self.mqtt_sub.cache.get(mqtt_power_topic)`. For solar generation (reported as negative Watts by meters), apply `abs()` so generation is positive in the power balance.
     - Fallback: if the topic is temporarily missing from the MQTT cache, immediately fall back to the Home Assistant entity (`ha_power_entity`).
   - Eliminates polling latency while preserving 100% resilience.

---

## 15. Unified 6-Box Metrics Grid with Integrated Monetary Costs & Canonical Theme Colors

1. **Standardized 6-Box Metrics Grid (2 Rows × 3 Columns):**
   - Align both the historical Power Producers chart and the 24-Hour Ahead Prediction chart to use the exact same 6-card metrics layout:
     - **Box 1 (Zonnepanelen):** Total kWh, Last/Min kW, and Monetary Generation Value (€).
     - **Box 2 (Teruglevering):** Total kWh, Last/Min kW, and Monetary Export Revenue (€).
     - **Box 3 (Afname):** Total kWh, Last/Max kW, and Monetary Grid Cost (€).
     - **Box 4 (Totaal opgewekt):** Total kWh, Last/Min kW, and Total Generation Value (€).
     - **Box 5 (Opgewekt Gebruikt):** Total kWh, Last/Min kW, and Net Self-Consumption Avoidance Savings (€).
     - **Box 6 (Totaal Verbruik):** Total kWh, Last/Max kW, and Gross Energy Cost (€).
2. **Integrated Monetary Calculations with Dynamic Tariffs:**
   - Multiply each energy slice with its corresponding EPEX / EnergyZero spot price:
     - Discrete Riemann sum: $\text{Cost} = \sum \frac{P_i \cdot \Delta t_{\text{hours}} \cdot \text{price}_i}{1000.0}$ [€].
     - Display energy and monetary value together cleanly in the card header (e.g. `17.9 kWh` with `€6.05`).
3. **Canonical Color Theme (`data/theme_colors.json`):**
   - Maintain a single, centralized JSON configuration specifying hex, rgb, fill, and polarity for each metric, device type, and chart overlay:
     - Zonnepanelen: `#EAB308` (Yellow)
     - Teruglevering: `#10B981` (Emerald)
     - Afname: `#EF4444` (Red)
     - Totaal opgewekt: `#84CC16` (Lime)
     - Opgewekt Gebruikt: `#06B6D4` (Cyan)
     - Totaal Verbruik: `#F97316` (Orange)
     - Netto Lijn: `#EF4444` (Felrood)
     - Prijslijn: `#06B6D4` (Cyan gestreept)

---

## 16. Site-Specific Adapters Architecture (`site_adapters/`) & Heat Pump State Disaggregation

1. **Decoupled Architecture Principle (Core vs. Site Adapters):**
   - Keep generic open-source energy models, scheduling algorithms, and analytics strictly free from hardware-specific or site-specific quirks.
   - House installation-specific classifiers, bridges, and vendor adapters in a dedicated sub-package (`site_adapters/<vendor_hardware>/`, e.g. `site_adapters/daikin_p1p2/`).
2. **Autonomous Engine Rule (Avoid Dependency on External HA Automations):**
   - Core telemetry disaggregation must never depend on external Home Assistant YAML automations or helper scripts. If HA restarts, triggers misfire, or YAML automations are paused, the entire energy pipeline would fail.
   - Replicate the decision logic directly inside the engine via an autonomous classifier (`HeatPumpStateClassifier`) reading raw bus signals directly from MQTT, using Home Assistant entities only as a resilient secondary fallback.
3. **Heat Pump Disaggregation Decision Tree:**
   - **Standby Safety (< 48 W):** When total active power is below the idle compressor threshold (~30-36 W for Daikin Altherma), immediately classify as `STANDBY` with 100% of draw allocated to `standby_w`, preventing idle power from polluting heating or DHW integrals.
   - **DHW Mode:** If P1P2 action is `fan`, `DHW_Demand == 1`, 3-way valve is energized toward boiler, or HA `binary_sensor.hc_dhw_dhw_demand == 'on'`, allocate 100% of power to `dhw_w`.
   - **Cooling Mode:** If P1P2 action is `cooling`, `Climate_Cooling == 1`, or HA cooling mode is on, allocate to `cooling_w`.
   - **Space Heating (CV) Mode:** If P1P2 action is `heating`, `Climate_Heating == 1`, or HA heating mode is on, allocate to `heating_w`.
   - Disaggregated metrics enrich InfluxDB `energy_telemetry` with tag `mode={mode_tag}`.

---

## 18. Lean & Mean Two-Category Dashboard Architecture (Voorspelling vs. Historie)

When organizing high-density energy management dashboards, resist sprawling unstructured cards and redundant text clutter:
1. **The 4 Key KPI Boxes at the Top:**
   - Pin the four primary analytical outcomes (`Besparing Vandaag`, `Zelfconsumptie %`, `Warmtepomp COP`, and `Prognose Validatie %`) cleanly at the very top of the page without preceding vertical banner waste.
2. **Category 1: Voorspelling (Forecast):**
   - Groups forward-looking predictive models:
     - `Verbruiksvoorspelling`: 24-hour ahead rolling stacked bar chart, clean optimizer banner, non-smart solar appliance advice, and aligned 6-box projected energy and cost cards.
     - `Prijzen & Zonnevoorspelling`: EPEX Spot electricity market rate curve and Open-Meteo solar radiation forecast with quarter-hour / hourly toggle.
   - Dedicated Category Bar: Houses forecast-specific controls (`[ 1 Uur | 15 Min ]` and `[ Verversen ]`).
3. **Category 2: Historie (Historical Data):**
   - Groups empirical telemetry and performance auditing:
     - `Verbruikshistorie`: Dual-polarity power flows (Afname, Opgewekt Gebruikt, Teruglevering, Zon Direct Benut) with actual accumulated costs (€).
     - `Prestatie & Dagrapport`: Automated daily analytical digest and seasonal COP breakdown.
   - Dedicated Category Bar: Houses history-specific controls (`[ 📊 Staven | 📈 Lijn ]`, `[ 1 Uur | 15 Min ]`, `Periode [ 24 uur v ]`, and `[ Verversen ]`).
4. **Decluttering & Punchy Title Rule:**
   - Strip out redundant provenance badges (like `openhems`) on chart titles.
   - Remove verbose multi-line explanatory subtitles under graph headers.
   - Use direct, punchy Dutch titles (`Verbruiksvoorspelling`, `Prijzen & Zonnevoorspelling`, `Verbruikshistorie`).

---

## 19. Line Protocol Formatting Safety & Lossless Historical Backfill via HA Recorder History

1. **Line Protocol String Formatting Safety Pitfall:**
   - *Pitfall:* Referencing optional tag variables (e.g. `{mode_tag}`) in InfluxDB Line Protocol formatting strings without guaranteeing they are defined across all device types and branches throws an uncaught `NameError`. In background worker daemons, this silent crash aborts the 60-second flush loop indefinitely on every tick, causing all database writes to abruptly stop while external health checks continue reporting green.
   - *Solution:* Always evaluate optional tags safely before formatting:
     ```python
     mode_tag = f",mode={parts[6]}" if len(parts) > 6 else ""
     lines.append(f"energy_telemetry,device_id={dev_id},device_type={dev_type},flow={flow},source_type={src_type},vector={vector}{mode_tag} {field_name}={mean_val} {now_ns}")
     ```
2. **Lossless Historical Telemetry Backfill (Strict No-Mock Rule):**
   - If an ingestion daemon temporarily halts, NEVER substitute simulated or interpolated mock data.
   - Query Home Assistant Core's native history API (`/core/api/history/period/<timestamp>?filter_entity_id=...` using `SUPERVISOR_TOKEN`), which preserves genuine continuous sensor states (`sensor.power_consumption`, `sensor.power_production`, `sensor.zonnepanelen_power`, `sensor.warmtepomp_power`).
   - Resample high-frequency recorder state changes into 1-minute discrete averages matching the tumbling window, and POST them directly to the dedicated database (`openhems`) via Line Protocol to completely restore chart continuity without data loss.

---

## 20. Deterministic Canonical Unit Normalization (`kW` vs. `W`) & Hardware Contract Enforcement

1. **The Dangerous Fallacy of Numerical Magnitude Thresholds:**
   - *Pitfall:* Attempting to detect whether a power sensor is reporting in `kW` or `W` based on a numerical threshold (e.g. `if val < 25.0: val *= 1000.0`) is fundamentally flawed.
   - *Failure Mechanism:* In modern homes with solar PV or dynamic battery arbitrage, the house often operates in zero-grid balancing mode, drawing legitimately between `5 W` and `15 W` from the grid. A numerical heuristic wrongly assumes `10 W` is `0.010 kW` and multiplies it by 1,000, creating an artificial `10,000 W` spike that corrupts energy records and trips overload protection policies.
2. **Deterministic Contract Precedence (`models/canonical.py`):**
   - Enforce an explicit hardware-contract in the device registry (`heatpump_config.json`):
     ```json
     {
       "id": "main_grid_meter",
       "ha_power_entity": "sensor.power_consumption",
       "native_unit": "kW",
       "storage_unit": "W"
     }
     ```
   - In `normalize_power_reading(value, unit=None, device_cfg=None) -> Optional[float]`:
     1. **Device Configuration Contract (Highest Priority):** If `device_cfg['native_unit'] == 'kW'`, strictly multiply by 1,000.0 regardless of magnitude (`0.010 kW` becomes guaranteed `10.0 W`, and `1.485 kW` becomes `1485.0 W`).
     2. **Sensor Metadata (Priority 2):** If the Home Assistant entity attributes explicitly declare `unit_of_measurement == 'kW'`, multiply by 1,000.0.
     3. **Native Watt Pass-Through (Priority 3):** If `unit == 'W'` or `device_cfg['native_unit'] == 'W'` (e.g. Modbus Inepro meters), pass through the float unaltered (`35 W` stays `35.0 W`).
     4. **Input Safety:** Return `None` for non-numeric or transient states (`unavailable`, `unknown`, `None`).
3. **Strict Prohibition on Ad-Hoc Script Bypasses:**
   - Ad-hoc scripts, migration tools, and manual backfill runners must NEVER parse raw database states directly into InfluxDB without routing through `normalize_power_reading()`. Enforce regression tests in `tests/unit/test_canonical_models.py` verifying low-power zero-grid balancing, high-draw appliances, and hardware contract overrides.

---

## 21. Perfect Center-Aligned Horizontal 0-Axis Synchronization (`min = -max`)

When plotting dual-axis charts featuring dual-polarity power (W or kW) on the left axis and dynamic market electricity tariffs (€/kWh) on the right axis:
- **The Problem:** Setting independent dynamic bounds (e.g. power from $-2.5$ to $+4.5$ kW and price from $€0.00$ to $€0.40$/kWh) causes the 0-line of the price to sit at the very bottom while 0-power floats mid-canvas. Calculating dynamic `zeroRatio` shifts the horizon up and down on every data refresh.
- **The Center-Aligned Symmetric Horizon Pattern:**
  - Compute the maximum absolute bounds for power and price:
    ```javascript
    let maxAbsWatt = Math.max(...allWattVals.map(Math.abs), 1500);
    maxAbsWatt = Math.ceil(maxAbsWatt / 500) * 500;
    
    let maxAbsPrice = Math.max(...allPriceVals.map(Math.abs), 0.30);
    maxAbsPrice = Math.ceil(maxAbsPrice * 10) / 10;
    ```
  - Assign symmetric ranges to both axes:
    - Primary Left Axis (`y` in Watts): `min: -maxAbsWatt`, `max: maxAbsWatt`.
    - Secondary Right Axis (`y1` in €/kWh): `min: -maxAbsPrice`, `max: maxAbsPrice`.
  - **Result:** Because `min === -max` on both axes, the horizontal zero line for both Watts and Tariffs is mathematically locked to **exactly 50.0% of the canvas height** (exact center) regardless of screen width or zoom level. Highlight the center gridline with `lineWidth: 2` and a distinct border color (`#94A3B8` / `#CBD5E1`).

---

## 22. Contractually Differentiated Dynamic Tariffs & Styled Custom HTML Tooltips

### 1. Contractually Differentiated Dynamic Tariffs:
Never evaluate solar generation or grid flows against a single blanket electricity price:
- **Direct Solar Self-Consumption (Opgewekt Gebruikt):**
  - Valued against the **Full All-in EPEX Import Tariff** (including energy taxes, supplier markup, and 21% VAT, e.g. ~€0.28–€0.35/kWh).
  - *Mechanism:* Every kWh consumed directly from rooftop panels behind the meter avoids purchasing an equivalent kWh from the grid at the full consumer retail price.
- **Grid Export (Teruglevering):**
  - Valued against the **Dynamic Export Tariff** (kale EPEX Spot base price *minus* supplier export fee / verkoopopslag, e.g. €0.00605/kWh for Powerpeers, with zero energy tax or VAT pass-through, e.g. ~€0.11–€0.19/kWh).
  - *Mechanism:* In post-net-metering or dynamic billing, export compensation does not receive tax credit refunds; it is strictly indexed to spot market energy value minus commercial handling fees.

### 2. Custom Modern HTML Tooltips with Real Line Indicators & Mobile Pinning:
Standard Chart.js canvas tooltips display generic square color dots and vanish instantaneously on mobile touch screens:
- **The Mobile Touch Vanishing Pitfall:**
  - On touch devices, lifting a finger emits `touchend`, which triggers Chart.js to emit `tooltip.opacity = 0` within 1ms. Mobile users never see the tooltip or assume it is broken.
  - *Solution (Pinned on Tap):* In the custom tooltip handler, set `window.__tooltipPinned = true` when active data points are tapped, keeping the HTML tooltip visible with `opacity = 1` until the user explicitly taps outside the canvas (`!e.target.closest('canvas')`).
- **Visual Line Indicators for Curves:**
  - For line datasets (`Totaal Verbruik`, `Netto Grid Stroom`, `Stroomprijs All-in`), render true colored horizontal bars (`width: 18px; height: 3px; border-radius: 2px`) or dashed borders (`border-top: 2px dashed #06B6D4` for tariffs), reserving rounded square chips only for stacked bar loads.
- **Granular Interval Costs:**
  - Accompany every power figure with its interval monetary impact: `Afname: +€...` (in red), `Teruglevering: -€... opbr.` (in emerald), `Opgewekt Gebruikt: €... besp.` (in cyan), and `Totaal Verbruik: €... bruto` (in orange).
  - Include an explicit footer calculating the interval net balance (`Netto Kosten: €...` or `Netto Opbrengst: +€...`).

---

## 23. Unified Energy Chart Component Architecture (Forecast & History Identical)

Forward-looking predictive charts (`Verbruiksvoorspelling`) and backward-looking telemetry charts (`Verbruikshistorie`) must be functionally and visually identical to maintain consistency, eliminate cognitive friction, and avoid duplicate UI maintenance:

1. **Pure Energy Volume (kWh) as Primary Metric:**
   - Always plot discrete interval energy in **kWh** (`E = P_kW \cdot \Delta t`) rather than instantaneous power.
   - Left Y-axis title: `Opbrengst (-kWh) < 0 < Verbruik (+kWh)`.
   - Tick callbacks format pure kilowatt-hours: `1.00 kWh`, `1.50 kWh`, `0.00 kWh`, `-1.00 kWh`.
   - Tooltips display energy in kWh as the primary value with power in Watts/kW in secondary parentheses: `0.92 kWh (919 W)`.
2. **Symmetric Center-Aligned Zero Horizon (`min = -max`):**
   - Both the primary left Y-axis (kWh) and secondary right Y1-axis (€/kWh) must use symmetric bounds: `min = -maxAbsKwh`, `max = maxAbsKwh` and `min = -maxAbsPrice`, `max = maxAbsPrice`.
   - Locks the 0-line of both energy and price permanently to **exact 50% canvas height** regardless of zoom or aspect ratio.
3. **EPEX All-in Market Tariffs Overlay:**
   - Both charts display the cyan dashed line (`#06B6D4`, `borderDash: [4, 4]`) on the secondary right Y1-axis (`y1`), reflecting the active dynamic market rate.
4. **Shared Tooltip Component (`customHemsTooltipHandler`):**
   - Share a single, unified tooltip engine between forecast and history.
   - Displays real horizontal line markers for curve series and rounded pills for stacked bars.
   - Computes contractually differentiated monetary impacts per stream (full retail for import & self-consumption avoidance, spot minus commercial markup for export).
   - Omit redundant mirror datasets: if `Opgewekt Gebruikt` is present, suppress `Zon Direct Benut` in tooltips to prevent repetitive rows.
   - Concludes with an interval net summary footer (`Netto Kosten: €...` / `Netto Opbrengst: +€...`).

---

## 24. Chart.js Ingress Pitfalls: Callback Stripping & Double-Scaling

1. **Callback Stripping via `JSON.parse(JSON.stringify(config))`:**
   - *Symptom:* Switching tabs in an Ingress SPA breaks custom HTML tooltips and tick formatting on one of the charts, falling back to basic black canvas popups or unformatted numeric labels.
   - *Cause:* Using `JSON.parse(JSON.stringify(chartConfig))` to clone a Chart.js configuration across multiple canvases silently deletes all JavaScript functions (`plugins.tooltip.external`, `ticks.callback`, `grid.color`).
   - *Solution:* Never deep-clone chart configurations via JSON serialization. Use a factory function (`makeChartConfig()`) that returns a fresh object instance per canvas, or use shallow cloning (`Object.assign({}, chartConfig)`) that preserves function references.
2. **Double-Scaling Interval Energy (`kWh = kW * dt`):**
   - *Symptom:* Tooltips report absurdly low or high energy values (e.g. `0.00 kWh` or `1 W` when consumption is nearly 1 kWh).
   - *Cause:* If chart datasets are pre-converted to kWh before passing to Chart.js, a tooltip handler that assumes inputs are raw Watts and applies `absVal / 1000.0 * intervalH` divides the value a second time.
   - *Solution:* Standardize datasets across both charts to store pure kWh directly. In `customHemsTooltipHandler`, assign `kwhVal = abs(rawVal)` directly and derive instantaneous power in reverse: `powerW = Math.round((absVal * 1000.0) / intervalH)`.

---

## 25. Physical Reality Defaults & Opt-in What-If Simulation Toggles

In autonomous energy management systems, forward-looking predictive scheduling must adhere to the universal strict No-Mock directive:

1. **The Phantom Equipment Pitfall:**
   - Simulating hypothetical or planned hardware (such as an uninstalled 10 kWh home battery) by default in operational production charts produces phantom charge/discharge datasets (`Accu Laden: 0.00 kWh`, `Accu Ontladen: 0.00 kWh`), pollutes household energy balances, and misleads the homeowner into believing a physical actuator is being dispatched.
2. **Pure Physical Hardware as Default:**
   - In device registries (`heatpump_config.json`), devices not physically present must be marked `"installed": false, "enabled": false`.
   - The predictive dispatch engine must strictly plan only physically verified installed equipment (e.g. 350L SWW boiler, CV space heating, rooftop solar PV, and household baseload). Uninstalled devices are completely excluded from chart datasets, tooltip rows, and advice messages.
3. **Opt-in What-If Scenario Toggles (`[ 🔋 Accu: Uit | Simuleer ]`):**
   - To support financial ROI and capacity exploration without corrupting operational data, provide an interactive UI switch in the forecast header (`[ 🔋 Accu: Uit | Simuleer ]`).
   - When set to `Simuleer`, the API accepts `?simulate_battery=1` and returns the hypothetical schedule alongside a prominent visual indicator: `(Wat-als Simulatie)`.
   - This cleanly separates daily operational dispatch from exploratory financial what-if planning.
4. **Deduplication of Symmetrical Energy Telemetry:**
   - In dual-polarity power representations, self-consumed solar power can appear both as positive load (`Opgewekt Gebruikt: +829 W`) and as negative on-site production absorption (`Zon Direct Benut: -829 W`).
   - Displaying both identical figures with opposing polarities in the same hover tooltip creates confusing redundancy that looks like artificial mock data.
   - In UI tooltips, display each distinct energy flow strictly once: keep `Opgewekt Gebruikt: 0.83 kWh (€0.19 besp.)` and suppress the negative mirror dataset (`Zon Direct Benut`) so every row maps 1:1 to a real physical flow.

---

## 26. Multi-Resolution Energy & Cost Scaling, Rolling Horizon Sync, and Instant Tooltip Dismissal

### 1. Multi-Resolution Energy & Cost Scaling (1-Hour vs 15-Minute Integrals):
- **The Pitfall of Defaulting Duration (`intervalH`):**
  - When switching an empirical or predictive bar chart from 1-hour to 15-minute resolution (e.g. 24 to 96 bars), if the frontend dataset transformer fails to update its time-step factor, it falls back to `intervalH = 1.0h`.
  - A real 15-minute power reading (e.g. $1,545\text{ W}$) is erroneously integrated as:
    $$E = 1,545\text{ W} \times 1.0\text{ h} / 1,000 = 1.545\text{ kWh} \quad (\text{instead of } 0.386\text{ kWh})$$
  - The tooltip displays a fourfold inflated energy volume ($1.54\text{ kWh}$), fourfold inflated costs ($€0.55$ instead of $€0.14$), and derives an impossible household draw ($\frac{1.54\text{ kWh}}{0.25\text{ h}} = 6.18\text{ kW}$).
- **The Solution:**
  - Always pass and consume `data.interval_h` from the backend API.
  - In client-side transformers, explicitly bind `const intervalH = data.interval_h || (res === '15m' ? 0.25 : 1.0)`.
  - Ensure discrete interval energy and costs scale strictly with $\Delta t$:
    $$E_{\text{interval}} = \frac{P_{\text{watts}} \cdot \Delta t}{1,000} \quad [\text{kWh}], \qquad \text{Cost} = E_{\text{interval}} \cdot \text{Tariff}_{\text{all-in}} \quad [\text{€}]$$

### 2. Synchronized Rolling 24-Hour Horizon for Forward-Looking Charts:
- **The Stale Midnight Anchor Pitfall:**
  - Standard day-ahead pricing and weather charts frequently query API date endpoints and filter by `if dt.date() == today.date()`, causing the time-axis to begin at `00:00` midnight of the current day. By mid-morning or afternoon, half the chart displays past history rather than actionable forecast.
- **The Solution:**
  - Align all predictive and market charts to a rolling 24-hour horizon starting at the active slot: `Nu (%H:%M)` (or `Nu (%H:00)`).
  - Query both today's and tomorrow's day-ahead EPEX spot prices and 48-hour Open-Meteo irradiance forecasts.
  - Slice exactly 24 slots (1h) or 96 slots (15m) starting from `now.replace(minute=(now.minute // 15) * 15, second=0)` forward, guaranteeing seamless alignment across all forecasting tools.

### 3. Instant Tooltip Dismissal on Mouse Leave (Desktop Cursor vs Mobile Touch):
- **The Stuck Hover Box Pitfall:**
  - Implementing persistent pinning (`window.__tooltipPinned = true`) to help mobile users keep tooltips open on tap breaks desktop usability: moving the mouse cursor outside the chart area leaves the custom HTML box permanently floating over UI elements.
- **The Solution:**
  - Differentiate mouse cursor movement from touch events.
  - In `customHemsTooltipHandler`, dismiss the tooltip immediately (`opacity = '0'`, `pointer-events = 'none'`) whenever Chart.js emits `tooltip.opacity === 0` (cursor not hovering over a data point).
  - Attach `mouseleave` and `mouseout` event listeners to all chart canvases to guarantee immediate closure when the cursor crosses the canvas boundary.
  - Retain touch-friendly tap persistence exclusively by clearing tooltips on document `pointerdown` outside canvas elements.

---

## 27. Home Assistant Core as a Bi-Directional Infrastructure Pillar (Source & Actuation Target)

When designing a Home Assistant add-on or smart home management framework, Home Assistant Core is not merely an external tool or read-only sensor provider; it is a **primary bi-directional infrastructure pillar** operating alongside InfluxDB (Time-Series Storage) and MQTT (Streaming Message Bus).

### 1. The Dual Role of Home Assistant Core:
- **📥 Data-Bron (Incoming Sensor Telemetry):**
  - Continuous physical meter feeds: P1 DSMR smart meter (`sensor.power_consumption`, `sensor.power_production`).
  - Sub-metering and generation: SolarEdge inverter (`sensor.zonnepanelen_power_avg_5_minutes`), Daikin heat pump active power (`sensor.warmtepomp_power`).
  - Thermal sensors & operational states: 350L SWW boiler temperature (`sensor.hc_dhw_temperature_r5t_dhw_tank`), compressor state (`sensor.hc_mode_compressor`), and 3-way valve position.
  - Market tariffs & environmental feeds: EnergyZero dynamic hourly/quarter-hourly pricing entities and weather forecasts.
- **📤 Aansturing Doel (Actuators, Switches & Macro-Dispatch):**
  - Physical Smart Grid relay contacts: SG1/SG2 binary relays (`switch.warmtepomp_smart_grid_1_s10s`, `s11s`) wired to Daikin S10S/S11S inputs in volatile RAM.
  - Heat pump boost switches: `switch.hc_mode_altherma_on` (energizing forced DHW reheat cycles while locking out 9 kW backup heaters).
  - Climate setpoints: `climate.hc_dhw_dhw_setpoint` for dynamic hot water target adjustments.
  - Shiftable appliance plugs: smart sockets for dishwashers, washing machines, or EV chargers.

### 2. Infrastructure Console Visualization Standard (Verbindingen & Opslag):
Prominently display Home Assistant Core at the top of the Infrastructure view with:
1. **Header Card:**
   - Provider name: `Home Assistant Core API` with `INGEBOUWD (HAOS)` badge.
   - Internal Supervisor API endpoint: `http://supervisor/core/api`.
   - Live status indicator: pulsing green badge (`Verbonden (200 OK)`).
   - Core metadata: Home Assistant version (e.g. `2026.9.1`), location name (e.g. `WeidHuis`), and live ping latency in milliseconds (~5–10ms).
   - Test button: `[ ⚡ HA Verbinding Testen ]` invoking `POST /api/infrastructure/homeassistant/test`.
2. **Bi-Directional Split Grid (Bron vs. Doel):**
   - **Left Column (📥 Data-Bron):** Lists all configured incoming sensors with their device friendly name, entity ID (`font-mono text-cyan-400`), and live state with measurement units (`48.3 °C`, `1291 W`, `0.0 kW`).
   - **Right Column (📤 Aansturing Doel):** Lists all configured actuation targets with device friendly name, entity ID (`font-mono text-pink-400`), and live switch/state pill (`on` in emerald, `off` in slate).

### 3. Multi-Tier Supervisor Token Resolution & Secrets Vault Fallback:
- *Pitfall:* While `homeassistant_api: true` in `config.yaml` is meant to inject `SUPERVISOR_TOKEN`, subtle supervisor reloads, dev container environments, or standalone CLI test runs can leave `os.environ.get("SUPERVISOR_TOKEN")` undefined, breaking all HA API communication.
- *The Multi-Tier Resolver Pattern:*
  ```python
  def get_ha_api_token(sec: dict) -> str:
      return (
          os.environ.get("SUPERVISOR_TOKEN")
          or os.environ.get("HASSIO_TOKEN")
          or os.environ.get("HASS_TOKEN")
          or sec.get("homeassistant", {}).get("token", "")
      )
  ```
  Store verified backup tokens in the private secrets vault (`/config/open_hems_secrets.json`, permissions `chmod 0600`) so the add-on daemon and local test runners remain 100% operational across all environments.

---

## 28. Device Categorization per Connection Type & Full CRUD for Devices and Connectors

When scaling smart home and energy frameworks to multiple hardware resources, avoid sprawling unstructured lists where users cannot see how a device is connected:

### 1. Device Grouping by Connection Type (UI Pattern):
- Organize the **Apparaten & Hardware** catalog into 3 distinct sections based on `source_type`:
  1. 🏠 **Home Assistant Core Gekoppelde Apparaten:** Devices polled or controlled via Home Assistant entities (e.g. P1 DSMR meter, SWW boiler temperature sensor, and smart plugs).
  2. ⚡ **Directe MQTT & Modbus Apparaten:** Devices streaming high-frequency telemetry directly from local brokers (e.g. Inepro 103 solar and Inepro 102 heat pump Modbus meters on `mbmd/...`).
  3. 🔋 **Geplande / Standby Apparaten:** Equipment configured for simulation or future expansion (e.g. a planned home battery) with `installed: false` or `enabled: false`.
- **Quick Filter Bar:** Provide an interactive segmented pill bar at the top:
  `[ Alle Apparaten (N) | 🏠 Home Assistant (X) | ⚡ Direct MQTT (Y) | 🔋 Gepland (Z) ]`.

### 2. Device Hardware Contracts & Options in CRUD Modals:
- Ensure the Device Modal supports:
  - **Hardware Eenheid (Contract):** Hard selection between `Watt (W)` and `Kilowatt (kW)`. Enforces deterministic unit normalization, preventing zero-grid balancing errors.
  - **Installation & Activation Switches:** Checkboxes for `installed` (physical hardware present) and `enabled` (participates in active HEMS dispatch).
  - **Multi-Entity Mapping:** Power sensor (`sensor.xxx`), energy integral sensor, temperature sensor (e.g. DHW boiler `sensor.hc_dhw_temperature_r5t_dhw_tank`), and control switch (`switch.xxx` or `climate.xxx`).
  - **MQTT Topics:** Broker ID selection, telemetry topic, JSON key, and optional command topic.

### 3. Home Assistant Connector CRUD & In-Modal Testing:
- Treat Home Assistant Core as a first-class editable connector on the **Verbindingen & Opslag** tab:
  - **`[ ⚙️ Bewerken ]` Modal:** Configure the core URL (`https://<ha-domain>:8123` or `http://supervisor/core`), long-lived access token, timeout (seconds), and SSL verification toggle.
  - **In-Modal Ping Probe:** Include a `[ Testen ]` button directly in the modal that tests the connection before saving.
  - **Security Vault Rule:** Passwords and tokens must be stored exclusively in the `0600` private vault (`open_hems_secrets.json`), never in the plaintext site configuration. Mask existing tokens as `••••••••`.

### 4. Daemon Code Quality Guard (`python3 -m py_compile`):
- *Pitfall:* When programmatically modifying Python daemon files containing large embedded HTML or multi-line strings, whitespace indentation errors (`IndentationError`) can silently break container startup.
- **Solution:** Always run `python3 -m py_compile <daemon.py>` and a JavaScript syntax check (`node -c`) before deploying or releasing an add-on update.

---

## 29. Lean & Mean Settings Navigation Architecture ("Instellingen": Apparaten, Verbindingen, Data)

When finalizing the data collection and infrastructure layer in Home Assistant add-on dashboards, resist technical jargon or overly verbose navigation labels:

### 1. The Lean & Mean Menu Rule:
- Keep navigation labels direct, clean, and punchy. Avoid parenthetical qualifiers (e.g. use `"Apparaten"`, not `"Apparaten (Hardware Links)"`; use `"Verbindingen"`, not `"Verbindingen & Opslag (DB & MQTT)"`).
- Group the foundational layer under the single clear Dutch category header: **`Instellingen`** (replacing `"Laag 1: Data & Verbindingen"`).

### 2. Three Clean Submenus under "Instellingen":
1. **`Apparaten`:**
   - The physical and logical equipment catalog (P1 smart meter, heat pump, hot water boiler, solar PV, home battery).
   - Grouped dynamically by connection type with quick filter pills: `[ Alle Apparaten | 🏠 Home Assistant | ⚡ Direct MQTT | 🔋 Gepland / Standby ]`.
2. **`Verbindingen` (Consolidated Connector Console):**
   - Consolidates ALL external connections and interfaces into a single unified console:
     - **Home Assistant Core:** Bi-directional source & target entities with live states, latency probe, and `[ ⚙️ Bewerken ]` modal.
     - **MQTT Message Brokers:** Local Mosquitto broker (`core-mosquitto:1883`) or external gateways with socket verification and CRUD.
     - **Externe Data APIs & Feeds:** EPEX Spot market rates (EnergyZero) and Open-Meteo weather/solar forecasts. (Moves open APIs out of the top-level navigation into Verbindingen, eliminating sidebar clutter).
3. **`Data` (Storage & Pipeline Management):**
   - The dedicated datastore, retention, and ingest console:
     - **InfluxDB Tijdreeks Instanties:** Multi-instance database management (InfluxDB 1.8 / 2.x), retention policies, and credential test probes.
     - **60s Data Pipeline & Accumulator Monitor:** 3-stage flow diagram (Ingestion $\to$ 60s Window Accumulator $\to$ Datastore), RAM progress bar, and sample buffer.
     - **Live Telemetrie Monitor:** Live power balance table and real-time point ingestion counter.
     - **Test Telemetrie:** Direct write test button to validate database ingestion end-to-end.

---

## 30. Canonical Multi-Sensor & Multi-Actuator Device Architecture & Connector Decoupling

When scaling energy management and IoT controllers beyond single-metric devices, avoid binding a device to a single flat `ha_power_entity` or cluttering the connector console with device-level entities:

### 1. Complete Decoupling of Connectors (Transport) vs. Devices (Assets):
- **Connectors Tab ("Verbindingen"):**  
  Houses strictly the **transport lines and communication interfaces** (Home Assistant Core API with live ping latency and `[ ⚙️ Bewerken ]` modal, MQTT Mosquitto broker socket status, and external Market/Weather APIs). It displays a high-level summary (`N apparaten · M datastromen · K regiepunten`), but delegates all specific entity and topic assignments to the devices themselves.
- **Devices Tab ("Apparaten"):**  
  Houses the physical and logical energy assets (smart meter, heat pump, boiler, solar PV, home battery). Each device independently owns its own collection of **Sensors (Data-Inname)** and **Actuators (Aansturing & Regie)**.

### 2. Canonical Multi-Sensor Schema:
A single device frequently measures multiple physical streams or operates bi-directionally (e.g. a home battery charging from the grid while discharging to household loads; a smart grid heat pump drawing electrical power while reporting compressor running state, DHW demand, and water flow temperature).
- Each sensor in `dev["sensors"]` defines:
  - `id`: unique sensor key (e.g. `battery_charge_power`, `battery_discharge_power`, `compressor_state`).
  - `name`: human-readable description.
  - `role`: functional role in the energy balance:
    - `"consumer"`: Electrical or thermal load consuming energy. Added to total consumption integrals.
    - `"producer"`: Energy generation or feed-in (solar PV, battery discharge, grid export). Added to generation integrals.
    - `"state"`: Operational state, temperature, or SoC (%) providing decision context without direct power summation.
  - `connector`: transport line (`"homeassistant"` or `"mqtt"`).
  - `entity_id` / `topic`: the exact Home Assistant entity or MQTT topic.
  - `native_unit`: hardware contract (`"W"` vs. `"kW"`).

### 3. Canonical Multi-Actuator Schema (Automation Layer Readiness):
To prepare the system for automated dispatch, peak shaving, and tariff arbitrage without rebuilding the data model later, each device defines its controllable targets in `dev["actuators"]`:
- Each actuator defines:
  - `id`: actuator identifier (e.g. `smart_grid_mode`, `dhw_boost`, `battery_power_limit`).
  - `name`: friendly control label.
  - `type`: control archetype:
    - `"select"`: Multistate choice (e.g. `['Automatisch', 'Geadviseerd aan', 'Geforceerd aan', 'Geforceerd uit']`).
    - `"switch"`: Binary on/off toggle (e.g. forced DHW boost).
    - `"range"`: Numerical setpoint or percentage limit (e.g. boiler target $40\text{–}65^\circ\text{C}$, battery power limit $0\text{–}100\%$).
  - `connector`: dispatch target (`"homeassistant"` or `"mqtt"`).
  - `entity_id` / `control_topic`: target entity (e.g. `input_select.warmtepomp_smart_grid_modus`, `climate.hc_dhw_dhw_setpoint`).
  - `default_state`: safe fallback state.

### 4. Template-Based Device UX (Optie A Principle):
In device configuration modals:
- Selecting the Device Type (e.g. `Netmeter`, `Zonnepanelen`, `Warmtepomp`, `Warm Tapwatervat`, `Thuisbatterij`) automatically instantiates the canonical template sensors and actuators.
- Homeowners only need to map the entities/topics, while power users can add custom supplementary sensors or actuators via `[ + Sensor Toevoegen ]` and `[ + Actuator Toevoegen ]`.
- Preserves backward compatibility by mapping top-level `ha_power_entity` and `mqtt_power_topic` helpers to the primary active consumer/producer sensor.

---

## 31. Device Card UI Polish & Resilient ID-Based Modal Editing

When rendering complex hardware resource cards in Ingress SPAs:

### 1. Header Flexbox & Badge Overflow Prevention:
- *Pitfall:* A long device friendly name (e.g. "Daikin Altherma 3 H HT (18 kW)") inside a standard flex header (`flex justify-between items-start gap-2`) pushes type and status badges (`heat_pump`, `ACTIEF`) off the card boundary or forces ugly vertical line wrapping.
- *Solution:* Constrain the title container with `min-w-0 flex-1 mr-2` and `truncate` with `title="${dev.name}"`. Wrap the badges container with `flex items-center gap-1.5 flex-shrink-0`. The title cleanly truncates with ellipses (`...`) while the badges stay horizontally locked within card margins.

### 2. Clean Typography & Zero Favicon Clutter:
- Resist decorating card sections with emojis or favicons (e.g. 📥, 📤, 🏠, ⚡).
- Keep device cards clean, calm, and typography-driven with sleek monospace text for technical identifiers (`HA: sensor.xxx`, `MQTT: topic/xxx`) and clear role badges (`PRODUCENT`, `VERBRUIKER`, `STATUS`).

### 3. Header & Subtitle Hygiene:
- Omit redundant section subtitles like "Logging: Producer / Consumer" or "Automatiseringslaag" beneath section headers. Use clean, direct titles: `Databronnen (N)` and `Aansturing & Regie (M)`.
- Omit the technical device ID (e.g. `rooftop_solar` or `daikin_heat_pump`) underneath the title; display strictly the user-facing device friendly name.

### 4. Resilient ID-Based Memory Mapping for Modal Editing:
- *Pitfall (Inline JSON serialization):* Serializing rich device objects with nested sensors and actuators directly into inline HTML attributes (`onclick='openDeviceModal(${JSON.stringify(dev)})'`) breaks when property strings contain quotes, apostrophes, or nested brackets, rendering the "Bewerken" button completely unresponsive.
- *Pitfall (Unguarded DOM lookups):* In `openDeviceModal()`, attempting to set `.value` on optional parameter inputs (`modal-dev-min-runtime`, `modal-dev-max-power`) that are not present in the DOM throws an unhandled `TypeError: Cannot set properties of null (setting 'value')`, aborting modal display.
- *Solution:* Store devices in an in-memory dictionary map (`window.__cachedDevicesMap[dev.id] = dev`) and pass strictly the clean string ID to the handler: `<button onclick="openDeviceModal('${dev.id}')">Bewerken</button>`. In `openDeviceModal()`, look up the device from cache and guard all optional form elements defensively (`const el = document.getElementById(...); if (el) el.value = ...`).










