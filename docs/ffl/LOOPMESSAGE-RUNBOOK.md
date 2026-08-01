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
FFL_LOOPMESSAGE_WEBHOOK_AUTHORIZATION=<exact Authorization value configured in LoopMessage dashboard>
FFL_LOOPMESSAGE_SENDER_ID=<dedicated WhatsApp-capable LoopMessage sender id>
FFL_LOOPMESSAGE_WHATSAPP_CHANNEL_ENABLED=true
FFL_LOOPMESSAGE_WHATSAPP_CAPABILITY_PROOF=sandbox-verified
FFL_LOOPMESSAGE_WHATSAPP_CAPABILITY_PROOF_REF=<reviewed sandbox evidence ref>
FFL_COMMUNICATION_ALERT_WEBHOOK_URL=https://alerts.example.invalid/ffl
FFL_COMMUNICATION_ALERT_AUTHORIZATION=<optional alert authorization header>
```

No real values belong in Git, test data, seed data, Vercel configuration, logs,
or this runbook. Alert payloads contain counts only—never contacts, field text,
attachment URLs, ciphertext, or provider payloads.

## WhatsApp capability gate

FFL is WhatsApp-only. It never leaves `channel` unset for a work prompt, so
LoopMessage cannot silently choose iMessage, SMS, or RCS. A send requires all
of the following at runtime: the organization key, a dedicated sender ID,
`FFL_LOOPMESSAGE_WHATSAPP_CHANNEL_ENABLED=true`, the literal
`FFL_LOOPMESSAGE_WHATSAPP_CAPABILITY_PROOF=sandbox-verified`, and a non-empty
immutable validation reference. A true flag by itself does nothing.

All of the organization key, dashboard webhook authorization, sender ID,
enabled flag, proof literal, and proof reference must be present before FFL
accepts real inbound or outbound LoopMessage traffic; an absent value or failed
proof fails closed.

Before setting those variables for a live account, a named FFL operator must
record an account-level sandbox proof that the configured sender accepts
`channel: whatsapp`, can use the selected externally approved WhatsApp
template, and produces a status/callback that can be associated through FFL's
passthrough ID. Use a non-production test contact and the LoopMessage dashboard
for this controlled proof; do not use an operator's production work prompt. Put
the signed-off ticket/record ID in `FFL_LOOPMESSAGE_WHATSAPP_CAPABILITY_PROOF_REF`.

LoopMessage's current public webhook channel documentation lists iMessage, SMS,
and RCS rather than WhatsApp. Therefore FFL accepts no inbound delivery before
this account-level proof exists. After it exists, an omitted inbound `channel`
is tolerated for the documented schema variance, but a supplied channel must
be exactly `whatsapp`; any other value is quarantined with HTTP 200 and never
enters the candidate workflow.

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
