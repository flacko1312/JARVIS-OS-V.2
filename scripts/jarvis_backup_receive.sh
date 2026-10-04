#!/usr/bin/env bash
# JARVIS backup receiver/finalizer -- runs on Ubuntu after Windows pushes files.
#
# Called by jarvis_backup.ps1 via SSH:
#   jarvis_backup_receive.sh <STAMP>
#
# Expects files in: /mnt/lilith_data/backups/jarvis/incoming/<STAMP>/
# Validates JSON, generates checksums, creates manifest, promotes to snapshots/.
# Updates latest/ symlink on success. Never deletes incoming on failure.
#
# REQUIRED files: memory/long_term.json, memory/task_history.json
#   - All must be present and valid JSON for promotion.
# OPTIONAL files: config/ui_settings.json, config/layout_settings.json
#   - Missing optional files are SKIPPED, not failures.
#
# NO secrets are handled. No .env, no api_keys.json.
#
# Exit codes: 0=promoted  1=required file missing/invalid or no files
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
  log "ERROR: incoming directory does not exist: $INCOMING"
  exit 1
fi

REQUIRED_FILES=(
  "memory/long_term.json"
  "memory/task_history.json"
)

OPTIONAL_FILES=(
  "config/ui_settings.json"
  "config/layout_settings.json"
)

REQ_OK=0
REQ_FAILED=0
REQ_TOTAL=${#REQUIRED_FILES[@]}
OPT_OK=0
OPT_SKIPPED=0
OPT_FAILED=0
OPT_TOTAL=${#OPTIONAL_FILES[@]}

log "=== Validating snapshot $STAMP ==="

# --- Required files ---
for rel in "${REQUIRED_FILES[@]}"; do
  f="$INCOMING/$rel"
  if [ -f "$f" ]; then
    if verify_json "$f"; then
      size=$(stat -c%s "$f" 2>/dev/null || echo "?")
      log "OK [required]: $rel ($size bytes, valid JSON)"
      REQ_OK=$((REQ_OK + 1))
    else
      log "FAIL [required]: $rel present but invalid JSON"
      REQ_FAILED=$((REQ_FAILED + 1))
    fi
  else
    log "FAIL [required]: $rel not received"
    REQ_FAILED=$((REQ_FAILED + 1))
  fi
done

# --- Optional files ---
for rel in "${OPTIONAL_FILES[@]}"; do
  f="$INCOMING/$rel"
  if [ -f "$f" ]; then
    if verify_json "$f"; then
      size=$(stat -c%s "$f" 2>/dev/null || echo "?")
      log "OK [optional]: $rel ($size bytes, valid JSON)"
      OPT_OK=$((OPT_OK + 1))
    else
      log "FAIL [optional]: $rel present but invalid JSON"
      OPT_FAILED=$((OPT_FAILED + 1))
    fi
  else
    log "SKIP [optional]: $rel not present"
    OPT_SKIPPED=$((OPT_SKIPPED + 1))
  fi
done

TOTAL_FAILED=$((REQ_FAILED + OPT_FAILED))

# --- Gate: all required files must be OK ---
if [ "$REQ_FAILED" -gt 0 ]; then
  log "ERROR: $REQ_FAILED required file(s) missing or invalid; NOT promoting"
  log "Incoming preserved at: $INCOMING"
  exit 1
fi

if [ "$REQ_OK" -eq 0 ]; then
  log "ERROR: 0 required files valid; NOT promoting"
  log "Incoming preserved at: $INCOMING"
  exit 1
fi

# --- Checksums ---
(cd "$INCOMING" && find . -name '*.json' ! -name 'MANIFEST.json' -exec sha256sum {} + > SHA256SUMS.txt)
log "Checksums generated: SHA256SUMS.txt"

# --- Manifest ---
cat > "$INCOMING/MANIFEST.json" << EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "stamp": "$STAMP",
  "required_expected": $REQ_TOTAL,
  "required_ok": $REQ_OK,
  "optional_expected": $OPT_TOTAL,
  "optional_present": $OPT_OK,
  "optional_skipped": $OPT_SKIPPED,
  "files_failed": $TOTAL_FAILED,
  "retention_days": $RETENTION_DAYS
}
EOF
log "Manifest created"

# --- Promote: move incoming -> snapshots ---
DEST="$SNAPSHOTS/$STAMP"
mv "$INCOMING" "$DEST"
log "Promoted: $DEST"

# --- Update latest symlink ---
ln -sfn "$DEST" "$LATEST"
log "latest -> $DEST"

# --- Retention (only after successful promotion) ---
OLD=$(find "$SNAPSHOTS" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" 2>/dev/null | wc -l)
if [ "$OLD" -gt 0 ]; then
  CURRENT_LATEST=$(readlink -f "$LATEST" 2>/dev/null || echo "")
  find "$SNAPSHOTS" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" | while read -r old_dir; do
    if [ "$(readlink -f "$old_dir")" != "$CURRENT_LATEST" ]; then
      rm -rf "$old_dir"
      log "Retention: removed $(basename "$old_dir")"
    fi
  done
fi

# --- Clean empty incoming dir if any ---
rmdir "$BASE/incoming" 2>/dev/null || true

log "=== Done: required=$REQ_OK/$REQ_TOTAL optional=$OPT_OK/$OPT_TOTAL skipped=$OPT_SKIPPED failed=$TOTAL_FAILED -- snapshot $STAMP active ==="
exit 0
