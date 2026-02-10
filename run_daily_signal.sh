#!/bin/bash
# ============================================================
# Contrarian Alpha — Daily Signal Generation + LINE Notification
# Runs after US market close (~4:30 PM ET = 5:30 AM +8)
# Writes to Docker-mounted signals dir via symlink
# ============================================================

set -euo pipefail

BASE_DIR="/home/service/contrarian-alpha"
VENV="${BASE_DIR}/venv/bin/python3"
SCRIPT="${BASE_DIR}/scripts/daily_signal_v9.py"

export FMP_API_KEY="TDc1M5BjkEmnB57iOmmfvi8QdBdRLYFA"
export PYTHONPATH="${BASE_DIR}"

# LINE Push via centralized line-push-service (port 8730)
LINE_PUSH_URL="http://localhost:8730/api/push"

# Log
LOG_DIR="${BASE_DIR}/logs"
mkdir -p "${LOG_DIR}"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/daily_signal_$(date +%Y%m%d_%H%M%S).log"

send_line_push() {
    local message="$1"
    local response
    response=$(curl -s -w "\nHTTP:%{http_code}" -X POST "${LINE_PUSH_URL}" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg msg "${message}" '{"message": $msg}')")
    echo "LINE push: ${response}"
}

{
    echo "=== Daily Signal Run: $(date) ==="

    # 1. Generate signals for today
    SIGNAL_OUTPUT=$(${VENV} "${SCRIPT}" --source fmp --date "${TODAY}" 2>&1)
    echo "${SIGNAL_OUTPUT}"

    # 2. Check exits for open positions
    EXIT_OUTPUT=$(${VENV} "${SCRIPT}" --source fmp --check-exits 2>&1)
    echo "${EXIT_OUTPUT}"

    echo "=== Completed: $(date) ==="

    # 3. Parse and send LINE notification
    # Extract BUY signals
    BUY_LINES=$(echo "${SIGNAL_OUTPUT}" | grep "→ BUY" || true)
    # Extract exit events
    EXIT_LINES=$(echo "${EXIT_OUTPUT}" | grep -E "(TP hit|SL hit|Max hold|closed)" || true)
    # Extract trade count
    TRADE_COUNT=$(echo "${SIGNAL_OUTPUT}" | grep "Trade signals:" | grep -o '[0-9]*' || echo "0")
    EVENT_COUNT=$(echo "${SIGNAL_OUTPUT}" | grep "Events found:" | grep -o '[0-9]*' || echo "0")

    # Build notification message using $'\n' for real newlines
    MSG="📊 Contrarian Alpha Daily Report"
    MSG+=$'\n'"📅 ${TODAY}"
    MSG+=$'\n'
    MSG+=$'\n'"Events: ${EVENT_COUNT} | Trades: ${TRADE_COUNT}"

    if [ -n "${BUY_LINES}" ]; then
        MSG+=$'\n'$'\n'"🟢 BUY Signals:"
        while IFS= read -r line; do
            SYMBOL=$(echo "$line" | awk '{print $1}')
            PROB=$(echo "$line" | grep -o 'prob=[0-9.]*' | cut -d= -f2)
            MSG+=$'\n'"  ${SYMBOL} (prob=${PROB})"
        done <<< "${BUY_LINES}"
    else
        MSG+=$'\n'$'\n'"No new trades today."
    fi

    if [ -n "${EXIT_LINES}" ]; then
        MSG+=$'\n'$'\n'"🔴 Exits:"
        while IFS= read -r line; do
            MSG+=$'\n'"  ${line}"
        done <<< "${EXIT_LINES}"
    fi

    # Count open positions
    OPEN_COUNT=$(echo "${SIGNAL_OUTPUT}" | grep "Open positions:" | grep -o '[0-9]*' || echo "?")
    MSG+=$'\n'$'\n'"Open positions: ${OPEN_COUNT}"
    MSG+=$'\n'"🔗 https://contrarian-alpha.gpu5090.whaleforce.dev/dashboard"

    # Send LINE notification via centralized service
    send_line_push "${MSG}"

} 2>&1 | tee -a "${LOG_FILE}"

# Cleanup old logs (keep 30 days)
find "${LOG_DIR}" -name "daily_signal_*.log" -mtime +30 -delete 2>/dev/null || true
