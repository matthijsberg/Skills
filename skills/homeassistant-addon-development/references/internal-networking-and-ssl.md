# Internal Networking, SSL, and Inter-Addon Communication in Home Assistant

## 1. SSL Hostname Mismatches on Local & Host Networking

When an add-on terminates TLS using certificates from `/ssl` (e.g. Let's Encrypt for `<ha-domain>`):
- Connecting via `http://127.0.0.1:<port>`, `http://local-<addon>:<port>`, or raw LAN IP fails with SSL hostname verification errors (`[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch`).
- Connecting clients must use the fully qualified domain name (FQDN) matching the certificate (`https://<domain>:<port>`).
- **Best Practice for Add-on Architecture:** In nginx or reverse proxy configurations, provide dual listeners when possible:
  1. An encrypted external listener with SSL on the public port (e.g. `:3000` with certificate).
  2. A local unencrypted HTTP listener restricted to internal docker networks or localhost for latency-sensitive, cert-agnostic inter-addon communication.

## 2. Headless Inter-Addon Credential Sharing via `/share`

For headless add-ons that generate API keys or projects on first boot (e.g. Langfuse, local databases, message queues):
- Write the connection parameters to `/share/<addon-name>/<consumer>.env` with `0600` or `0644` permissions.
- Consumers can inspect `/share/<addon-name>/` at startup to auto-configure API keys without requiring manual copy-pasting from the user.
- Always include both the FQDN URL and the local container URL in the exported environment so consumers can choose the appropriate path.

## 3. In-Memory Process Lifecycle & Add-on Restarts

- Pulling code updates or installing Python packages into shared virtualenvs on disk does NOT hot-reload running daemon processes.
- Any background worker, supervisor, or gateway daemon spawned at boot keeps serving pre-update modules in memory.
- To apply new plugins or updated packages, trigger a full container restart via Home Assistant service `hassio.addon_restart` with the add-on slug or through the Home Assistant Settings -> Add-ons UI.

## 4. Packaging OCI-Embedded Multi-Service Appliances (e.g., UniFi OS Server)

When packaging vendor appliances that distribute a multi-service OCI image embedded inside a proprietary host installer (such as Ubiquiti's **UniFi OS Server**) as a Home Assistant Add-on:

1. **Multi-Stage Build-Time OCI Extraction (Avoid Nested Podman/VM):**
   - Poll the vendor's release API (for UniFi OS Server: `https://download.svc.ui.com/v1/downloads/products/slugs/unifi-os-server`) in GitHub Actions to resolve `linux-x64` / `linux-arm64` installer URLs and companion `.deb` packages (`unifi-uos_sysvinit.deb`).
   - Extract the embedded `image.tar` using `binwalk --run-as=root -e installer.bin` (or `7z`), parse `oci/index.json` -> manifest digest -> `.layers[].digest`, and flatten layers into `/rootfs` while applying OCI whiteout markers (`.wh..wh..opq` and `.wh.<name>`).
   - Build the runtime container `FROM scratch` with `/rootfs` and a custom entrypoint.
2. **HAOS Cgroup v2 & Systemd Constraints:**
   - HAOS runs on **cgroup v2** and the Supervisor starts add-on containers with a private cgroup namespace (`--cgroupns=private`) and a read-only `/sys/fs/cgroup` mount (`cgroup_namespace: host` is not supported in `config.yaml`).
   - **Preferred (`SYS_ADMIN`-free):** Replace `/bin/systemctl` and `/sbin/init` with `docker-systemctl-replacement` (`systemctl3.py`) or **s6-overlay v3** definitions so services (`postgresql`, `mongodb`, `rabbitmq-server`, `ulp-go`, `unifi-core`, `unifi`, `nginx`) run directly with only `NET_ADMIN` and `NET_RAW`.
   - **Native `/sbin/init` (systemd) as PID 1:** Requires `SYS_ADMIN` in `config.yaml`, `STOPSIGNAL SIGRTMIN+3`, `exec` tmpfs on `/run` and `/tmp`, and mounting a writable cgroup hierarchy in the entrypoint before `exec /sbin/init`.
3. **Persistent `/data` Mapping & Idempotent DB Pre-Seeding:**
   - Symlink or bind-mount `/var/lib/unifi`, `/var/lib/uosserver`, `/data/unifi-core`, `/var/lib/postgresql`, `/var/lib/mongodb`, and `/etc/rabbitmq/ssl` into subdirectories under `/data`, and persist `/data/uos_uuid` (UUIDv5 format with nibble `5` at index 14).
   - Pre-seed required PostgreSQL roles and databases idempotently in the entrypoint before starting services, because upstream `pre-start.sh` scripts fail on parallel first-boot races.
4. **Querying Add-on Versions When Supervisor API Returns 403:**
   - When direct `http://supervisor/addons` requests return `403 Forbidden` inside the agent container, use `ha_list_entities(domain='update')` and `ha_get_state(entity_id='update.<addon>_update')` (or SSH via your configured host alias, e.g. `ssh haos`, or `-i <SSH_KEY> -p <SSH_PORT> root@172.30.32.1`) to inspect installed add-on versions and device firmware states.

## 5. Local HA Apps vs. Git Monorepo Drift & LLM Runtime Tuning

1. **HA Apps CLI & Terminology:**
   - Home Assistant has officially rebranded Add-ons to **Apps**. The CLI commands use `ha apps` (the older `ha addons` is deprecated). Use `ha apps info <slug>`, `ha apps logs <slug>`, `ha apps update <slug>`, and `ha apps rebuild <slug>`.
2. **Detecting Host `/addons/` vs Git Monorepo Drift:**
   - On HAOS, local apps live on the host filesystem under `/addons/<folder>` while your Git monorepo lives in `<REPO_ROOT>/apps/<folder>`.
   - Always compare both paths before planning or executing updates: live debugging frequently occurs directly in `/addons/<slug>` on the host, leaving the monorepo on older base images (e.g. legacy IPEX-LLM vs newer Vulkan builds). Always sync live changes into the Git repository before cutting releases.
3. **Hardware-Accelerated LLM Apps (Ollama / Intel Arc iGPU):**
   - **VRAM & KV-Cache Management:** Intel iGPUs utilize shared system RAM. To prevent OOM and lower memory footprints during long conversations, enable Flash Attention and quantize KV-cache: `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0`.
   - **Intel Arc / Xe Vulkan Stability:** On Intel Arc / Arrow Lake iGPUs running Mesa Vulkan drivers, integer dot products and cooperative matrix ops can cause GPU TDR timeouts or corrupt output. Always enforce `GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1` and `GGML_VK_DISABLE_COOPMAT=1`.
   - **Context Window & Multi-Model Residency:** With Flash Attention enabled, default context length can safely be configured to `4096` or `8192` tokens on systems with ≥16 GB RAM; set `max_loaded_models: 0` to allow Ollama to dynamically manage residency according to available VRAM.


