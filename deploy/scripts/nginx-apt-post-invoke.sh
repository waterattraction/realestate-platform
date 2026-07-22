#!/bin/bash
# dpkg/apt post-invoke: if nginx packages were touched, ensure service is healthy.
# Installed as /etc/apt/apt.conf.d/99realestate-nginx-watchdog via install script.
set -euo pipefail

LOG=/var/log/nginx-watchdog.log
ts=$(date '+%Y-%m-%d %H:%M:%S %z')

if ! dpkg -l nginx-core 2>/dev/null | grep -q '^ii'; then
  exit 0
fi

if ! systemctl is-active --quiet nginx 2>/dev/null; then
  msg="apt-post-invoke ${ts}: nginx inactive after apt — attempting start"
  echo "${msg}" >>"${LOG}"
  logger -t nginx-watchdog -p daemon.err "${msg}"
  systemctl start nginx 2>>"${LOG}" || true
fi

if ! nginx -t >/dev/null 2>&1; then
  msg="apt-post-invoke ${ts}: nginx -t FAILED after apt"
  echo "${msg}" >>"${LOG}"
  logger -t nginx-watchdog -p daemon.err "${msg}"
  exit 0
fi

# Run full watchdog once after apt (non-fatal)
/opt/realestate-platform/deploy/scripts/nginx-watchdog.sh >>"${LOG}" 2>&1 || true
