# Automated Pre-Commit Secret Scanner for Home Assistant Add-ons

## 1. Overview
When publishing Home Assistant add-ons or integrations to public repositories (such as GitHub), accidental commits of Home Assistant tokens, API keys, private keys, or environment files must be prevented deterministically at the git level.

---

## 2. Blocked File Patterns
The following files must be included in `.gitignore` and hard-blocked from staging:
- `*.ha_api_config.json`
- `options.json` (Home Assistant add-on options often contain passwords/tokens)
- `google_token.json`, `client_secret*.json`
- `*.pem`, `*.key`, `id_rsa`, `id_ed25519`
- `.env`, `secrets.yaml`

---

## 3. Secret Detection Patterns (Regex)
```python
SECRET_PATTERNS = [
    # GitHub Tokens
    (r"gh[pousr]_[A-Za-z0-9_]{36,255}", "GitHub Token"),
    (r"github_pat_[A-Za-z0-9_]{82}", "GitHub Fine-Grained Token"),

    # Home Assistant & JWT Tokens
    (r"eyJhbGciOi[A-Za-z0-9_\-\.]+\.[A-Za-z0-9_\-\.]+\.[A-Za-z0-9_\-\.]+", "JWT / Home Assistant Access Token"),

    # Cryptographic Private Keys
    (r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY", "Cryptographic Private Key"),

    # Telegram Bot Tokens
    (r"\b\d{9,10}:[A-Za-z0-9_-]{35}\b", "Telegram Bot API Token"),

    # Generic API Keys & Passwords
    (r"(?i)(api[_-]?key|secret|password|passwd|auth[_-]?token|bearer[_-]?token)\s*[:=]\s*['\"][a-zA-Z0-9_\-\.]{12,}['\"]", "Hardcoded API Key / Password"),

    # Google OAuth Secrets
    (r"\"client_secret\"\s*:\s*\"[^\"]{10,}\"", "Google OAuth Client Secret"),
    (r"\"refresh_token\"\s*:\s*\"[^\"]{10,}\"", "Google OAuth Refresh Token"),
]
```

---

## 4. Git Pre-Commit Hook Installation
Install `.git/hooks/pre-commit` in the add-on repository:

```sh
#!/bin/sh
# Git Pre-Commit Hook: Secret & Credential Scanner
python3 "$(git rev-parse --show-toplevel)/scripts/secret_scanner.py"
```

Ensure the hook is executable:
```bash
chmod +x .git/hooks/pre-commit
```

When a developer or agent runs `git commit`, Git automatically executes the scanner on `git diff --cached`. If any forbidden token or file is found, the commit is physically aborted (exit code 1) with an actionable error message.

---

## 5. Automated Python Linting & Scope Guardrail with Ruff (`ruff.toml`)

In addition to secret scanning, every Python-based add-on repository should integrate an automated Ruff linter in the pre-commit workflow.

### The Problem: Silent Scoping & Undefined Name Traps in Monolithic Routers
In large modular router architectures (such as `routes_analytics.py`, `routes_system.py`), two insidious runtime bugs frequently slip through manual reviews and standard test suites that mock endpoints:
1. **`UnboundLocalError` from In-Function Imports:** Importing a helper inside a downstream `if` branch (e.g. `from api.energy_feed import get_epex_tariffs_cached` at line 1600) marks that identifier as a local variable across the *entire* function in Python's bytecode. Earlier branches calling that same helper immediately fail at runtime with `local variable referenced before assignment`.
2. **`F821 Undefined Name`:** References to classes or timezone identifiers (e.g. `BatterySpec`, `AMS_TZ`) that were accidentally omitted from imports.

### Configuration (`ruff.toml`)
Place `ruff.toml` at the add-on repository root:

```toml
# Ruff Configuration for Home Assistant Add-ons
target-version = "py311"
line-length = 140

exclude = [
    ".git",
    ".pytest_cache",
    "__pycache__",
    "venv",
    "web",
]

[lint]
select = [
    "F",   # Pyflakes (undefined names F821, unused imports F401, unbound locals F823)
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
]
ignore = [
    "E501", # Line length (handled by line-length=140)
    "E402", # Module level import not at top of file
    "E701", # Multiple statements on one line (colons)
    "E741", # Ambiguous variable name
    "F841", # Unused local variable
]

[lint.per-file-ignores]
"tests/*" = ["F401", "F841", "F811"]
"__init__.py" = ["F401"]
```

### Combined 5-Stage Pre-Commit Hook Pipeline
Update `.git/hooks/pre-commit` to execute the full security & quality pipeline in under 1 second:

```sh
#!/bin/sh
# Git Pre-Commit Hook: Secrets, Bandit Security, Ruff Linter, Mypy Types & Node.js Frontend Guard
set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"

echo "🔒 [1/5] Running Secret & Credential Scanner..."
python3 "${REPO_ROOT}/scripts/secret_scanner.py"

echo "🛡️ [2/5] Running Bandit Python Security Vulnerability Scanner..."
if command -v bandit >/dev/null 2>&1; then
    bandit -r "${REPO_ROOT}/api" "${REPO_ROOT}/layer3_scheduling" "${REPO_ROOT}/models" -s B104,B310,B608 -ll
fi

echo "⚡ [3/5] Running Ruff Linter & Syntax Guard..."
if command -v ruff >/dev/null 2>&1; then
    ruff check "${REPO_ROOT}"
fi

echo "🔍 [4/5] Running Mypy Static Type Checker..."
if command -v mypy >/dev/null 2>&1; then
    (cd "${REPO_ROOT}" && mypy)
fi

echo "🌐 [5/5] Running Frontend JavaScript Syntax Guard (Node.js)..."
if command -v node >/dev/null 2>&1; then
    for js_file in "${REPO_ROOT}"/web/js/*.js "${REPO_ROOT}"/web/js/modules/*.js; do
        if [ -f "$js_file" ]; then
            node --check "$js_file"
        fi
    done
fi
echo "✓ All pre-commit security & quality checks passed!"
```

---

## 6. Mypy Static Type Checking for Mathematical & Dispatch Cores (`mypy.ini`)

### Why Type Checking Matters for HEMS Solvers
In mathematical solvers (like SciPy HiGHS LP or Dynamic Programming backward inductions), Python's dynamic typing hides severe bugs until execution:
- Passing incompatible solver bound shapes (e.g. `tuple[int, None]` instead of `tuple[float, Optional[float]]`).
- `None` dereferencing when calling attributes on objects that might be uninitialized during network latency or fallback (`summary.runs` vs `summary.decision_details`).
- Dict unpack type mismatches in `@dataclass` factory methods (`cls.from_config(**kwargs)`).

### Configuration (`mypy.ini`)
Place `mypy.ini` at the add-on root to target critical mathematical, physical, and canonical models:

```ini
[mypy]
python_version = 3.11
ignore_missing_imports = True
explicit_package_bases = True
check_untyped_defs = True
warn_redundant_casts = True
warn_unused_ignores = True

# Target core physical, mathematical, and data model packages
files = models, layer3_scheduling/battery_policy.py, layer3_scheduling/dhw_specs.py, layer3_scheduling/tariff_provider.py
```

---

## 7. Node.js Client-Side JavaScript Syntax Guard (`node --check`)

### The "Blank Screen" UI Pitfall
In custom Home Assistant add-on web dashboards (`web/js/app.js`, `web/js/modules/*.js`), a single syntax error, unclosed bracket, or trailing comma in older browsers causes the browser's JavaScript engine to halt parsing before executing the application. The result is a completely blank screen (whiteout) without any helpful server error logs.

### Fast Lightweight Verification without Heavy npm Dependencies
Rather than installing heavyweight npm toolchains (webpack, babel, eslint) inside lightweight Alpine/HA add-ons, leverage the built-in Node.js syntax checker (`node --check <file.js>`):
- Runs in under **80 ms** across all project scripts.
- Parses the full ECMAScript AST and catches syntax errors, mismatched brackets, and invalid tokens.
- Fails fast and blocks the commit before broken UI assets reach production.

---

## 8. Bandit AST Security Scanner (`bandit`) & JSON Schema Validation (`jsonschema`)

### Fast In-Tree AST Security Checks
Bandit parses Python source trees into an Abstract Syntax Tree to identify security flaws before code is pushed:
- **Command:** `bandit -r api/ layer3_scheduling/ models/ -s B104,B310,B608 -ll`
- `-s B104,B310,B608`: Skips known container/HAOS constraints (e.g. binding to `0.0.0.0` for Ingress bridge, raw InfluxQL queries, and URL handlers that are guarded by custom helpers).
- `-ll`: Reports Medium and High severity issues only, preventing noise from trivial assert statements in tests.

### Formal JSON Schema Validation for Device Profiles & Configs
In Home Assistant add-ons with extensible hardware libraries (`config/device_library/*.json`), human errors in JSON schemas (e.g. missing required fields, typos in capabilities enums) crash runtime initialization.
- Integrate formal `jsonschema.validate` tests into `tests/unit/test_device_library_profiles.py`.
- Tests run in < 50ms and guarantee that every template conforms strictly to `schema/device_profile.schema.json`.

---

## 9. Security Audit Triage & Remediation for HAOS Add-ons

Automated security scanners (Semgrep, Hadolint, Bandit, Mantis) evaluate add-ons against generic cloud/Linux environments. Distinguish between actual security vulnerabilities and Home Assistant Supervisor architecture requirements:

### 1. The Container Root Scanner Trap (CWE-250) — Do NOT Blindly Change
- **The Finding:** Scanners flag `Dockerfile` lacking a `USER` directive, demanding an unprivileged user (e.g. `USER app`).
- **The HAOS Trap:** Home Assistant OS mounts `/data/options.json` with strict `0600 root:root` permissions and `/config` (`/homeassistant/`) under root ownership. An unprivileged container user crashes on boot with `Permission denied` when reading configuration or saving user settings.
- **Remediation:** Retain container root execution and document the architectural justification in the `Dockerfile`. Container isolation in HAOS is enforced by Supervisor via Docker cgroups and AppArmor profiles.

### 2. Insecure TLS Contexts (CWE-295) — Strict WAN vs. LAN Separation
- **The Finding:** Code uses `ssl._create_unverified_context()` or `verify_mode = ssl.CERT_NONE` to communicate with Home Assistant.
- **The Vulnerability:** If applied globally, external WAN calls (e.g. Open-Meteo weather, dynamic tariff APIs) skip TLS certificate verification, allowing on-path attackers to forge market prices and weather signals.
- **Remediation:**
  - External WAN endpoints MUST strictly use verified TLS: `ssl.create_default_context()`.
  - Local LAN/HA endpoints (`172.30.32.1`, `localhost`, `.local`) can use an internal unverified context if local self-signed certificates are in use.

### 3. URL Scheme Whitelisting for `urllib.request` (CWE-939)
- **The Finding:** Using `urllib.request.urlopen(url)` on dynamic URLs allows unexpected schemes (such as `file://` reading local files).
- **Remediation:** Centralize HTTP requests in a safe helper (`safe_urlopen`) that parses the URL and explicitly enforces `scheme in ("http", "https")`, raising `ValueError` on any other scheme.

### 4. Client-Side JavaScript Prototype Pollution (CWE-915)
- **The Finding:** Recursive dictionary lookups or mergers in client-side JavaScript (`web/js/i18n.js`) traversing keys without property validation.
- **Remediation:** Explicitly check and reject `__proto__`, `constructor`, and `prototype` in traversal loops, and verify property ownership using `Object.prototype.hasOwnProperty.call(val, key)` instead of the `in` operator.

### 5. Scanner Script Self-Scanning Exclusion Trap
- **The Pitfall:** When running recursive regex scans across the repository (e.g. `grep -rE` in a bash `security_audit.sh` or Python regex scanner), searching without excluding the audit script itself flags the pattern definitions themselves (such as `ghp_`, `eyJhbGciOi`, or `password`).
- **Remediation:** Always explicitly exclude the scanning tool or script from its own traversal:
  ```bash
  grep -rnE "(api[_-]?key|secret|password|token)" . --exclude="security_audit.sh" --exclude="secret_scanner.py"
  ```
  In Python, check `if path.name in ("secret_scanner.py", "security_audit.sh"): continue`.


