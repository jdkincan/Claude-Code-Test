#!/usr/bin/env bash
# Push the current checkout to the running VM and restart the app.
# Run from GCP Cloud Shell in the repo root:  bash deploy/update.sh
set -euo pipefail

ZONE="${ZONE:-us-central1-a}"
VM_NAME="${VM_NAME:-options-toolkit}"

echo "==> Copying app to $VM_NAME..."
gcloud compute ssh "$VM_NAME" --zone "$ZONE" --command "mkdir -p ~/options-toolkit"
gcloud compute scp --recurse --zone "$ZONE" --compress \
  app docs tests deploy requirements.txt run.py README.md \
  "$VM_NAME:~/options-toolkit/"

echo "==> Installing and restarting..."
gcloud compute ssh "$VM_NAME" --zone "$ZONE" --command '
  set -e
  sudo rsync -a --delete --exclude venv --exclude data --exclude deploy.env \
    ~/options-toolkit/ /opt/options-toolkit/
  sudo /opt/options-toolkit/venv/bin/pip install -q -r /opt/options-toolkit/requirements.txt
  sudo systemctl restart options-toolkit
  sudo systemctl --no-pager --lines=3 status options-toolkit'
echo "==> Updated."
