---
title: HA Add-on Security & Maintenance Scanning
description: Full-stack security verification across lockfiles, upstream GHSA advisories, Dockerfiles, and CI Trivy OS/package image scans.
---

# HA Add-on Security & Maintenance Scanning

Checking only `config.yaml` versions or `==` pins in `requirements.txt` misses CVEs in `uv.lock` transitive dependencies, `npm` lockfiles, upstream wrapper advisories, base OS packages (`apt`/`apk`), and Go/Node binaries inside the container image.

## 1. Local & Weekly Maintenance Audit (`tools/maintenance/`)

Run the maintenance checker before planning or approving updates:

```bash
python3 <REPO_ROOT>/tools/maintenance/main.py check
python3 <REPO_ROOT>/tools/maintenance/main.py plan
```

### Verification Layers
1. **Lockfile & Dependency CVEs (OSV.dev `querybatch`)**:
   - Parse `uv.lock` (`tomllib`), `requirements.txt` (`==` pins), and `package-lock.json` (`npm`).
   - Query `https://api.osv.dev/v1/querybatch` in batches of 100, then fetch `https://api.osv.dev/v1/vulns/<id>` only for matched IDs.
   - Read `database_specific.severity` and `affected[].ranges[].events[].fixed` — never attempt to parse a `CVSS:3.x/...` vector string as a numeric score.
2. **Upstream Wrapper Advisories & Release Notes**:
   - Query `https://api.github.com/repos/<owner>/<repo>/security-advisories` and evaluate `vulnerable_version_range` against the installed add-on version.
   - Scan release notes between the installed and target versions for `CVE-`, `GHSA-`, and security-fix indicators; escalate `LOW` patch updates to `MEDIUM` or `HIGH` when security fixes are present.
3. **Dockerfile & `build.yaml` Supply-Chain Hygiene**:
   - Flag `:latest` or untagged `FROM` / `build_from` references, `curl|sh` pipes without SHA-256 verification, `apt-get install` without `/var/lib/apt/lists/*` cleanup, `apk add` without `--no-cache`, and unpinned `requirements.txt` specs without a lockfile.
   - Enable `cve_check: true`, `ghsa_check: true`, and `dockerfile_audit: true` in `maintenance.yaml` even for `upstream_wrapper` apps (never disable `cve_check` just because `requirements.txt` is absent).
4. **Version Sync on Upgrade**:
   - When bumping an `upstream_wrapper` add-on, synchronize matching old-version tags/args across `config.yaml`, `Dockerfile` (`FROM` / `ARG`), `build.yaml` (`args`), and `pyproject.toml`, not `config.yaml` alone.

### Pitfalls
- **Running bare `pytest` on monorepo tools** fails with `ModuleNotFoundError: No module named 'tools'` because `pytest` omits CWD from `sys.path`; always invoke `python3 -m pytest` or ensure the repo root is inserted into `sys.path`.
- **Rate-limiting on GitHub API** occurs quickly across 8+ apps when unauthenticated; pass `GITHUB_TOKEN` / `GH_TOKEN` in headers when present in the environment.

## 2. Container OS & Binary Scanning in GitHub Actions (Trivy)

When running inside HAOS without a local Docker daemon or `trivy` binary, enforce OS (`dpkg`/`apt`/`apk`) and compiled-library (`npm`, Go, Python) CVE checks in CI before publishing to GHCR:

1. **Filesystem & Misconfig Scan (`lint-and-test`)**:
   - Run `aquasecurity/trivy-action` with `scan-type: "fs"`, `scanners: "vuln,misconfig,secret"`, `severity: "HIGH,CRITICAL"`, `ignore-unfixed: true`, and `exit-code: "1"`.
2. **Built Image Gate (before `home-assistant/builder` publish)**:
   - Build the `amd64` image locally in CI using `BUILD_FROM` and `args` parsed from `build.yaml`.
   - Run Trivy `scan-type: "image"` (`vuln-type: "os,library"`) with `format: "sarif"` (`exit-code: "0"`) -> upload via `github/codeql-action/upload-sarif@v3` (`if: always()`, `permissions: security-events: write`) -> enforce `exit-code: "1"` in a gate step.
   - Make the GHCR publish `build` job depend on (`needs:`) the image security-scan job so vulnerable OS or package layers are never published.
3. **Scheduled Full-Repo Audit**:
   - Run a weekly `schedule` workflow ahead of the weekly maintenance cron to scan all add-ons (building large GPU/LLM images in isolated matrix jobs with runner disk cleanup before `docker build`).
