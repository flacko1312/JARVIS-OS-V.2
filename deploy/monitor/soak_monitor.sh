#!/bin/bash
# JARVIS Headless 24h soak monitor
# Samples metrics every 5 minutes, writes CSV to logs/
# Usage: nohup bash deploy/monitor/soak_monitor.sh &

INTERVAL=300
DURATION=86400
LOGDIR="/home/flako1312/jarvis-headless/logs"
mkdir -p "$LOGDIR"
OUTFILE="$LOGDIR/soak_$(date +%Y%m%d_%H%M%S).csv"
SAMPLES=$((DURATION / INTERVAL))

echo "timestamp,sample,pid,rss_mib,cpu_pct,mem_avail_mib,swap_used_mib,load_1m,health_state,service_active,restarts" > "$OUTFILE"
echo "Soak monitor started: $OUTFILE ($SAMPLES samples over ${DURATION}s)"

for i in $(seq 1 $SAMPLES); do
    PID=$(systemctl --user show -p MainPID jarvis-headless 2>/dev/null | cut -d= -f2)
    TS=$(date -Iseconds)
    if [ "$PID" -gt 0 ] 2>/dev/null; then
        RSS=$(ps -p "$PID" -o rss --no-headers 2>/dev/null | awk '{printf "%.1f", $1/1024}')
        CPU=$(ps -p "$PID" -o %cpu --no-headers 2>/dev/null | tr -d ' ')
    else
        RSS="0.0"; CPU="0.0"
    fi
    MEM_AVAIL=$(awk '/MemAvailable/{printf "%.0f", $2/1024}' /proc/meminfo)
    SWAP_USED=$(free -m | awk '/Swap/{print $3}')
    LOAD=$(awk '{print $1}' /proc/loadavg)
    HEALTH=$(curl -s --connect-timeout 2 http://127.0.0.1:7470/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state','FAIL'))" 2>/dev/null || echo "DOWN")
    ACTIVE=$(systemctl --user is-active jarvis-headless 2>/dev/null || echo "unknown")
    RESTARTS=$(systemctl --user show -p NRestarts jarvis-headless 2>/dev/null | cut -d= -f2)
    echo "$TS,$i,$PID,$RSS,$CPU,$MEM_AVAIL,$SWAP_USED,$LOAD,$HEALTH,$ACTIVE,${RESTARTS:-0}" >> "$OUTFILE"
    sleep $INTERVAL
done
echo "Soak monitor complete: $OUTFILE"
