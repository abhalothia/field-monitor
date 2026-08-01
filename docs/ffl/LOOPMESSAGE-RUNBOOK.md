# LoopMessage production runbook

Run communications maintenance only on the private Hetzner FFL host. It is a
local bounded command, never a public API endpoint:

```bash
python -m ffl.communications.worker --once
```

Do not deploy the live LoopMessage worker or receiving webhook on Vercel,
another serverless/preview runtime, a browser client, or a developer laptop
holding production secrets. The private Hetzner webhook service only durably
accepts a sealed receipt and responds; the Hetzner worker performs later
processing.

## Private environment file

Create `/etc/ffl/communications-worker.env` as `root:root` with `0600` mode:

```ini
FFL_DATABASE_PATH=/srv/ffl/data/ffl.db
FFL_EVIDENCE_DIR=/srv/ffl/evidence
FFL_COMMUNICATION_RECEIPT_KEY=<private receipt key>
FFL_LOOPMESSAGE_ORGANIZATION_API_KEY=<organization API key>
FFL_COMMUNICATION_ALERT_WEBHOOK_URL=https://alerts.example.invalid/ffl
FFL_COMMUNICATION_ALERT_AUTHORIZATION=<optional alert authorization header>
```

No real values belong in Git, test data, seed data, Vercel configuration, logs,
or this runbook. Alert payloads contain counts only—never contacts, field text,
attachment URLs, ciphertext, or provider payloads.

## Schedule and authorization

Use the checked-in `deploy/hetzner/ffl-communications-worker.service` and
`.timer` templates. Replace only the installation paths; do not add secrets to
the unit file. Run as the dedicated unprivileged `ffl-communications` user.

```bash
sudo install -m 0644 deploy/hetzner/ffl-communications-worker.service /etc/systemd/system/
sudo install -m 0644 deploy/hetzner/ffl-communications-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ffl-communications-worker.timer
```

Limit manual runs to a named operations group through a narrow sudo rule for
`systemctl start ffl-communications-worker.service`; no public worker trigger
is permitted. The timer runs every minute and alerts when unknown deliveries,
retryable receipts, or terminal media-retention failures exist.
