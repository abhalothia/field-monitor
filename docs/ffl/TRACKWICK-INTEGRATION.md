# TrackWick integration

AGRO CEO connects to Fortune's TrackWick tenant as a **read-only, manager-triggered** source of field-operation context. It uses the verified TrackOlap EEP API V2 task stream and productivity endpoint; it does not use the browser, write to TrackWick, or expose credentials to a manager session.

This is a source layer, not the manager's operating record. The precise
source-to-screen boundary is in [Operating architecture](OPERATING-ARCHITECTURE.md):
TrackWick may inform aggregate reach, reported chemical activity, crop signals,
and field-worker filing; it never creates a farm pin, reviewed farmer, or
automatic diagnosis.

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
```

Optional bounds are `FFL_TRACKWICK_TASK_PAGE_SIZE` (1–250, default 100), `FFL_TRACKWICK_TASK_MAX_PAGES` (1–1000, default 500), and `FFL_TRACKWICK_DELTA_LOOKBACK_DAYS` (1–31, default 2). The connector uses only these GET endpoints:

- `/cust/1/api/task/list`, filtered to the approved `Farmer Visit` form;
- `/cust/1/api/asset/productivity`, for the current India reporting date.

Before the first refresh, apply the reviewed private migrations through
`0007_agro_field_capture.sql` to the intended Supabase project and create the
real accountable Fortune manager in `agro_people` with the role
`farm_manager`, `operations_lead`, or `agronomist`. The refresh will fail
closed if that owner is absent or has another role; it never creates a
fictional person to make a dashboard look populated.

## What enters AGRO CEO

One task can safely become a farmer-task context row, completed visit, issue observation, and reported pesticide event. Productivity rows create attendance and active field-worker context. The manager-only endpoints are:

- `POST /api/v1/trackwick/refresh`
- `GET /api/v1/trackwick/health`
- `GET /api/v1/trackwick/metrics`

The refresh is manual and manager-authorized. Its published records are aggregate source context only; they never create farms, complete work, make a pesticide recommendation, or create an agronomic/compliance verdict.

Severity stays `unknown` unless Fortune explicitly adds a low/moderate/high/critical field to the Farmer Visit form and supplies its exact label in `FFL_TRACKWICK_SEVERITY_FORM_KEY`. AGRO CEO never infers severity from a pest or disease name. New submissions then carry the field worker's stated severity; existing source records remain unchanged.

The manager's **Refresh** control invokes this source refresh after manager
access is unlocked, then reloads the same TrackWick metrics. The first successful
run is a one-time historical baseline, because honest coverage needs the full
known farmer-task population. Later refreshes use TrackWick's verified
epoch-millisecond `createDateBegin` / `createDateEnd` filters over an overlapping
two-India-day window. It is a visible server pull—not a hidden
browser-to-provider connection—and every run carries its sync scope,
received/accepted counts, and safe health state in the private database.

The Vercel function allows 60 seconds for the initial baseline; the verified
current baseline takes roughly 25 seconds upstream. Routine two-day pulls are
materially smaller. If the tenant grows beyond that budget, run the same
server-only refresh from a private worker instead of weakening the data model
or exposing provider access to the browser.

## What is deliberately discarded

The connector never persists or returns farmer names, mobile numbers, email, photos, exact GPS, address geometry, raw `formDetails`, task URLs, or the customer/API credentials. A farmer is represented by TrackWick's opaque `customerIden`; village is retained only when it is explicitly supplied as a coarse field-form value.

TrackWick does not provide an authoritative territory owner, purchase commitment, collection/weighbridge record, grade, lot, residue test, or EU-compliance result. Those require their own reviewed Fortune sources. A pesticide record is a review cue, never proof that the crop is compliant.
