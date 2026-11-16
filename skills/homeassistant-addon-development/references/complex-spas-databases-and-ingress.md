# Multi-Service Databases, Complex SPAs & Ingress Architecture in Home Assistant Add-ons

Architectural patterns and operational guidelines for deploying complex multi-tier stacks (e.g. Next.js, Langfuse, ClickHouse, PostgreSQL, Redis, SeaweedFS) as Home Assistant OS Add-ons.

---

## 1. Optional Dynamic Port Mapping Pattern (`ports: <port>/tcp: null`)

In Home Assistant add-on manifests (`config.yaml`), exposing a network port directly to the host LAN must be user-configurable and default to disabled (Ingress only):

```yaml
# In config.yaml:
ports:
  3000/tcp: null
ports_description:
  3000/tcp: "Direct LAN Web UI and API ingestion port (optional; leave empty for Ingress-only)"
```

### Operational Rules:
- **Port empty (`null`):** Supervisor does NOT publish any port on the host IP. The container is completely isolated from the host LAN, and traffic routes exclusively through Home Assistant Ingress (sidebar) and the internal Docker network.
- **Port entered (e.g. `3000`):** Supervisor automatically binds the container's port 3000 to the host's LAN IP (`http://<ha-ip>:3000`).
- **Inter-Add-on Communication:** Other add-ons on the shared `hassio` Docker network do NOT need a host port. They reach the container directly using its internal Docker DNS hostname (`http://<hostname>:3000`, e.g. `http://local-langfuse:3000` or `http://<repo-hash>-langfuse:3000`).
- **Never use `host_network: true` unnecessarily:** Exposing ports via `ports:` keeps network namespace isolation intact, whereas `host_network: true` eliminates container network boundaries.

---

## 2. Next.js / SPA Build-Time Base Path vs. Dynamic Ingress Tokens

Modern frontend frameworks (Next.js, Vite, Nuxt) inline asset base paths (`NEXT_PUBLIC_BASE_PATH`) at **build time**. However, Home Assistant Ingress mounts add-ons under dynamic runtime prefixes:
`/api/hassio_ingress/<session_token>/` (which changes upon reinstall or between environments).

Attempting to run an unprefixed build behind Nginx path rewrites causes:
- 404 errors on `_next/static/` chunks and fonts.
- Client-side pushState navigation escaping the iframe and hitting Home Assistant Core root (`/`).

### The Runtime Placeholder Substitution Pattern:
1. **Build Time (CI / GitHub Actions):**
   - Build the Next.js frontend with an explicit unique placeholder:
     ```dockerfile
     ENV NEXT_PUBLIC_BASE_PATH=/__HA_INGRESS_BASEPATH_PLACEHOLDER__
     ```
2. **Runtime Initialization (`s6` oneshot / `init-basepath`):**
   - On container startup, read the dynamic ingress entrypoint:
     ```bash
     INGRESS_ENTRY=$(bashio::addon.ingress_entry)
     ```
   - Copy pristine build assets to an ephemeral container directory (e.g. `/run/web_runtime/`).
   - Run a targeted string replacement across `.js`, `.html`, `.css`, `.json` assets:
     ```bash
     find /run/web_runtime/ -type f \( -name "*.js" -o -name "*.html" -o -name "*.json" -o -name "*.css" \) \
       -exec sed -i "s|/__HA_INGRESS_BASEPATH_PLACEHOLDER__|${INGRESS_ENTRY}|g" {} +
     ```
   - Point the web server at `/run/web_runtime/`. Because this directory is in container RAM/ephemeral storage, it does not bloat `/data` or HA backups.

---

## 3. Dual Nginx Listener Architecture

To support both **HA Ingress** and **Direct LAN / API Ingestion** simultaneously:

```nginx
# 1. Ingress Listener (Port 8099)
server {
    listen 8099;
    # Accept connections from entire internal HA docker bridge subnet & loopback
    allow 172.30.32.0/23;
    allow 127.0.0.1;
    deny all;

    # Cold start timeout protection for DB migrations and Next.js initialization
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    location / {
        # Strip frame-busting headers so HA sidebar iframe renders
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;
        
        # Forward to local application
        proxy_pass http://127.0.0.1:3100;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# 2. LAN / Direct API Listener (Port 3000)
server {
    listen 3000;

    location / {
        # Direct API calls and LAN web access
        proxy_pass http://127.0.0.1:3100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 4. Multi-Service Database Supervision & Cold Backup Invariants

When running stateful multi-tier databases (PostgreSQL, ClickHouse, Redis, SeaweedFS) inside an add-on container:

1. **Explicit Shutdown Timeout (`timeout: 120`):**
   - Home Assistant's default container stop timeout is **10 seconds**, after which Supervisor sends `SIGKILL`.
   - Databases like ClickHouse and PostgreSQL undergoing background mutations or WAL flushes will suffer data corruption if killed ungracefully.
   - Always declare `timeout: 120` in `config.yaml` to guarantee S6-overlay services stop cleanly.
2. **Cold Backup Declarations (`backup: cold`):**
   - Never snapshot live database files during write activity.
   - Set `backup: cold` in `config.yaml`. Supervisor stops the container, creates a tarball of `/data/` (Postgres, ClickHouse, Redis AOF), and restarts the add-on. Backups are guaranteed consistent by construction.
3. **Internal Loopback Binding (`127.0.0.1`):**
   - All internal supporting daemons (Postgres `:5432`, Redis `:6379`, ClickHouse `:8123`, SeaweedFS `:8333`) must bind strictly to `127.0.0.1`.
   - Only the Nginx frontend reverse proxy binds to `0.0.0.0` inside the container, preventing other add-ons on the Docker bridge from accessing raw database sockets.

---

## 5. S6-Overlay v3 Service Graph & Readiness Gates Pattern

When orchestrating multi-container stacks in a single Home Assistant Add-on via S6-overlay v3 (`/etc/s6-overlay/s6-rc.d/`):

1. **The `user/contents.d/` Activation Mandate:**
   - Defining a service directory under `/etc/s6-overlay/s6-rc.d/<service_name>` is NOT sufficient.
   - S6-overlay v3 compiles its runtime database from the bundle `user`. To activate each service, you MUST create an empty marker file:
     ```bash
     touch /etc/s6-overlay/s6-rc.d/user/contents.d/<service_name>
     ```
   - Omission causes S6 to completely ignore the service during boot.
2. **Readiness Gate Oneshots over Blind Sleeps:**
   - Downstream applications (Web UI, API workers) crash-loop if started before databases or blob stores finish initializing.
   - Model initialization as a two-stage pattern:
     - Stage A: The daemon itself runs as a `longrun` service (`type: longrun`, `run` script).
     - Stage B: A corresponding readiness gate runs as a `oneshot` service (`type: oneshot`, `dependencies: <daemon>`, `up` script).
     - The `up` script polls loopback ports (e.g. `pg_isready -h 127.0.0.1 -p 5432`, `curl -sf http://127.0.0.1:8123/ping`, or `curl -sf http://127.0.0.1:8333/`) with a bounded timeout (30s) and performs idempotency checks (creating default users, databases, or S3 buckets) before exiting 0.
   - Applications declare dependencies on the *readiness oneshot*, never directly on the raw daemon.
3. **SeaweedFS as the Standard S3 Blob Store (Identities & Volume Batch Allocation):**
   - Avoid legacy/archived MinIO Community Edition binaries. Use SeaweedFS as a lightweight Go binary providing S3 API compatibility and native TTL bucket support.
   - **S3 Identities & Permissions (`s3.json`):** SeaweedFS S3 rejects arbitrary AWS Signature v4 credentials with `InvalidAccessKeyId / 403 Access Denied` unless declared in an identity file. During container startup (`init-secrets`), generate `/etc/seaweedfs/s3.json` with the client's `accessKey` and `secretKey`, granting `"actions": ["Read", "Write", "List", "Tagging", "Admin"]`. Pass `-s3.config=/etc/seaweedfs/s3.json` to `weed server`.
   - **Volume Allocation Batch Ceiling Trap (`-volume.max`):** SeaweedFS master grows collection volumes in default batches of 7. Setting `-volume.max=5` (or any value $< 7$) causes the master to fail collection growth with `create 7 volume, created 0: Not enough data nodes found!` and `No writable volumes and no free volumes left`. Always set `-volume.max=30` (or higher):
     ```bash
     exec weed server -dir=/data/seaweedfs -s3 -filer -s3.port=8333 -s3.config=/etc/seaweedfs/s3.json -volume.max=30 -ip=127.0.0.1
     ```
4. **First-Run Secret Generation & Ephemeral Container Environment:**
   - Generate high-entropy cryptographic keys (`NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`, database passwords) on first boot into `/data/secrets.env` with `chmod 600`.
   - Source secrets into an ephemeral `/run/app.env` consumed by application processes.
   - If other add-ons (like Hermes) need credentials, provide an opt-in config flag (`export_hermes_env: true`) that writes credentials to `/share/<addon>/client.env`, avoiding manual credential copying.

---

## 6. Dockerfile & Scaffolding Multi-Stage Pitfalls

1. **Top-Level `ARG BUILD_FROM` Placement in Multi-Stage Builds:**
   - *Pitfall:* In multi-stage Dockerfiles extracting assets from upstream images (`FROM upstream:tag AS extractor`), placing `ARG BUILD_FROM=...` after the first `FROM` or right above `FROM ${BUILD_FROM}` causes Dockerfile linters and parsers to reject the line with `base name (${BUILD_FROM}) should not be blank [51]`.
   - *Rule:* Always define `ARG BUILD_FROM=...` at the very first line of the Dockerfile (before any `FROM` statement). Scoped ARGs must precede the entire multi-stage build tree.
2. **Grep Negative Pattern Flag Collision in Security Audit Scripts:**
   - *Pitfall:* Running `grep -rE "${pattern}" ...` when the search pattern begins with a dash or hyphen (e.g. `-----BEGIN (RSA|OPENSSH|EC|PGP) PRIVATE KEY`) causes `grep` to interpret the pattern as an unrecognized command-line flag (`grep: unrecognized option '-----BEGIN ...'`), failing the audit.
   - *Rule:* Always pass the double-dash `--` argument separator before the search pattern: `grep -rE --exclude-dir=".git" -- "${pattern}" "${REPO_ROOT}"`.
3. **Flaky External Apt Repositories & The Multi-Stage Binary Extraction Pattern:**
   - *Pitfall:* Adding external third-party apt repositories inside `Dockerfile` (e.g. `curl -fsSL https://packages.clickhouse.com/keys/clickhouse.key | gpg --dearmor...`) frequently breaks in CI with `curl: (22) The requested URL returned error: 403` or repository network timeouts due to CDN bot mitigation or changing signing keys.
   - *Rule:* For complex multi-arch binaries (ClickHouse, SeaweedFS, Vector), pull directly from their official multi-arch Docker image in a multi-stage build stage (`FROM clickhouse/clickhouse-server:26.3 AS clickhouse-source`, `COPY --from=clickhouse-source /usr/bin/clickhouse /usr/bin/clickhouse`). This guarantees reproducible, network-resilient CI builds on both `amd64` and `aarch64` without apt repository dependencies.

---

## 7. Home Assistant Assist & Voice LLM Tracing Architecture

To route Home Assistant's native voice assistant (HA Assist, ESP32 voice satellites, dashboard chat) into the local observability stack:

1. **OpenAI-Compatible Ingestion Endpoint:**
   - Expose the OpenAI API-compatible drop-in route via Nginx (e.g. `http://local-langfuse:3000/api/public/openai/v1` or an intermediate LiteLLM proxy).
2. **Extended OpenAI Conversation Integration:**
   - Configure HA's **Extended OpenAI Conversation** (or core **OpenAI Conversation**) integration to point its `base_url` to the internal add-on hostname: `http://local-langfuse:3000/api/public/openai/v1`.
   - Provide the project Secret Key (`sk-lf-...`) generated by the add-on.
3. **Trace Invariants:**
   - Traces capture user voice transcripts, system prompts, injected HA entity states, tool calls (`light.turn_on`, `climate.set_temperature`), token usage, and latency in one unified dashboard alongside autonomous agent runs.

---

## 8. S6-Overlay v3 Secret-Passing & Race Condition Prevention

In S6-overlay v3, longrun and oneshot services without explicit dependencies launch **concurrently** at container startup.

### Operational Rules:
- **Mandatory `init-secrets` Dependency:** Any daemon or initialization oneshot that reads credentials from `/data/secrets.env` (e.g. Redis reading `${REDIS_PASSWORD}`, PostgreSQL cluster init, ClickHouse grant scripts, S3 bucket provisioning, retention schedulers) MUST declare `init-secrets` in its `dependencies` file:
  ```
  # in /etc/s6-overlay/s6-rc.d/<service>/dependencies:
  init-secrets
  ```
  *Failure Mechanism:* If omitted, S6 starts the daemon while `init_secrets.sh` is still generating keys, causing scripts to fail with `./run: line 2: /data/secrets.env: No such file or directory`.
- **Directory Permissions for Dropped-Privilege Daemons:** When generating persistent folders under `/data` (e.g. `/data/postgres`), remember `/data` is created as `root:root`. Daemons dropping privileges (e.g. `su-exec postgres postgres -D /data/postgres`) will fail with `Permission denied` on config files unless `init_dirs.sh` explicitly executes `chown -R postgres:postgres /data/postgres` before starting the database.

---

## 9. C-Runtime Parity in Multi-Stage Upstream Container Extractions (musl vs glibc)

When building an add-on container by extracting pre-built Node.js, Go, or Rust runtimes from official upstream Docker images (`COPY --from=upstream-source /app ...`):

- **The NAPI `.node` & Prisma Architecture Mismatch Trap:**
  - *Symptom:* Node.js / Rust applications crash on startup with `Cannot find native binding`, `Cannot find module '@.../native-linux-x64-musl'`, or Prisma `Prisma Client could not locate the Query Engine for runtime "linux-musl-openssl-3.0.x"`.
  - *Mechanism:* Official Docker images for modern applications (such as Langfuse Web & Worker v4 based on RHEL/glibc) bundle pre-compiled native Rust/NAPI modules linked against **GNU glibc** (e.g. `langfuse-native.linux-x64-gnu.node`) and Prisma engines built for OpenSSL 3 (`libquery_engine-rhel-openssl-3.0.x.so.node`). If the add-on's `Dockerfile` uses an Alpine base (`ghcr.io/home-assistant/{arch}-base:3.21`), Node.js demands musl `.node` binaries that do not exist.
  - *The S6-Supervise CPU Burn Trap:* Because `s6-supervise` has no restart backoff, a process crashing on native module load is respawned hundreds of times per minute in an unthrottled infinite loop. This rapidly drives container PIDs to >400,000 and burns 10–15% constant host CPU while logging repeated startup crashes.
  - *Rule:* Always match C-runtime parity between the add-on base image and upstream binaries:
    1. **For glibc/RHEL/Debian upstream assets (e.g. Langfuse v4):** Use Home Assistant's Debian base image `ghcr.io/home-assistant/{arch}-base-debian:trixie` (Debian 13 Trixie, glibc 2.41, OpenSSL 3.0, with S6-overlay v3 built-in). Both `@langfuse/native` (`*.linux-x64-gnu.node`) and Prisma OpenSSL 3.0 query engines load out-of-the-box natively. Install dependencies via `apt-get` (`nodejs`, `postgresql`, `redis-server`, `nginx`, `curl`, `jq`, `openssl`).
       - *PostgreSQL Version Pinning on Persistent `/data`:* Debian Trixie repos default to PostgreSQL 17. If an existing persistent volume in `/data/postgres` was initialized on PostgreSQL 16, PostgreSQL 17 aborts startup with `FATAL: database files are incompatible`. Add the official PGDG repository (`http://apt.postgresql.org/pub/repos/apt/ trixie-pgdg main`) to install `postgresql-16` and `postgresql-contrib-16`, guaranteeing binary compatibility without forced re-initialization.
       - *Prisma Query Engine Path Resolution:* To prevent platform string detection mismatches (`debian-openssl-3.0.x` vs `rhel-openssl-3.0.x`), export `PRISMA_QUERY_ENGINE_LIBRARY` pointing directly to the vendor engine file in `/run/<addon>.env` and symlink `libquery_engine-rhel-openssl-3.0.x.so.node` to `libquery_engine-debian-openssl-3.0.x.so.node`.
       - *S6 Restart Throttling:* In background worker `run` scripts, add a safety sleep on unexpected exit to prevent S6-supervise from tight-looping if an unexpected runtime failure occurs.
    2. **For musl/Alpine upstream assets:** Use Home Assistant's native Alpine base (`ghcr.io/home-assistant/{arch}-base:3.21`) strictly when upstream binaries are compiled against musl libc.
- **ClickHouse & SeaweedFS:**
  - ClickHouse's official binary (`/usr/bin/clickhouse`) runs under glibc without donor libraries when hosted on Debian Trixie.
  - SeaweedFS is a statically linked Go binary that runs natively on both Alpine and Debian.

---

## 10. Database Initialization & Scripting Pitfalls

1. **PostgreSQL Database Creation in Bash Entrypoints:**
   - *Pitfall:* Passing `SELECT 'CREATE DATABASE ...' WHERE NOT EXISTS ... \gexec` inside `psql -c "..."` fails with `ERROR: syntax error at or near "\"` because `\gexec` is an interactive psql metacommando not parsed in non-interactive `-c` execution.
   - *Solution:* Use standard shell test with `createdb`:
     ```bash
     if ! su-exec postgres psql -h 127.0.0.1 -p 5432 -tAc "SELECT 1 FROM pg_database WHERE datname = 'langfuse'" | grep -q 1; then
       su-exec postgres createdb -h 127.0.0.1 -p 5432 -O langfuse langfuse
     fi
     ```
2. **ClickHouse HTTP Multi-Query Execution (`?multiquery=1`):**
   - *Pitfall:* POSTing multiple SQL statements (e.g. `CREATE USER ...; GRANT ...; GRANT ...;`) to ClickHouse's HTTP port (`http://127.0.0.1:8123/`) executes only the first query and rejects the rest with `Multi-statements are not allowed`.
   - *Solution:* Append `?multiquery=1` to the URL: `curl -sS "http://127.0.0.1:8123/?multiquery=1" -d "..."`.
3. **SeaweedFS S3 Gateway Filer Prerequisite:**
   - *Pitfall:* Running `weed server -s3` without `-filer` aborts with command usage output.
   - *Rule:* SeaweedFS S3 is a gateway layered on the Filer metadata store. Always pass `-filer`:
     ```bash
     exec weed server -dir=/data/seaweedfs -s3 -filer -s3.port=8333 -volume.max=5 -ip=127.0.0.1
     ```

---

## 11. Supervisor API Permissions & Basepath Fallbacks

1. **Manifest API Grants (`hassio_api: true`):**
   - When an add-on script invokes `bashio::addon.ingress_entry` or Supervisor endpoints, the manifest (`config.yaml`) must declare:
     ```yaml
     hassio_api: true
     hassio_role: default
     ```
   - Without `hassio_api: true`, `bashio::addon.ingress_entry` exits with `[ERROR] Unable to access the API, forbidden` (exit code 1).
2. **Defensive Ingress Entry Fallbacks:**
   - Never allow a failed Supervisor API call to abort container startup with `set -e`. Wrap extraction with a fallback:
     ```bash
     INGRESS_ENTRY=""
     if [ -f "/usr/lib/bashio/bashio.sh" ]; then
       source "/usr/lib/bashio/bashio.sh"
       INGRESS_ENTRY="$(bashio::addon.ingress_entry 2>/dev/null || true)"
     fi
     if [ -z "${INGRESS_ENTRY}" ]; then
       INGRESS_ENTRY="/api/hassio_ingress/local_${ADDON_SLUG}"
     fi
     ```

---

## 12. GitHub Actions Builder vs GHCR Image Naming

When publishing multi-arch images via `home-assistant/builder`:
- *Pitfall:* Passing `--docker-hub "ghcr.io/<owner>"` AND `--image "ghcr.io/<owner>/{arch}-addon-<slug>"` causes the builder to concatenate both arguments, pushing to `ghcr.io/<owner>/ghcr.io/<owner>/{arch}-addon-<slug>`.
- *Symptom:* Supervisor attempting to pull `ghcr.io/<owner>/amd64-addon-<slug>:tag` receives `[500] error from registry: denied` / HTTP 401 because the image does not exist at that registry path.
- *Rule:* When `--docker-hub` is set, `--image` must be strictly `{arch}-addon-<slug>`:
  ```yaml
  with:
    args: |
      --target <slug> \
      --image "{arch}-addon-<slug>" \
      --docker-hub "ghcr.io/${{ github.repository_owner }}" \
      --amd64 \
      --aarch64
  ```

---

## 13. Port Collisions in Multi-Process Containers (`listen EADDRINUSE`)

In multi-process add-on containers (e.g. Langfuse Web + Async Worker), both services frequently read a shared environment file (e.g. `/run/langfuse.env`) containing `PORT=3100`:
- *Symptom:* Web server crashes immediately with `Error: listen EADDRINUSE: address already in use 127.0.0.1:3100`, causing Nginx on port 8099 to return **504 Gateway Timeout** when accessed via Home Assistant Ingress.
- *Mechanism:* Background workers (like Langfuse Worker) often run their own internal HTTP health/metrics server using the `$PORT` environment variable. When Worker launches before or alongside Web, it binds to 3100 first, blocking Web from starting.
- *Rule:* In the Worker's S6 `run` script, explicitly override `$PORT` after sourcing the environment: `export PORT=3101`. Reserve `PORT=3100` strictly for the public Web server.

---

## 14. Upstream Next.js Server Entrypoint Paths (`./web/server.js`)

- *Symptom:* Web server crashes with `Error: Cannot find module '/opt/.../server.js'` (MODULE_NOT_FOUND).
- *Mechanism:* In monorepo builds (Turbo, pnpm, Nx), the production output bundle is nested inside the workspace package directory (e.g. `./web/server.js` or `apps/web/server.js`), not in the monorepo root.
- *Rule:* Inspect the upstream Dockerfile's `CMD` or `entrypoint.sh` for the exact relative path: invoke `exec ./web/entrypoint.sh node ./web/server.js`.

---

## 15. Missing Migration CLI Binaries in Container Extractions

- *Symptom:* Container entrypoint script fails during startup migrations with `/opt/.../entrypoint.sh: 108: prisma: not found` or `Error: golang-migrate is not installed or not in PATH`.
- *Mechanism:* Extracting only the application folder (`COPY --from=... /app /opt/...`) misses global migration CLI binaries installed into `/usr/local/bin` during the upstream multi-stage build.
- *Rule:* In the `Dockerfile`, install or copy the migration CLIs globally into `$PATH`:
  ```dockerfile
  RUN npm install -g prisma@<version>
  COPY --from=web-source /usr/local/bin /usr/local/bin
  ```
  And install the `golang-migrate` CLI if ClickHouse migrations are managed separately.

---

## 16. ClickHouse Multi-Stage Alpine Binary Donor Libraries

- *Symptom:* Copying `/usr/bin/clickhouse` from `clickhouse-server:*-alpine` into a standard Alpine container crashes with `Error relocating /usr/bin/clickhouse: __pthread_mutex_unlock: symbol not found`.
- *Mechanism:* ClickHouse's Alpine image uses a multi-stage `glibc-donor` build that copies glibc libraries (`libc.so.6`, `libpthread.so.0`, `ld-2.35.so`) into `/lib` and `/lib64`. Copying only `/usr/bin/clickhouse` leaves out the required glibc donor libraries.
- *Rule:* Copy the donor libraries alongside the binary:
  ```dockerfile
  COPY --from=clickhouse-source /lib/libc.so.6 /lib/libpthread.so.0 /lib/libdl.so.2 /lib/libm.so.6 /lib/librt.so.1 /lib/libresolv.so.2 /lib/
  COPY --from=clickhouse-source /lib/ld-*.so /lib/
  COPY --from=clickhouse-source /lib64 /lib64
  ```

---

## 17. PostgreSQL Socket Lockfile Directory in Alpine (`/run/postgresql`)

- *Symptom:* PostgreSQL crashes on startup with `FATAL: could not create lock file "/run/postgresql/.s.PGSQL.5432.lock": No such file or directory`.
- *Mechanism:* On Alpine Linux, PostgreSQL defaults its UNIX domain socket directory to `/run/postgresql/`. Since `/run` is tmpfs/ephemeral in containers, `/run/postgresql` does not exist on boot.
- *Rule:* In `init_dirs.sh`, always create and chown the socket directory: `mkdir -p /run/postgresql && chown -R postgres:postgres /run/postgresql`.
- *Version Migration Invariant:* If migrating between PostgreSQL major versions (e.g. 15 on Debian vs 16 on Alpine), check `/data/postgres/PG_VERSION`. If incompatible, re-initialize or warn before starting `postgres`.

---

## 18. Next.js Ingress "Loading..." Freeze & Client-Side Chunk Hydration

- *Symptom:* Opening the add-on via Home Assistant Ingress (sidebar or "Open Web UI") shows a dark screen with a broken image icon and stays permanently stuck on `Loading ...`.
- *Mechanism:* Pre-built Next.js production builds baked with default root path (`basePath: ""`) emit HTML containing absolute asset paths (`src="/_next/static/..."`, `href="/icon.png"`) and an embedded `<script id="__NEXT_DATA__">{"basePath":""...}`. When viewed inside Home Assistant Ingress at `https://<ha-url>/api/hassio_ingress/<token>/`:
  1. The browser resolves `/_next/...` relative to the root domain (`https://<ha-url>/_next/...`), completely bypassing the Ingress session token. Home Assistant Core returns 404 Not Found for all script chunks.
  2. Because the JavaScript bundles fail to load, Next.js client-side React hydration never executes, leaving the initial static fallback markup (`Loading ...`) on screen forever.
- *Rule:* The add-on's internal Nginx reverse proxy on the Ingress port (8099) must dynamically rewrite asset paths and hydrate `__NEXT_DATA__` using `$http_x_ingress_path`:
  ```nginx
  # Clear compression so sub_filter can rewrite HTML and JS responses
  proxy_set_header Accept-Encoding "";

  sub_filter_once off;
  sub_filter_types *;
  # Hydrate Next.js router with the dynamic Ingress prefix
  sub_filter '"basePath":""' '"basePath":"$http_x_ingress_path"';
  # Prefix static chunks and icons
  sub_filter '"/_next/' '"$http_x_ingress_path/_next/';
  sub_filter "'/_next/" "'$http_x_ingress_path/_next/";
  sub_filter 'src="/_next/' 'src="$http_x_ingress_path/_next/';
  sub_filter 'href="/_next/' 'href="$http_x_ingress_path/_next/';
  sub_filter 'src="/' 'src="$http_x_ingress_path/';
  sub_filter 'href="/' 'href="$http_x_ingress_path/';
  sub_filter '<head>' '<head><base href="$http_x_ingress_path/">';
  ```

---

## 19. HTTPS Termination vs Add-on Ingress Certificate Mapping

- *Question:* When Home Assistant Core runs over HTTPS (`https://<ha-domain>:8123` via Let's Encrypt or Nginx Proxy Manager), does an Ingress add-on need SSL certificates mapped (`map: ["ssl:rw"]`)?
- *Rule:* **For Ingress (Port 8099): No.** Home Assistant Core handles TLS termination at the public domain boundary. Supervisor routes Ingress requests internally across the private Docker bridge network (`172.30.32.0/23`) as standard HTTP to the add-on's internal `ingress_port` (8099), while injecting `X-Forwarded-Proto: https` and `X-Forwarded-Host: <ha-domain>`.
- *Action for Ingress:* The add-on only needs to forward `X-Forwarded-Proto $scheme` and `X-Forwarded-Host $http_host` to upstream application daemons so session cookies (e.g. NextAuth `__Secure-next-auth.session-token`) are configured with appropriate HTTPS security attributes.
- *Action for Optional LAN Ports (Port 3000):* When exposing a direct port on an HTTPS-only setup, browsers accessing `https://<ha-domain>:<port>` will hit SSL handshake errors if Nginx speaks plain HTTP. Map `map: ["ssl:ro"]` in `config.yaml`. In `init_config.sh`, check if `/ssl/fullchain.pem` and `/ssl/privkey.pem` exist. If present, generate an Nginx snippet:
  ```nginx
  listen 3000 ssl;
  ssl_certificate /ssl/fullchain.pem;
  ssl_certificate_key /ssl/privkey.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers HIGH:!aNULL:!MD5;
  error_page 497 https://$host:3000$request_uri;
  ```
  And include it in Nginx (`include /run/nginx_port_3000.conf;`). If absent, fall back to `listen 3000;`.

---

## 20. Declarative ClickHouse User Configuration (`users.d/*.xml`)

- *Symptom:* Background workers crash on boot with `ClickHouse query failed with non-retryable error: langfuse: Authentication failed: password is incorrect, or there is no user with such name`.
- *Mechanism:* Attempting to create ClickHouse users and grant permissions imperatively via `curl` to `:8123` in an S6 startup oneshot is prone to race conditions if ClickHouse restarts or is under heavy schema migration load.
- *Rule:* Generate user configurations declaratively in `/etc/clickhouse-server/users.d/<user>.xml` during `init-secrets` before ClickHouse boots:
  ```xml
  <clickhouse>
      <users>
          <langfuse>
              <password>${CLICKHOUSE_PASSWORD}</password>
              <networks><ip>::/0</ip></networks>
              <profile>default</profile>
              <quota>default</quota>
              <access_management>1</access_management>
              <named_collection_control>1</named_collection_control>
              <show_named_collections>1</show_named_collections>
              <show_named_collections_secrets>1</show_named_collections_secrets>
          </langfuse>
      </users>
  </clickhouse>
  ```
  ClickHouse loads all XML definitions in `users.d/` atomically at startup without external HTTP API dependencies.

---

## 21. Eliminating Startup Supervisor API Calls for Ingress Paths

- *Symptom:* Supervisor logs report `ERROR (MainThread) [supervisor.api.middleware.security] Invalid token for access /addons/self/info`.
- *Mechanism:* Invoking `bashio::addon.ingress_entry` inside container startup scripts queries the Supervisor REST API endpoint `http://supervisor/addons/self/info`. When an add-on restarts quickly, Supervisor's ephemeral session token for the container is either stale or rejected if `hassio_api: true` permissions are restricted.
- *Rule:* Never make synchronous Supervisor API calls during container boot to discover the Ingress prefix. Home Assistant Supervisor injects the active ingress path into the `X-Ingress-Path` header on **every single incoming HTTP request**. In Nginx on port 8099, read `$http_x_ingress_path` directly to dynamically substitute base paths in HTML and JavaScript responses. Container boot remains 100% autonomous, decoupled from Supervisor API latency or token validity.

---

## 22. Store Version Bumping for Ingress Asset Busting (`ha apps update` vs `rebuild`)

- *Symptom:* After modifying Nginx or frontend code and executing `ha apps rebuild`, the user re-opens Ingress in Home Assistant but continues to see the old version number in the UI and remains stuck on stale cached assets.
- *Mechanism:* Home Assistant Supervisor and client browsers aggressively cache Ingress HTML and chunk tokens. If the `version:` in `config.yaml` is unchanged, Supervisor does not register a new app release, and browsers retain cached iframe DOM state. When a new version is committed to the local store repository, running `ha apps rebuild` will be blocked by Supervisor with:
  `Error: Local and store versions of app <slug> differ, use Update instead of Rebuild`.
- *Rule:* Whenever delivering a container fix, always increment the version string in `config.yaml` (e.g. `4.0.0-1` -> `4.0.0-2`), reload the store (`ha store reload`), and invoke `ha apps update local_<slug>` instead of `rebuild`. This immediately updates the version badge in the Home Assistant UI, invalidates stale Ingress session tokens, and forces the browser to fetch fresh assets.

---

## 23. NextAuth Dynamic Host Trust (`AUTH_TRUST_HOST`) & Fetch Interception in Ingress

- *Symptom:* Ingress web UI renders the header, a broken image placeholder, and stays permanently stuck on `Loading ...`.
- *Mechanism:* Next.js applications using NextAuth for authentication initialize a client-side `SessionProvider` that calls `getSession()`. When `NEXTAUTH_URL` is hardcoded to the external domain (e.g. `https://hass.domain.nl:8123`), the compiled client bundle makes absolute fetches directly to `https://hass.domain.nl:8123/api/auth/session`, completely bypassing the `/api/hassio_ingress/<token>` prefix and returning 404 from Home Assistant Core. Furthermore, if the request protocol appears as plain `http`, NextAuth rejects session cookie creation.
- *Rule:*
  1. In the container environment (`/run/langfuse.env`), configure `AUTH_TRUST_HOST=true` and internal loopback `NEXTAUTH_URL=http://127.0.0.1:3100` (or `NEXTAUTH_URL_INTERNAL=http://127.0.0.1:3100`). NextAuth dynamically trusts the incoming proxy headers and emits relative API paths instead of forcing external domain URLs.
  2. In the client-side JavaScript interceptor, parse every fetch with `new URL(input, window.location.href)`. If `u.origin === window.location.origin` and `u.pathname` starts with `/` without the Ingress prefix, rewrite it to `$http_x_ingress_path + u.pathname + u.search + u.hash`.

---

## 24. WHATWG `<base href>` Root-Relative Bypass & Client-Side Fetch Interception

- *Symptom:* Static assets (SVGs, icons like `<img src="/icon.svg">`) and client fetches (`fetch("/api/...")`) bypass `<base href="$http_x_ingress_path/">` and load from the root domain (`https://<domain>/icon.svg`), displaying broken images and failing API calls.
- *Mechanism:* The WHATWG HTML URL standard specifies that URLs starting with a leading slash (`/`) are **root-relative** and resolve directly against the origin host (`https://<domain>`), explicitly ignoring `<base href>`. Only purely relative paths without a leading slash respect `<base href>`.
- *Rule:* In Ingress Nginx configurations serving pre-compiled SPAs:
  1. **Rewrite HTML Tags in Nginx:** Apply `sub_filter 'src="/' 'src="$http_x_ingress_path/';` and `sub_filter 'href="/' 'href="$http_x_ingress_path/';` across HTML responses. Because Nginx replaces strings in a single streaming pass, existing Ingress paths are not matched twice.
  2. **Inject Head Interceptor:** Inject an inline `<script>` into `<head>` wrapping `window.fetch`, `XMLHttpRequest.prototype.open`, `history.pushState`, and `history.replaceState` before any framework bundles execute.

---

## 25. Supervisor "App Already Running" Lock during UI Rebuild & Mobile WebView Cache

- *Symptom:* Clicking "Rebuild" in the Home Assistant Add-on UI fails with a red notification stating *"An error occurred, check supervisor logs"*; Supervisor logs show `WARNING (MainThread) [supervisor.apps.app] local_<slug> is already running!`. On mobile devices, the Ingress view remains stuck on `Loading ...` even after the server is confirmed running.
- *Mechanism:* Home Assistant Supervisor locks the "Rebuild" action in the web UI while the target container is in `state: started`. On mobile devices (Home Assistant Companion App for Android and iOS), the internal WebView caches iframe DOM state and local session storage aggressively across app switches.
- *Rule:*
  1. To rebuild an active container from the host CLI without stopping it manually first, bump the version in `config.yaml` and execute `ha store reload && ha apps update local_<slug>` (which performs an atomic blue/green re-build and container swap).
  2. When verifying Ingress fixes on mobile devices, instruct the user to refresh the WebView cache explicitly (*Settings ➔ Companion app ➔ Debugging ➔ Clear cache / Refresh Webview*) or test in an incognito desktop browser tab.

---

## 26. Native Home Assistant KPI Sensor Publishing (`homeassistant_api: true` & REST API)

When an add-on collects or computes background metrics (such as LLM tokens, costs, or system health), it can publish native sensors directly into Home Assistant without requiring manual user YAML configuration in `configuration.yaml`.

### Manifest Requirement:
- In `config.yaml`, declare `homeassistant_api: true`.
- Home Assistant Supervisor automatically injects the `SUPERVISOR_TOKEN` environment variable into the container.

### Publishing Protocol:
- Post states and attributes to `http://supervisor/core/api/states/<entity_id>`:
  ```json
  POST /core/api/states/sensor.langfuse_tokens_today
  Authorization: Bearer <SUPERVISOR_TOKEN>
  Content-Type: application/json

  {
    "state": "1250",
    "attributes": {
      "friendly_name": "Langfuse Tokens Today",
      "icon": "mdi:counter",
      "unit_of_measurement": "tokens",
      "state_class": "total",
      "input_tokens": 1000,
      "output_tokens": 250
    }
  }
  ```

### Background Execution & Runtime Parity:
- **Container Language Parity:** Write the reporter script in the container's native runtime. If the container runs on Alpine Node.js without Python, write `reporter.js` using Node's standard `http` module. Invoking `exec python3 ...` in an Alpine container lacking Python fails silently or crash-loops with `exec: python3: not found`.
- **S6-Overlay v3 Service Attachment:** To ensure the reporter runs reliably across reboots without failing S6-rc compilation, attach background daemon tasks into the `dependencies` of top-level services (like `nginx/dependencies`) or spawn them from an existing longrun service script.
- **Fail-Open Loop:** Wrap API queries and sensor posts in defensive `try/catch` blocks with retry backoff so temporary database restarts or migrations do not crash the reporter.

---

## 27. Persistent Storage Invariant for Add-on Databases (`/data` vs `/var/lib`)

- *Symptom:* After updating or rebuilding an add-on container, analytical databases (e.g. ClickHouse, Redis) lose all historical data, traces, and metrics, appearing completely empty.
- *Mechanism:* In Home Assistant OS Add-on architecture, **only `/data` is backed by a persistent Docker host volume**. Files written anywhere else in the container filesystem (such as default `/var/lib/clickhouse`, `/var/lib/redis`, `/var/lib/postgresql`) reside in the ephemeral container overlay and are permanently discarded when the container is recreated during an update or rebuild.
- *Rule:* Never rely on default database storage paths:
  1. **ClickHouse:** Drop `/etc/clickhouse-server/config.d/storage.xml` mapping `<path>/data/clickhouse/</path>`, `<tmp_path>/data/clickhouse/tmp/</tmp_path>`, `<user_files_path>/data/clickhouse/user_files/</user_files_path>`.
  2. **PostgreSQL:** Initialize and run clusters strictly with `-D /data/postgres`.
  3. **Redis:** Launch daemon with `--dir /data/redis --appendonly yes`.
  4. **SeaweedFS:** Launch with `-dir=/data/seaweedfs`.
  5. In `init_dirs.sh`, guarantee proper permissions (`chmod 700 /data/postgres /data/secrets`, `chmod -R 777 /data/clickhouse /data/redis /data/seaweedfs`).

---

## 28. Manifest `ingress_panel: true` Mandate & The Supervisor 401 Session Validation Trap

- *Symptom:* Clicking the add-on's sidebar item in Home Assistant renders a broken iframe with 401 errors on all sub-resources; Home Assistant Core logs show:
  `ERROR (MainThread) [homeassistant.components.hassio.handler] Client error on /ingress/validate_session request 401, message='Attempt to decode JSON with unexpected mimetype: text/plain; charset=utf-8', url='http://172.30.32.2/ingress/validate_session'`
  `ERROR (MainThread) [homeassistant.components.hassio] Failed to call /ingress/validate_session`.
- *Mechanism:* Simply specifying `panel_title: "My Add-on"` or `panel_icon: ...` in `config.yaml` does NOT register an Ingress sidebar panel. Without `ingress_panel: true`, Supervisor records `ingress_panel: false` in app metadata. When the user navigates to the custom panel, Home Assistant Core queries Supervisor's `/ingress/validate_session` to authenticate the user session. Supervisor rejects the call with 401 Unauthorized because the panel is not declared as an Ingress panel, causing Core to block all subsequent asset proxying.
- *Rule:* Always declare `ingress_panel: true` in `config.yaml` alongside `ingress: true` and `ingress_port: <port>`.

---

## 29. Double-Proxy HTTPS Protocol Translation (`X-Forwarded-Proto https`) & Mixed Content Elimination

- *Symptom:* Ingress web interface gets stuck on loading; browser console reports `Mixed Content: The page at 'https://<domain>:8123/...' was loaded over HTTPS, but requested an insecure resource 'http://...'. This request has been blocked; the content must be served over HTTPS.`
- *Mechanism:* Home Assistant terminates SSL at the public gateway (`https://<domain>:8123`) and proxies internally over unencrypted HTTP to the add-on container's Ingress port (`:8099`). If Nginx uses `proxy_set_header X-Forwarded-Proto $scheme;`, `$scheme` resolves to `http` because the container-level socket is plain HTTP. The upstream web server and auth libraries believe the connection is insecure, refuse to issue `Secure` session cookies, and generate `http://` asset and redirect links that browsers block as Mixed Content.
- *Rule:* In the Ingress Nginx listener:
  1. Hardcode or preserve client HTTPS: `proxy_set_header X-Forwarded-Proto https;`.
  2. Forward proxy prefixes: `proxy_set_header X-Forwarded-Host $http_x_forwarded_host;` and `proxy_set_header X-Forwarded-Prefix $http_x_ingress_path;`.
  3. Inject CSP upgrade header into `<head>`: `<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">` to automatically upgrade any remaining plain HTTP calls.
  4. Rewrite HTTP redirects: `proxy_redirect ~^https?://[^/]+(.*)$ $http_x_ingress_path$1;` and `proxy_redirect / $http_x_ingress_path/;`.

---

## 30. Lightweight Add-on Ingress GUIs & Auth Bypass Pattern (`X-Ingress-Path`)

When an add-on serves both headless machine clients (such as Hermes Agent or external automations requiring Bearer token authentication) and an interactive web playground for human operators behind Home Assistant Ingress:

### Manifest Requirements:
```yaml
ingress: true
ingress_port: 8000
ingress_panel: true
panel_icon: "mdi:router-network"
panel_title: "My Add-on"
```

### 1. Ingress Auth Bypass Protocol (`X-Ingress-Path`):
- Home Assistant Core terminates user authentication before proxying traffic to the add-on's `ingress_port`.
- Supervisor automatically attaches the `X-Ingress-Path` header (`/api/hassio_ingress/<token>`) to every request entering via Ingress.
- In the backend middleware or authentication dependency, inspect `X-Ingress-Path`. If present, allow the request unconditionally without demanding an `Authorization: Bearer <token>` header:
  ```python
  def verify_api_key(request: Request, authorization: str | None = Header(None)):
      # Home Assistant Ingress passes authenticated requests with X-Ingress-Path
      if request.headers.get("X-Ingress-Path"):
          return True
      # Direct LAN / headless callers must supply valid Bearer token
      expected_key = os.environ.get("API_KEY")
      if not expected_key:
          return True
      if authorization != f"Bearer {expected_key}":
          raise HTTPException(status_code=401, detail="Unauthorized")
      return True
  ```
- This completely eliminates friction for operators testing prompts or viewing dashboards directly in Home Assistant, while maintaining zero-trust token enforcement for external bridge network calls.

### 2. Strictly Relative Frontend URLs:
- The browser accesses the UI at `https://<ha-url>/api/hassio_ingress/<token>/`.
- **Never use root-relative paths** (`fetch('/v1/route')` or `<script src="/app.js">`). Root-relative URLs resolve directly against the root domain (`https://<ha-url>/v1/route`), skipping the Ingress proxy token and returning 404 from Home Assistant Core.
- **Always use directory-relative paths** (`fetch('./v1/route')` or `fetch('v1/route')`). This ensures the browser resolves endpoints within the active Ingress session token prefix.

### 3. Offline-First Vanilla WebUI (Zero External CDN Dependencies):
- Embedded Add-on UIs must be completely self-contained. Home Assistant installations frequently run offline or in segmented IoT VLANs without external internet access.
- Avoid external CDNs for stylesheets, fonts, or frameworks (`cdnjs.cloudflare.com`, `cdn.jsdelivr.net`, Google Fonts). Embed clean HTML5, vanilla CSS3 (matching Home Assistant dark mode styling), and vanilla JavaScript directly in the server response or bundle them locally inside the container image.

---

## 31. LLM Web UI Streaming Mandate & Ingress Idle Connection Timeouts (`Failed to fetch`)

When serving local AI/LLM interfaces (e.g. Ollama, Llama.cpp, vLLM) behind Home Assistant Ingress or reverse proxies:

### Symptom:
Small test prompts (`"Say ready"`) succeed in seconds, but prompts requiring longer generations or code generation fail after ~60 seconds with a red frontend error: `❌ Fout: Failed to fetch`.

### Mechanism:
1. Large models (e.g. 14B/32B/35B MoE) or reasoning/thinking models (e.g. DeepSeek-R1, Qwen 3.5 MoE, Ornith) generate internal thinking tokens before emitting the final answer. Full generation often takes 60–90+ seconds.
2. When the frontend or backend proxy uses non-streaming requests (`stream: false` in fetch, `stream=False` in Python `requests`), the server buffers the entire response in memory before sending a single byte to the client.
3. Mobile browsers (Home Assistant Companion App), 5G/LTE carrier NAT tables, and reverse proxies (Nginx, Cloudflare, HA Ingress) enforce a strict 60-second idle connection timeout on requests with zero transmitted bytes. The TCP connection is abruptly terminated, causing client-side `fetch()` to reject with `TypeError: Failed to fetch`.

### Operational Rules:
1. **Mandatory Streaming in UI (`stream: true`):** Always use streaming (Server-Sent Events / chunked transfer) in LLM web UIs. The first tokens reach the client within 1–2 seconds, keeping the HTTP socket actively transmitting data and resetting idle connection timers indefinitely.
2. **Chunked Streaming in Intermediate Proxies:** If an add-on web server proxies to a backend LLM daemon (e.g. Python `web_server.py` proxying to `localhost:11434`), it must use `stream=True` and yield chunks directly (`Transfer-Encoding: chunked`) to the client instead of buffering `resp.content`.
3. **Hardware Selection for Local AI in HAOS (Intel NPU vs Arc iGPU):**
   - Intel Core Ultra processors expose both an NPU (`/dev/accel/accel0`, ~13 TOPS) and an Arc iGPU (`/dev/dri/renderD128`, ~60+ TOPS).
   - The NPU has restricted runtime operator support, lacks host-unified memory optimisations, and requires custom Level Zero drivers not mapped by standard HA containers.
   - For all local LLM and computer vision workloads in Home Assistant Add-ons, target the Arc iGPU (`renderD128`) via Vulkan (`GGML_VK_PREFER_HOST_MEMORY=1`) or OpenVINO.

---

## 32. Disconnect-Resilient Generation & Auto-Resume Pattern for Mobile/Ingress LLMs

When operators query local LLMs via Home Assistant Ingress from mobile devices (e.g. Home Assistant Companion App over 4G/5G or fluctuating Wi-Fi):

### Problem:
Long-running generations (reasoning/thinking models, code synthesis) take 30–90+ seconds. Mobile network transitions (handover between cell towers, switching from Wi-Fi to 5G, walking into an elevator, backgrounding the mobile app) abruptly drop the TCP connection. Under standard HTTP streaming, the client's `ReadableStream` errors out, the response is discarded, and the user must re-submit the entire prompt from scratch.

### Architecture for Transport-Decoupled Generation:
1. **Client-Assigned `message_id` & LocalStorage State:**
   - Every outgoing prompt generates a unique `message_id` (e.g. `msg_<timestamp>_<rand>`).
   - The client writes the user prompt and `message_id` into browser `localStorage` before initiating the network call. If the Companion App reloads or the WebView is purged, the frontend recognizes a generation is in-flight.
2. **Server-Side Generation Decoupling:**
   - In the add-on intermediate proxy (e.g. Python `web_server.py`), decouple upstream LLM reading from the client's HTTP response socket.
   - Spawn an asynchronous background task reading Ollama/Llama.cpp chunks into an in-memory buffer (`active_generations[message_id]`).
   - If the client's HTTP connection terminates mid-generation, **the server worker does NOT abort**. It continues reading tokens into the buffer until the model finishes (`done: true`).
3. **Auto-Reconnect & Token Catch-Up (`/api/chat_resume`):**
   - In the browser, wrap the streaming `fetch()` reader in a disconnect handler.
   - Upon network abort, transition the UI state to a non-destructive status: `📡 Verbinding herstellen... (poging N)`.
   - The client runs a bounded exponential backoff polling `/api/chat_resume?id=<message_id>&offset=<received_token_length>`.
   - When network connectivity returns:
     - If the model is still executing, the server immediately streams buffered tokens from `offset` onward and continues live generation.
     - If the model already finished while offline, the server returns the complete payload, triggering markdown rendering, copy buttons, and metrics.






