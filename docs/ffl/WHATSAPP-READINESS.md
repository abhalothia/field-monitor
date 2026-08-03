# WhatsApp readiness report

`ffl.communications.readiness` is a pure, manager-safe configuration report
for the FFL LoopMessage lane. It does not read an environment, call a provider,
or inspect/send any message. Its response has only booleans, stable gap codes,
and the provider name; it never includes credentials, sender/contact addresses,
receipt data, provider message IDs, media URLs, or message content.

This is a close-the-loop dispatch, evidence, and ownership readiness check. It
does not replace existing Trackolap/Streamlit detection, coverage, or hotspot
analytics; reviewed signals from those systems may later create FFL work, while
their analytics remain separately attributable.

The report is fail-closed. Both real inbound and real outbound remain ineligible
until every check is true:

- organization API access is configured;
- dashboard webhook authorization is configured;
- the private receipt key is configured;
- the dedicated FFL sender is configured;
- the WhatsApp-only channel gate is enabled;
- a reviewed `sandbox-verified` capability proof and its immutable reference
  are present; and
- the private FFL recovery worker is attested as installed and scheduled.

`private_worker_attested` is a deployment-owned input. It must be supplied
only by trusted deployment composition after the private Hetzner worker service
and its timer are installed; it must not come from an HTTP request, browser, or
Vercel/preview environment.

## Future manager route integration

No route is added by this change. When browser manager authentication exists,
the server composition root may add a manager-only `GET
/api/v1/communications/readiness` route. It should:

1. use `Depends(require_manager)`;
2. build `WhatsAppReadinessConfig.from_loopmessage_provider` from
   `request.app.state.communication_provider`, the *boolean* presence of the
   receipt key, and a deployment-owned worker attestation; and
3. return `whatsapp_readiness(config)` directly.

It must not return a raw provider object or read/send/update provider state.
The separate LoopMessage dashboard authorization remains solely for the
provider webhook; it is not manager authentication.

For the private deployment and WhatsApp sender-proof procedure, use the
canonical [LoopMessage runbook](LOOPMESSAGE-RUNBOOK.md).
