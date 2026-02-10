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

# LINE Messaging API
LINE_CHANNEL_TOKEN="VHPc2N8BeXU3ES5m43HrGKiC2neAeI0WdHFNQcxd4a0oHJ5jcJM8tw4bLZBDnxYYXvF7+bm/WoRpH7BA14NJi151e/m/zNJg/yAbIylD56h5wzpWoiT0NVaGae4XzB9jLReBBXFQT7enCLfGHYjJpwdB04t89/1O/w1cDnyilFU="
LINE_USERS_FILE="${BASE_DIR}/configs/line_users.json"

# Log
LOG_DIR="${BASE_DIR}/logs"
mkdir -p "${LOG_DIR}"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/daily_signal_$(date +%Y%m%d_%H%M%S).log"

send_line_message_to_user() {
    local user_id="$1"
    local message="$2"
    local payload
    payload=$(jq -n --arg to "${user_id}" --arg text "${message}" \
        '{"to": $to, "messages": [{"type": "text", "text": $text}]}')
    local response
    response=$(curl -s -w "\nHTTP:%{http_code}" -X POST https://api.line.me/v2/bot/message/push \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${LINE_CHANNEL_TOKEN}" \
        -d "${payload}")
    echo "LINE push to ${user_id}: ${response}"
}

send_line_message_all() {
    local message="$1"
    if [ ! -f "${LINE_USERS_FILE}" ]; then
        echo "WARNING: LINE users file not found: ${LINE_USERS_FILE}"
        return
    fi
    local user_count
    user_count=$(jq 'length' "${LINE_USERS_FILE}")
    echo "Sending LINE notification to ${user_count} user(s)..."
    for i in $(seq 0 $((user_count - 1))); do
        local uid
        uid=$(jq -r ".[$i].user_id" "${LINE_USERS_FILE}")
        send_line_message_to_user "${uid}" "${message}"
    done
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

    # Send LINE notification to ALL registered users
    send_line_message_all "${MSG}"

} 2>&1 | tee -a "${LOG_FILE}"

# Cleanup old logs (keep 30 days)
find "${LOG_DIR}" -name "daily_signal_*.log" -mtime +30 -delete 2>/dev/null || true
