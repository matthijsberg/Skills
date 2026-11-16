# Monolithic Add-on Daemon Refactoring & Modular Router Architecture

When building complex Home Assistant Add-ons (such as HEMS frameworks, data collectors, or automation platforms), daemons often start as a single Python script (`daemon.py`) that embeds HTML/JavaScript strings and handles dozens of REST endpoints. Over iterations, this monolith easily balloons to 10,000–15,000+ lines, creating extreme context fatigue, high git-merge conflicts, and making frontend linting/syntax highlighting impossible.

---

## The 3-Phase Decoupling Pattern

To decompose an oversized add-on daemon safely without risking operational downtime or regression:

```
                  ┌─────────────────────────────────────────┐
                  │          MONOLITHIC DAEMON              │
                  │             (14,500+ LOC)               │
                  │  • Embedded HTML/JS strings (9,200 LOC) │
                  │  • Chained if path == ... (3,100 LOC)   │
                  │  • Background threads & state (2,200)   │
                  └────────────────────┬────────────────────┘
                                       │
     ┌─────────────────────────────────┼─────────────────────────────────┐
     ▼ (Phase 1)                       ▼ (Phase 2)                       ▼ (Phase 3)
┌────────────────────────┐   ┌───────────────────────────┐   ┌────────────────────────┐
│   STATIC SPA ASSETS    │   │    MODULAR DOMAIN ROUTERS │   │   LEAN DAEMON SERVICE  │
│   (/web/index.html)    │   │    (/api/routes_*.py)     │   │      (< 300 LOC)       │
│ • Pure HTML/JS/CSS     │   │ • routes_analytics.py     │   │ • Service bootstrap    │
│ • Full IDE linting     │   │ • routes_model.py         │   │ • Thread supervisor    │
│ • Zero Python string   │   │ • routes_schedule.py      │   │ • Port socket binding  │
│   escaping issues      │   │ • routes_system.py        │   │ • Clean router dispatch│
│ • Fast disk reads      │   │ • context.py (shared SOT) │   └────────────────────────┘
└────────────────────────┘   └───────────────────────────┘
```

---

## Phase 1: Frontend Decoupling to `web/` (Instant 60–65% Reduction)

### The Problem
Embedding client-side Single Page Applications (SPAs) inside Python multi-line triple-quoted strings (`html = """<!DOCTYPE html>..."""`):
1. Defeats client-side linters (`eslint`, `prettier`), TypeScript checkers, and syntax highlighters.
2. Inadvertently breaks whenever Python string formatters or text replace operations touch accidental braces or quotes.
3. Consumes ~65% of the daemon's total line count with static presentation code.

### The Migration Recipe
1. Extract the raw HTML, Tailwind CSS, and client-side JavaScript into `/web/index.html`.
2. Ensure the add-on's `Dockerfile` copies the `web/` directory into the container build context:
   ```dockerfile
   COPY . /opt/open-hems/
   ```
3. In the Python daemon, replace the 9,000-line string literal with a clean 15-line file streamer:
   ```python
   WEB_DIR = Path(__file__).parent / "web"
   INDEX_HTML_PATH = WEB_DIR / "index.html"

   def _serve_spa(self):
       try:
           if INDEX_HTML_PATH.exists():
               with open(INDEX_HTML_PATH, "rb") as f:
                   content = f.read()
               self.send_response(200)
               self.send_header("Content-Type", "text/html; charset=utf-8")
               self.send_header("Content-Length", str(len(content)))
               self.send_header("Cache-Control", "no-cache")
               self.end_headers()
               self.wfile.write(content)
           else:
               self._send_json({"error": "web/index.html not found"}, 404)
       except Exception as e:
           self._send_json({"error": str(e)}, 500)
   ```
4. Support static file delivery with proper MIME types for future JS/CSS/image asset splits:
   ```python
   def _serve_static_file(self, file_path: Path):
       import mimetypes
       ctype, _ = mimetypes.guess_type(str(file_path))
       with open(file_path, "rb") as f:
           content = f.read()
       self.send_response(200)
       self.send_header("Content-Type", ctype or "application/octet-stream")
       self.send_header("Content-Length", str(len(content)))
       self.send_header("Cache-Control", "public, max-age=3600")
       self.end_headers()
       self.wfile.write(content)
   ```
5. **Version Synchronization:** Ensure automated release scripts (`version_manager.py`) update the version strings in both `config.yaml`, `daemon.py`, and `web/index.html`.

---

## Phase 2: Modular Domain Routers & Shared Context

### The Problem
`BaseHTTPRequestHandler` methods (`do_GET`, `do_POST`, `do_PUT`, `do_DELETE`) that contain 3,000+ lines of linear `if path == ...:` conditionals become impossible to maintain, debug, or unit test in isolation.

### The Solution: 4 Domain Routers + 1 Shared Context
Group endpoints strictly by their architectural domain into separate router modules under `api/`:

1. **`api/context.py` (The Single Source of Truth & Shared Helpers):**
   - Holds shared configuration paths (`CONFIG_FILE`, `PARAMS_FILE`, `SECRETS_FILE`).
   - Common utilities (`load_json`, `save_json`, `load_secrets`, `get_ha_states_map`, `calculate_poa_solar_kw`, `format_slot_label`).
   - Central canonical plan generation (`ensure_active_canonical_plan()`).
   - Prevents circular imports: all router modules import from `api.context`, never from each other.
2. **`api/routes_analytics.py`:**
   - Power producers, actual vs predicted telemetry, EPEX electricity prices, historical DHW runs, and OTel-aligned decision audit logs.
3. **`api/routes_model.py`:**
   - 2R1C space heating thermal forecasts, DHW 350L tank trajectories, model parameter recommendations (GET/POST accept/reject), and self-learning model retraining.
4. **`api/routes_schedule.py`:**
   - 24h rolling dispatch schedule chart data, active control states, policy CRUD, and force-recalculation triggers.
5. **`api/routes_system.py`:**
   - Single Source of Truth consistency verification, daemon status, external providers, device and tariff CRUD, and infrastructure connectivity probes (HA/MQTT/InfluxDB).

### Router Handler Signature Pattern
Each router exposes domain-dispatched handlers returning a boolean indicating whether the request was handled:

```python
# In api/routes_analytics.py
def handle_get(handler, path: str, qp: dict) -> bool:
    if path == "/api/analytics":
        handler._send_json({"status": "online", ...})
        return True
    if path.startswith("/api/analytics/electricity_prices"):
        # ...
        return True
    return False
```

### Critical Pitfalls in Router Decoupling

1. **The Bare Return / Double HTTP Response Fallthrough Pitfall:**
   - *Symptom:* Clients or MCP tools report JSON parsing failures such as `Extra data: line 29 column 2 (char 746)`. Examining raw socket curl output reveals two concatenated HTTP responses (`HTTP/1.0 200 OK Content-Type: application/json` immediately followed by `HTTP/1.0 200 OK Content-Type: text/html`).
   - *Cause:* In the original monolithic `do_GET`, a bare `return` exited the handler cleanly. When extracted into a router function returning a boolean (`if routes_*.handle_get(...): return`), a bare `return` returns `None`. In Python, `None` is falsy, causing the dispatcher in `daemon.py` to evaluate the branch as unhandled and fall through to `self._serve_spa()`.
   - *Rule:* Every matched route branch inside a router function MUST explicitly `return True`. Ensure both the `try` path and the error `except` block return `True` so even failed API calls do not fall through to the SPA fallback.

2. **Automated AST Undefined-Name Pre-Flight for Decoupled Modules:**
   - *Symptom:* Container starts and serves basic routes, but specific endpoints (e.g. `/api/schedule/chart-data`) abruptly drop connections with `NameError: name 'get_epex_tariffs_cached' is not defined`.
   - *Cause:* Standard bytecode compilation (`python3 -m py_compile`) only validates syntax; it does not check whether names referenced inside function bodies are imported or defined.
   - *Rule:* Before committing and rebuilding add-on containers after a modular refactor, run an AST undefined-name check across all new router modules:
     ```python
     import ast, builtins, pathlib
     builtins_set = set(dir(builtins))
     for p in pathlib.Path("api").glob("routes_*.py"):
         tree = ast.parse(p.read_text())
         imported = {n.asname or n.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for n in node.names}
         defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
         used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
         unresolved = used - defined - imported - builtins_set - {"__file__", "__name__"}
         if unresolved:
             raise SystemExit(f"Undefined names in {p.name}: {unresolved}")
     ```

3. **Subpackage Relative File Path Depth (`__file__`):**
   - *Symptom:* Endpoints serving local schema files (e.g. `/api/openapi.json`) return 404 or `FileNotFoundError` after refactoring into `api/routes_system.py`.
   - *Cause:* In the root daemon, `os.path.join(os.path.dirname(__file__), "docs", "openapi.json")` pointed to `/opt/open-hems/docs/openapi.json`. Inside `api/`, `__file__` is one level deeper, resolving to `/opt/open-hems/api/docs/openapi.json`.
   - *Rule:* Always traverse up two levels `os.path.dirname(os.path.dirname(__file__))` or reference a single project root constant (`PROJECT_ROOT = Path(__file__).resolve().parents[1]`) defined in `api/context.py`.

4. **Dynamic Root `sys.path` Anchoring vs. Legacy Sibling Path Pollution:**
   - *Symptom:* `TypeError: TelemetrySanitizer.sanitize() got an unexpected keyword argument` or modules mysteriously reverting to older signatures despite editing files in the add-on directory.
   - *Cause:* Residual lines like `sys.path.insert(0, "/config/projects/<old_name>")` place an external or legacy staging folder ahead of the active add-on package, causing the Python interpreter to import stale package versions.
   - *Rule:* Always dynamically anchor package roots relative to the running module file:
     ```python
     ROOT_DIR = str(Path(__file__).resolve().parents[1])
     if ROOT_DIR not in sys.path:
         sys.path.insert(0, ROOT_DIR)
     ```
     Never hardcode absolute paths to external development checkouts inside containerized add-on code.

### Delegation in `daemon.py`
The monolithic `do_GET` collapses into clean delegation:

```python
def do_GET(self):
    parsed = urllib.parse.urlparse(self.path)
    path = parsed.path.rstrip("/") or "/"
    query_params = urllib.parse.parse_qs(parsed.query)

    # 1. Dispatch to modular domain routers
    if routes_analytics.handle_get(self, path, query_params):
        return
    if routes_model.handle_get(self, path, query_params):
        return
    if routes_schedule.handle_get(self, path, query_params):
        return
    if routes_system.handle_get(self, path, query_params):
        return

    # 2. Static files
    if path.startswith("/static/") or path.startswith("/web/"):
        # ...
        return

    # 3. SPA Fallback
    self._serve_spa()
```

### AST Guardrail Updating
When architectural purity tests (such as `test_ast_handler_purity.py`) verify Dumb View invariants (e.g. asserting that `/api/model/decomposition` or `/api/health/consistency` consume `ensure_active_canonical_plan` without making direct HTTP/HA calls), update the test source collector to inspect the combined backend source across `daemon.py` and all `api/routes_*.py` files.
