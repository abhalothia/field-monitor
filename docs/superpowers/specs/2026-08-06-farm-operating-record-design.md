# The Farm Operating Record

## Decision

AGRO CEO is farm-first. A farm is the one durable operating record that
connects people, field work, dated updates, evidence, and supply history.
Every view is a different useful cut of that same record; the product does
not create separate mini-products for farmers, workers, disease, or history.

## The one record

The farm profile opens as an in-place panel and always answers five questions:

1. **What is true now?** Active crop, review state, open accountable work,
   and the latest dated field update.
2. **Who is involved?** Reviewed growers and field workers, with their role
   and effective date. Reported source people remain explicitly reported and
   never become accounts.
3. **What changed?** A single chronological activity stream of reviewed field
   signals plus TrackWick source events. Each row declares its source and
   review state.
4. **What needs attention?** Open AGRO CEO actions first, then separate
   TrackWick tasks awaiting review.
5. **What is the context?** Historical procurement at village/variety/month
   level only. It is never attributed to an individual or a farm without a
   reviewed link.

The header is compact: farm name/place, reviewed or reported state, latest
activity date, and one next action. No generic KPIs and no map from source
coordinates.

## First release: one directory, one record

The first release has only two new product behaviours:

1. **Fields** becomes the useful directory: filter by reviewed/reported,
   place, crop, open work, and latest update.
2. Opening any result shows the **Farm Record** panel.

The Farm Record has four small sections: **Now**, **People**, **Updates**, and
**Context**. Farmers and field workers are links or labels inside People;
disease is a dated finding inside Updates; historical procurement is the
Context section. Nothing receives its own dashboard or separate data model.

Home and Actions simply link to the relevant Farm Record. Farmers remains a
lightweight finder until the farm record is proved useful. Settings retains
the muted **WhatsApp updates — Coming soon** row.

## Profile states and safety

There are only three honest layers:

- **Reviewed operating truth:** canonical farm, allocation, relationship,
  published geometry, and accountable work.
- **Reported TrackWick context:** candidate farm, source task/visit/activity,
  reference counts, reported people and field workers. It is not a farm
  boundary, login, completion, or recommendation.
- **Historical supply context:** aggregated purchase cohorts. It provides
  footprint, seasonality, and variety context only.

All APIs remain manager-only. They whitelist display fields and never return
phone numbers, provider IDs, raw forms/payloads, remote media URLs, source
coordinates, or credentials. A disease card appears only when a reviewed or
reported field finding includes a known classification; otherwise it is not
rendered. There is no “farm health” score.

## Data model and read models

No duplicate canonical tables are created.

- Existing `operational_blocks`, allocations, reviewed relationships, work,
  and field signals remain the reviewed layer.
- Existing TrackWick typed tables remain the reported source lane.
- Existing procurement cohorts remain history.
- New server-side profile DTOs compose those sources into bounded read models:
  `farm_record`, `person_context`, `farm_activity`, and `history_context`.

Every returned activity item has: `occurred_at`, `kind`, `state`
(`reviewed`/`reported`), farm/candidate reference, concise summary, owner or
reported actor label when safe, and a destination action. The browser does
not join raw records itself.

## Interaction

- A list row opens one side panel; opening another item replaces the panel.
- Filter state is visible, resettable, and URL-backed where practical.
- Date controls default to the last 30 days for live updates; history defaults
  to the published historical window.
- A reported event has only **Review in Farm Truth** as a state-changing path.
- A reviewed event may open its accountable action or field record.
- Empty states state which layer is absent and offer the next honest move.

## Delivery order

1. Extend the existing farm profile service with four safe sections: Now,
   People, Updates, and Context.
2. Add one manager-only Farm Record endpoint and bounded Fields filters.
3. Render the four sections in the existing in-place farm profile panel.
4. Make Home and Actions open the matching Farm Record where an ID exists.
5. Test redaction, state separation, filter bounds, date ordering, and empty
   paths; then deploy.

## Non-goals

- No inferred farms, disease diagnoses, ownership claims, or map markers.
- No automatic source-to-canonical promotion.
- No WhatsApp send/receive activation.
- No raw provider data in the browser.
