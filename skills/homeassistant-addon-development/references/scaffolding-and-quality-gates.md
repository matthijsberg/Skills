# Scaffolding and Quality Gates for Home Assistant Add-ons & HA Apps

A standardized template and verification pattern for developing robust, test-driven Home Assistant Add-ons and HA Apps.

---

## 1. Standard HA App Scaffolding Layout

Every production add-on in a monorepo (`<REPO_ROOT>/apps/<folder>/` or `/config/addons/<folder>/`) should maintain this directory layout:

```
<addon-slug>/
├── config.yaml          # Add-on manifest (schema, options, ports, ingress, arch)
├── build.yaml           # Base image declaration (pinned versions, target archs)
├── Dockerfile           # Layered container build
├── translations/
│   └── en.yaml          # English UI labels and descriptions for all schema options
├── rootfs/
│   ├── run.sh           # Container entrypoint parsing /data/options.json
│   └── usr/src/app/     # Application source code
├── knowledge/           # Open Knowledge Format (OKF v0.2) bundle
│   ├── index.md         # Root manifest declaring okf_version: "0.2"
│   ├── architecture/    # Architecture decision records & service contracts
│   └── operations/      # Operational procedures, storage persistence, and tuning
├── tests/               # Automated pytest suite
│   ├── conftest.py      # App path injection and mock environment flags
│   ├── test_addon_config.py # Manifest schema and translation coverage assertions
│   ├── test_api.py      # FastAPI TestClient endpoint integration tests
│   └── test_okf.py      # OKF v0.2 bundle conformance verification
├── scripts/
│   ├── setup.sh         # One-click verification runner (all gates)
│   ├── test_config.py   # Standalone manifest and translation validator
│   ├── validate_okf.sh  # Standalone bash validator for OKF v0.2
│   └── security_audit.sh # Pre-commit forbidden credential and token scanner
├── pyproject.toml       # Python packaging, ruff linting, and pytest config
├── README.md            # Human documentation, badges, and quickstart
├── DOCS.md              # Add-on store documentation tab
├── CHANGELOG.md         # SemVer release history
└── PRD.md               # Normative requirements specification
```

---

## 2. Manifest & Translation Coverage Gate

Supervisor requires exact schema-to-option parity. Create `scripts/test_config.py` to ensure:
- All required top-level keys exist (`name`, `slug`, `version`, `arch`, `startup`, `boot`, `options`, `schema`).
- Every key in `options` has a matching type definition in `schema`.
- Every key in `options` has an English entry in `translations/en.yaml` under `configuration.<key>.name` and `configuration.<key>.description`.
- Exposed ports are mapped to `null` by default in `config.yaml` to allow optional user-configured LAN host port mapping while preserving internal container network routing.

---

## 3. Mock Mode Adapter Pattern for Heavy Dependencies

Home Assistant Add-ons often embed heavy runtimes (e.g. PyTorch, Hugging Face transformers, ClickHouse, or external engines) with multi-gigabyte models or donor binaries.
- Running full unit and regression suites in dev environments, local shells, or CI should not require downloading gigabytes of weights or specialized GPU drivers.
- **Rule:** Implement a clean `mock_mode` adapter (via `MOCK_MODE=1` or `<ADDON>_MOCK_MODE=1`) that simulates engine responses deterministically.
- `conftest.py` sets `os.environ["<ADDON>_MOCK_MODE"] = "1"` by default so `pytest tests/` runs in sub-second time.

---

## 4. Open Knowledge Format (OKF v0.2) Bundle

Document architectural decisions, service contracts, and operational invariants in `knowledge/` following the OKF v0.2 specification:
- Root `knowledge/index.md` must start with YAML frontmatter containing `okf_version: "0.2"`.
- Every concept `.md` file must have frontmatter containing `id`, `title`, `type`, `status: active` (or `stable`), `trust`, `generated`, and `sources`.
- Internal markdown cross-links must point to existing concept files.

---

## 5. Security & Secret Audit Scanner

Include `scripts/security_audit.sh` that scans the add-on folder before git commits for forbidden secret patterns:
- GitHub PATs (`ghp_`, `github_pat_`)
- JWT tokens (`eyJhbGciOi`)
- Private keys (`-----BEGIN ... PRIVATE KEY`)
- Vendor API keys (Anthropic, OpenAI, Google AI Studio)
- Ensure `.env` is listed in `.gitignore`.
- **Exclude Binary & Venv Directories:** Always pass `-I` (ignore binary files) and `--exclude-dir=".venv" --exclude-dir=".pytest_cache" --exclude-dir=".ruff_cache"` to `grep -rE` in `security_audit.sh` — compiled wheels and Rust binaries inside `.venv` (such as `ruff`) contain byte sequences that false-match regexes and pollute audit output.

---

## 6. One-Click Setup Script (`scripts/setup.sh`)

Chain all quality gates in `scripts/setup.sh`:
1. Bootstrap local `.venv` via `uv venv "${REPO_ROOT}/.venv" && uv pip install --python "${REPO_ROOT}/.venv/bin/python3" pyyaml pytest ruff` if `.venv/bin/python3` is absent — bare `python3` in the container environment does not guarantee `pyyaml` or `pytest` are installed.
2. Manifest validation (`python3 scripts/test_config.py` — support both `config.yaml` and `config.yaml.disabled` so pre-staged apps can pass all CI/quality gates before store activation)
3. OKF bundle validation (`bash scripts/validate_okf.sh`)
4. Security audit (`bash scripts/security_audit.sh`)
5. Shell syntax check (`bash -n scripts/*.sh rootfs/*.sh`)
6. Code style & linting (`ruff check .`)
7. Pytest suite (`pytest tests/ -v`)
Ensure all scripts are executable (`chmod +x scripts/*.sh rootfs/*.sh`).

---

## 7. Staging and Live Deployment via the `/share/addons` Bridge

### Mandatory "Local-First Build & Verify Before Git Commit" Invariant
For ALL Home Assistant Apps, follow this strict development and release lifecycle:
1. **Local Staging & Direct Host Sync**: Synchronize modified files directly to the host root `/addons/<folder>/` via `rsync` over SSH (using your configured `~/.ssh/config` host alias, e.g. `haos`, or `-p <SSH_PORT> -i <SSH_KEY> root@172.30.32.1`; do NOT sync only to `/config/addons/`, which Supervisor ignores):
   ```bash
   rsync -avz --delete \
       --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' \
       <REPO_ROOT>/apps/<folder>/ <HAOS_SSH_HOST>:/addons/<folder>/
   ```
   *(Always prefer `rsync` over bare `scp -r` — Python virtualenvs create broken/platform-specific symlinks like `lib64 -> lib` that cause `scp -r` to fail mid-upload).*
2. **Local Upgrade / Rebuild (`ha apps update` vs `rebuild`)**:
   Trigger store reload and container upgrade/compilation directly on the HAOS host via SSH (note: `local_<slug>` uses the `slug:` in `config.yaml`, which may have underscores even if `<folder>` uses hyphens):
   ```bash
   ssh <HAOS_SSH_HOST> "ha store reload && (ha apps update local_<slug> || ha apps rebuild local_<slug>)"
   ```
   *Rule:* A `rebuild` NEVER performs a version upgrade. When `version` in `config.yaml` is bumped, `ha store reload` + `ha apps update local_<slug>` is mandatory; `rebuild` is only for re-compiling when the version string is unchanged.
3. **Live Host Verification**:
   - Verify container status: `ha apps info local_<slug> | grep -E '^(version|version_latest|update_available|state):'` (expect `state: started`, `update_available: false`, `version == version_latest`).
   - Inspect resource consumption: `ha apps stats local_<slug>` (ensure RAM and CPU stay strictly within configured limits).
   - Verify logs and endpoints: `ha apps logs local_<slug> | tail -n 30` and run a live functional smoke test against the running service.
4. **Git Commit & Push ONLY Upon Proven Stability**:
   NEVER commit or push changes to the GitHub repository until the container is running, live-tested, and verified on the Home Assistant OS host. Git commits represent verified, working artifacts, not speculative edits.

   * **The "Versions Differ, Use Update instead of Rebuild" Supervisor Trap:** When `version` in `config.yaml` is incremented, Supervisor registers the new version while the running container has the old version. Running `ha apps rebuild` is actively rejected with `Error: Local and store versions of app differ, use Update instead of Rebuild`. Always invoke `ha apps update` first; only fall back to `rebuild` when iterating without a version bump.
   * **The `/share/addons/<slug>/web` Frontend Precedence Trap:** Add-ons that mount `/share` and serve `/share/addons/<slug>/web` ahead of the container's bundled `/app/web` directory will continue serving stale HTML/JS if only `/addons/<slug>/` on the host is synced and rebuilt. Whenever `/share/addons/<slug>/web` exists on the host, either sync updated `web/` assets to `/share/addons/<slug>/web` as well or remove the override directory so the container's newly built frontend assets take effect immediately.
   * **Path Resolution Invariant (`/config` vs `/homeassistant`):** On Home Assistant OS, `/config` on the host is a symlink resolving to `/homeassistant` (`/config -> /homeassistant`). Scripts using `Path("/config/addons/...").resolve()` expand to `/homeassistant/addons/...` (which does not exist on the host). Derive repo paths dynamically via `Path(__file__).resolve().parents[...]` so test suites and integrity gates succeed identically inside dev containers and on the host.
   * **Fallback when SSH is Stopped:**
     If SSH to `<HAOS_SSH_HOST>` returns `Connection refused` (SSH add-on stopped), execute in the Home Assistant Web Terminal UI:
     ```bash
     cp -r /share/addons/<folder> /addons/ && ha store reload
     ```
     Then trigger the build via **Settings > Add-ons > Add-on Store > Local add-ons > <Add-on> > Install / Rebuild**.
   * **The "Live Container Hot-Patch Reversion" Trap & Version Tracking:**
     - *Pitfall:* Copying files directly into a running container via `docker cp` (e.g. `docker cp index.html <container>:/index.html`) is tempting for rapid in-situ probes, but restarting the app (`ha apps restart local_<slug>`) or rebooting the host instantiates a fresh container from the underlying Docker image, silently discarding all hot-patched files and reverting to the stale interface ("I restarted the container and now see the old interface again").
     - *Rule:* Never conclude a deployment or bugfix on a live `docker cp` injection. Bump `version` in `config.yaml` and `CHANGELOG.md`, sync to `/addons/<folder>/`, run `ha store reload && ha apps update local_<slug>`, and render the exact version badge in the WebUI header.
   * **Supervisor REST API Option Updating Pattern (via Host SSH):**
     The Home Assistant CLI (`ha apps`) intentionally lacks a standalone `options` subcommand, and add-on container tokens (`$SUPERVISOR_TOKEN` inside an agent add-on container) return `403 Forbidden` on Supervisor management endpoints. To read and update add-on options programmatically without asking the user to click in the UI:
     - Execute the Supervisor API call inside the host SSH session (`ssh <HAOS_SSH_HOST>`), where `$SUPERVISOR_TOKEN` has manager privileges.
     - **Slug Precision:** Use `local_<config_yaml_slug>` (from `config.yaml`'s `slug:` field, often with underscores), not necessarily the hyphenated folder name (`/addons/<folder>`).
     - **Full Options Dictionary Mandate:** Supervisor rejects partial option dictionaries with `Missing option '<key>' in root`. Always `GET http://supervisor/addons/local_<slug>/info` first, merge your changes into `data["options"]`, and `POST` the complete dictionary to `http://supervisor/addons/local_<slug>/options`.
     - **Secret-Safe Stdin Pattern:** When injecting API keys or tokens, pipe the secret over SSH `stdin` into a `shlex.quote`-wrapped `python3 -c` script (never embed secrets in CLI args or `json.dumps`-escaped strings that mangle newlines).
     - **Reload Restart:** Run `ha apps restart local_<slug>` after updating options when the add-on reads `/data/options.json` only at process startup.

---

## 8. App Store Branding: icon.png and logo.png

Home Assistant Supervisor automatically detects visual branding assets placed in the add-on root directory:
- **`icon.png` (512x512):** 1:1 square or squircle PNG displayed in the Add-on Store listing, installed app cards, and sidebar panel.
- **`logo.png` (1280x640):** 2:1 aspect ratio banner displayed as the header hero image on the Add-on details and installation page.
- **Supervisor Auto-Discovery:** On `ha store reload`, Supervisor inspects the directory and flips `icon: true` and `logo: true` in `ha apps info local_<slug>`.
- **Automated Verification:** Include assertions in `tests/test_addon_config.py` to prevent regressions where images are accidentally omitted from release packages:
  ```python
  def test_icon_and_logo_exist():
      icon_path = ADDON_ROOT / "icon.png"
      logo_path = ADDON_ROOT / "logo.png"
      assert icon_path.exists(), "icon.png must exist for HA App Store"
      assert logo_path.exists(), "logo.png must exist for HA App Store"
      assert icon_path.stat().st_size > 1000
      assert logo_path.stat().st_size > 1000
  ```

---

## 9. Multi-App Repository Architecture, Naming & Archiving (`apps/` vs `apps-archive/`)

When maintaining a Home Assistant App repository (such as `<owner>/<ha-apps-repo>`):

### Home Assistant "Apps" Rebranding & Slugs
- Home Assistant has officially rebranded Add-ons to **Apps** in both the UI and CLI (`ha apps`).
- All repository directory names and app slugs MUST be strict lowercase **kebab-case** (e.g. `open-hems`, `langfuse`, `hermes-agent`, `matrix-synapse`).
- Avoid redundant `-addon` suffixes in directory names or slugs (e.g. use `roon-spotify` instead of `roon-spotify-addon`).

### Supervisor Discovery Invariant & Archiving
- **Discovery Depth:** The Home Assistant Supervisor scans repository directories up to **2 levels deep** for `config.yaml` or `config.json`.
- **Repository Structure:**
  - Active apps: Located in `apps/<slug>/` (or top-level `<slug>/`).
  - Archived apps: Located in `apps-archive/<slug>/`.
- **Archiving Rule:** Simply moving an app into an `apps-archive/` or `archived/` directory still causes Supervisor to discover and list it in the App Store if its manifest file remains valid! To archive an app cleanly without store pollution, **disable or rename the manifest file** (e.g. rename `config.yaml` to `config.yaml.disabled` or `config.yaml.archived`).

### Repository Manifest: repository.yaml vs repository.json
Modern Home Assistant repositories prefer `repository.yaml` over legacy `repository.json`:
```yaml
name: "<Repository Name>"
url: "https://github.com/<owner>/<ha-apps-repo>"
maintainer: "<Maintainer Name> <<email>>"
```

### Git Subtree Monorepo Consolidation
When merging previously standalone add-on repositories into a single monorepo repository while preserving full commit history and `git blame` provenance:
```bash
git remote add <remote-name> <remote-url>
git fetch <remote-name>
git subtree add --prefix=apps/<slug> <remote-name>/main -m "feat: subtree import <slug>"
git remote remove <remote-name>
```

### GitHub Actions CI/CD Workflow Path Alignment
In monorepos (`apps/<slug>/`), ensure `.github/workflows/*.yml` reflect the subfolder structure:
- **Trigger filters:** Set `paths: ["apps/<slug>/**", ".github/workflows/addon-<slug>.yml"]`.
- **Working directory:** Run quality gates via `cd apps/<slug> && ./scripts/setup.sh`.
- **Builder action:** Pass `--target apps/<slug>` to `home-assistant/builder`.

### Safe Local Path Renaming & Symlink Aliasing
When renaming a project folder on the host (e.g. `old-addons-repo` -> `new-apps-repo`), create a symlink from the old path to the new path (`ln -s /path/to/new-apps-repo /path/to/old-addons-repo`) to ensure external tooling, cron scripts, and IDE bookmarks do not fail.

### Host SSH Authentication for Autonomous & Server-Side Git Operations
To allow the HA host or an agent to push releases directly to GitHub without failing on interactive HTTPS credential prompts:
1. Generate an ed25519 key pair on persistent storage (e.g. `/config/.ssh/id_ed25519`).
2. Add the public key (`.pub`) to GitHub Settings -> SSH Keys.
3. Configure `~/.ssh/config` (and symlink `/root/.ssh/config -> /config/.ssh/config` if OpenSSH reads `pw_dir` rather than `$HOME`) with `Host github.com` and `Host <HAOS_SSH_HOST>` (holding `HostName`, `Port`, `User`, `IdentityFile`) so site-specific ports and keys stay out of generic scripts and skills.

### Developer Environment Distinction (Host/Container vs. Local Workstation)
Never instruct the user to run commands referencing `/config/...` paths in their personal laptop/workstation terminal (e.g. macOS Terminal or Windows PowerShell):
- `/config/...` is the internal path within the Home Assistant server/container.
- When an SSH key is configured on the host, execute all Git staging, commits, and pushes directly from the agent or host container.
- If the user needs to clone the repository to their personal workstation, instruct them to clone the GitHub remote (`git clone git@github.com:...`) into their local workstation directory (e.g. `~/Projects/`) rather than navigating to host-internal paths.

### Repository Deprecation Pattern
When deprecating a legacy repository (e.g. Beta repositories consolidated into main):
1. Strip all legacy add-on directories and `repository.json`.
2. Replace `README.md` with an explicit deprecation banner directing users to the new consolidated repository URL.

---

## 10. Ingress WebUI & Ingress Authentication Bypass

When embedding an interactive WebUI into Home Assistant:
- **Manifest Configuration (`config.yaml`):**
  ```yaml
  ingress: true
  ingress_port: 8000
  ingress_panel: true
  panel_icon: "mdi:router-network"
  panel_title: "My Add-on"
  ```
- **Authentication Bypass via `X-Ingress-Path`:**
  Home Assistant Ingress proxies requests through Core's reverse proxy and automatically injects an `X-Ingress-Path` header (e.g. `/api/hassio_ingress/<token>/`).
  For add-on endpoints that otherwise mandate Bearer API token authentication, bypass token verification when `X-Ingress-Path` is present:
  ```python
  def verify_api_key(
      authorization: Optional[str] = Header(default=None),
      x_ingress_path: Optional[str] = Header(default=None),
  ) -> None:
      # Ingress requests are pre-authenticated by Home Assistant Core security perimeter
      if x_ingress_path:
          return
      if not config.api_key:
          return
      # Validate Bearer authorization...
  ```
- **Offline-First Asset Rule:**
  Ingress HTML/JS/CSS assets must be 100% self-contained and offline-first (no external CDNs such as Google Fonts, Cloudflare cdnjs, or unpkg). External fetches fail on air-gapped systems or isolated local LANs.

---

## 11. Extensible Schema Configuration (List vs Map Pattern)

When an add-on requires user-configurable profiles or dynamic rule sets (e.g. task families, routing tables, upstream targets):

- **Supervisor Schema Pattern:**
  Supervisor strict validation rejects arbitrary dictionary keys. Use a list of sub-schemas in `config.yaml`:
  ```yaml
  options:
    families:
      - name: "quick"
        criteria: "small talk, greetings, facts"
        model: "gemini-3.5-flash-lite"
        effort: "low"
        max_tokens: 1024
        temperature: 0.2
        thinking_budget: 0
  schema:
    families:
      - name: "str"
        criteria: "str"
        model: "str"
        effort: "list(low|medium|high)?"
        max_tokens: "int?"
        temperature: "float?"
        thinking_budget: "int?"
  ```
  In Home Assistant's UI, this renders an "+ ADD ITEM" button allowing users to define arbitrary named profiles while keeping schema validation strict.

- **Dual Parser Support (List & Dict):**
  Users often switch to the "Edit in YAML" tab and write a map rather than a list. The application configuration loader should parse both formats transparently:
  ```python
  if isinstance(raw_data, list):
      for item in raw_data:
          name = str(item["name"]).strip().lower()
          loaded[name] = ProfileConfig(...)
  elif isinstance(raw_data, dict):
      for name, item in raw_data.items():
          loaded[name.strip().lower()] = ProfileConfig(...)
  ```

- **Omission Semantics for Upstream Defaults:**
  Optional parameters (e.g. `temperature`, `thinking_budget`) should default to `None`. When serialized into upstream API calls, omit `None` fields so the model provider's natural defaults are respected without forcing artificial constraints.

---

## 12. Language & Documentation Invariant (Strict English)

Even when user interactions or design discussions occur in Dutch (or another local language):
- **Rule:** All Add-on/App source code, configuration manifests (`config.yaml`, `build.yaml`), translation files (`en.yaml`), documentation (`PRD.md`, `README.md`, `DOCS.md`, `CHANGELOG.md`), container logs, error messages, and Ingress WebUI user interface text MUST be written strictly in **English**.
- Never mix Dutch and English in code comments, manifests, or UI labels. Keep the entire codebase and artifact set professionally English.

---

## 13. Add-on Migration, Renaming & Slug Cleanup Workflow

When renaming, splitting, or migrating an add-on slug (e.g. `laya` / `local_laya` -> `ha_system_1` / `local_ha_system_1`):
1. **Clean up old app on host:**
   ```bash
   ha apps stop local_<old_slug> && ha apps uninstall local_<old_slug>
   ```
2. **Remove old directories:**
   Delete `/addons/<old_slug>` and `/share/addons/<old_slug>` from the host and dev filesystem to avoid ghost entries in the Supervisor store.
3. **Reload Supervisor Store:**
   ```bash
   ha store reload
   ```
4. **Install & start new app:**
   ```bash
   ha apps install local_<new_slug> && ha apps start local_<new_slug>
   ```
   Verify with `ha apps info local_<new_slug>` that `state: started` and ingress URL are active.

---

## 14. Intel Arc / GPU Level-Zero JIT Compilation & Persistent Disk Cache

- **Pitfall:** On Intel Arc iGPU (Level-Zero / PyTorch XPU), the very first forward pass during container warmup takes 25–45 seconds while Level-Zero compiles SPIR-V device code and GPU kernels into machine binaries.
- **The Ephemeral Cache Trap:** By default, Intel Compute Runtime (NEO) compiles in RAM or `/tmp`. On every container restart or rebuild, the shader cache is wiped, forcing the user to endure the 25–45s delay again on their first turn.
- **Rule:** Export persistent cache environment variables in `run.sh` mapped to `/data` (e.g. `export NEO_CACHE_PERSISTENT=1`, `export NEO_CACHE_DIR="/data/neo_cache"`). Once compiled, binary `.l0_cache` files are read directly from persistent disk in <1ms across container reboots.
- **Concurrency Deadlock:** The Intel Level-Zero driver does not support simultaneous, parallel forward passes on the same model context across multiple OS threads (e.g. `Promise.all` in the WebUI). Wrap all model inference calls in a mutex lock (`threading.Lock()`) and sequence WebUI requests sequentially.

---

## 15. In-Memory Registry Caching, Exact Overrides & Area Precedence

When building smart home fast-path or decision engines interfacing with Home Assistant:

- **Z-Wave / Ghost Device Filtering during State Sync:**
  When synchronizing from Home Assistant Core `/states`, filter out non-actionable devices:
  1. Entities with `entity_category in ("config", "diagnostic")` (e.g. Access Point status LEDs).
  2. Redundant Z-Wave Basic Command Class endpoints (`*_basic`, `*_basic_\d+`).
  3. Orphaned restored entities (`attrs.get("restored") is True` with state `unavailable` or `unknown`).
  4. Network device status LEDs (`light.ap_*`, `*_status_led`, `*_indicator`).
- **Area Precedence for Room Lighting:**
  When a user commands a room (e.g. "turn off lights in the conservatory"), prioritize the Area Registry over individual entities that happen to contain the room name in their slug (e.g. `light.serre_gordijnen_licht`). Generate native `{"area": "<room>", "domain": "light"}` tool calls.
- **Specific Subtype Preservation:**
  Keep device qualifiers (`spots`, `ledstrip`, `hanglamp`) in target tokens so specific device commands target the exact entity rather than the whole area.
- **MDI Icon Semantic Mapping:**
  Extract device type hints from Home Assistant icons (`mdi:led-strip*` -> `led_strip`, `mdi:spotlight*` -> `spots`, `mdi:curtains*` -> `cover`) to automatically associate friendly names with device categories.
- **Exact String Overrides Layer:**
  Store in `/addon_configs/<slug>/corrections.yaml` (persistent across updates, included in backups). Match normalized lowercase text only (no regex). Check overrides before neural network inference to return in <0.5ms with 100% confidence.
- **Configurable Confidence Thresholds:**
  Expose `min_confidence` (default 0.60) for model fallback and `domotica_min_confidence` (default 0.70) in `config.yaml` schema so users can tune the fail-open threshold directly in the HA UI.

---

## 16. Ingress Iframe Caching & Sidebar Panel Sync Pitfalls

When updating Add-on Ingress WebUIs:

- **Aggressive Browser Iframe Caching:**
  Home Assistant renders Ingress within an `<iframe>` (`/api/hassio_ingress/<token>/`). Browsers (notably Firefox and Chrome) cache iframe HTML responses in memory. Hard-refreshing the parent Home Assistant page (`Cmd+R` / `F5`) only refreshes Lovelace, leaving the embedded Ingress iframe running stale code.
  - **Mandatory Headers on Ingress Root (`/`):**
    ```python
    response = HTMLResponse(content=html)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    ```
  - **Head Meta Tags:** Include matching `<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">` in the HTML template.
- **Supervisor `ingress_panel: true` Desync:**
  During local development or add-on updates, `ingress_panel` in `ha apps info <slug>` can remain `false` even if declared in `config.yaml`.
  If missing from the sidebar, enable via Supervisor API:
  ```bash
  curl -s -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" -H "Content-Type: application/json" \
      -d '{"ingress_panel": true}' http://supervisor/addons/<slug>/options
  ```
- **Rebuild Supervisor Sidebar Flapping (Perceived HA Reboots):**
  Running `ha apps rebuild` repeatedly on an app with `ingress_panel: true` triggers container stop/start and image compilation. Supervisor broadcasts WebSocket panel update events to all open Home Assistant sessions, causing browser tabs to disconnect ("No PONG received after 27.5s") and reload panels, giving the false illusion that Home Assistant Core itself is rebooting. Minimize rapid sequential rebuilds and inform the user if rebuilds are in progress.

---

## 17. Registry Mirror Staleness Auto-Recovery

When maintaining an in-memory entity mirror (e.g. for sub-50ms deterministic fast-paths):
- **Pitfall:** If staleness checks (`(time.time() - last_sync) > max_staleness`) merely flag `is_stale = True` without triggering a sync, the add-on permanently locks out the fast-path after the TTL expires (e.g. 60 minutes), escalating all turns to cloud LLMs with `rejected_reason: "mirror_stale"`.
- **Rule:** Staleness checks must trigger an active background `self.sync(force=True)`. Only reject if the Home Assistant Core API is genuinely unreachable.

---

## 18. Pluggable Multilingual Language Pack Architecture

To make smart home fast-paths and neural routers language-extensible without modifying application code:
- **YAML Language Packs:** Store language specifications in `languages/<lang>.yaml` (and support user additions in `/addon_configs/<slug>/languages/<lang>.yaml`).
- **Pack Schema:**
  - `domain_keywords`: Device domain nouns and triggers.
  - `action_keywords`: Action verbs mapped to Home Assistant services (`turn_on`, `turn_off`, `set_temperature`, `open_cover`).
  - `question_words` & `condition_patterns`: Imperative safety gating regexes.
  - `speech_templates`: Natural localized confirmation feedback.
  - `laya_criteria`: Language-specific semantic anchors merged into the LLM criteria prompt.
- **Dynamic Aggregation:** On boot, the `LanguageRegistry` aggregates keywords across all active YAML files, allowing mixed-language commands without manual switching.

---

## 19. System 1 vs System 2 Smarthome & Routing Architecture

When designing a two-tier cognitive architecture (System 1 fast edge reflex + System 2 deep upstream reasoning) for Home Assistant:

### The Single Action Generator Invariant
- The **Smarthome Action Generator** (e.g. Python `HAResolver`) is the **sole authoritative executor** interfacing with the Home Assistant Core REST API.
- It receives structured execution payloads from three upstream suppliers:
  1. **Zero-LLM Fast-Path Gate:** Deterministic rule qualification for simple imperatives (<0.5ms).
  2. **Local System 1 Neural Model (XPU):** Semantic slot extraction (`room`, `device_type`, `scope`) on Intel Arc iGPU (~80ms).
  3. **Upstream Cloud LLM (System 2):** When complex, ambiguous, or multi-step requests escalate to the cloud, the LLM emits a native Home Assistant tool call (e.g. `HassTurnOff`) that feeds back into the local Smarthome Action Generator.
- **Directionality Rule:** The Smarthome Action Generator **never** outputs to the Upstream LLM; the Upstream LLM outputs tool calls **to** the generator.
- **Knowledge/Code Isolation:** General, code, and deep knowledge queries bypass the Smarthome Action Generator completely. Their execution terminates as raw LLM text/code answers, preventing non-domotica queries from accidentally touching smart home devices.

### Whole-Home Substring Collisions
- **Trap:** Matching whole-home English tokens using substring checks (e.g. `"all" in text.lower()`) collides with Dutch words such as `"alle"` (*"doe alle lampen in de woonkamer aan"*). This causes room-specific commands to be mistakenly converted into whole-home commands, turning off every light in the house!
- **Rule:** Enforce room dominance (`has_specific_room = bool(slots.get("room") and slots["room"] != "unspecified")`). Only trigger whole-home scope when no specific room is detected AND exact whitespace-tokenized words match (`any(w in text.split() for w in ("house", "huis", "home", "overal"))`).

---

## 20. Operator Approval Gates, Safe Diff Parsing & Workspace Sandboxing in HA Add-on APIs

When exposing agentic, MCP, or API endpoints from an Add-on that execute code, triage security vulnerabilities, or trigger external egress/costs:

### Ingress / Operator Approval Gates vs Agent Self-Approval (SEC-02)
- **The Self-Approval Trap:** If an add-on exposes `/api/approve/{job_id}` behind the same Bearer token used by calling agents (or unauthenticated on LAN), any caller or sub-agent that receives `job_id` can immediately call the approval endpoint to self-approve its own egress or action.
- **Rule:** Approval and rejection endpoints must strictly verify that the request originates from the Home Assistant Ingress proxy (`172.30.32.2` or request header `X-Ingress-Path`) or a local operator session. Reject any external caller IP with HTTP 403.
- **Expiration Discipline:** Pending approvals must carry an expiry TTL (e.g. 30 minutes). Once expired, transition the job to `cancelled` (with `approval_expired`) and HTTP 410.

### Ephemeral Workspace Lifecycle & Garbage Collection (LOGIC-03)
- **The Orphaned Upload Workspace Leak:** If an agent uploads code archives into ephemeral scratch folders (e.g. `/data/workspaces/upload_<id>`), cleaning up only inside the background task worker leaves orphaned directories on disk whenever a job is rejected, cancelled, or expires.
- **Rule:** Implement a centralized `cleanup_job_workspaces(job)` helper and invoke it across all terminal states: completion, failure, rejection, cancellation, and expiration.

### Unified Diff Line Parsing for Security Scanners (LOGIC-04)
- **The Indented Diff Trap:** When checking added lines in git diffs or patch payloads for security violations, `line.startswith("+")` silently misses added lines if the diff is wrapped in indented multiline strings, markdown code blocks, or JSON payloads (e.g. `        +import subprocess`).
- **Rule:** Always strip leading indentation before testing for diff addition markers:
  ```python
  added_lines = [
      l.strip()[1:] for l in clean_diff.splitlines()
      if l.strip().startswith("+") and not l.strip().startswith("+++")
  ]
  added_diff = "\n".join(added_lines)
  ```

### Archive Extraction & YAML Billion-Laughs Hardening (SEC-01, SEC-06, SEC-08)
- **Reject `.git` in Archives:** Unpacking untrusted tar/zip archives must reject entries containing `.git` directories. If `.git/config` is written, subsequent Git CLI calls can trigger arbitrary command execution via `core.fsmonitor` or hooks.
- **Block Symlinks and Hardlinks:** Reject symlinks (`tarinfo.issym()`) and hardlinks (`tarinfo.islnk()`) during archive extraction to prevent container directory traversal escapes.
- **Prevent YAML Entity Expansion:** When parsing untrusted YAML frontmatter, standard `yaml.safe_load` still expands YAML anchors and aliases. Use a custom `yaml.SafeLoader` subclass overriding `compose_node` to reject any `AliasEvent` immediately.

---

## 21. Systemd-Based Vendor Appliances & Cgroup v2 Constraints in HAOS

When packaging upstream appliances distributed as multi-service `systemd` OCI images or Podman installers (such as Ubiquiti UniFi OS Server):
- **Build-Time OCI Extraction & Self-Extracting ELF ZIP Structure:**
  - Upstream vendor installers distributed as standalone Linux executables frequently bundle their payloads as self-extracting ZIP archives appended to an ELF binary (`PK\x03\x04` magic header).
  - Use `unzip -p installer.bin image.tar` directly in a multi-stage `Dockerfile` (`AS extractor`) rather than requiring heavy tools like `binwalk` or attempting to execute the installer at build time.
  - An OCI `image.tar` contains `manifest.json` with sequential layer tarballs. Extract layers into `/rootfs` in manifest order, actively deleting target files matching `.wh.<name>` whiteout markers to prevent deleted files or stale configs from polluting the final image.
- **HAOS Cgroup v2 Read-Only Pitfall:** Home Assistant Supervisor runs on cgroup v2 with `--cgroupns=private` and mounts `/sys/fs/cgroup` read-only (`ro`), and does not expose a `cgroup_namespace: host` manifest option. Launching `/sbin/init` (`systemd`) as PID 1 fails unless `/sys/fs/cgroup` is writable or `systemd` is replaced. Prefer a drop-in unit runner (`docker-systemctl-replacement` / `systemctl3.py`) or `s6-overlay` wrapper to parse and supervise upstream `.service` unit files without requiring `privileged: true` or `SYS_ADMIN`.
- **Single-Volume `/data` Persistence & Pre-Seeding:** Because HAOS only persists `/data` across container updates, symlink or bind-mount all vendor state directories (`/var/lib/...`, `/etc/...`) into subdirectories under `/data` in `run.sh`, and idempotently pre-seed local PostgreSQL roles and databases before launching upstream services whose `pre-start.sh` scripts fail on parallel first boot.
- **Dynamic Cgroup v2 Memory Auto-Tuning:** Analytical or multi-service engines (Java JVM, PostgreSQL, RabbitMQ) crash if unconstrained or manually over-allocated. In `run.sh`, inspect `/sys/fs/cgroup/memory.max`. If set, automatically scale JVM heap limits (e.g. 45% of container limit) to keep total memory safely beneath host boundaries across different hardware tiers (e.g. 4 GB Raspberry Pi vs 64 GB x86 server).
- **Universal Database Migration via Application Dropzones:** Never attempt raw binary database filesystem conversions across major engine/version shifts (e.g. MongoDB MMAPv1/WiredTiger to PostgreSQL 16). Implement an automated dropzone scan in `run.sh` searching `/backup/` and `/share/` for native backup archives (`.unf`), staging them to the vendor's auto-backup directory on first boot to leverage upstream native schema migration engines.
- **External Host Backup Mapping Invariant (`backup:rw` & `/backup/<app>/` Symlink):** Never let an appliance write automatic or manual backups solely to internal container directories (`/var/lib/.../backup/`). Backups stored under the container's private `/data` volume are lost if the add-on is uninstalled or corrupted. In `config.yaml`, declare `map: [backup:rw]`, and in `run.sh`, symlink the internal backup directory directly to `/backup/<app>/` on the host filesystem. This ensures all automated and manual snapshots survive add-on reinstalls and are immediately accessible to central HA backup tools.
- **Central SSL Certificate Auto-Discovery & Mapping Invariant (`ssl:rw` & `/ssl`):** Avoid forcing users to accept self-signed certificates or manually import certificates into proprietary keystores. In `config.yaml`, declare `map: [ssl:rw]`, and provide optional `ssl_cert: "str?"` and `ssl_key: "str?"` schema options with matching English translations. In `run.sh`, implement auto-discovery: if explicit options are provided, use them; if empty, automatically check for central `/ssl/fullchain.pem` and `/ssl/privkey.pem` (from Let's Encrypt or Nginx Proxy Manager) and deploy them to the appliance's reverse proxy or keystore for zero-config trusted HTTPS.
- **Public Community App Generalization Invariant:** When preparing an App for public release, strictly isolate personal site references (specific gateway models, switch counts, private LAN subnets) from `PRD.md` into an optional private reference doc. The public PRD and manifest must define a generic multi-arch matrix (`amd64` and `aarch64`) with user-configurable port options.
- **Multi-Model Triad Architecture Review Gate & 3-Round Cost Cap:**
  - For complex appliance wrappers or greenfield HA Apps, run architectural review across 3 distinct personas: Lead Architect (Gemini Argon 4: HAOS/Supervisor invariants, Mantis security gates, final binding decisions), Deep Systems (OpenAI high-reasoning model: OCI flattening, cgroup v2, kernel capabilities), and Packaging/Lifecycle (OpenAI capable model: storage persistence, service supervision, migration scripts).
  - **Strict 3-Round Token Cap:** Enforce a hard ceiling of maximum 3 interaction rounds per topic:
    - *Round 1 (Stance & Proposal):* Deep Systems and Packaging architects present concrete technical proposals.
    - *Round 2 (Critical Sparring):* Architects critique each other's proposals, uncovering edge cases (ABI collisions, memory leaks, migration failures).
    - *Round 3 (Binding Synthesis):* Lead Architect synthesizes the trade-offs into an unambiguous, binding architectural decision.
  - This strict discipline prevents open-ended multi-agent token exhaustion while generating razor-sharp technical blueprints.
- **Pre-Flight Scaffolding Gating for Low-Cost (Flash) Model Execution:**
  - When delegating implementation or maintenance to low-cost Flash models (`gemini-flash-latest`), never leave architectural placeholders (e.g. `<installer-url>`, `<sha256>`).
  - Pre-author concrete boilerplate blueprints for the multi-stage `Dockerfile` (extractor + whiteout logic) and `rootfs/run.sh` (cgroup parsing, pre-seeding, supervisor handoff), backed by an automated test suite (`tests/test_dockerfile.py`, `./scripts/setup.sh`). Flash models excel at mechanical file authoring and test-driven convergence, but hallucinate or attempt unsupported nested container flags if required to invent OCI extraction or systemd workarounds from scratch.

---

## 22. Local LLM & Ollama Vulkan Add-on Invariants (Intel Arc & Unified RAM)

When packaging Ollama or local LLM inference engines on Home Assistant OS with Vulkan hardware acceleration (Intel Arc discrete/integrated GPUs):

### Mandatory Driver Stack & Precision Overrides
- **Mesa 26 ANV PPA:** Ubuntu base images must include `ppa:ernstp/mesarc` (Mesa 26.0+). Mesa 26 provides `VK_KHR_pipeline_binary` and fixes Xe-LPG / Xe2 pipeline stutters on Arrow Lake and Lunar Lake.
- **Integer Dot Product Workaround:** Export `GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1` unconditionally. Mesa ANV integer dot product operations corrupt quantized tensor math, producing garbled/repeating output (llama.cpp #17056).
- **Cooperative Matrix TDR Prevention:** Export `GGML_VK_DISABLE_COOPMAT=1` and `GGML_VK_DISABLE_COOPMAT2=1` to prevent GPU Timeout Detection and Recovery (TDR) resets and kernel panics.

### Eliminating the `llvmpipe` CPU Trap via Driver ICD Isolation
- **The llvmpipe Trap:** By default, Mesa exposes both the hardware GPU (`GPU0: Intel(R) Graphics`) and the CPU software rasterizer (`GPU1: llvmpipe (LLVM)`). If device enumeration is unrestricted, Ollama multi-device scheduling (`OLLAMA_SCHED_SPREAD=1`) can split layers onto CPU-emulated Vulkan, plummeting token throughput.
- **Rule:** Clamp `VK_DRIVER_FILES` and `VK_ICD_FILENAMES` strictly to the vendor ICD (`/usr/share/vulkan/icd.d/intel_icd.x86_64.json` or `radeon_icd.x86_64.json`), and set `GGML_VK_VISIBLE_DEVICES="0"` and `OLLAMA_IGPU_ENABLE=1`. This completely hides `llvmpipe` from Vulkan device discovery and guarantees 100% execution on hardware iGPU.

### Unified Memory Optimization & Persistent Shader Caching
- **Direct Unified Host Memory (`GGML_VK_PREFER_HOST_MEMORY=1`):** Integrated GPUs use shared system RAM. The Vulkan driver defaults to querying a small device-local VRAM heap (clamped to 2–4 GB), triggering premature layer eviction or false OOM errors. Setting `GGML_VK_PREFER_HOST_MEMORY=1` unlocks full system RAM (e.g. 48 GB) directly, bypassing redundant memory copies and delivering an empirical 10%–15% throughput boost.
- **Persistent NVMe Shader Caching:** Mesa ANV compiles compute pipelines at runtime into `/root/.cache`, which is lost on container restart. Export `MESA_SHADER_CACHE_DIR="/share/ollama_models/.mesa_cache"`, `MESA_SHADER_CACHE_MAX_SIZE="2G"`, and `ANV_ENABLE_PIPELINE_CACHE=1`. This persists compiled SPIR-V shader binaries to NVMe storage across container reboots, eliminating first-token warmup stutters.
- **The UINT32_MAX Buffer Limit & Output Layer CPU Drop:** Mesa ANV enforces `maxStorageBufferRange` ≈ 4 GB. If memory sizing drops the final layer (`lm_head`) onto CPU while hidden layers remain on GPU, precision mismatch at dequantization triggers immediate End-Of-Sequence (EOS) tokens (generating only 2–3 tokens before exiting). Models must fit 100% of layers on the GPU.
- **Flash Attention + KV Cache Quantization:** Export `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0`. This halves KV-cache memory footprint on unified RAM, allowing 8192-token contexts without triggering layer backoff.
- **The Context Sizing × Concurrency Memory Multiplication Trap:** In Ollama / llama.cpp, context memory is allocated per parallel slot. Configuring `context_length: 32256` alongside `num_parallel: 4` forces an internal context reservation of `32256 × 4 = 129,024` tokens! On 7B+ models, this requires over 16 GB solely for the KV cache and stalls model initialization until hitting `OLLAMA_LOAD_TIMEOUT: 5m0s`, causing requests to freeze for 4–5 minutes before returning HTTP 400. For local Home Assistant add-on deployments, explicitly pin `num_parallel: 1`, `context_length: 8192` (or 4096), and `max_loaded_models: 1` to ensure models load in <2.5 seconds with compute buffers under 300 MB.

### Autonomous Generation Hang Watchdog & Circuit Breaker
- **The Shallow TCP Ping Trap:** A GPU deadlock or driver stall leaves TCP port 11434 responsive while generation requests hang indefinitely. The supervisor TCP watchdog cannot detect this.
- **Two-Tier Probe Pattern:** In `run.sh`, run a background watchdog loop every 300s:
  1. Inspect `/api/ps` via curl. If no model is loaded (idle `keep_alive` expired), skip probing to avoid waking the model.
  2. If loaded, send a minimal non-streaming prompt (`{"prompt": "hi", "options": {"num_predict": 1}}`) with a 60s timeout.
  3. Track triggers in `/tmp/ollama_watchdog_triggers`. If restarts exceed 3 within a rolling 30-minute window, trip the circuit breaker and halt restarts with a `FATAL` log to avoid thrashing.

### The Reasoning / Thinking Model Latency Trap on Edge Hardware
- **Pitfall:** Deploying modern reasoning / thinking models (models trained with extended chain-of-thought, e.g. Qwen 3.6, DeepSeek-R1 distills, Ornith 1.5) as the default edge model on integrated GPUs.
- **Mechanism:** On an iGPU (shared system RAM), large 14B–35B models run at ~1.5 to 10 tokens/sec. Reasoning models generate hundreds or thousands of internal thinking tokens before emitting the first user-visible answer token. At 10 t/s, unconstrained thinking (`budget = 2,147,483,647`, `repeat_penalty = 1.0`, `temp = 1.0`) leads to runaway loops (generating 3,000–4,000+ reasoning tokens for 7+ minutes), triggering repetition loop detectors (`🔁 Response dominated by repeated text`) or client socket timeouts.
- **Rule:** For interactive Home Assistant turn execution and fast-path routing, default to compact, non-reasoning instruct models (e.g. `qwen2.5:1.5b` or `llama3.2:3b`), which deliver 80–120 tokens/sec and sub-second responses. Only route to thinking models for asynchronous, batch, or background tasks where multi-minute generation times are explicitly tolerated.
- **Sampling Constraint Invariant for Edge CoT:** When using local chain-of-thought models for scheduled reports, always pass bounded sampling options: `temperature: 0.6`, `num_predict: 2000` (or `max_tokens: 2000`), and `presence_penalty: 0.2`. `num_predict` is the *total* generation cap (reasoning tokens + final report combined) — an overly restrictive ceiling (e.g. 150–400 tokens) will truncate complex multi-app reports mid-sentence, while unconstrained generation (`repeat_penalty = 1.0`, `temp = 1.0`) triggers 4,000+ token runaway loops. The `0.6` temperature and `0.2` presence penalty naturally bound the internal thinking trace to ~60–100 tokens while allowing full report delivery in <20 seconds.

### Ingress WebUI Proxy: CORS Preflight (OPTIONS), Streaming Keep-Alive & Ingress Double-Slash Traps
- **The CORS Preflight `OPTIONS` Trap (`Failed to fetch`):** When Home Assistant Ingress embeds an interactive chat or model manager WebUI, any browser `fetch()` call with `Content-Type: application/json` (chat messages, model pulls) or `DELETE` requests triggers a mandatory CORS preflight `OPTIONS` check. If the internal proxy server (e.g. Python's `SimpleHTTPRequestHandler`) does not implement `do_OPTIONS`, it returns `HTTP 501 Unsupported method ('OPTIONS')`. Browsers (Chrome, Safari, HA Companion mobile apps) abort the request before it reaches Ollama, presenting as an unhelpful `Error: Failed to fetch` in the UI.
  - **Rule:** Implement `do_OPTIONS` returning `200 OK` with explicit `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: GET, POST, DELETE, PUT, PATCH, OPTIONS`, `Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With`, `Access-Control-Max-Age: 86400`, and `Content-Length: 0`.
- **The HTTP/1.1 Streaming Framing & Chunk Reader Stall:** Forwarding raw token chunks from an upstream LLM through Python's `SimpleHTTPRequestHandler` without strict RFC 9112 chunked transfer framing (`<hex-len>\r\n<data>\r\n` terminated by `0\r\n\r\n`) breaks the browser's `response.body.getReader()` across Home Assistant Ingress reverse proxies. The browser's HTTP parser cannot verify chunk boundaries and hangs indefinitely waiting for socket closure.
  - **The Buffered REST Rule for Add-on WebUIs:** For embedded admin/test WebUIs in Home Assistant Add-ons, avoid raw chunked streaming unless backed by a full async ASGI server (FastAPI/Uvicorn). Set `stream: false` in frontend `fetch()` calls and buffer responses in the proxy with an explicit `Content-Length` header (`resp.content`, `send_header("Content-Length", str(len(content)))`). This completely eliminates streaming stalls, premature EOF drops, and proxy buffering timeouts while still returning full generation statistics (`eval_count`, `eval_duration`, `tokens/s`).
- **The Periodic Dropdown DOM Wipe Trap:** Periodically polling model-catalog endpoints (e.g. `setInterval(fetchModels, 5000)`) where the handler resets the select dropdown (`modelSelect.innerHTML = ''`) wipes out the user's active selection mid-click and closes the menu. Decouple frontend polling: fetch the model catalog only once on page load or after explicit downloads/deletions, and restrict recurring interval timers strictly to lightweight state monitors (`/api/ps`) that update status labels without altering dropdown DOM nodes.
- **Ingress Double-Slash Path Trap:** Home Assistant Ingress URL routing can forward requests with duplicate leading slashes (e.g. `//api/chat`, `//api/tags`). Strict string matching (`path.startswith("/api/")`) evaluates to `False`, dropping the request into static file handler 404s. Always normalize paths via `'/' + self.path.lstrip('/')` before route matching.
- **The Ingress Nginx Chunked Request Body Trap (`Transfer-Encoding: chunked`):**
  - **Mechanism:** When Home Assistant Supervisor's Nginx Ingress reverse-proxy forwards incoming client `POST`, `PUT`, or `DELETE` requests with JSON payloads, it forwards the request body using `Transfer-Encoding: chunked` rather than sending a `Content-Length` header.
  - **The Silent Failure:** If a custom Python proxy (e.g. using `http.server.SimpleHTTPRequestHandler`) only reads request bodies via `int(self.headers.get("Content-Length", 0))`, it finds 0 or `None`. The proxy then forwards an empty body (`data=None` or empty payload) to the upstream engine (Ollama, local API), while the unconsumed chunk stream remains buffered in `self.rfile`. The upstream engine sits waiting indefinitely for the JSON payload until hitting its read timeout (e.g. 300s), logging a 500/timeout error which the client browser displays as `Failed to fetch`.
  - **The Rule:** Any custom Python proxy handling Ingress requests must inspect `Transfer-Encoding` for `"chunked"`, assemble the chunks before proxying, and **strictly strip** `transfer-encoding` from the forwarded headers:
    ```python
    body = None
    if method in ["POST", "DELETE", "PUT", "PATCH"]:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" in transfer_encoding:
            chunks = []
            while True:
                line = self.rfile.readline().strip()
                if not line:
                    break
                try:
                    chunk_len = int(line, 16)
                except ValueError:
                    break
                if chunk_len == 0:
                    self.rfile.readline() # consume trailing CRLF
                    break
                chunks.append(self.rfile.read(chunk_len))
                self.rfile.readline() # consume trailing CRLF
            body = b"".join(chunks)
        else:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length)

    # CRITICAL: Always strip transfer-encoding in addition to host and content-length!
    # If transfer-encoding: chunked is forwarded with an assembled bytes body, upstream
    # engines (e.g. Go/Ollama) expect hex chunk headers and reject with HTTP 400.
    headers = {k: v for k, v in self.headers.items() if k.lower() not in ["host", "content-length", "transfer-encoding"]}
    resp = requests.request(method, url, data=body, headers=headers, stream=False, timeout=300)
    ```
  - **Multi-Endpoint Schema Normalization (`/api/chat` vs `/api/generate`):**
    When the frontend interacts with upstream inference engines exposing multiple endpoint conventions, resolve responses polymorphically in JavaScript:
    `const reply = (data.message && data.message.content) ? data.message.content : (data.response || "");`
    This ensures that both single-turn generation tests and multi-turn conversational chat payloads display without blank bubbles or `undefined` text.
- **Dual-Access Port Architecture (Ingress + Direct LAN Port):**
  - Always expose a direct LAN port mapping in `config.yaml` (`ports: { 8099/tcp: 8099 }` or `null` default) alongside `ingress: true`.
  - This provides the operator with an instant, direct browser link (`http://<ha-ip>:8099/`) to test the application unproxied, completely bypassing Ingress iframes, mobile WebView iframe restrictions, and Supervisor Nginx chunking traps.

### Mobile Virtual Keyboard, `alert()` Suppression & Touch Targets in Ingress WebUIs
- **The Mobile Virtual Keyboard `onkeypress` Trap:** Input fields bound with `onkeypress="if (event.key === 'Enter') ..."` fail completely on mobile devices (Android Gboard, iOS virtual keyboard). Mobile keyboards generate `input` and `composition` events and do NOT fire deprecated `keypress` events when tapping the blue Enter/Go/Send key.
  - **Rule:** Always wrap input areas in a semantic HTML `<form onsubmit="event.preventDefault(); sendMessage();">`. Submitting via a form guarantees that tapping Enter/Go/Send on any virtual keyboard or tapping a `<button type="submit">` triggers submission reliably across desktop and mobile.
- **Mobile Webview `alert()` Suppression in HA Companion App:** Within the Home Assistant Companion App and mobile webviews running Ingress iframes, `window.alert()` dialogs are frequently suppressed, blocked, or fail silently. If validation logic relies on `alert("Please select a model first")` and returns, the user experiences total unresponsiveness with no visual feedback.
  - **Rule:** Never use `alert()` for user notifications or error reporting in Ingress WebUIs. Render all notifications, validations, and test results directly as in-DOM status messages or chat bubbles inside the UI.
- **Mobile Touch Target & Viewport Zoom Prevention:**
  - Set input field font sizes to at least 16px (`font-size: 16px;`) — mobile Safari and Chrome automatically trigger unwanted page zoom when focusing input fields with font sizes smaller than 16px.
  - Interactive controls (buttons, select dropdowns) must maintain a minimum touch target size of 44x44px (`min-height: 44px;`) for comfortable mobile touch operation.
  - Include `<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">` to prevent mobile layout clipping in Ingress iframes.
- **The Mobile Select Dropdown Auto-Selection Trap:**
  - In mobile WebViews (iOS Safari, Android Chrome in HA Companion App), when `<option>` elements are dynamically appended via JavaScript to a `<select>` that initially had an empty value (`<option value="">Laden...</option>`), mobile WebViews do NOT automatically select the first option. `modelSelect.value` remains `""` (empty string). If the script checks `const modelToUse = modelSelect.value; if (!modelToUse) return;`, the handler silently aborts without making any network request, giving the false illusion that tapping buttons or submitting does nothing.
  - **Rule:** After dynamically populating `<select>` options in Ingress WebUIs, explicitly set `selectedIndex = 0` and `.value = options[0].value`:
    ```javascript
    if (prevVal && Array.from(modelSelect.options).some(o => o.value === prevVal)) {
        modelSelect.value = prevVal;
    } else if (modelSelect.options.length > 0) {
        modelSelect.selectedIndex = 0;
        modelSelect.value = modelSelect.options[0].value;
    }
    ```
    Additionally, add an automatic fallback in submission handlers: `let modelToUse = modelSelect.value || (modelSelect.options[0] ? modelSelect.options[0].value : null);`.

### Dual-Model Resident Serving & Zero-Reload Switching (`max_loaded_models >= 2`)
- **System 1 / System 2 in Unified VRAM:** On systems with unified host RAM unlocked via `GGML_VK_PREFER_HOST_MEMORY=1` (e.g. 48 GB host RAM granting 41 GiB to Vulkan), configure `max_loaded_models: 2` (or 3) in add-on options rather than the default `1`.
- **Zero-Latency Tier Switching:** Ollama keeps separate runner instances preloaded in VRAM (e.g., a fast ~2.3 GB 3B model alongside a heavy ~21.5 GB 35B MoE model, totaling ~23.8 GB). Switching between the fast reflex model (for Home Assistant voice commands and intent parsing) and the heavy reasoning model (for Hermes deep planning and code analysis) incurs **0.00s load time** (~1.2 ms dispatch overhead) without triggering disk thrashing or model eviction.

### Token Throughput Physics on Intel Arc Xe-LPG iGPU (Arrow Lake / Meteor Lake)
- **The Empirical Speed Baseline:**
  - 3B dense models (`qwen2.5:3b`, `llama3.2:3b`): **~15 to 16 tokens/sec**.
  - 7B dense models (`qwen2.5:7b`): **~10 to 12 tokens/sec**.
  - 35B MoE models (`ornith-1.5:35b`, ~3B active params/token): **~9 to 10 tokens/sec**.
- **The Physical Ceiling:** These numbers are not an artifact of misconfiguration or driver bugs. They represent the physical ceiling of an integrated GPU (8 Xe cores sharing a 28W–45W SoC TDP and a dual-channel DDR5 memory bus of 75–90 GB/s):
  1. *Memory Bandwidth Bound:* Autoregressive decoding (batch size = 1) streams active parameter weights from memory on every single token.
  2. *Vulkan Dispatch Latency:* A 36-layer model requires ~300 discrete Vulkan compute shader dispatches per token through the Linux DRM / KMD ring buffer (`/dev/dri/renderD128`). At ~0.18 ms per layer dispatch, the ring buffer turn-around introduces a hard floor of ~60 ms per token (~16 t/s).
  3. *Practical Adequacy:* 16 t/s equals ~12 words per second (three times human reading speed). Typical Home Assistant action confirmations (~12 tokens) complete in ~750 ms, providing sub-second latency for interactive smart home voice and turn execution.

---

## 23. Autonomous Maintenance Framework, Upstream Drift Auditing & Ephemeral HA Mock Runs

When operating a suite of production Home Assistant Apps (`<REPO_ROOT>/apps/`):

### Weekly Maintenance Orchestration Lifecycle
Execute a recurring weekly audit cycle orchestrated by the agent against `<REPO_ROOT>/apps/`:
1. **Upstream Drift & Security Audit:** Check upstream base images (Debian/Ubuntu/Alpine), container tags, GitHub software releases, language dependencies (`pip-audit`, `npm audit`, OSV.dev CVE database), secret scanners, and OKF v0.2 guidance.
2. **Interactive Plan Formulation & Urgency Classification:**
   - Present a concise Telegram maintenance digest classifying each app with a **Low / Medium / High** urgency rating:
     - *High*: Dependency CVEs / secret leaks or major breaking upstream bumps.
     - *Medium*: Upstream feature / minor releases or stale base images.
     - *Low*: Routine patch bumps or non-critical dependency updates.
   - Provide a per-app brief summary of proposed changes and an explicit approval request (`Approve <app>` or `Approve all`) before modifying files or triggering builds.
3. **Multi-Trigger Invocation (Cron + On-Demand):**
   - Support automated scheduled execution (e.g. Sunday 11:00 AM CET, outside quiet hours and after morning activities) with conversational session attachment (`attach_to_session: true`).
   - Support immediate on-demand CLI execution (`python3 tools/maintenance/main.py [check|plan|test|execute]`) or conversational trigger (`/check-maintenance`).
4. **Strict Failure Quarantine Policy:**
   - If pre-flight linting, unit tests, or the mock run fails, production remains 100% untouched.
   - Quarantine the update, log the root cause / s6 crash trace, notify the operator, and hold the branch/PR without merging.
5. **Deterministic Documentation & OKF Gate:**
   - Automatically bump version in `config.yaml`, prepend structured entries to `CHANGELOG.md`, record maintenance events in OKF `knowledge/log.md`, and update `README.md` / `DOCS.md`.
   - Enforce gate via `validate_okf.sh` before committing to the maintenance branch (`maint/<app>-<version>`).
6. **Mandatory Mantis Security Diff Review Gate (Gemini 4 Argon & OpenRouter GLM-5.3):**
   - Before any app update is committed or deployed, extract the unified git diff (`git diff HEAD -- apps/<slug>`) and execute an automated review pass through the Mantis Security Agent MCP server (`mantis_review_diff`). Target **Gemini 4 Argon** (`gemini-4-argon`) by default, or OpenRouter's **GLM 5.3** (`z-ai/glm-5.3`):
     ```json
     {"diff": "<patch>", "context": "Home Assistant add-on on HAOS, behind Ingress", "llm": {"provider": "gemini", "model": "gemini-4-argon"}}
     ```
     Or with OpenRouter:
     ```json
     {"diff": "<patch>", "context": "Home Assistant add-on on HAOS, behind Ingress", "llm": {"provider": "openrouter", "model": "z-ai/glm-5.3"}}
     ```
   - **Gating Verdict**: If Mantis reports findings or verdict != CLEAN, immediately abort the upgrade branch, roll back local changes, and report the vulnerability details.
   - **Audit Record**: On a clean verdict, record the Mantis job ID and verdict in `CHANGELOG.md` (e.g. `Mantis (gemini-4-argon) passed [Job: rev_..., Verdict: CLEAN]` or `Mantis (z-ai/glm-5.3) passed [Job: rev_..., Verdict: CLEAN]`).
7. **End-to-End Live Deployment Verification:**
   - A maintenance update or bugfix is **NOT complete until live redeployment on Home Assistant OS is executed and verified**.
   - Simply modifying files in `<REPO_ROOT>/` or `/config/addons/` does NOT update the running add-on. Supervisor reads local add-ons from `/addons/<folder>/` on the host root filesystem.
   - Always execute the full deployment bridge:
     1. Sync files to host `/addons/<folder>/` via `rsync` over SSH (`<HAOS_SSH_HOST>`).
     2. Run `ha store reload`.
     3. Execute `ha apps update local_<slug>` (or `rebuild` only when `version` did not change).
     4. Verify `ha apps info local_<slug>` shows `state: started`, `version == version_latest`, and `update_available: false`.
     5. Query the container's healthcheck or API endpoint to confirm clean runtime initialization.

### Per-App Maintenance Contract (`apps/<slug>/maintenance.yaml`)
To prevent monolithic configuration drift, declare upstream targets and testing hooks per app:
```yaml
name: "My App"
app_type: "local_app"               # local_app | upstream_wrapper | infra
upstream:
  github_repo: "owner/upstream-repo" # or docker_image: "repo/image", base_image: "debian:bookworm-slim"
  pip_file: "requirements.txt"
healthcheck:
  port: 8000
  endpoint: "/health"
  timeout_seconds: 30
security:
  cve_check: true                   # OSV.dev query
  secret_scan: true                 # regex & token patterns
  okf_required: true                # OKF v0.2 bundle conformance
docs:
  sync_changelog: true
  sync_readme: true
  sync_okf: true
test_commands:
  - "pytest tests/"
  - "./scripts/validate_okf.sh"
```

- **Upstream Wrapper SemVer Alignment Invariant:** When an add-on is classified as `app_type: "upstream_wrapper"` tracking an upstream repository or Docker tag (e.g. Ollama, Langfuse), avoid maintaining independent disconnected minor version numbers in `config.yaml` (e.g. declaring add-on `0.8.0` while upstream publishes `0.40.15`). Automated maintenance checkers comparing SemVer will calculate false-positive major/minor version jumps (`0.8.0` -> `0.40.15`). Lock the add-on `config.yaml` version directly to the upstream engine version (`0.40.15`) so Supervisor updates, maintenance digests, and upstream release notes remain completely synchronized.

### The UV Test Runner & Container Python Pitfalls
- **The `uv run --system` Trap:** In container environments where `uv` is installed, running `uv run --system pytest` fails with `error: unexpected argument '--system'`. To run test tools without polluting the global environment or failing when packages are absent from system python, use `uv run --with pytest pytest <args>`.
- **The Python 3.14+ Host vs Debian Bookworm PyO3 Build Trap:** When the host or agent environment runs a cutting-edge Python version (e.g. Python 3.14), executing `uv run --with-requirements requirements.txt` defaults to compiling native wheels for the host Python. Rust-based packages using PyO3 (such as `pydantic-core`) fail with `the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)`.
  - **Rule:** When testing add-ons based on Debian Bookworm (or pinned base images), explicitly pin the target Python version:
    `uv run --python 3.11 --with pytest --with-requirements requirements.txt pytest tests/`
- **The System Python vs Virtualenv Package Split:** Addon hosts often have Python packages (such as `pyyaml`) installed under `/usr/bin/python3` while local virtualenvs or tool venvs lack them. Always verify package availability or explicitly invoke via `/usr/bin/python3` or `uv run --with <pkg>` rather than assuming unadorned `python3` has third-party libraries installed.
- **Phantom SDK Dependencies & Transitive Deadlocks:**
  - Before troubleshooting complex version constraint deadlocks (e.g. `semgrep` pinning `opentelemetry-api <1.26` while `mcp >= 2.0` requires `opentelemetry-api >= 1.28`), audit whether the add-on actually imports the external SDK (`import mcp`). If the service implements the protocol natively (e.g. JSON-RPC 2.0 endpoints directly in FastAPI), remove the phantom SDK from `requirements.txt` to instantly resolve CVEs and eliminate transitive lockfile conflicts.
- **Telegram Slash Command Interception Pitfall:**
  - Telegram clients and messaging gateways treat any message with a leading slash (`/check-maintenance`) as a native bot command. If not registered in the static gateway `COMMAND_REGISTRY`, the platform intercepts and drops it with an unknown command error. Instruct operators to use conversational phrasing without leading slashes (e.g. `"check maintenance"`, `"run maintenance check"`).

### The Ephemeral HA Mock Run Invariant
- **The Live In-Place Collision Trap:** Rebuilding or updating an add-on directly on its live production slug (`local_<slug>`) to test an upgrade risks taking down mission-critical home services (e.g. `open-hems`, `unifi-os-server`, `mantis`) or corrupting production database volumes in `/data`.
- **Rule:** Never execute test or mock runs against active production slugs or mounts:
  1. Register an isolated ephemeral staging slug (`local_<slug>_test`) pointing to an isolated directory (`/share/addons/<slug>_test/`) with non-colliding host ports (ports mapped to `null`).
  2. Provide deterministic `mock_options` in the staging manifest that bypass production state writes.
  3. Trigger an ephemeral container build via Supervisor API (`POST /addons/local_<slug>_test/install` or `rebuild`).
  4. Stream container logs for 30–60 seconds to verify clean S6-overlay boot, dependency initialization, and HTTP 200 on healthcheck endpoints.
  5. Cleanly stop (`POST /addons/local_<slug>_test/stop`) and uninstall (`POST /addons/local_<slug>_test/uninstall`) the test slug, leaving zero residual containers or stale mounts on the HA host.

### Upstream Node.js ESM & Prisma Alpine/Musl Runtime Traps
- **The Alpine 3.20 Node.js 20 ESM Crash (`ERR_REQUIRE_ESM`):**
  - **Mechanism:** Modern upstream Node applications (e.g. Langfuse v4) use ESM-only packages (such as `uuid >= 14`). In Alpine 3.20 (which packages Node 20.15.1), CommonJS `require()` of ES modules fails on startup with `Error [ERR_REQUIRE_ESM]: require() of ES Module ... not supported`.
  - **Rule:** For add-ons bundling modern Node.js services, bump `BUILD_FROM` to Alpine 3.21 (`ghcr.io/home-assistant/amd64-base:3.21` and `aarch64-base:3.21`). Alpine 3.21 ships Node.js 22 (`v22.23+`), which supports synchronous ESM `require()` out of the box.
- **The Prisma Multi-Engine Musl Mismatch (`linux-musl-openssl-3.0.x`):**
  - **Mechanism:** Upstream images built on Debian/RHEL glibc bundle Prisma query engines compiled for `rhel-openssl-3.0.x`. When Next.js or worker assets are copied into an Alpine (musl) Home Assistant add-on container, Prisma Client crashes with `PrismaClientInitializationError: Prisma Client could not locate the Query Engine for runtime "linux-musl-openssl-3.0.x"`.
  - **Rule:** Ensure the globally installed or engine-bundled musl binary is explicitly targeted:
    Export `PRISMA_QUERY_ENGINE_LIBRARY="/usr/local/lib/node_modules/prisma/libquery_engine-linux-musl-openssl-3.0.x.so.node"` in service environment files (e.g. `/run/langfuse.env` or `init_config.sh`) before launching Web or Worker daemons so Prisma resolves the native engine without failing.
- **The Native Compiled Rust/Node Binding Glibc vs Musl Trap & s6 Zero-Backoff Spin Storm:**
  - **Mechanism:** Upstream multi-arch Node applications increasingly bundle pre-compiled native Rust/C++ bindings (e.g. `@langfuse/native`) compiled solely for `glibc` (`linux-x64-gnu`). When copied into an Alpine (`musl`) container (`ghcr.io/home-assistant/amd64-base:3.x`), loader chains fail immediately at runtime (`Cannot find module '@langfuse/native-linux-x64-musl'`).
  - **The s6-supervise Zero-Backoff Spin Storm:** Because `s6-supervise` lacks exponential restart backoff by default, an unhandled native binding crash on startup causes s6 to respawn the Node.js process hundreds of times per minute. This inflates process IDs into the hundreds of thousands (PIDs > 400,000) and burns 6%–12% constant CPU doing nothing but restarting crashing runtimes.
  - **Rule:** When wrapping upstream applications that bundle pre-compiled native Rust/C++ bindings or complex Prisma stacks, do not attempt to patch musl compatibility onto Alpine. Build the add-on on a Debian base image (`ghcr.io/home-assistant/{arch}-base-debian:trixie` for Debian 13 / glibc 2.41 or `bookworm` for Debian 12) so native bindings and query engines execute against native glibc without translation or spin loops.
  - **PostgreSQL 16 Persistence Compatibility on Debian Trixie:** Debian Trixie packages PostgreSQL 17 by default. If migrating an add-on whose persistent `/data/postgres` directory was initialized under PostgreSQL 16 (on Alpine), PostgreSQL 17 refuses to start (`FATAL: database files are incompatible with server (version 16 vs 17)`). Maintain 100% binary compatibility by adding the official PostgreSQL repository (`http://apt.postgresql.org/pub/repos/apt/ trixie-pgdg main`) and installing `postgresql-16` and `postgresql-contrib-16`.
  - **Prisma Query Engine Resolution, `/tmp/prisma-engines` Fallback & The Symlinked CLI Trap:**
    1. *The Broken `/usr/local/bin/prisma` Symlink Trap:* When copying binaries via `COPY --from=upstream-source /usr/local/bin /usr/local/bin`, the `prisma` CLI executable is often an npm symlink pointing to `../lib/node_modules/prisma/build/index.js`. If `/usr/local/lib/node_modules` is omitted from the multi-stage copy, `/usr/local/bin/prisma` becomes a dangling symlink, causing database migration scripts to fail with `prisma: not found`. Always copy both `/usr/local/bin` and `/usr/local/lib/node_modules`.
    2. *The Dynamic Path & Multi-Process Trap:* In pnpm workspaces, dependency hashes shift across upstream releases (e.g. `@prisma+client@6.19.3_..._magicast@...`), and auxiliary background workers or migration runners may not inherit `PRISMA_QUERY_ENGINE_LIBRARY`. However, Prisma Client natively searches `/tmp/prisma-engines/libquery_engine-debian-openssl-3.0.x.so.node`. In `init_config.sh`, copy the discovered engine to `/tmp/prisma-engines/`:
       ```bash
       mkdir -p /tmp/prisma-engines
       ENGINE_FILE=$(find /opt/langfuse-web-pristine /opt/langfuse-worker -name "libquery_engine-rhel-openssl-3.0.x.so.node" 2>/dev/null | head -n 1)
       if [ -n "${ENGINE_FILE}" ] && [ -f "${ENGINE_FILE}" ]; then
         cp -f "${ENGINE_FILE}" /tmp/prisma-engines/libquery_engine-debian-openssl-3.0.x.so.node
         cp -f "${ENGINE_FILE}" /tmp/prisma-engines/libquery_engine-rhel-openssl-3.0.x.so.node
         cp -f "${ENGINE_FILE}" /tmp/prisma-engines/libquery_engine-linux-openssl-3.0.x.so.node
       fi
       ```
       *(Note: Search `/opt/...-pristine` rather than `/opt/...` if `init-config` runs before asset substitution scripts).*

### Frenck Community Release Notes & CHANGELOG Convention
When authoring release notes or updating `CHANGELOG.md` for Home Assistant Apps and Add-ons, strictly follow the canonical format established by Franck Nijhof (@frenck / Home Assistant Community Add-ons):
```markdown
## [<version>] - <YYYY-MM-DD>

## What’s changed

## ⬆️ Dependency updates
- ⬆️ Update ...

## 🚀 Features
- 🚀 ...

## 🐛 Bug fixes
- 🐛 ...

## 🧰 Maintenance
- 🛡️ Verified clean security diff review via Mantis Security Agent (gemini-4-argon) [Job: rev_..., Verdict: CLEAN]
- 🧰 ...
```
Never use unstructured un-categorized lists or non-standard emoji groupings. Follow this exact categorization structure.

- **Maintenance Cronjob Scoping Invariant (`enabled_toolsets`):** When configuring scheduled maintenance jobs (e.g. `ha-apps-weekly-maintenance`) that call LLMs, always explicitly bound the toolsets:
  - Update checks and execution: `enabled_toolsets: ["file", "terminal", "web"]` (collapses prompt schemas from 24k tokens to <6.5k tokens, reducing prefill time on edge hardware by >70%).
  - Summaries or reporting: `enabled_toolsets: []` (~1.8k tokens, <15s prefill).
  - Never allow maintenance cronjobs to inherit the unconstrained global toolset (which forces multi-minute prefill times and repetitive thinking loops on local edge SLMs).

---

## 24. Heavy Database Engines, Memory Caps & Docker-less HAOS OOM Diagnostics

When bundling enterprise analytical engines (ClickHouse, Elasticsearch, JVM, Redis, or multi-worker Node stacks) inside Home Assistant Add-ons:

### The "Unenforced Engine Memory Cap" & ClickHouse 90% Host RAM Exhaustion Trap
- **Mechanism:** Exposing an options schema field in `config.yaml` (e.g. `clickhouse_memory_limit_mb: 4096`) does nothing unless the init script dynamically writes that cap into the engine's configuration file. Analytical engines like ClickHouse calculate defaults based on total host physical RAM (`max_server_memory_usage_to_ram_ratio = 0.9`). On a 64 GB host, ClickHouse attempts to claim ~57 GB of RAM.
- **The Cascade Failure:** When traces or analytics ingest, the engine and child workers exhaust host RAM, push swap to 100%, and cause massive disk I/O thrashing that pushes host load averages past 300+. The Linux kernel OOM killer then intervenes, killing victim processes (including the Hermes Gateway and other critical add-ons).
- **Rule:** Every configurable memory option must be explicitly compiled into the engine's config directory in `init_config.sh` or `init_secrets.sh`:
  ```bash
  # Calculate bytes from MB option (default 4096 MB)
  CH_MEM_BYTES=$(( ${CLICKHOUSE_MEM_MB:-4096} * 1024 * 1024 ))
  CH_QUERY_MEM_BYTES=$(( CH_MEM_BYTES / 2 ))
  CH_USER_MEM_BYTES=$(( CH_MEM_BYTES * 3 / 4 ))

  mkdir -p /etc/clickhouse-server/config.d /etc/clickhouse-server/users.d

  cat <<EOF > /etc/clickhouse-server/config.d/01-memory.xml
  <clickhouse>
      <max_server_memory_usage>${CH_MEM_BYTES}</max_server_memory_usage>
      <max_server_memory_usage_to_ram_ratio>0.0</max_server_memory_usage_to_ram_ratio>
  </clickhouse>
  EOF
  chmod 644 /etc/clickhouse-server/config.d/01-memory.xml

  cat <<EOF > /etc/clickhouse-server/users.d/01-memory.xml
  <clickhouse>
      <profiles>
          <default>
              <max_memory_usage>${CH_QUERY_MEM_BYTES}</max_memory_usage>
              <max_memory_usage_for_user>${CH_USER_MEM_BYTES}</max_memory_usage_for_user>
          </default>
      </profiles>
  </clickhouse>
  EOF
  chmod 644 /etc/clickhouse-server/users.d/01-memory.xml
  ```
  - **Static Rootfs Fallback:** Bake default `01-memory.xml` files directly into `rootfs/etc/clickhouse-server/config.d/` and `users.d/` during container build so the engine is physically capped even before scripts execute.
  - **s6-overlay Dependency Ordering:** The database service (`/etc/s6-overlay/s6-rc.d/<engine>/dependencies`) MUST declare `init-config` as an explicit dependency. Without this, s6-overlay boots the engine in parallel with config generation, launching the process with unconstrained defaults before caps are rendered.
  - **The s6-overlay Backgrounding Trap (`command &` in `run`) & Leaked Process Bomb:** Never spawn background tasks using `&` (e.g. `node script.js &`) inside an s6 service `run` script. s6-overlay only tracks the foreground process (`exec ...`). When the main process crashes or restarts, backgrounded processes are orphaned and unmanaged. Over repeated restarts, dozens of duplicate zombie workers accumulate in memory, exhausting swap and RAM. Any auxiliary or periodic task MUST be configured as an independent, supervised s6-overlay service (`/etc/s6-overlay/s6-rc.d/<service>/run`).
- **Node.js Concurrency Discipline:** Always set `--max-old-space-size` via `NODE_OPTIONS` for web and worker processes, and ensure background queue workers (e.g. BullMQ, Celery) have a hard concurrency limit (`CONCURRENCY=2` or `4`) to prevent worker fork bombs during burst ingestion.
- **Multi-Service Auxiliary DB Memory Ceilings (Redis & Postgres):** Capping analytical engines (like ClickHouse) is incomplete if auxiliary stores lack memory boundaries. Redis without `maxmemory` grows indefinitely until host OOM: always set `maxmemory 512mb` (or appropriate fraction) and `maxmemory-policy allkeys-lru` in `/etc/redis.conf`. Postgres must configure explicit `shared_buffers = 128MB` and `work_mem = 16MB` in `postgresql.conf` to avoid concurrent connection memory spikes.
- **Internal Database Network & Privilege Scoping:** Application database credentials must never hold administrative authority (`access_management: 1`, `named_collection_control: 1`) or open IP masks (`<ip>::/0</ip>`). Scope container database users strictly to loopback (`127.0.0.1` and `::1`) with schema-only read/write grants.

### Headless HAOS OOM & Thrashing Diagnostic Playbook (When Docker CLI is Absent)
When diagnosing severe host slowdowns, load spikes (>50), or container flapping from inside an agent container without host Docker CLI access:
1. **Host Memory & Thrashing Triad:** Run `uptime && free -h && df -h /`.
   - High load average (100–300+) combined with low CPU usage and near-zero available memory (`mem_available < 1GiB`, `swap_used` at 100%) confirms swap thrashing / memory exhaustion, not compute saturation.
2. **Kernel OOM Fingerprint:** Inspect the kernel ring buffer via `dmesg -T | grep -E "oom-kill|Out of memory"`.
   - The kernel logs the exact culprit process (`task=clickhouse-serv`), cgroup scope (`task_memcg=/system.slice/docker-<id>.scope`), total virtual memory, and resident memory (`anon-rss`) at the exact moment of termination.
3. **Supervisor API Authentication:** Call `http://supervisor/supervisor/info` or `http://supervisor/addons/<slug>/info` passing `X-Supervisor-Token: $SUPERVISOR_TOKEN` (note: `X-Supervisor-Token` header, as standard `Authorization: Bearer` can be rejected with 403 on Supervisor admin endpoints). Inspect the `addons` array to verify which add-on containers transitioned to `error` or `stopped`.

---

## 25. Autonomous Host Self-Protection & Add-on Circuit Breaker Watchdog

When Home Assistant hosts host heavy AI, analytical, or camera workloads alongside critical smart home automation:

### The "Unattended Midnight Swap Thrashing" Host Freeze Trap
- **Mechanism:** A memory leak in an auxiliary add-on (e.g. ClickHouse, Ollama, Frigate, Langfuse worker) exhausts RAM and swap in the early morning hours. Standard alerting watchdogs suppress notifications during quiet hours (22:00–08:00) by policy. By morning, the Linux kernel is thrashing in swap (load average >300), the web interface is dead, and the host requires a hard power cycle.
- **Rule:** Implement an autonomous **Circuit Breaker & Self-Healing Watchdog** (`system_health_watchdog.py`) that acts to protect the host, bypassing quiet-hour notification suppression when defensive actions are taken.

### Safe Architecture & Escalation Discipline
1. **Watchdog Execution Frequency Mandate (Every 3 Minutes):**
   - High-throughput engines (ClickHouse, Node queue workers, Ollama GPU models) can consume 50+ GB of RAM and 4 GB of swap in under 4 minutes. A standard 15-minute cron interval is too slow to prevent an OS-level OOM freeze. The self-healing watchdog (`system_health_watchdog.py`) MUST execute on a tight 3-minute schedule (`every 3m`). Because the check is a zero-LLM lightweight probe (`no_agent: true`), it consumes negligible CPU while guaranteeing intervention before kernel swap thrashing.
2. **Host-Level Danger Thresholds:**
   - `RAM >= 88.0%` AND (`ram_free <= 5.0 GB` OR `swap_used >= 1.5 GB`), OR `RAM >= 92.0%`.
   - `CPU >= 95.0%` sustained OR Linux 1-minute `load >= 30.0`.
3. **Protected Core Infrastructure (`PROTECTED_APPS`):**
   - Core automation, database, and control services must **NEVER** be restarted or stopped automatically:
     `core_mosquitto`, `core_zwave_js`, `<influxdb_slug>`, `<adguard_slug>`, `<agent_addon_slug>`, `<backup_slug>`, `<ssh_slug>`, `<vscode_slug>`.
3. **Culprit Isolation via Multiple Signal Vectors:**
   - *Vector 1 (Kernel Ring Buffer):* Scan `dmesg -T` for recent OOM kills or cgroup events, mapping process names to add-on slugs (e.g. `clickhouse-serv` ➔ `local_langfuse`, `ollama` ➔ `local_ollama_vulkan`, `ffmpeg`/`go2rtc` ➔ `ccab4aaf_frigate`).
   - *Vector 2 (Health Probes):* Probe local HTTP health endpoints of running non-critical add-ons with a short 2-second timeout. Locked or thrashing engines fail probes or time out.
   - *Vector 3 (Recoverable Apps Priority):* If no specific process is named in `dmesg`, target active recoverable heavy apps in order of resource weight.
4. **Two-Stage Circuit Breaker Execution (3-Hour Sliding Window):**
   - *First Offense in Window:* Trigger `hassio.addon_restart` via Home Assistant Core REST API (`POST http://supervisor/core/api/services/hassio/addon_restart` with `{"addon": "<slug>"}`). Notify Telegram with an auto-recovery status notice.
   - *Repeat Offense in Window (>=1 recent restart):* Trip the circuit breaker: trigger `hassio.addon_stop` (`POST http://supervisor/core/api/services/hassio/addon_stop`). Mark the app permanently disabled in state and deliver a critical Telegram alert informing the operator that the app was stopped to prevent a host crash.
5. **Quiet Hours Policy for Self-Healing:**
   - Routine informational warnings ("Disk 86% full") stay silent during quiet hours.
   - Defensive interventions (restarting or disabling an add-on to avert an OS crash) are delivered immediately so the operator has an audit trail upon waking.

---

## 26. High-Trust Agent & Shell Add-ons: Storage Maps, AppArmor & Privilege Boundaries

When packaging AI agents, developer tooling, or terminal utilities that combine root shells, compilers, and Supervisor API tokens:

### The `backup:rw` Storage Mapping Trap
- **Mechanism:** Mapping `backup:rw` gives the container full read and write access to all Home Assistant backup snapshots stored on the host filesystem.
- **The Attack Surface:** A compromised LLM agent, rogue shell script, or prompt-injection payload can tamper with host backup archives (a potential extortion/ransomware vector) or read snapshots from other add-ons containing plaintext passwords, cloud API keys, and database dumps.
- **Rule:** Never grant `backup:rw` to interactive agents or web terminals. Restrict backup mappings strictly to `ro` if inspection is necessary, or drop the map entirely and rely on Home Assistant's native Supervisor backup API (`POST /backups/new/partial`).

### AppArmor `complain` vs `enforce` Posture in Production
- **Mechanism:** AppArmor profiles declaring `flags=(..., complain)` enforce **only** explicit `deny` rules (such as self-integrity blocks preventing the agent from modifying `run.sh` or `/usr/local/lib/hermes-*`). All other capability and resource access rules are logged in audit logs, not blocked.
- **Rule:** Use `complain` mode strictly for initial staging and empirical capability discovery. For production releases of high-trust add-ons, promote to `enforce` mode so capability gaps and unexpected host probing are physically blocked at the kernel boundary.

### Multi-Profile Isolation & Shared UID Limits
- **The Shared-Root Isolation Illusion:** Running multiple distinct user profiles under `root` (UID 0) inside the same container provides filesystem organization, not cryptographic or OS-level process isolation.
- **Rule:** Because any process running as root can inspect `/proc/<pid>/mem`, trace sibling processes, and read mode 0600 `.env` files across profile directories, running multi-profile agents under a single container UID allows any single compromised session to read tokens belonging to other users. For true multi-tenant isolation, isolate profiles under distinct non-root service UIDs or execute them in isolated sub-containers.









