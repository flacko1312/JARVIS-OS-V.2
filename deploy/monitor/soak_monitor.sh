#!/bin/bash
# JARVIS Headless 24h soak monitor v2
# Designed to run as a systemd transient unit via:
#   systemd-run --user --unit=jarvis-soak --remain-after-exit \
#     bash /home/flako1312/jarvis-headless/deploy/monitor/soak_monitor.sh
#
# Survives SSH disconnection, Claude session close, Windows shutdown.

INTERVAL=300
DURATION=86400
LOGDIR="/home/flako1312/jarvis-headless/logs"
mkdir -p "$LOGDIR"
OUTFILE="$LOGDIR/soak_$(date +%Y%m%d_%H%M%S).csv"
SAMPLES=$((DURATION / INTERVAL))

export XDG_RUNTIME_DIR=/run/user/1000

echo "timestamp,sample,pid,rss_mib,cpu_pct,mem_avail_mib,swap_used_mib,load_1m,health_state,service_active,restarts" > "$OUTFILE"
echo "[soak] started: $OUTFILE ($SAMPLES samples, ${INTERVAL}s interval, ${DURATION}s total)"

for i in $(seq 1 $SAMPLES); do
    PID=$(systemctl --user show -p MainPID jarvis-headless 2>/dev/null | cut -d= -f2)
    TS=$(date -Iseconds)
    if [ -n "$PID" ] && [ "$PID" -gt 0 ] 2>/dev/null; then
        RSS=$(awk '/^VmRSS:/{printf "%.1f", $2/1024}' /proc/"$PID"/status 2>/dev/null || echo "0.0")
        CPU=$(ps -p "$PID" -o %cpu --no-headers 2>/dev/null | tr -d ' ' || echo "0.0")
    else
        RSS="0.0"; CPU="0.0"; PID="0"
    fi
    MEM_AVAIL=$(awk '/MemAvailable:/{printf "%.0f", $2/1024}' /proc/meminfo)
    SWAP_USED=$(awk '/SwapTotal:/{t=$2} /SwapFree:/{printf "%.0f", (t-$2)/1024}' /proc/meminfo)
    LOAD=$(cut -d' ' -f1 /proc/loadavg)
    HEALTH=$(curl -s --connect-timeout 3 --max-time 5 http://127.0.0.1:7470/health 2>/dev/null)
    STATE=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state','FAIL'))" 2>/dev/null || echo "DOWN")
    ACTIVE=$(systemctl --user is-active jarvis-headless 2>/dev/null || echo "unknown")
    RESTARTS=$(systemctl --user show -p NRestarts jarvis-headless 2>/dev/null | cut -d= -f2 || echo "-1")
    echo "$TS,$i,$PID,$RSS,$CPU,$MEM_AVAIL,$SWAP_USED,$LOAD,$STATE,$ACTIVE,${RESTARTS:-0}" >> "$OUTFILE"
    echo "[soak] sample $i/$SAMPLES pid=$PID rss=${RSS}MiB mem=${MEM_AVAIL}MiB"
    sleep $INTERVAL
done
echo "[soak] complete: $OUTFILE"
