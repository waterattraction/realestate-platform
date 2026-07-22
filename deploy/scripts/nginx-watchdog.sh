#!/bin/bash
# Nginx / HTTPS watchdog for jiakubo.com reverse proxy.
# Alerts via journal + /var/log/nginx-watchdog.log (+ optional mail to root).
set -euo pipefail

DOMAIN="${NGINX_WATCHDOG_DOMAIN:-jiakubo.com}"
LOG="${NGINX_WATCHDOG_LOG:-/var/log/nginx-watchdog.log}"
STATE_DIR="${NGINX_WATCHDOG_STATE:-/var/lib/nginx-watchdog}"
ALERT_FLAG="${STATE_DIR}/ALERT"
OK_FLAG="${STATE_DIR}/OK"

mkdir -p "${STATE_DIR}"
touch "${LOG}"

ts() { date '+%Y-%m-%d %H:%M:%S %z'; }

fail=0
reasons=()

if ! systemctl is-active --quiet nginx; then
  fail=1
  reasons+=("nginx.service not active ($(systemctl is-active nginx 2>/dev/null || true))")
fi

if ! nginx -t >/dev/null 2>&1; then
  fail=1
  reasons+=("nginx -t failed")
fi

if ! ss -tlnp 2>/dev/null | grep -qE ':443\s'; then
  fail=1
  reasons+=("nothing listening on :443")
fi

if ! ss -tlnp 2>/dev/null | grep -qE ':80\s'; then
  fail=1
  reasons+=("nothing listening on :80")
fi

# Local HTTPS probe (ignore cert name mismatch on IP)
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 \
  -k "https://127.0.0.1/login" -H "Host: ${DOMAIN}" 2>/dev/null || echo "000")
if [[ "${code}" != "200" && "${code}" != "302" ]]; then
  fail=1
  reasons+=("local https://127.0.0.1/login Host=${DOMAIN} returned ${code}")
fi

# Backend still up? (helps distinguish nginx vs app)
bcode=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
  "http://127.0.0.1:8000/login" 2>/dev/null || echo "000")
if [[ "${bcode}" != "200" && "${bcode}" != "302" ]]; then
  reasons+=("backend :8000/login returned ${bcode} (nginx may be OK)")
fi

msg="nginx-watchdog $(ts): "
if [[ "${fail}" -eq 0 ]]; then
  msg+="OK (https_local=${code} backend=${bcode})"
  echo "${msg}" | tee -a "${LOG}" >/dev/null
  logger -t nginx-watchdog -p daemon.info "${msg}"
  rm -f "${ALERT_FLAG}"
  echo "$(ts) OK" >"${OK_FLAG}"
  exit 0
fi

detail=$(IFS='; '; echo "${reasons[*]}")
msg+="ALERT: ${detail}"
echo "${msg}" | tee -a "${LOG}" >/dev/null
logger -t nginx-watchdog -p daemon.err "${msg}"
echo "$(ts)" >"${ALERT_FLAG}"
echo "${detail}" >>"${ALERT_FLAG}"

# Best-effort mail (often undelivered without relay; still useful if mailx works)
if command -v mailx >/dev/null 2>&1; then
  printf '%s\n' "${msg}" | mailx -s "[${DOMAIN}] Nginx watchdog ALERT" root 2>/dev/null || true
fi

exit 1
