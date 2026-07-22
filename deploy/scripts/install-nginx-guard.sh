#!/bin/bash
# Install Nginx hold + watchdog timer + apt post-invoke hook.
set -euo pipefail

REPO="/opt/realestate-platform"
SCRIPTS="${REPO}/deploy/scripts"
SYSTEMD_SRC="${REPO}/deploy/systemd"

chmod +x \
  "${SCRIPTS}/hold-nginx-packages.sh" \
  "${SCRIPTS}/nginx-watchdog.sh" \
  "${SCRIPTS}/nginx-apt-post-invoke.sh" \
  "${SCRIPTS}/install-nginx-guard.sh"

echo "==> Hold packages + unattended blacklist"
"${SCRIPTS}/hold-nginx-packages.sh"

echo "==> Install apt post-invoke hook"
cat >/etc/apt/apt.conf.d/99realestate-nginx-watchdog <<EOF
DPkg::Post-Invoke { "${SCRIPTS}/nginx-apt-post-invoke.sh"; };
EOF

echo "==> Install systemd timer"
cp "${SYSTEMD_SRC}/nginx-watchdog.service" /etc/systemd/system/nginx-watchdog.service
cp "${SYSTEMD_SRC}/nginx-watchdog.timer" /etc/systemd/system/nginx-watchdog.timer
systemctl daemon-reload
systemctl enable --now nginx-watchdog.timer

echo "==> Run watchdog once"
"${SCRIPTS}/nginx-watchdog.sh" || true

echo "==> Status"
systemctl status nginx-watchdog.timer --no-pager | head -15
apt-mark showhold | grep -E 'nginx|libnginx' || true
echo "Alert flag (if any): /var/lib/nginx-watchdog/ALERT"
echo "Log: /var/log/nginx-watchdog.log"
echo "Done."
