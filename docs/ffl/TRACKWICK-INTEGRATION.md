# TrackWick integration

AGRO CEO connects to Fortune's TrackWick tenant as a **read-only, manager-triggered** source of field-operation context. It uses the verified TrackOlap EEP API V2 task stream, Customer CRM list, and productivity endpoint; it does not use the browser, write to TrackWick, or expose credentials to a manager session.

This is a source layer, not the manager's operating record. The precise
source-to-screen boundary is in [Operating architecture](OPERATING-ARCHITECTURE.md):
TrackWick may inform aggregate reach, farmer and field-worker candidates,
reported chemical activity, crop signals, and field-worker filing; it never
creates a canonical farm pin, reviewed farmer, land right, or automatic
diagnosis.

## Server configuration

Set these only in the deployment secret manager or server environment. Do not put values in source code, browser configuration, a database record, or a client-side `.env` file.

```text
FFL_DATABASE_URL=<private Supabase transaction-pooler DSN>
FFL_POSTGRES_SCHEMA=agro
FFL_MANAGER_PERSON_ID=<existing agro_people id for the accountable Fortune manager>
FFL_TRACKWICK_ENABLED=true
FFL_TRACKWICK_CUSTOMER_ID=<TrackWick customer id>
FFL_TRACKWICK_API_KEY=<TrackWick API key>
FFL_TRACKWICK_API_KEY_REFERENCE=env://FFL_TRACKWICK_API_KEY
FFL_TRACKWICK_TENANT_ID=fortune-paddy
FFL_TRACKWICK_REPORTING_TIMEZONE=Asia/Kolkata
# Optional: exact TrackWick form label for a human-reported low/moderate/high/critical field
FFL_TRACKWICK_SEVERITY_FORM_KEY=<exact form field label>
# Optional: exact form label for an approved plot-photo field; no guessed label is read
FFL_TRACKWICK_PLOT_PHOTO_FORM_KEY=<exact form field label>
```

Optional bounds are `FFL_TRACKWICK_TASK_PAGE_SIZE` (1–250, default 100), `FFL_TRACKWICK_TASK_MAX_PAGES` (1–1000, default 500), and `FFL_TRACKWICK_DELTA_LOOKBACK_DAYS` (1–31, default 2). The connector uses only these GET endpoints:

- `/cust/1/api/task/list`, for the approved Fortune task history;
- `/cust/1/api/customer/list`, for the Fortune Customer CRM;
- `/cust/1/api/asset/productivity`, for the current India reporting date.

Before the first refresh, apply the reviewed private migrations through
`0011_agro_trackwick_media_origin_check.sql` to the intended Supabase project.
Then provision the explicitly approved AGRO CEO staff through
`provision_initial_fortune_team`: Aakash Bhalothia and Ajay Bhalothia are
owners, and Daksh Bhatia is an admin. Each has the existing accountable
`operations_lead` role for source operations, while app access lives in the
separate `agro_access_memberships` table. A name alone does not create a login:
each identity remains pending until Fortune supplies a verified email and Auth
subject. The refresh fails closed if its owner is absent or has another role.

## What enters AGRO CEO

One task can safely become a farmer-task context row, completed visit, issue observation, reported pesticide event, crop context, safe follow-up, soil context, or farm candidate. Customer rows become farmer profiles; task assignment becomes basic field-worker context. Productivity rows create attendance and active field-worker context. The manager-only endpoints are:

- `POST /api/v1/trackwick/refresh`
- `GET /api/v1/trackwick/health`
- `GET /api/v1/trackwick/metrics`
- `GET /api/v1/trackwick/board`
- `GET /api/v1/trackwick/command-centre-board`

The refresh is manual and manager-authorized. Its published records are source context only; farmer, farm, and field-worker basics remain candidates until reviewed. They never create a canonical farm, complete work, make a pesticide recommendation, or create an agronomic/compliance verdict.

### Candidate evidence used by Farm Truth

Farm Truth discovery reads only the already-ingested typed private tables. One
candidate is one exact completed registration plus one exact registered plot,
from the same enabled TrackWick source, with:

- a valid completed registration task and completed registration;
- a valid linked farmer party;
- positive reported plot area, or positive registration total area as the
  explicit fallback;
- at least one valid completed Farmer Visit observed inside the manager's
  selected season; and
- valid in-season visits and linked open work as supporting evidence, including
  a field-worker candidate only when those typed tasks support that worker.

The candidate card uses only generated labels, bounded counts, display names,
explicit village/block/district and Gata context, reported area, registration
timing, crop timing, crop stage, and transparent reason chips. Discovery does
not fetch fresh provider data and does not write to any TrackWick evidence
table.

The separate private evidence lane retains only the extra source facts needed
for a useful private evidence board and later review: customer/registration
mobiles in a restricted contact vault, typed tasks/visits/plots, exact source
points, and remote crop/plot-photo references from TrackWick's approved image host.
It marks registration/CRM points as declared and task/visit/photo points as
observed. Those pins are never farm boundaries, and a refresh never copies a
photo or sends private evidence to the browser.

`/board` and `/command-centre-board` are manager-only browser projections, not
private evidence exports. They contain only named reported farmers, reported
farm candidates, redacted source-work labels/dates, and photo *counts*. They
never serialise field workers, maps or GPS/location values, contacts,
source/provider IDs or statuses, raw forms, addresses, remote image URLs, or
image bytes. Exact source points and worker context remain server-internal
evidence for the reviewed Farm Truth workflow; they never become a field
boundary or verified Fortune farm.

Severity stays `unknown` unless Fortune explicitly adds a low/moderate/high/critical field to the Farmer Visit form and supplies its exact label in `FFL_TRACKWICK_SEVERITY_FORM_KEY`. AGRO CEO never infers severity from a pest or disease name. New submissions then carry the field worker's stated severity; existing source records remain unchanged.

The manager's **Refresh** control invokes this source refresh after manager
access is unlocked, then reloads the same TrackWick metrics. The first successful
run is a one-time historical baseline, because honest coverage needs the full
known farmer-task population. Later refreshes use TrackWick's verified
epoch-millisecond `createDateBegin` / `createDateEnd` filters over an overlapping
two-India-day window. It is a visible server pull—not a hidden
browser-to-provider connection—and every run carries its sync scope,
received/accepted counts, and safe health state in the private database.

The initial historical baseline can take longer than a browser-facing function
budget. Run it from a private worker or the reviewed direct operator path; do
not shorten history, weaken the data model, or expose provider access to the
browser. Routine two-day pulls are materially smaller.

## What is deliberately discarded

The CRM-basics lane retains a farmer or field-worker **name** only with its
stable TrackWick identifier; that is the minimum needed to review a real
person. A farmer is otherwise represented by TrackWick's opaque
`customerIden`. If an older task omits that field but has the verified Fortune
shape `FC-01734 (Farmer Name)`, the connector retains only `FC-01734`; a name
alone is rejected. Village, block, district, reported acreage, and crop timing
are retained only when they come from their reviewed, explicit form fields.

Both lanes discard Aadhaar numbers and images, family details, signatures,
email, free-text comments, unknown photo labels, raw `formDetails`, task URLs,
and the customer/API credentials. The private lane keeps an approved photo as
a remote reference only: no copied bytes, EXIF extraction, or AI
interpretation occurs during sync.

The Farm Truth candidate, decision response, canonical record, and map path
intentionally exclude all of the following, even when the private evidence
lane retained a typed reference for restricted source operations:

- phone numbers and other contact values;
- Aadhaar numbers or Aadhaar-derived material;
- raw GPS coordinates, provider addresses, and geo-address text;
- source media, media URLs, image bytes, and EXIF data; and
- raw form text, free-text answers, raw payloads, provider identifiers, and
  credentials.

On `Accept`, one transaction creates the canonical parcel/block/allocation,
dated right, scoped grower relationship, and optional supported field-worker
relationship. It also creates private `reviewed` source links from the farmer
and optional worker parties to canonical people, from the exact source plot to
the canonical parcel/block, and from the selected supporting tasks to the crop
allocation. One private audit event records the case transition and the source
receipt IDs needed to trace the decision. Those links and audit metadata are
server-side provenance; they are not returned by Farm Truth list/detail or
decision responses. The underlying TrackWick evidence is not changed.

`Needs evidence` records the constrained missing-evidence kind, reason,
reviewer, owner, and review time on the private case so it can remain
accountable in Inbox. `Reject` records its reason, reviewer, and review time.
Neither decision creates a parcel, block, allocation, relationship, right,
reviewed source link, or acceptance audit event.

TrackWick does not provide an authoritative territory owner, purchase commitment, collection/weighbridge record, grade, lot, residue test, or EU-compliance result. Those require their own reviewed Fortune sources. A pesticide record is a review cue, never proof that the crop is compliant.
