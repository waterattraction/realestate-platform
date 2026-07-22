#!/bin/bash
# Hold Nginx packages so unattended-upgrades cannot silently break the reverse proxy.
# Also blacklist them in /etc/apt/apt.conf.d/51realestate-nginx-hold.
#
# Usage:
#   sudo ./hold-nginx-packages.sh          # hold + blacklist
#   sudo ./hold-nginx-packages.sh unhold   # remove holds (blacklist file kept; edit/remove manually if needed)
set -euo pipefail

PKGS=(
  nginx
  nginx-core
  nginx-common
  libnginx-mod-http-geoip2
  libnginx-mod-http-image-filter
  libnginx-mod-http-xslt-filter
  libnginx-mod-mail
  libnginx-mod-stream
  libnginx-mod-stream-geoip2
)

MODE="${1:-hold}"
CONF=/etc/apt/apt.conf.d/51realestate-nginx-hold

if [[ "${MODE}" == "unhold" ]]; then
  echo "==> apt-mark unhold Nginx packages..."
  for p in "${PKGS[@]}"; do
    apt-mark unhold "$p" >/dev/null 2>&1 || true
    echo "  unheld: $p"
  done
  echo "==> Remaining holds:"
  apt-mark showhold | grep -E 'nginx|libnginx' || echo "  (none)"
  echo "Note: ${CONF} blacklist still active; remove that file to allow unattended upgrades."
  exit 0
fi

echo "==> apt-mark hold Nginx packages..."
for p in "${PKGS[@]}"; do
  if dpkg -l "$p" 2>/dev/null | grep -q '^ii'; then
    apt-mark hold "$p" >/dev/null
    echo "  held: $p"
  else
    echo "  skip (not installed): $p"
  fi
done

echo "==> Writing ${CONF}..."
cat >"${CONF}" <<'EOF'
// Real Estate platform — do not auto-upgrade Nginx (2026-07-22 outage: unattended nginx upgrade left service down).
// Manual upgrade: remove hold, upgrade carefully, restore /etc/nginx/sites-enabled/realestate.conf, then re-hold.
//   sudo /opt/realestate-platform/deploy/scripts/hold-nginx-packages.sh unhold
//   sudo apt upgrade nginx nginx-core nginx-common
//   sudo nginx -t && sudo systemctl reload nginx
//   sudo /opt/realestate-platform/deploy/scripts/hold-nginx-packages.sh
Unattended-Upgrade::Package-Blacklist {
    "nginx$";
    "nginx-core$";
    "nginx-common$";
    "libnginx-mod-.*";
};
EOF

echo "==> Current holds:"
apt-mark showhold | grep -E 'nginx|libnginx' || true
echo "Done."
