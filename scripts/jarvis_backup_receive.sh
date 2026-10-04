#!/usr/bin/env bash
# JARVIS backup receiver/finalizer — runs on Ubuntu after Windows pushes files.
#
# Called by jarvis_backup.ps1 via SSH:
#   jarvis_backup_receive.sh <STAMP>
#
# Expects files in: /mnt/lilith_data/backups/jarvis/incoming/<STAMP>/
# Validates JSON, generates checksums, creates manifest, promotes to snapshots/.
# Updates latest/ symlink on success. Never deletes incoming on failure.
#
# NO secrets are handled. No .env, no api_keys.json.
#
# Exit codes: 0=promoted  1=validation failed or no files
set -euo pipefail

STAMP="${1:?usage: jarvis_backup_receive.sh <STAMP>}"
BASE="/mnt/lilith_data/backups/jarvis"
INCOMING="$BASE/incoming/$STAMP"
SNAPSHOTS="$BASE/snapshots"
LATEST="$BASE/latest"
LOGDIR="$BASE/logs"
RETENTION_DAYS=14

mkdir -p "$SNAPSHOTS" "$LOGDIR"
LOGFILE="$LOGDIR/receive_${STAMP}.log"

log() {
  local msg
  msg="$(date '+%Y-%m-%d %H:%M:%S') [jarvis_receive] $*"
  echo "$msg" | tee -a "$LOGFILE"
}

verify_json() {
  local file="$1"
  [ -f "$file" ] && [ -s "$file" ] && \
    python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$file" 2>/dev/null
}

# --- Validate incoming ---
if [ ! -d "$INCOMING" ]; then
  log "ERROR: directorio incoming no existe: $INCOMING"
  exit 1
fi

DATA_FILES=(
  "memory/long_term.json"
  "memory/task_history.json"
  "config/ui_settings.json"
  "config/layout_settings.json"
)

DATA_OK=0
DATA_TOTAL=${#DATA_FILES[@]}

log "=== Validando snapshot $STAMP ==="

for rel in "${DATA_FILES[@]}"; do
  f="$INCOMING/$rel"
  if [ -f "$f" ]; then
    if verify_json "$f"; then
      size=$(stat -c%s "$f" 2>/dev/null || echo "?")
      log "OK: $rel ($size bytes, JSON válido)"
      DATA_OK=$((DATA_OK + 1))
    else
      log "FAIL: $rel presente pero JSON inválido"
    fi
  else
    log "SKIP: $rel no recibido"
  fi
done

if [ "$DATA_OK" -eq 0 ]; then
  log "ERROR: 0 archivos válidos; snapshot NO promovido"
  log "Incoming preservado en: $INCOMING"
  exit 1
fi

# --- Checksums ---
(cd "$INCOMING" && find . -name '*.json' -exec sha256sum {} + > SHA256SUMS.txt)
log "Checksums: $INCOMING/SHA256SUMS.txt"

# --- Manifest ---
cat > "$INCOMING/MANIFEST.json" << EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "stamp": "$STAMP",
  "files_expected": $DATA_TOTAL,
  "files_ok": $DATA_OK,
  "files_failed": $((DATA_TOTAL - DATA_OK)),
  "retention_days": $RETENTION_DAYS
}
EOF
log "Manifest creado"

# --- Promote: move incoming → snapshots ---
DEST="$SNAPSHOTS/$STAMP"
mv "$INCOMING" "$DEST"
log "Promovido: $DEST"

# --- Update latest symlink ---
ln -sfn "$DEST" "$LATEST"
log "latest → $DEST"

# --- Retention (only after successful promotion) ---
OLD=$(find "$SNAPSHOTS" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" 2>/dev/null | wc -l)
if [ "$OLD" -gt 0 ]; then
  CURRENT_LATEST=$(readlink -f "$LATEST" 2>/dev/null || echo "")
  find "$SNAPSHOTS" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" | while read -r old_dir; do
    if [ "$(readlink -f "$old_dir")" != "$CURRENT_LATEST" ]; then
      rm -rf "$old_dir"
      log "Retención: eliminado $(basename "$old_dir")"
    fi
  done
fi

# --- Clean empty incoming dir if any ---
rmdir "$BASE/incoming" 2>/dev/null || true

log "=== Fin: $DATA_OK/$DATA_TOTAL archivos válidos, snapshot $STAMP activo ==="
exit 0
