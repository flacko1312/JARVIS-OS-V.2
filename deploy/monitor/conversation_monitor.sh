#!/bin/bash
# Monitor during physical conversation test (~5 min)
# Usage: bash deploy/monitor/conversation_monitor.sh
# Samples every 15 seconds for 6 minutes

INTERVAL=15
DURATION=360
LOGDIR="/home/flako1312/jarvis-headless/logs"
mkdir -p "$LOGDIR"
OUTFILE="$LOGDIR/conversation_$(date +%Y%m%d_%H%M%S).csv"
SAMPLES=$((DURATION / INTERVAL))

echo "timestamp,sample,pid,rss_mib,cpu_pct,mem_avail_mib,swap_used_mib,health_state,restarts" > "$OUTFILE"
echo "Conversation monitor started: $OUTFILE ($SAMPLES samples over ${DURATION}s)"
echo "BEGIN speaking to JARVIS now."

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
    HEALTH=$(curl -s --connect-timeout 2 http://127.0.0.1:7470/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state','FAIL'))" 2>/dev/null || echo "DOWN")
    RESTARTS=$(systemctl --user show -p NRestarts jarvis-headless 2>/dev/null | cut -d= -f2)
    echo "$TS,$i,$PID,$RSS,$CPU,$MEM_AVAIL,$SWAP_USED,$HEALTH,${RESTARTS:-0}" >> "$OUTFILE"
    echo "[$i/$SAMPLES] RSS=${RSS}MiB CPU=${CPU}% MemAvail=${MEM_AVAIL}MiB Swap=${SWAP_USED}MiB Health=$HEALTH"
    sleep $INTERVAL
done
echo "Conversation monitor complete: $OUTFILE"
PEAK=$(awk -F, 'NR>1{if($4+0>max)max=$4+0}END{printf "%.1f MiB\n",max}' "$OUTFILE")
MIN_MEM=$(awk -F, 'NR>1{if(NR==2||($6+0)<min)min=$6+0}END{printf "%.0f MiB\n",min}' "$OUTFILE")
echo "Peak RSS: $PEAK"
echo "Min MemAvail: $MIN_MEM"
