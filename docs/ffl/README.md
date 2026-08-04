# AGRO CEO for Fortune Rice

AGRO CEO is Fortune Rice's private operating surface for seeing the field
programme clearly and making the next move. It is deliberately small: it does
not try to turn a visit log, a source export, or an AI summary into a second
farm-management system.

The product has one promise:

> Know what is growing where, what changed, who owns the next move, and what
> proof supports it.

## Start here

| If you need to understand… | Read… |
|---|---|
| The product, its objects, data boundaries, and six-view manager experience | [Operating architecture](OPERATING-ARCHITECTURE.md) |
| The durable domain model and evidence rules | [System spine](PRD-SYSTEM-SPINE.md) |
| The minimum real farm data needed to begin | [Data foundation](DATA-FOUNDATION.md) and [Farm manifest import](FARM-MANIFEST-IMPORT.md) |
| How TrackWick context is read, normalised, and kept private | [TrackWick integration](TRACKWICK-INTEGRATION.md) |
| What is actually present in the live Fortune TrackWick tenant | [Live TrackWick inventory](TRACKWICK-LIVE-INVENTORY.md) |
| How to measure Fortune purchase share without retaining grower identities | [Purchase capture](PURCHASE-CAPTURE.md) |
| What is live, what must be configured next, and the three future operating loops | [Next tiers](NEXT-TIERS.md) |
| How to run or deploy the private application | [Local run](LOCAL-RUN.md) and [Deployment](DEPLOYMENT.md) |

## What this product is—and is not

It is a shared operating ledger for a crop season. It is not a generic farmer
CRM, a nationwide map, a pesticide recommendation engine, a scraped Streamlit
clone, or a composite farm-health score.

TrackWick remains the field team's existing source workflow. AGRO CEO reads
approved context from it and makes the manager's decision surface cleaner. It
does not create or edit TrackWick tasks, people, attendance, or pesticide
records.

## The three company outcomes

1. **Purchase capture** — increase the share of a linked grower's reported
   harvest purchased by Fortune. Until Fortune supplies a reviewed seasonal
   harvest/purchase snapshot, show *Farmer reach*, not purchase share.
2. **Export-ready proof** — retain a reported chemical record and the evidence
   needed for compliance review. A reported application is never presented as
   residue, compliance, or EU-export proof.
3. **Earlier field intervention** — make fresh field signals visible with an
   owner and a next move. A signal is a detection to inspect, not a diagnosis
   or automatic treatment instruction.

Every displayed number must say whose population it covers, its time window,
what it does **not** prove, and the next human move when it is incomplete.

## The operating principle

One thing, one meaning:

- **Farm** is the reviewed physical operating record.
- **Field** is the operational block within it.
- **Crop** lives inside a field for one season; it is not a top-level object.
- **Farmer** is a reviewed relationship to the programme, never inferred from
  a visit row or purchase record.
- **Field worker** is a reviewed person with a scoped operating role.
- **Inbox** holds decisions and promises at risk; it is not an activity feed.

The [operating architecture](OPERATING-ARCHITECTURE.md) makes those meanings,
the display contract, and the source-to-screen path explicit.

## Status, plainly

The app can safely show the minimal Fortune experience with a single local
fallback record while the private operating record is empty. That fallback is
not labelled as a demo and does not create data.

The TrackWick connector has been verified as a read-only source adapter, but
it remains fail-closed until Fortune names the accountable manager record and
places the sanctioned credentials in the server secret manager. Real source
rows are not imported merely to make the UI look busy.
