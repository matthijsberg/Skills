# Ingress Daemons, Frontend Charts, Release Engineering & MCP Patterns

Extended reference for Home Assistant Add-on daemons, Ingress SPAs, Chart.js/InfluxDB telemetry, 4-tier SemVer, and MCP integration.

---

## 1. Container Networking, Timezones & Python HTTP Daemons

- **HAOS Add-on `/config` Mount Path Discrepancy:** In HAOS, `map: ["config:rw"]` mounts the host's `/homeassistant/` directory inside that add-on at `/config`. An agent container has its own `/config` (mapped to `/addon_configs/<agent_addon_slug>/`). Sync shared HA Core files to `/homeassistant/` via host SSH (`ssh <HAOS_SSH_HOST>`).
- **Docker Bridge HA Core Access (`172.30.32.1:8123`):** Container DNS often fails to resolve external FQDNs (`https://<ha-domain>:8123`). Prioritize internal paths:
  1. `https://172.30.32.1:8123` (Docker bridge to HA Core)
  2. `https://homeassistant:8123`
  3. `http://supervisor/core` (requires `homeassistant_api: true` in `config.yaml` for `SUPERVISOR_TOKEN` injection)
  4. Configured external URL as last fallback.
- **Timezone Alignment:** Containers default to UTC. Pass `zoneinfo.ZoneInfo("<TZ>")` explicitly to `.astimezone()`, set `TZ` in `config.yaml` `environment:`, and export `TZ` in `run.sh`.
- **Unbuffered Python Logs (`python3 -u`):** Export `PYTHONUNBUFFERED=1` and launch daemons with `exec python3 -u` so logs appear immediately in `ha apps logs`.
- **Docker `HEALTHCHECK`:** Supervisor only checks PID 1. Expose a fast (`<5ms`) `/healthz` endpoint and declare `HEALTHCHECK` in `Dockerfile` so Supervisor detects deadlocks.
- **`ThreadingHTTPServer` & `Content-Length`:** Use `ThreadingHTTPServer` (`daemon_threads = True`, `allow_reuse_address = True`) with `threading.Lock()`. In `BaseHTTPRequestHandler`, always compute payload bytes first and emit `Content-Length: str(len(payload))` to avoid HTTP/1.1 keep-alive hangs.
- **Socket Stream Exhaustion (`self.rfile`):** Read the request body once in `do_POST` and pass the parsed `body` dict to sub-routers; never call `_read_json_body()` twice on the same request.
- **Decouple Heavy Work:** Return HTTP 200 immediately on config updates and run expensive recalculations on a background `daemon=True` thread.
- **CLI Option Reassignment:** When parsing `--config` via `argparse`, reassign `global CONFIG_FILE` before starting worker threads.
- **Multi-Tier Token Fallback:** Resolve `SUPERVISOR_TOKEN` -> `HASSIO_TOKEN` -> `HASS_TOKEN` -> `0600` secrets vault.

---

## 2. InfluxDB, Unit Normalization & Relay Actuation

- **No `fill(previous)` on Sparse DBs:** Use `fill(none)` and merge real points in Python to avoid flat artificial blocks.
- **Unit Normalization (`kW` vs `W`):** Inspect `unit_of_measurement` before writing; multiply `kW` by `1000.0` so all power telemetry stores canonical Watts.
- **Line Protocol Tag Safety:** Initialize optional tags (`mode_tag = ...` with empty default) and wrap flush loops in `try/except` with full tracebacks so a `NameError` never silently kills the collector loop.
- **Idempotent Physical Actuation & Anti-Chattering:**
  1. Compare `target != current` before calling `switch.turn_on`/`turn_off` (prevents 1,440 events/day on optimistic MQTT switches).
  2. Use primitive string states rather than Python `Enum` objects in equality checks.
  3. Enforce minimum compressor dwell times (15–20 min) and disable competing legacy HA automations.
  4. For multi-relay truth tables, delegate to an HA `input_select` and configure bi-directional sync automations with `for: "00:00:01"` and `mode: restart` to avoid 15–50 ms intermediate-state ping-pong loops.
- **Canonical HA Statistics vs. Raw Influx:** For total household load behind solar export, query `home-assistant_v2.db` (`statistics`): `Total = Grid Import + max(0, Solar - Grid Export)`, using 25th-percentile/median for night standby and trimmed means for daytime.
- **Summer Lockout on Predictive Heating:** Force space heating to `0.0 kW` when 24h mean outdoor temp `>= 15 °C`, max `>= 18 °C`, or outside active heating season.
- **Cronjob Datastore & Output Hygiene:** Keep legacy cronjob databases separate from dedicated add-on DBs (`openhems`), and route non-fatal cron warnings to log files rather than `stdout` (which messaging gateways forward verbatim).

---

## 3. Ingress Frontend, Chart.js & Responsive UI

- **JS Hoisting & Shallow Cloning:** Run `node -c` in CI/pre-commit. Hoist `var chartInstance = null;` and never deep-clone Chart.js configs with `JSON.parse(JSON.stringify(...))` (it strips callback functions); use factory functions or `Object.assign`.
- **Unified Dual-Polarity Energy Charts:**
  - Stack loads `> 0` and generation `< 0` in the **same** `stack: 'energy'` identifier so positive/negative bars align in one vertical column.
  - Overlay net grid power as a continuous red line (`#EF4444`).
  - Synchronize dual Y-axes (`zeroRatio = |minY| / (maxY - minY)`) so `0 kW` and `0 €/kWh` share the same grid line.
  - Scale integrals by `intervalH` (`1.0` for 1h, `0.25` for 15m) from API `interval_h`; reverse-derive power in tooltips as `Math.round(absVal * 1000 / intervalH)`.
  - Suppress mirror rows (e.g. showing both `+829 W` self-consumed and `-829 W` solar used) in tooltips.
  - Start rolling 24h forecasts from the current slot (`Nu`), not static `00:00`.
  - Keep physical reality (`installed: true` only) as default; gate hypothetical devices behind an explicit simulation toggle.
- **Tooltip Dismissal & Mobile UX:**
  - Bind `mouseleave`/`mouseout` on canvases and a document-level `pointerdown`/`touchstart` listener to clear stuck tooltips on mobile WebViews; filter `<= 0.02` noise rows.
  - Place legends below canvases in `flex-wrap gap-2.5` containers.
  - Constrain card titles with `min-w-0 flex-1 truncate` and badges with `flex-shrink-0`. Cache device objects in `window.__cachedDevicesMap` and pass only IDs in `onclick` handlers.
  - Use an off-canvas mobile drawer (`-translate-x-full md:relative md:translate-x-0`) with backdrop overlay and auto-close on navigation.
  - Verify `<div>`/`</div>` tag balance per tab section so premature closures do not break outer padding.

---

## 4. 4-Tier SemVer, Isolated Vault & Pre-Release Gates

- **4-Tier Semantic Versioning:** `MAJOR.MINOR.PATCH-dev.BUILD` (Tier 1 breaking, Tier 2 public GitHub release with `CHANGELOG.md`, Tier 3 stable local patch, Tier 4 internal dev iteration).
- **Isolated Secrets Vault:** Store credentials in a `chmod 0600` vault outside Git; return masked placeholders (`"••••••••"`) in GET APIs and pass only IDs to test endpoints.
- **Pre-Commit & Integrity Gates:**
  - Scan staged diffs for secrets (`ghp_`, `github_pat_`, `eyJhbGciOi`, private keys) and block `.env`/`options.json`/`*.pem`/`*.key`.
  - Construct synthetic test tokens dynamically in unit tests (`'ghp_' + '1' * 36`) so static scanners do not trip.
  - Always export `PYTHONPATH="${REPO_ROOT}"` when invoking `pytest` inside git hooks.
  - Run `ruff check .`, JS syntax checks (`node -c`), and post-flight live HTTP smoke tests (triggering automatic rollback on failure).
- **External Supervisor Flag:** Pass `--external-supervisor` (or env flag) to self-updating daemons so `run.sh` remains the sole process supervisor without polling conflicts.

---

## 5. Multi-Profile MCP Registration & OKF v0.2 Highlights

- **Active Profile MCP Path:** Register add-on MCP servers in the active profile's `config.yaml` (resolve via `get_hermes_home() / "config.yaml"`), not the root config.
- **Decoupled Credentials & Context Calibration:** Hold provider API keys inside the add-on's Supervisor options; pass only model selectors (`triage`/`deep`) and a runtime `context` string over MCP so scanners down-rank internal HAOS bridge calls (`http://supervisor/`, `172.30.32.1:8123`).
- **OKF v0.2 Hygiene:** Clamp exported concept filenames to 50–60 chars (`NAME_MAX` protection) and skip reserved `index.md` / `log.md` files during bundle import. See `references/sandboxed-security-addons-and-okf.md`.
