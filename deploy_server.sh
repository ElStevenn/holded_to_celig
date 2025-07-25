#!/usr/bin/env bash
set -euo pipefail

# ==== CONFIG ====
DOMAIN="integracion-luis.paumateu.com"
EMAIL="paumat17@gmail.com"
APP_DIR="/home/ubuntu/holded_to_celig"   # path with docker-compose.yml
SERVICE="app"                            # compose service name
PORT=8080                                # host-side port you mapped to localhost
WEBROOT="/var/www/letsencrypt"
ACME_PATH="${WEBROOT}/.well-known/acme-challenge"
NGINX_CONF="/etc/nginx/sites-available/${SERVICE}"
ENABLED="/etc/nginx/sites-enabled/${SERVICE}"
DOCKER_COMPOSE="docker compose"          # or "sudo docker compose" if root needed
# ==============

echo "▶ Building / starting container"
cd "$APP_DIR"
$DOCKER_COMPOSE build "$SERVICE"
$DOCKER_COMPOSE up -d "$SERVICE"

echo "▶ Preparing webroot for ACME"
sudo mkdir -p "$ACME_PATH"
sudo chown -R www-data:www-data "$WEBROOT"

echo "▶ Creating temporary HTTP vhost (ACME + proxy)"
sudo tee "$NGINX_CONF" >/dev/null <<EOF
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    location ^~ /.well-known/acme-challenge/ {
        alias ${ACME_PATH}/;
        default_type text/plain;
        try_files \$uri =404;
    }

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo ln -sf "$NGINX_CONF" "$ENABLED"
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "▶ Testing ACME path"
echo test | sudo tee "${ACME_PATH}/probe" >/dev/null
curl -fs "http://127.0.0.1/.well-known/acme-challenge/probe" >/dev/null \
  || { echo "✗ ACME path failed"; exit 1; }
sudo rm "${ACME_PATH}/probe"
echo "✔ ACME path OK"

echo "▶ Getting/renewing cert"
if [ -d "/etc/letsencrypt/live/${DOMAIN}" ]; then
  sudo certbot renew \
    --webroot -w "$WEBROOT" \
    --deploy-hook "systemctl reload nginx" \
    --non-interactive --agree-tos --email "$EMAIL" || true
else
  sudo certbot certonly --webroot -w "$WEBROOT" \
    --non-interactive --agree-tos \
    --email "$EMAIL" \
    --domain "$DOMAIN" \
    --domain "www.${DOMAIN}"
fi

echo "▶ Writing final HTTPS vhost + redirect"
sudo tee "$NGINX_CONF" >/dev/null <<EOF
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${DOMAIN} www.${DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo nginx -t
sudo systemctl reload nginx

echo "✅ Done: https://${DOMAIN}"
