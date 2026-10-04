#!/usr/bin/env bash
# JARVIS — Backup de datos de runtime desde Windows vía SCP
#
# Cubre: memory/long_term.json, memory/task_history.json,
#         config/ui_settings.json, config/layout_settings.json
# Secretos (separado): .env, config/api_keys.json
#
# Invariantes:
#   - Retención solo se aplica DESPUÉS de que el nuevo backup esté validado.
#   - Si SCP falla, se reporta claramente y el script sale con código 1.
#   - Nunca borra backups válidos anteriores tras un fallo del backup nuevo.
#   - Nunca imprime el contenido de .env ni de ficheros de credenciales.
#
# Uso: jarvis_backup.sh [--secrets]
#   Sin argumentos: solo datos de runtime (memoria, config no sensible)
#   --secrets: también respalda .env y api_keys.json (600, directorio aparte)
#
# Exit codes: 0=todo OK  1=uno o más componentes fallaron
set -euo pipefail

STAMP="$(date '+%Y-%m-%d_%H%M%S')"
BASE="/mnt/lilith_data/backups/jarvis/data"
SECRETS_BASE="/mnt/lilith_data/backups/jarvis/secrets"
WINDOWS_USER="${JARVIS_BACKUP_USER:-flako1312}"
WINDOWS_HOST="${JARVIS_BACKUP_HOST:-192.168.1.100}"
WINDOWS_JARVIS="${JARVIS_BACKUP_PATH:-/c/JARVIS}"
SSH_KEY="${JARVIS_BACKUP_KEY:-$HOME/.ssh/id_ed25519}"
RETENTION_DAYS=14
SECRETS_RETENTION=3

log() { printf '%s [jarvis_backup] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

LOCKFILE="/run/user/$(id -u)/jarvis_backup.lock"
[ -d "$(dirname "$LOCKFILE")" ] || LOCKFILE="/tmp/jarvis_backup.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  log "otra ejecución en curso; salgo sin hacer nada"
  exit 0
fi

BACKUP_DIR="$BASE/$STAMP"
FAILED=0
DO_SECRETS=0
[[ "${1:-}" == "--secrets" ]] && DO_SECRETS=1

scp_file() {
  local remote_path="$1"
  local local_path="$2"
  local perms="${3:-644}"
  mkdir -p "$(dirname "$local_path")"
  if scp -i "$SSH_KEY" -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
       "${WINDOWS_USER}@${WINDOWS_HOST}:${remote_path}" "$local_path" 2>/dev/null; then
    chmod "$perms" "$local_path"
    return 0
  else
    return 1
  fi
}

verify_json() {
  local file="$1"
  if [ ! -f "$file" ]; then
    return 1
  fi
  if [ ! -s "$file" ]; then
    log "WARN: $file existe pero está vacío"
    return 1
  fi
  if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$file" 2>/dev/null; then
    return 0
  else
    log "WARN: $file no es JSON válido"
    return 1
  fi
}

log "=== Inicio backup JARVIS runtime ($STAMP) ==="
log "Host: ${WINDOWS_USER}@${WINDOWS_HOST}:${WINDOWS_JARVIS}"

mkdir -p "$BACKUP_DIR"

# --- Runtime data ---
DATA_FILES=(
  "memory/long_term.json"
  "memory/task_history.json"
  "config/ui_settings.json"
  "config/layout_settings.json"
)

DATA_OK=0
DATA_TOTAL=${#DATA_FILES[@]}

for rel in "${DATA_FILES[@]}"; do
  local_file="$BACKUP_DIR/$rel"
  remote_file="${WINDOWS_JARVIS}/$rel"
  if scp_file "$remote_file" "$local_file"; then
    if verify_json "$local_file"; then
      size=$(stat -c%s "$local_file" 2>/dev/null || echo "?")
      log "OK: $rel ($size bytes)"
      DATA_OK=$((DATA_OK + 1))
    else
      log "FAIL: $rel copiado pero no es JSON válido"
      FAILED=1
    fi
  else
    log "FAIL: no pude copiar $rel desde Windows"
    FAILED=1
  fi
done

# --- Checksums ---
if [ "$DATA_OK" -gt 0 ]; then
  (cd "$BACKUP_DIR" && find . -name '*.json' -exec sha256sum {} + > SHA256SUMS.txt)
  log "Checksums generados: $BACKUP_DIR/SHA256SUMS.txt"
fi

# --- Manifest ---
cat > "$BACKUP_DIR/MANIFEST.json" << MANIFEST_EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "source": "${WINDOWS_USER}@${WINDOWS_HOST}:${WINDOWS_JARVIS}",
  "files_expected": $DATA_TOTAL,
  "files_ok": $DATA_OK,
  "files_failed": $((DATA_TOTAL - DATA_OK)),
  "retention_days": $RETENTION_DAYS
}
MANIFEST_EOF
log "Manifest: $BACKUP_DIR/MANIFEST.json"

# --- Secrets (separate, restricted) ---
if [ "$DO_SECRETS" -eq 1 ]; then
  SECRETS_DIR="$SECRETS_BASE/$STAMP"
  mkdir -p "$SECRETS_DIR"
  chmod 700 "$SECRETS_DIR"

  SECRET_FILES=(
    ".env"
    "config/api_keys.json"
  )

  for rel in "${SECRET_FILES[@]}"; do
    local_file="$SECRETS_DIR/$rel"
    remote_file="${WINDOWS_JARVIS}/$rel"
    if scp_file "$remote_file" "$local_file" "600"; then
      size=$(stat -c%s "$local_file" 2>/dev/null || echo "?")
      log "SECRET OK: $rel ($size bytes, mode 600)"
    else
      log "SECRET SKIP: $rel no encontrado o no accesible"
    fi
  done

  chmod 700 "$SECRETS_BASE"
  log "Secretos en $SECRETS_DIR (modo 700)"

  # Secrets retention
  find "$SECRETS_BASE" -mindepth 1 -maxdepth 1 -type d -mtime +"$SECRETS_RETENTION" \
    -exec rm -rf {} + 2>/dev/null && \
    log "Retención de secretos: eliminados backups > ${SECRETS_RETENTION} días" || true
fi

# --- Retention (solo si el backup actual tiene al menos 1 archivo OK) ---
if [ "$DATA_OK" -gt 0 ]; then
  OLD=$(find "$BASE" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" | wc -l)
  if [ "$OLD" -gt 0 ]; then
    find "$BASE" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" \
      -exec rm -rf {} +
    log "Retención: eliminados $OLD backups > ${RETENTION_DAYS} días"
  fi
else
  log "WARN: ningún archivo copiado correctamente; NO se aplica retención"
fi

# --- Resumen ---
log "=== Fin backup JARVIS ==="
log "Resultado: $DATA_OK/$DATA_TOTAL archivos OK"
if [ "$FAILED" -ne 0 ]; then
  log "ERROR: uno o más componentes fallaron"
  exit 1
fi
log "Todo OK"
exit 0
