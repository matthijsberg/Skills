---
name: homeassistant-addon-development
description: "Use when building, upgrading, or debugging HA Add-ons."
license: MIT
metadata:
  version: "2.0.0"
  author: Hermes Agent
  platforms: [linux]
  tags: [homeassistant, ha-addon, ha-apps, docker, s6-overlay, supervisor, yaml]
  related_skills: [collaborative-software-development, homeassistant]
---

# Home Assistant Add-on Development

Build, upgrade, configure, and troubleshoot Home Assistant Apps (local add-ons under `/addons/<folder>/` on the HAOS host).

## When to Use

- Creating, scaffolding, or refactoring a Home Assistant Add-on / HA App.
- Upgrading a local add-on version (`ha store reload && ha apps update local_<slug>`), rebuilding images, or updating Supervisor `options` programmatically.
- Configuring `config.yaml` (`map`, `options`/`schema`, `ingress`, `homeassistant_api`, `hassio_api`), `build.yaml`, `Dockerfile`, or S6-overlay v3 services.
- Diagnosing Supervisor build errors, Ingress 401/404/504 issues, container networking, or host resource problems.

---

## Standard Repository Layout

```
<addon-folder>/
├── config.yaml          # Manifest (version, slug, schema, options, map, ports, ingress)
├── build.yaml           # Multi-arch base image spec
├── Dockerfile           # Container build spec
├── DOCS.md              # Documentation tab in HA UI (zero-rebuild reload via ha store reload)
├── CHANGELOG.md         # Changelog tab in HA UI
├── README.md            # Store overview card
├── translations/en.yaml # UI labels for configuration options
└── rootfs/              # Container filesystem overlay & s6-overlay services / run.sh
```

---

## Local Build, Upgrade & Option Lifecycle

All local add-on changes follow the **local-first build and verify before Git commit** rule. Keep site-specific SSH hosts, ports, and key paths in `~/.ssh/config` (e.g. `Host haos`) rather than hardcoding them in scripts or skills.

1. **Discover SSH Target:** Check `~/.ssh/config` (or `/config/.ssh/config`; note OpenSSH reads `pw_dir/.ssh/config`, so symlink `/root/.ssh/config` if needed) for the HAOS host alias (e.g. `ssh haos`).
2. **Sync to Host `/addons/<folder>/`:** Supervisor builds strictly from `/addons/<folder>/` on the HAOS host, never from `/config/addons/` inside another container's volume:
   ```bash
   rsync -avz --delete \
       --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' \
       <REPO_ROOT>/apps/<folder>/ <HAOS_SSH_HOST>:/addons/<folder>/
   ```
3. **Upgrade vs. Rebuild (`rebuild` NEVER upgrades a version):**
   - **Version bumped** (`config.yaml` `version:` + `CHANGELOG.md` updated): run `ha store reload` then `ha apps update local_<slug>`. (`ha apps rebuild` is rejected when store and local versions differ.)
   - **Same version** (iterating without a bump): run `ha store reload && ha apps rebuild local_<slug>`.
   - **Folder vs. `config.yaml` Slug:** The directory on `/addons/<folder>/` may use hyphens, while `local_<slug>` comes from `config.yaml`'s `slug:` field (often underscores). Verify with `ha apps list`.
   - Never place `ha apps restart` as an intermediate fallback between `update` and `rebuild` — `restart` exits 0 on the old image and skips compilation.
4. **Update Options via Supervisor API over SSH (Zero UI Clicks):**
   - An agent container's `$SUPERVISOR_TOKEN` lacks the `manager` role (`403 Forbidden`), and `ha_call_service` blocks `hassio`. Inside the host SSH session (`ssh <HAOS_SSH_HOST>`), `$SUPERVISOR_TOKEN` and `ha` have full manager privileges. Only ask the user for manual UI steps if SSH itself fails (`Connection refused`) and state that the SSH add-on needs to be started.
   - Because `ha apps` has no `options` subcommand: `GET http://supervisor/addons/local_<slug>/info` -> merge edits into the full `data["options"]` dictionary (Supervisor rejects partial dicts) -> `POST http://supervisor/addons/local_<slug>/options` (pipe secrets over SSH `stdin` into a `shlex.quote`-wrapped `python3 -c`, never CLI args) -> run `ha apps restart local_<slug>` so the daemon reloads `/data/options.json`.
5. **Verify Live Before Git Commit:**
   - `ha apps info local_<slug>` (`state: started`, `update_available: false`, `version == version_latest`)
   - `ha apps stats local_<slug>` and `ha apps logs local_<slug> | tail -n 30`
   - Run a real functional smoke test against the live endpoint before committing/pushing.

---

## Core Pitfalls & Invariants

- **Supervisor `ARG BUILD_FROM` Trap:** Supervisor injects `--build-arg BUILD_FROM=ghcr.io/home-assistant/base:latest` (Alpine). For Debian/glibc apps (e.g. Semgrep, manylinux wheels), hardcode `FROM debian:bookworm-slim` without `ARG BUILD_FROM`.
- **S6-Overlay PID 1 vs `init: false`:** Single-binary apps (`init: false`) fail on HA base images with `s6-overlay-suexec: fatal: can only run as pid 1`. Use `alpine:3.20` (or Debian) directly when `init: false`.
- **S6-Overlay Env & Dependencies:** In S6 v3, services reading `/data/secrets.env` must declare `init-secrets` in `dependencies`; export vars via `/var/run/s6/container_environment/` and never background tasks with `&` inside a `run` script.
- **Ingress Paths & Proxying:** Bind `0.0.0.0:<ingress_port>`, use relative `./api/...` fetches in client JS (never `/api/...`), and do not map `ssl:rw` solely for Ingress (HA Core terminates TLS).
- **Direct Bridge HA Core Access:** Inside containers, prefer `https://172.30.32.1:8123` or `http://supervisor/core` (requires `homeassistant_api: true` in `config.yaml`) over external FQDNs.
- **Zero-Rebuild Frontend Hot-Reload & Cache Busting:** Serve `/share/addons/<folder>/web` when present during dev, clean it up on release, and version query params (`?v=X.Y.Z`) + `Cache-Control: no-cache` for WebViews.
- **Fail-Fast Imports & Packaging Parity:** Never swallow top-level import errors; mirror all AST imports in `Dockerfile` and `requirements.txt`.

---

## Reference Guide

Load the specific reference file with `skill_view(name='homeassistant-addon-development', file_path='references/<file>')`:

| Topic | Reference File |
|---|---|
| Scaffolding, quality gates, SSH bridge, DB memory caps, OOM watchdogs, AppArmor | `references/scaffolding-and-quality-gates.md` |
| Ingress daemons, HTTP/1.1 keep-alive, Chart.js/InfluxDB, SemVer, MCP & OKF highlights | `references/ingress-daemons-and-frontend-pitfalls.md` |
| Internal networking, SSL dual-listeners, `/share` credential bootstrap, OCI extraction | `references/internal-networking-and-ssl.md` |
| Complex SPAs (Next.js/NextAuth), Postgres/ClickHouse/SeaweedFS S3, cold backups | `references/complex-spas-databases-and-ingress.md` |
| S6-overlay `init: false` recipes & GitHub `repository.yaml` indexing | `references/s6-overlay-and-addon-repositories.md` |
| Sandboxed AI security add-ons, Ingress approval gating & OKF v0.2 bundles | `references/sandboxed-security-addons-and-okf.md` |
| Security & maintenance scanning (OSV.dev, GHSA, Trivy CI gates) | `references/security-and-maintenance-scanning.md` |
| Pre-commit secret scanner, Bandit/Ruff/Mypy hooks & container permissions | `references/pre-commit-secret-scanner.md` |
| Multi-version snapshot backup & automated rollback scripts | `references/addon-backup-and-rollback.md` |
| Intel Arc iGPU (XPU) & NPU hardware acceleration, Level Zero & minimal privileges | `references/hardware-acceleration-gpu.md` |
| Frigate NVR OpenVINO GPU/NPU offloading & zero-CPU recording | `references/frigate-nvr-hardware-acceleration.md` |
| LLM serving add-ons, gateway routing & Ingress streaming | `references/llm-serving-and-gateway-routing.md` |
| Monolithic daemon refactoring into modular domain routers | `references/monolithic-daemon-refactoring-and-modular-routers.md` |
| Layer 1 connectivity, telemetry, HA connector & device/sensor contracts | `references/layer1-connectivity-and-data-collection.md` |
| Framework add-ons, generic policy archetypes & dynamic entity discovery | `references/framework-addons-and-ingress-ui.md` |
| Inverted 5-layer analytics hierarchy & monorepo scoping | `references/layer5-analytics-and-monorepo-scoping.md` |
