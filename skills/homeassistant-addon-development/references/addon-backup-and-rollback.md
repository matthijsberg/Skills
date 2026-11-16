# Multi-Version Backup Retention & Automated Rollback for Home Assistant Add-ons

When maintaining and deploying custom Home Assistant Add-ons on production systems, updates must never risk taking the system down without an immediate recovery path.

## Core Architectural Principles

1. **Automated Snapshot Before Every Deployment (Step 0):**
   - Before bumping version numbers or rebuilding container images, archive the current running directory to `/config/addons_archive/<addon_slug>/v<current_version>_<timestamp>/`.
2. **Multi-Version FIFO Rotation:**
   - Retain the last 5 stable snapshots to balance disk space with rollback flexibility.
3. **Automated Git Release Tagging:**
   - Create annotated Git tags (`git tag -a "v<version>" -m "Release v<version>"`) and push with `--tags`.
4. **Automated Failure Interception:**
   - If `ha apps rebuild` or `ha apps restart` returns non-zero during deployment, automatically trigger rollback to the immediately preceding snapshot within seconds.

---

## Starter Scripts

### 1. `scripts/rollback.sh`
```bash
#!/usr/bin/env bash
set -e

ARCHIVE_DIR="/config/addons_archive/<addon_slug>"
ADDON_DIR="/config/addons/<addon_slug>"
SSH_HOST="${HAOS_SSH_HOST:-haos}"  # Configured in ~/.ssh/config (or set SSH_PORT/SSH_KEY)

mkdir -p "${ARCHIVE_DIR}"

if [ "$1" = "list" ]; then
    echo "=== 📦 Available Backup Snapshots ==="
    ls -1td "${ARCHIVE_DIR}"/* 2>/dev/null || echo "No backups found."
    exit 0
fi

TARGET_BACKUP="$1"
if [ -z "${TARGET_BACKUP}" ]; then
    TARGET_BACKUP=$(ls -1td "${ARCHIVE_DIR}"/* 2>/dev/null | head -n 1)
fi

if [ -z "${TARGET_BACKUP}" ] || [ ! -d "${TARGET_BACKUP}" ]; then
    echo "❌ Error: No valid backup snapshot found to roll back to."
    exit 1
fi

echo "=== 🔄 Rolling back to snapshot: ${TARGET_BACKUP} ==="

# 1. Restore local files
rm -rf "${ADDON_DIR}"/*
cp -r "${TARGET_BACKUP}"/* "${ADDON_DIR}/"

# 2. Sync to HA host /addons/ volume and reload/upgrade
rsync -avz --delete --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    "${ADDON_DIR}/" "${SSH_HOST}:/addons/<addon_folder>/"
ssh "${SSH_HOST}" "ha store reload && (ha apps update local_<addon_slug> || ha apps rebuild local_<addon_slug>)"

echo "=== ✅ Rollback Complete! ==="
```

### 2. Integration in `scripts/deploy_update.sh`
```bash
# Snapshot step before bump
CURRENT_VER=$(python3 "${ADDON_DIR}/scripts/version_manager.py" status | awk '{print $NF}')
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SNAPSHOT_DIR="${ARCHIVE_DIR}/v${CURRENT_VER}_${TIMESTAMP}"

mkdir -p "${SNAPSHOT_DIR}"
cp -r "${ADDON_DIR}"/* "${SNAPSHOT_DIR}/"

# Rotate older snapshots (keep 5)
cd "${ARCHIVE_DIR}"
ls -1td v* 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm -rf

# Upgrade with fallback
if ! ssh "${SSH_HOST}" "ha store reload && (ha apps update local_<addon_slug> || ha apps rebuild local_<addon_slug>)"; then
    echo "❌ Upgrade failed! Rolling back to ${SNAPSHOT_DIR}..."
    bash "${ADDON_DIR}/scripts/rollback.sh" "${SNAPSHOT_DIR}"
    exit 1
fi
```
