<#
.SYNOPSIS
  JARVIS runtime backup sender — pushes data files from Windows to Ubuntu via SCP.

.DESCRIPTION
  Copies runtime JSON files from C:\JARVIS to the Ubuntu backup server's incoming
  directory. The Ubuntu receiver script validates and promotes the snapshot.

  NO secrets (.env, api_keys.json, tokens) are included.

.PARAMETER UbuntuUser
  SSH user on the Ubuntu server. Required on first run; cached in config after.

.PARAMETER UbuntuHost
  Ubuntu server IP or hostname. Required on first run; cached in config after.

.PARAMETER SshKey
  Path to the SSH private key for Ubuntu. Default: $HOME\.ssh\id_ed25519

.PARAMETER JarvisRoot
  Path to the JARVIS install on Windows. Default: C:\JARVIS

.EXAMPLE
  .\jarvis_backup.ps1 -UbuntuUser flako1312 -UbuntuHost 192.168.1.51
  .\jarvis_backup.ps1   # uses cached config from previous run
#>

param(
    [string]$UbuntuUser,
    [string]$UbuntuHost,
    [string]$SshKey = "$HOME\.ssh\id_ed25519",
    [string]$JarvisRoot = "C:\JARVIS"
)

$ErrorActionPreference = "Stop"

$ConfigFile = Join-Path $JarvisRoot "config\backup_target.json"
$LogDir = Join-Path $JarvisRoot "logs"
$Stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$LogFile = Join-Path $LogDir "jarvis_backup.log"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [jarvis_backup] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

# --- Resolve Ubuntu target ---
if ($UbuntuUser -and $UbuntuHost) {
    $target = @{ user = $UbuntuUser; host = $UbuntuHost }
    $target | ConvertTo-Json | Set-Content -Path $ConfigFile -Encoding UTF8
    Log "Config guardado: $ConfigFile"
} elseif (Test-Path $ConfigFile) {
    $target = Get-Content $ConfigFile -Raw | ConvertFrom-Json
    Log "Config cargado: $($target.user)@$($target.host)"
} else {
    Log "ERROR: No hay config. Ejecuta con -UbuntuUser y -UbuntuHost la primera vez."
    exit 1
}

$RemoteUser = $target.user
$RemoteHost = $target.host
$RemoteIncoming = "/mnt/lilith_data/backups/jarvis/incoming/$Stamp"

# --- Validate SSH key ---
if (-not (Test-Path $SshKey)) {
    Log "ERROR: Clave SSH no encontrada: $SshKey"
    exit 1
}

# --- Test SSH connectivity ---
Log "=== Inicio backup JARVIS runtime ($Stamp) ==="
Log "Destino: $RemoteUser@${RemoteHost}:/mnt/lilith_data/backups/jarvis/"

try {
    $testResult = & ssh -i $SshKey -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new `
        -o BatchMode=yes "$RemoteUser@$RemoteHost" "echo OK" 2>&1
    if ($testResult -ne "OK") {
        Log "ERROR: SSH test fallo: $testResult"
        exit 1
    }
} catch {
    Log "ERROR: No se puede conectar a $RemoteHost : $_"
    exit 1
}

# --- Runtime data files (NO secrets) ---
$DataFiles = @(
    "memory\long_term.json",
    "memory\task_history.json",
    "config\ui_settings.json",
    "config\layout_settings.json"
)

# --- Create remote incoming directory ---
& ssh -i $SshKey "$RemoteUser@$RemoteHost" "mkdir -p '$RemoteIncoming/memory' '$RemoteIncoming/config'"

$ok = 0
$failed = 0
$total = $DataFiles.Count

foreach ($rel in $DataFiles) {
    $localPath = Join-Path $JarvisRoot $rel
    $remotePath = $rel -replace '\\', '/'

    if (-not (Test-Path $localPath)) {
        Log "SKIP: $rel no existe en $JarvisRoot"
        $failed++
        continue
    }

    # Validate JSON locally before sending
    try {
        $null = Get-Content $localPath -Raw | ConvertFrom-Json
    } catch {
        Log "FAIL: $rel no es JSON valido localmente"
        $failed++
        continue
    }

    try {
        & scp -i $SshKey -o ConnectTimeout=10 "$localPath" "${RemoteUser}@${RemoteHost}:${RemoteIncoming}/${remotePath}" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $size = (Get-Item $localPath).Length
            Log "OK: $rel ($size bytes)"
            $ok++
        } else {
            Log "FAIL: scp fallo para $rel"
            $failed++
        }
    } catch {
        Log "FAIL: error copiando $rel : $_"
        $failed++
    }
}

Log "Transferencia: $ok/$total archivos OK"

if ($ok -eq 0) {
    Log "ERROR: ningun archivo copiado; abortando"
    & ssh -i $SshKey "$RemoteUser@$RemoteHost" "rm -rf '$RemoteIncoming'" 2>$null
    exit 1
}

# --- Trigger Ubuntu receiver/finalizer ---
Log "Ejecutando receiver en Ubuntu..."
$receiveResult = & ssh -i $SshKey "$RemoteUser@$RemoteHost" `
    "/home/flako1312/JARVIS-OS-V2/scripts/jarvis_backup_receive.sh '$Stamp'" 2>&1
$receiveExit = $LASTEXITCODE

foreach ($line in $receiveResult) { Log "  [ubuntu] $line" }

if ($receiveExit -ne 0) {
    Log "ERROR: receiver fallo (exit $receiveExit)"
    exit 1
}

Log "=== Fin backup JARVIS ==="
Log "Resultado final: $ok/$total archivos OK, snapshot promovido en Ubuntu"
exit 0
