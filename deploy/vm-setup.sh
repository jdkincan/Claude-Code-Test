#!/usr/bin/env bash
# Configure the VM to serve the Options Toolkit. Idempotent — safe to re-run.
# Expects the repo at ~/options-toolkit with a deploy.env file
# (DOMAIN, DUCKDNS_TOKEN, APP_PASSWORD) beside it. Run by gcp-deploy.sh.
set -euo pipefail

SRC="$HOME/options-toolkit"
APP_DIR=/opt/options-toolkit
DATA_DIR=/var/lib/options-toolkit
ENV_FILE=/etc/options-toolkit.env

# shellcheck disable=SC1091
source "$SRC/deploy.env"
: "${DOMAIN:?}" ; : "${DUCKDNS_TOKEN:?}" ; : "${APP_PASSWORD:?}"
SUBDOMAIN="${DOMAIN%%.duckdns.org}"

echo "==> Installing packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip sqlite3 rsync \
  debian-keyring debian-archive-keyring apt-transport-https curl gnupg

if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -qq && sudo apt-get install -y -qq caddy
fi

echo "==> Installing app to $APP_DIR..."
sudo mkdir -p "$APP_DIR" "$DATA_DIR" "$DATA_DIR/backups"
sudo rsync -a --delete --exclude venv --exclude data --exclude deploy.env "$SRC/" "$APP_DIR/"
[ -d "$APP_DIR/venv" ] || sudo python3 -m venv "$APP_DIR/venv"
sudo "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

sudo useradd --system --no-create-home --shell /usr/sbin/nologin options 2>/dev/null || true
sudo chown -R options:options "$DATA_DIR"

echo "==> Writing env + systemd service..."
if [ ! -f "$ENV_FILE" ]; then
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
else
  SECRET_KEY=$(sudo grep '^SECRET_KEY=' "$ENV_FILE" | cut -d= -f2)
fi
sudo tee "$ENV_FILE" >/dev/null <<EOF
APP_PASSWORD=$APP_PASSWORD
SECRET_KEY=$SECRET_KEY
PORTFOLIO_DATA_DIR=$DATA_DIR
EOF
sudo chmod 600 "$ENV_FILE"

sudo tee /etc/systemd/system/options-toolkit.service >/dev/null <<EOF
[Unit]
Description=Options Toolkit web app
After=network.target

[Service]
User=options
EnvironmentFile=$ENV_FILE
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now options-toolkit
sudo systemctl restart options-toolkit

echo "==> Configuring Caddy for https://$DOMAIN..."
sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
$DOMAIN {
    reverse_proxy 127.0.0.1:8000
}
EOF
sudo systemctl reload caddy || sudo systemctl restart caddy

echo "==> DuckDNS updater (keeps the domain pointed at this VM's ephemeral IP)..."
sudo tee /usr/local/bin/duckdns-update.sh >/dev/null <<EOF
#!/usr/bin/env bash
# Uses DuckDNS's IP auto-detect; VM has no static IP (free tier).
curl -fsS "https://www.duckdns.org/update?domains=$SUBDOMAIN&token=$DUCKDNS_TOKEN&ip=" >/dev/null
EOF
sudo chmod 700 /usr/local/bin/duckdns-update.sh
sudo /usr/local/bin/duckdns-update.sh
echo "*/5 * * * * root /usr/local/bin/duckdns-update.sh" | sudo tee /etc/cron.d/duckdns >/dev/null

echo "==> Nightly SQLite backup (14-day rotation in $DATA_DIR/backups)..."
sudo tee /usr/local/bin/options-backup.sh >/dev/null <<EOF
#!/usr/bin/env bash
set -e
[ -f $DATA_DIR/portfolio.db ] || exit 0
sqlite3 $DATA_DIR/portfolio.db ".backup $DATA_DIR/backups/portfolio-\$(date +%F).db"
find $DATA_DIR/backups -name 'portfolio-*.db' -mtime +14 -delete
EOF
sudo chmod 755 /usr/local/bin/options-backup.sh
echo "0 3 * * * root /usr/local/bin/options-backup.sh" | sudo tee /etc/cron.d/options-backup >/dev/null

rm -f "$SRC/deploy.env"
echo "==> Setup complete. App service status:"
sudo systemctl --no-pager --lines=3 status options-toolkit || true
