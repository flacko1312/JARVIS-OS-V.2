<#
.SYNOPSIS
  JARVIS runtime backup sender -- pushes data files from Windows to Ubuntu via SCP.

.DESCRIPTION
  Copies runtime JSON files from C:\JARVIS to the Ubuntu backup server's incoming
  directory. The Ubuntu receiver script validates and promotes the snapshot.

  Files are classified as REQUIRED or OPTIONAL. Missing optional files are skipped
  without error. Missing required files abort the backup.

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
    Add-Content -Path $LogFile -Value $line -Encoding ASCII
}

# --- Resolve Ubuntu target ---
if ($UbuntuUser -and $UbuntuHost) {
    $target = @{ user = $UbuntuUser; host = $UbuntuHost }
    $target | ConvertTo-Json | Set-Content -Path $ConfigFile -Encoding UTF8
    Log "Config saved: $ConfigFile"
} elseif (Test-Path $ConfigFile) {
    $target = Get-Content $ConfigFile -Raw | ConvertFrom-Json
    Log "Config loaded: $($target.user)@$($target.host)"
} else {
    Log "ERROR: No config found. Run with -UbuntuUser and -UbuntuHost on first use."
    exit 1
}

$RemoteUser = $target.user
$RemoteHost = $target.host
$RemoteIncoming = "/mnt/lilith_data/backups/jarvis/incoming/$Stamp"

# --- Validate SSH key ---
if (-not (Test-Path $SshKey)) {
    Log "ERROR: SSH key not found: $SshKey"
    exit 1
}

# --- Test SSH connectivity ---
Log "=== Start JARVIS runtime backup ($Stamp) ==="
Log "Target: $RemoteUser@${RemoteHost}:/mnt/lilith_data/backups/jarvis/"

try {
    $testResult = & ssh -i $SshKey -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new `
        -o BatchMode=yes "$RemoteUser@$RemoteHost" "echo OK" 2>&1
    if ($testResult -ne "OK") {
        Log "ERROR: SSH test failed: $testResult"
        exit 1
    }
} catch {
    Log "ERROR: Cannot connect to $RemoteHost : $_"
    exit 1
}

# --- File definitions (NO secrets) ---
$RequiredFiles = @(
    "memory\long_term.json",
    "memory\task_history.json"
)

$OptionalFiles = @(
    "config\ui_settings.json",
    "config\layout_settings.json"
)

# --- Create remote incoming directory ---
& ssh -i $SshKey "$RemoteUser@$RemoteHost" "mkdir -p '$RemoteIncoming/memory' '$RemoteIncoming/config'"

$reqOk = 0
$reqFailed = 0
$optOk = 0
$optSkipped = 0
$optFailed = 0

# --- Transfer REQUIRED files ---
foreach ($rel in $RequiredFiles) {
    $localPath = Join-Path $JarvisRoot $rel
    $remotePath = $rel -replace '\\', '/'

    if (-not (Test-Path $localPath)) {
        Log "FAIL [required]: $rel not found in $JarvisRoot"
        $reqFailed++
        continue
    }

    try {
        $null = Get-Content $localPath -Raw | ConvertFrom-Json
    } catch {
        Log "FAIL [required]: $rel is not valid JSON locally"
        $reqFailed++
        continue
    }

    try {
        & scp -i $SshKey -o ConnectTimeout=10 "$localPath" "${RemoteUser}@${RemoteHost}:${RemoteIncoming}/${remotePath}" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $size = (Get-Item $localPath).Length
            Log "OK [required]: $rel ($size bytes)"
            $reqOk++
        } else {
            Log "FAIL [required]: scp failed for $rel"
            $reqFailed++
        }
    } catch {
        Log "FAIL [required]: error copying $rel : $_"
        $reqFailed++
    }
}

# --- Transfer OPTIONAL files ---
foreach ($rel in $OptionalFiles) {
    $localPath = Join-Path $JarvisRoot $rel
    $remotePath = $rel -replace '\\', '/'

    if (-not (Test-Path $localPath)) {
        Log "SKIP [optional]: $rel not present"
        $optSkipped++
        continue
    }

    try {
        $null = Get-Content $localPath -Raw | ConvertFrom-Json
    } catch {
        Log "FAIL [optional]: $rel is not valid JSON locally"
        $optFailed++
        continue
    }

    try {
        & scp -i $SshKey -o ConnectTimeout=10 "$localPath" "${RemoteUser}@${RemoteHost}:${RemoteIncoming}/${remotePath}" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $size = (Get-Item $localPath).Length
            Log "OK [optional]: $rel ($size bytes)"
            $optOk++
        } else {
            Log "FAIL [optional]: scp failed for $rel"
            $optFailed++
        }
    } catch {
        Log "FAIL [optional]: error copying $rel : $_"
        $optFailed++
    }
}

$totalFailed = $reqFailed + $optFailed
$totalOk = $reqOk + $optOk

Log "Transfer: required=$reqOk/$($RequiredFiles.Count) optional=$optOk/$($OptionalFiles.Count) skipped=$optSkipped failed=$totalFailed"

# --- Abort if any required file failed ---
if ($reqFailed -gt 0) {
    Log "ERROR: $reqFailed required file(s) failed; aborting"
    & ssh -i $SshKey "$RemoteUser@$RemoteHost" "rm -rf '$RemoteIncoming'" 2>$null
    exit 1
}

if ($totalOk -eq 0) {
    Log "ERROR: no files copied; aborting"
    & ssh -i $SshKey "$RemoteUser@$RemoteHost" "rm -rf '$RemoteIncoming'" 2>$null
    exit 1
}

# --- Trigger Ubuntu receiver/finalizer ---
Log "Running receiver on Ubuntu..."
$receiveResult = & ssh -i $SshKey "$RemoteUser@$RemoteHost" `
    "/home/flako1312/JARVIS-OS-V2/scripts/jarvis_backup_receive.sh '$Stamp'" 2>&1
$receiveExit = $LASTEXITCODE

foreach ($line in $receiveResult) { Log "  [ubuntu] $line" }

if ($receiveExit -ne 0) {
    Log "ERROR: receiver failed (exit $receiveExit)"
    exit 1
}

Log "=== End JARVIS backup ==="
Log "Result: required=$reqOk/$($RequiredFiles.Count) optional=$optOk skipped=$optSkipped failed=$totalFailed -- snapshot promoted"
exit 0
