# Deploying to GCP (free-tier VM + HTTPS + password)

Runs the toolkit 24/7 on a free `e2-micro` VM with a real HTTPS certificate
and the app's built-in password login, reachable from any browser (including
a locked-down work laptop). Total cost: ~$0/month (free tier covers the VM
and disk; egress at personal-use volumes rounds to zero).

Architecture: `browser → Caddy (HTTPS, Let's Encrypt) → uvicorn on localhost
→ SQLite on the VM disk`. A cron keeps your DuckDNS hostname pointed at the
VM's ephemeral IP (avoids the ~$3.60/mo static-IP fee), and a nightly cron
backs up the database with 14-day rotation.

## One-time setup (~10 minutes)

### 1. Create a DuckDNS hostname (2 min)

1. Go to <https://www.duckdns.org> and sign in (Google login works).
2. Add a subdomain, e.g. `yourname-options` → your hostname is
   `yourname-options.duckdns.org`.
3. Copy your **token** from the top of the DuckDNS page.

### 2. Deploy from Cloud Shell (5 min)

1. Open <https://console.cloud.google.com> → click the **Cloud Shell** icon
   (`>_`, top right). Make sure a project is selected (`gcloud config
   set project YOUR_PROJECT_ID` if not).
2. Clone the repo and run the deploy script — each line is a separate
   command (mobile-friendly; the script prompts for your DuckDNS domain,
   token, and app password one at a time):

   ```bash
   git clone https://github.com/jdkincan/Claude-Code-Test.git
   cd Claude-Code-Test
   git checkout claude/personal-brokerage-options-l5x5so
   bash deploy/gcp-deploy.sh
   ```

   (Cloning a private repo in Cloud Shell: use a GitHub personal access
   token when prompted, or `gh auth login`.)

   Non-interactive alternative: pass the values as env vars instead of
   answering prompts —
   `DOMAIN=... DUCKDNS_TOKEN=... APP_PASSWORD=... bash deploy/gcp-deploy.sh`.

3. Wait ~1 minute after the script finishes for Caddy to obtain the
   certificate, then open **`https://yourname-options.duckdns.org`** and log
   in with your `APP_PASSWORD`.

### 3. Smoke check

```bash
curl -I https://yourname-options.duckdns.org        # expect HTTP/2 303 (redirect to /login)
```

## Updating the app later

From Cloud Shell, in the repo directory:

```bash
git pull
bash deploy/update.sh
```

## Operations

| Task | Command (Cloud Shell) |
|---|---|
| SSH into the VM | `gcloud compute ssh options-toolkit --zone us-central1-a` |
| App logs | `sudo journalctl -u options-toolkit -f` (on the VM) |
| Caddy/TLS logs | `sudo journalctl -u caddy -f` (on the VM) |
| Restart app | `sudo systemctl restart options-toolkit` (on the VM) |
| Change password | edit `/etc/options-toolkit.env` on the VM, then restart |
| Backups | nightly to `/var/lib/options-toolkit/backups/`, 14-day rotation |
| Restore a backup | stop app; copy backup over `/var/lib/options-toolkit/portfolio.db`; start app |

Optional off-VM backups: create a GCS bucket and add to the backup cron on
the VM: `gsutil cp /var/lib/options-toolkit/backups/portfolio-$(date +%F).db gs://YOUR_BUCKET/`
(grant the VM's service account Storage Object Creator).

## Security notes

- Two layers: TLS via Caddy/Let's Encrypt, plus the app's session login
  (`APP_PASSWORD`). There is no account lockout — pick a long password.
- Ports 80/443 are the only ones open; the app itself listens on localhost
  only. SSH goes through Google's IAP-backed `gcloud compute ssh`.
- The VM auto-restarts the app on crash (`Restart=always`) and survives
  reboots (`systemctl enable`).
