#!/bin/bash
# jiakubo.com HTTPS 一键启用（需先在阿里云安全组放行 80/443）
set -euo pipefail

DOMAIN="jiakubo.com"
REPO="/opt/realestate-platform"
EMAIL="admin@jiakubo.com"

echo "==> 检查 80 端口外网可达性..."
if ! curl -sf --connect-timeout 5 "http://${DOMAIN}/" >/dev/null; then
  echo "ERROR: 外网无法访问 http://${DOMAIN}/"
  echo "请先在阿里云安全组放行入方向 TCP 80、443，然后重试。"
  exit 1
fi

echo "==> 申请 Let's Encrypt 证书..."
sudo certbot certonly --webroot -w /var/www/certbot \
  -d "${DOMAIN}" --non-interactive --agree-tos -m "${EMAIL}" \
  --deploy-hook "systemctl reload nginx"

if [ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
  echo "ERROR: 证书申请失败，查看 /var/log/letsencrypt/letsencrypt.log"
  exit 1
fi

echo "==> 部署 HTTPS Nginx 配置..."
sudo cp "${REPO}/deploy/nginx/realestate-jiakubo.conf" /etc/nginx/sites-available/realestate.conf
sudo nginx -t
sudo systemctl reload nginx

echo "==> 配置导入接口基础认证（如尚未配置）..."
if [ ! -f /etc/nginx/.htpasswd-ingestion ]; then
  PASS=$(openssl rand -base64 12)
  echo "ingestion:${PASS}" | sudo tee /root/.ingestion-htpasswd-credentials >/dev/null
  sudo apt-get install -y apache2-utils >/dev/null 2>&1 || true
  echo "ingestion:$(openssl passwd -apr1 "${PASS}")" | sudo tee /etc/nginx/.htpasswd-ingestion >/dev/null
  sudo chmod 640 /etc/nginx/.htpasswd-ingestion
  echo "导入接口凭据已写入 /root/.ingestion-htpasswd-credentials"
fi

echo "==> 启用 UFW 防火墙..."
sudo ufw --force reset >/dev/null 2>&1 || true
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo ""
echo "完成！请访问: https://${DOMAIN}/"
echo "导入接口: https://${DOMAIN}/ingestion/pipeline （需 Basic Auth）"
