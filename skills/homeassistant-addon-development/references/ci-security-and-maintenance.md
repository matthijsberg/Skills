# CI Security Scanning & Automated Add-on Maintenance

## 1. Multi-Layer Security Verification

Checking only upstream app releases (`config.yaml` vs GitHub tags) misses OS packages, transitive lockfile dependencies, and bundled multi-stage binaries. Cover all layers together:

1. **Lockfile & Advisory Check (Static / Fast):**
   - Parse `requirements.txt` (exact `==` pins + flag unpinned specs when no lockfile exists), `uv.lock` (TOML via `tomllib`, excluding `virtual`/`editable` local entries), and `package-lock.json` (`npm` v1/v2/v3).
   - Batch-query `https://api.osv.dev/v1/querybatch` (chunks of 100), then fetch `/v1/vulns/{id}` once per unique matched ID. Read `database_specific.severity` (`CRITICAL`/`HIGH` -> `HIGH`) and `affected[].ranges[].events[].fixed` — never parse `CVSS:3.x` vector strings as numeric scores.
   - Query `https://api.github.com/repos/{owner}/{repo}/security-advisories` and evaluate `vulnerable_version_range` against `current_version`; scan intermediate release bodies for `CVE-`/`GHSA-` and security keywords.
   - Audit `Dockerfile` and `build.yaml` for `:latest` or untagged `FROM` images, `curl|sh` without checksum verification, and missing `apt`/`apk` cache cleanup.
2. **Container OS & Library Scan in CI (`aquasecurity/trivy-action`):**
   - Build the `amd64` image locally in GitHub Actions (passing `build_from.amd64` and `args` from `build.yaml` via `--build-arg`) BEFORE publishing to GHCR.
   - Scan the built image with `aquasecurity/trivy-action@v0.36.0` (`scan-type: image`, `vuln-type: os,library`, `severity: HIGH,CRITICAL`, `ignore-unfixed: true`), and upload SARIF via `github/codeql-action/upload-sarif@v4` (v3 is deprecated) before the gating step (`exit-code: 1`).
3. **Architecture & Trust-Boundary Audit (Mantis):**
   - Pair Trivy (package/OS/binary CVEs) with Mantis (`mantis_review_diff` on upgrade PRs/branches and `mantis_start_audit` for periodic deep reviews of `Dockerfile`, init scripts, and HA Ingress/privilege configs).

## 2. HAOS & Trivy Pitfalls

- **HAOS root entrypoint (`DS-0002`):** Trivy flags Dockerfiles without a non-root `USER` as `DS-0002` (`HIGH`). Because HAOS Supervisor mounts `/data/options.json` as `0600 root:root` and s6-overlay requires root entrypoints, document `DS-0002` in a repo-root `.trivyignore.yaml` and pass `trivyignores: .trivyignore.yaml` in `trivy-action`.
- **Secret scanner false positives on third-party images:** Running `scanners: secret` against built wrapper images triggers on UI placeholder strings inside compiled frontend bundles and Debian's default `ssl-cert-snakeoil.key`. Run `scanners: vuln,misconfig,secret` on repository `fs` scans, and `scanners: vuln` on built wrapper `image` scans.
- **Fixing vs escalating unfixable upstream CVEs:** Always remediate what is actionable first (`apt-get update && apt-get upgrade -y` in `Dockerfile` for OS CVEs, `uv lock --upgrade-package <pkg>` for lockfiles, bumping pinned Go/CLI binaries, or compiling single-purpose Go CLIs from source). Prebuilt multi-driver Go binaries (e.g. `golang-migrate`) bundle dozens of unused database/cloud drivers and older Go stdlibs; compile only the required drivers in a `FROM --platform=$BUILDPLATFORM golang:<latest>-trixie` builder stage (`CGO_ENABLED=0 GOOS=linux GOARCH=<target> go build -tags '<needed-drivers> file'`) to strip unused CVEs cleanly. When an upstream base-image binary or vendor bundle truly has no patched release, report the exact unfixable findings with options; if temporarily exempted, scope each `.trivyignore.yaml` `vulnerabilities:` entry by exact container `paths:` (without leading `/`) and an `expired_at: YYYY-MM-DD` date so the same CVE elsewhere or after expiry still fails CI.
- **Version sync across files:** Automated version bumps must synchronize matching `old_version` references in `Dockerfile` (`FROM ...:<ver>`, `ARG *_VERSION`), `build.yaml` (`args`), and `pyproject.toml` alongside `config.yaml`, or the built container will keep running the previous upstream version.
- **Running maintenance tests in monorepos:** Invoking `pytest tools/.../tests/` directly does not put the repo root on `sys.path`; use `python3 -m pytest` or prepend the repo root to `sys.path` inside the test module.

## 3. Mantis SAST, Cross-Container Paths & Scheduled Audits

- **Exclude vendored dirs in Semgrep SAST:** Running `semgrep scan --no-git-ignore` without `--exclude` scans `.venv/`, `site-packages/`, and `node_modules/`, drowning first-party findings in dependency noise. Always pass `--exclude .venv --exclude venv --exclude node_modules --exclude .git --exclude __pycache__ --exclude .pytest_cache --exclude .mypy_cache --exclude .ruff_cache --exclude site-packages`.
- **Non-blocking tree hashing (`os.walk`):** Never run synchronous `os.walk` + regex secret-redaction across mounted HAOS roots on an async FastAPI/MCP event loop without pruning cache/venv dirs (`dirs[:] = ...`) and skipping files >512 KB; offload tree hashing to `asyncio.to_thread()`.
- **Cross-container path mapping on HAOS:** Inside an add-on container, `/config` maps to `/addon_configs/<self_slug>/` on the host, NOT HA Core's `/homeassistant`. A sibling scanner add-on mounting `homeassistant_config:ro` + `all_addon_configs:ro` accesses that add-on's `/config/...` tree at `/addon_configs/<agent_slug>/...`.
- **Supervisor permission boundary for sibling add-ons:** An add-on with `hassio_api: true` (default role) can read `GET http://supervisor/addons/<slug>/info` and trigger `POST /api/services/hassio/addon_restart` via HA Core API, but receives `403 Forbidden` on `POST /addons/<slug>/rebuild` and `/options` — those require HA UI operator action (or explicit `hassio_role: admin`).
- **Scheduled audits with LLM overrides without breaking SEC-02:**
  - Merge `args.llm` overrides with `APP_OPTIONS["providers"][provider]` (`api_key`, `base_url`) and env vars at execution time, and allow keyless local `ollama` calls (`provider == "ollama" or bool(api_key)`).
  - Never expose `/api/approve/{job_id}` to non-Ingress callers. To run unattended bi-weekly/scheduled audits, gate `auto_approve=True` strictly against an operator-configured `auto_approve_scheduled_paths` allowlist in `config.yaml` options (default `[]`).
