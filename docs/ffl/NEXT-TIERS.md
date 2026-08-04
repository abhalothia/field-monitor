# Fortune next tiers

This is the smallest sequence that turns the deployed operating surface into a
real Fortune programme tool. A tier is complete only when its final operating
action works with production data. It is not complete when the screen exists.

## Tier 0 — stable private manager surface — complete

The manager application is deployed from `main` to Vercel. The server's
dedicated `agro_vc_runtime` role can read and update the existing private
operating lane without receiving browser, delete, DDL, or migration authority.
The live launch login and portfolio now return `200`; the prior production
permission error is gone.

This tier deliberately does **not** mean that a source row becomes a Fortune
farm, farmer, worker, crop fact, purchase fact, or compliance claim. Those
need the reviewed relationships and evidence described below.

## Tier 1 — make the Fortune portal usable — next

**Outcome:** an invited Fortune staff member can sign in with their own phone
at `fortune.agroceo.com`; their role, rather than a shared password, decides
whether they can use the manager surface.

1. Attach `fortune.agroceo.com` (or a carefully reviewed wildcard) to the
   existing Vercel `agro-ceo` project and complete the DNS records Vercel
   supplies. The customer record is already active in the private database;
   DNS must point to the same running project before the hostname can resolve.
2. Set the portal's Production-only encrypted variables: base domain, session
   secret and max age, Supabase URL and publishable key, and OTP channel. Keep
   the existing database role and launch password server-side.
3. Enable Supabase Phone Auth and an approved delivery provider. Start with
   SMS; choose WhatsApp only after the provider, template/India regulatory
   requirements, cost, rate limits, and fallback are explicitly approved.
4. Invite the three named Fortune operators only after they provide or confirm
   their own mobile number and consent to this sign-in method. Do not copy a
   number out of TrackWick into identity data. The two Bhalothias are owners;
   Daksh is an admin.
5. Run a short role test: owner/admin reaches `/manager`; a test farmer or
   field-worker account sees only their own portal and cannot fetch manager
   data. Record who performed it and remove any setup token immediately.

**Gate:** this is a configuration task, not more frontend work. The current
Vercel integration can inspect projects, deployments, logs, and domains but
does not expose a mutation for attaching a domain or setting encrypted
environment variables. Those two actions must happen in the Vercel dashboard
or via an authenticated Vercel CLI/API credential with that scope.

## Tier 2 — prove three Fortune operating loops

**Outcome:** each company goal has one visible decision, one accountable
person, and a source-backed result. Build one narrow vertical slice at a time.

| Loop | First durable record | Manager sees | Never imply |
|---|---|---|---|
| Purchase capture | reviewed seasonal harvest estimate and Fortune procurement/weighbridge record, both linked to the same reviewed farmer/field/crop | purchase-share coverage, unmatched records, and owner of the next match | market share or 100% purchase share when either side is unknown |
| Export-ready chemical proof | approved crop-kit/schedule version plus a reported application, field/crop link, actor, time, and evidence reference | exceptions needing review and missing proof | residue clearance, EU compliance, or a treatment recommendation |
| Earlier intervention | source field signal linked to a field/crop, followed by assigned work, proof, and a human-reviewed outcome | a small action ledger: what changed, who owns it, and whether proof arrived | diagnosis, cure, or success merely because someone filed a visit |

The existing TrackWick read lane is context for these loops; it is not the
system-of-record for a reviewed identity, boundary, purchase, or compliance
fact. Sources must retain their external IDs, timestamps, raw payload
fingerprints, source precision, and review state. The manager screen should
continue to show **reach** rather than a fabricated outcome when the numerator
or denominator is missing.

**Gate:** demonstrate one real linked example for each loop in a single
season, then expand. No bulk import to make charts look full.

## Tier 3 — give people a useful view of their own work

**Outcome:** a farmer or field worker sees a small, safe history that answers
their immediate question without exposing the programme.

- A **field worker** sees their assigned work, the visit they submitted, what
  evidence is still needed, and the next due action.
- A **farmer** sees only their reviewed farm/field/crop relationship,
  confirmed visit history, and later their own confirmed procurement history.
- A **manager** continues to see the shared Fortune operating surface.

Every portal screen resolves access from a verified phone identity plus a
current reviewed membership. It never grants a view because a TrackWick name,
contact row, phone, or farmer code looks similar. Start with a small Hindi
pilot whose copy is completely Hindi where Hindi is selected, then add offline
capture only after the data model and conflict behaviour are tested.

**Gate:** a farmer/worker test account must be unable to request another
person's URL, map location, contact data, or manager route.

## Later, not now — image intelligence

When Fortune elects to discuss it, a photo intake lane can first preserve the
original, EXIF/GPS precision, capture time, consent, attachment checksum, and
human review state. Image AI may then create a *reviewable observation* tied
to the image; it must never silently alter a farm fact, diagnose a crop, or
recommend chemical use. This needs its own accuracy, consent, retention, and
human-approval gates before it is enabled.

## Rule for every future tier

Add a screen only when it makes one decision faster or safer. Every number
names its source, scope, time window, and what it does not prove. Every new
automation has a named human who can correct it.
