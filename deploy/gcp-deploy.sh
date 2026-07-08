#!/usr/bin/env bash
# Deploy the Options Toolkit to a GCP free-tier e2-micro VM.
#
# Run from GCP Cloud Shell, in the repo root:
#   DOMAIN=myname-options.duckdns.org \
#   DUCKDNS_TOKEN=xxxxxxxx-xxxx-xxxx \
#   APP_PASSWORD='choose-a-strong-password' \
#   bash deploy/gcp-deploy.sh
#
# Optional: ZONE (default us-central1-a — free-tier eligible), VM_NAME.
set -euo pipefail

: "${DOMAIN:?set DOMAIN to your DuckDNS hostname, e.g. myname-options.duckdns.org}"
: "${DUCKDNS_TOKEN:?set DUCKDNS_TOKEN from https://www.duckdns.org}"
: "${APP_PASSWORD:?set APP_PASSWORD to the login password you want}"
ZONE="${ZONE:-us-central1-a}"
VM_NAME="${VM_NAME:-options-toolkit}"

PROJECT=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROJECT" ] || { echo "No GCP project set. Run: gcloud config set project YOUR_PROJECT_ID"; exit 1; }
echo "==> Project: $PROJECT  Zone: $ZONE  VM: $VM_NAME  Domain: $DOMAIN"

# --- VM (free tier: e2-micro in us-central1/us-east1/us-west1, 30GB pd-standard)
if ! gcloud compute instances describe "$VM_NAME" --zone "$ZONE" >/dev/null 2>&1; then
  echo "==> Creating VM..."
  gcloud compute instances create "$VM_NAME" \
    --zone "$ZONE" \
    --machine-type e2-micro \
    --image-family debian-12 --image-project debian-cloud \
    --boot-disk-size 30GB --boot-disk-type pd-standard \
    --tags http-server,https-server
  echo "==> Waiting for SSH to come up..."
  sleep 25
else
  echo "==> VM already exists, reusing it."
fi

# --- Firewall (idempotent; default network usually has these already)
for rule in "allow-http:tcp:80:http-server" "allow-https:tcp:443:https-server"; do
  IFS=: read -r name proto port tag <<< "$rule"
  gcloud compute firewall-rules describe "$name" >/dev/null 2>&1 || \
    gcloud compute firewall-rules create "$name" \
      --allow "$proto:$port" --target-tags "$tag" --direction INGRESS || true
done

# --- Copy the app and a private env file
echo "==> Copying app to VM..."
ENVFILE=$(mktemp)
chmod 600 "$ENVFILE"
cat > "$ENVFILE" <<EOF
DOMAIN=$DOMAIN
DUCKDNS_TOKEN=$DUCKDNS_TOKEN
APP_PASSWORD=$APP_PASSWORD
EOF
gcloud compute ssh "$VM_NAME" --zone "$ZONE" --command "rm -rf ~/options-toolkit && mkdir -p ~/options-toolkit"
gcloud compute scp --recurse --zone "$ZONE" --compress \
  app docs tests deploy requirements.txt run.py README.md \
  "$VM_NAME:~/options-toolkit/"
gcloud compute scp --zone "$ZONE" "$ENVFILE" "$VM_NAME:~/options-toolkit/deploy.env"
rm -f "$ENVFILE"

# --- Configure the VM (idempotent)
echo "==> Running VM setup (installs Caddy, python venv, systemd service)..."
gcloud compute ssh "$VM_NAME" --zone "$ZONE" --command "bash ~/options-toolkit/deploy/vm-setup.sh"

IP=$(gcloud compute instances describe "$VM_NAME" --zone "$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
echo
echo "==> Done. VM external IP: $IP (DuckDNS keeps $DOMAIN pointed at it automatically)"
echo "==> Give Caddy a minute to obtain the Let's Encrypt certificate, then open:"
echo "    https://$DOMAIN"
