# PRD 05 — FFL Regional Conditions Service

**Status:** Future product; internal-first

## Objective

Create a trustworthy regional conditions service that combines officially sourced public context with privacy-safe FFL operating evidence. It should help FFL identify where attention may be needed and eventually provide a credible public view of relevant regional conditions.

This is not a generic agricultural news feed or a claim to predict farm outcomes.

## Users

| User | Job to be done |
|---|---|
| FFL operations | Understand regional weather, practice, and risk context across operating units. |
| Agronomist | Compare field signals with dated official context before deciding whether to intervene. |
| Leadership | See where operating exposure is concentrated without exposing individual farm data. |
| External audience, later | Consume a clearly sourced, aggregate regional signal product. |

## Signal classes

- Official weather observations, forecasts, warnings, and rainfall from IMD.
- Official agromet bulletins, retained with district, crop, issued time, and original content.
- Daily mandi trend context with market, commodity, variety, grade, unit, arrival, and price date.
- Verified FFL aggregate operational indicators, only where a privacy and data-rights policy permits publication.
- Existing satellite, water, and IoT partner outputs, when a valid commercial and licensing arrangement permits their use.

## Requirements

### Trust and provenance

- Every displayed signal identifies provider, source URL or identifier, observed/issued time, received time, coverage geography, resolution, freshness target, and licence/usage constraints.
- The product distinguishes direct observation, provider forecast, human assessment, model inference, and aggregate operating statistic.
- An expired, failed, or incomplete source is marked as stale; the last known value is never presented as current.

### Internal-first release model

- The first release is available only to authorised FFL users and attaches regional context to operating decisions.
- A public release is permitted only for aggregate, non-identifying data that passes a documented privacy, rights, and methodology review.
- Exact farm boundaries, field photos, leases, individual farmer data, proprietary input use, buyer terms, and FFL unit economics are excluded from public outputs.

### Regional views

- Users can select a region and time range and see a concise context timeline: weather/warnings, market context, agronomic bulletins, and approved aggregate FFL indicators.
- The product supports source filtering and a plain-language explanation of what each signal does and does not mean.
- Regional signals can create a candidate watch item, but a human or deterministic FFL policy must decide whether it creates operational work.

## Release gates

Before any public release, FFL must have:

- A source inventory with explicit rights to use and display each data class.
- A written aggregation and re-identification-risk policy.
- A freshness/availability policy and public methodology page.
- An internal review showing that the signal is useful and not misleading to field or management users.
- A correction process for source errors and a contact path for affected parties.

## Success criteria

- An internal user can trace any regional signal to its source and appropriate limitations.
- A source outage is visible before it can mislead an operating decision.
- Public output, if released, contains no individual or farm-reidentifiable operating data.
- At least one regional signal demonstrably improves an internal watch or planning decision before the service is promoted externally.

## Non-goals

- Replacing IMD, AGMARKNET, or partner data products.
- Publishing a yield or profit forecast as a verified fact.
- Monetising farmer or field-level data.
