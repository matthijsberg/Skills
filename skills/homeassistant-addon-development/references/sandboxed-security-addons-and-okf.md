# Sandboxed AI Security Add-ons, Model Context Protocol & Open Knowledge Format (OKF v0.2)

This reference outlines the architecture, sandboxing invariants, build recipes, and OKF v0.2 knowledge specifications for building AI security auditing services (like Google Mantis) as Home Assistant Add-ons.

---

## 1. Container Isolation & Sandboxing Invariants

When developing Home Assistant Add-ons that run security audits, code reviews, or execute untrusted code:
- **The Docker Socket Exposure Trap:** Never mount `/var/run/docker.sock` into an add-on container to spin up sibling containers. In Home Assistant OS, access to the Docker socket allows complete escape to the host with root privileges, compromising Home Assistant Core, Supervisor, and all local smart home devices.
- **Static-First Rule on Bare-Metal HAOS Hosts:** On single-machine HAOS hardware controlling physical home systems, do not run in-container dynamic exploit reproducers or untrusted target code. Running `bubblewrap` in an add-on requires `privileged: [SYS_ADMIN]` and custom AppArmor, weakening the host boundary. For v1 auditing, enforce **pure static analysis**:
  - Deterministic pre-pass (Semgrep CE with vendored rules, Gitleaks, ShellCheck, Hadolint) parsing code without executing it.
  - LLM stages restricted strictly to structured tools (`read_file`, `list_dir`, `write_finding`) — never provide a shell or network execution tool.
  - Generated patches must be evaluated with `git apply --check` only, never executed. Dynamic exploit execution should be deferred to a separate off-host VM or container runner.
- **Egress Approval & Agent Self-Approval Prevention:**
  - If source code or configuration is sent to cloud LLMs, enforce an explicit pre-flight approval step before any network egress occurs.
  - **Self-Approval Prevention Rule:** Autonomous agents calling security tools over MCP must NOT be able to approve their own requests. Approvals must be gated behind Home Assistant user authentication on the add-on's **Ingress web UI panel** (`/approve/<job_id>`). The agent may relay the warning text and Ingress approval link to chat (e.g. Telegram), but approval requires the human operator to authenticate via HA.
- **Shared Workspace Storage Convention (`/share/projects/`):**
  - To avoid uploading large multi-megabyte repositories over MCP tool calls, adopt `/share/projects/<repo_name>` as the canonical local workspace. Hermes maps `/share` read-write for project development, while the security auditor add-on maps `/share` read-only (`share:ro`). This enables fast deterministic commit/content hashing (`SNAPSHOT_ID`) and SQLite AST caching across runs.

---

## 2. Base Image Defaulting Trap (`ARG BUILD_FROM` vs Direct Debian)

- **Symptom:** Add-on container build fails during Supervisor build with `/bin/ash: apt-get: not found (exit code 127)`.
- **Cause:** Home Assistant Supervisor passes `--build-arg BUILD_FROM=ghcr.io/home-assistant/base:latest` (which defaults to Alpine Linux with `/bin/ash`), and marks `build.yaml` as deprecated. If a Dockerfile specifies `ARG BUILD_FROM=...` and `FROM ${BUILD_FROM}`, Docker Buildx accepts Supervisor's build-arg and pulls Alpine, causing all `apt-get` commands to fail.
- **Rule:** For add-ons requiring standard Debian/glibc (e.g. for Semgrep CE, Gitleaks, Python precompiled manylinux wheels), hardcode `FROM debian:bookworm-slim` directly in `Dockerfile` without `ARG BUILD_FROM`, ensuring Buildx strictly uses Debian regardless of Supervisor defaults.

---

## 3. Context-Aware Vulnerability Calibration

- **Symptom:** Generic SAST scanners (Semgrep, Bandit) flag dozens of internal Supervisor or HA Core calls (`http://supervisor/...`, `172.30.32.1:8123`) as dangerous local file disclosures (`CWE-939`) or unauthenticated routes, flooding reports with false positives.
- **Rule:** Security tools must accept a free-text `context` parameter from calling agents describing runtime boundaries (e.g. *"Home Assistant add-on on HAOS behind Ingress reverse proxy with internal Docker network isolation"*). Feed this into the critic/calibration stage to re-classify internal bridge endpoints from critical alerts to informational notices, cutting alert fatigue by >80%.

---

## 4. Git Subprocess & Untrusted Archive Confinement

- **Git Execution Safety (`core.fsmonitor` & `core.hooksPath`):** Malicious repositories or uploaded archives can carry a crafted `.git/config` configuring `core.fsmonitor` or git hooks pointing to an executable payload, triggering arbitrary command execution during routine status probes. Always pass `-c core.fsmonitor=false -c core.hooksPath=/dev/null --no-optional-locks` on all subprocess git commands against audited targets:
  ```python
  GIT_SAFE_ARGS = [
      "git",
      "-c", "core.fsmonitor=false",
      "-c", "core.hooksPath=/dev/null",
      "--no-optional-locks",
      "-C", str(target_path),
  ]
  ```
- **Archive Extraction Hardening (`safely_extract_tar`):**
  - **Git Metadata Rejection:** Reject any archive member containing `.git` directory segments (`if ".git" in Path(member.name).parts`). If git history is needed, require a verified `git bundle`.
  - **Symlink & Hardlink Confinement:** Reject symlinks and hardlinks in uploaded archives (`if member.issym() or member.islnk(): raise ValueError(...)`) to prevent escaping the extraction root.
  - **Traversal Protection:** Ensure `target_path == dest_resolved or dest_resolved in target_path.parents`.
- **In-Memory Patch Checks:** Never write `.patch` files directly to audited target directories (which fail on read-only mounts like `/addons:ro`). Pipe diffs directly into `git apply --check -` via `subprocess.run(stdin=patch_diff)` with fsmonitor and hooks disabled.

---

## 5. Ingress UI Sanitization & Approval Lifecycles

- **DOM XSS Sanitization:** Always escape untrusted text from audited repositories (`f.title`, `f.file`, `f.rationale`, `suggested_patch`, `targets`) using an `escapeHtml()` helper before inserting into `.innerHTML` in Ingress panels.
- **Approval Window Expiration:** Enforce a strict 30-minute expiration window (`1800s`) on approval requests. Expired jobs must transition to `cancelled` with HTTP 410, preventing stale authorization replays.
- **Credential Masking in Errors:** Never embed API keys (like Gemini keys) in URL query parameters where HTTP client status exceptions capture them in traceback strings. Pass keys exclusively via headers (`x-goog-api-key`).

---

## 6. Open Knowledge Format (OKF v0.2) Implementation & Bundle Hygiene

When integrating OKF v0.2 for cross-agent security memory, ensure exported directory bundles strictly follow spec rules:
1. **Root `index.md`:** MUST carry `okf_version: "0.2"` frontmatter.
2. **Subdirectory `index.md`:** MUST NOT have frontmatter (pure progressive disclosure markdown lists per E3).
3. **Changelog (`log.md`):** MUST use ISO 8601 date headings (`## YYYY-MM-DD` per W5).
4. **Filename Clamping:** Truncate generated concept filenames to $\le 50$ characters (`{concept_id}_{slug[:50]}.md`) to prevent Linux `NAME_MAX` errors (`[Errno 36] File name too long`) on long scanner rule titles.
5. **Reserved File Import Guard:** Bundle importers MUST explicitly skip reserved files (`index.md`, `log.md`) to avoid ingesting navigation indexes as concept documents.
6. **Billion-Laughs Frontmatter Guard:** Override `compose_node` in the YAML loader to detect and reject `yaml.events.AliasEvent`, preventing alias expansion attacks in frontmatter.
7. **Trust Tier Ladder:** Derive trust from frontmatter `verified`:
   - `human:<id>` $\rightarrow$ `human_reviewed`
   - `process:<id>` or `machine:<id>` $\rightarrow$ `machine_confirmed`
   - absent $\rightarrow$ `unverified`
