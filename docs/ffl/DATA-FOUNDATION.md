# FFL data foundation

**Status:** operating blueprint for the first real farm; data source code must remain disabled until its access, terms, owner, and mapping are reviewed.

## The point

FFL does not need a giant agriculture data lake. It needs one reliable answer to a manager's daily question:

> What should we do on this block today, who owns it, what evidence supports it, and what will we learn if it works or fails?

The operating record is the centre. External data supplies context; it never overwrites a checked field observation, a harvest measurement, an approved decision, or a buyer commitment.

## The minimum complete farm record

| Data family | First records | Why it matters | Capture cadence |
|---|---|---|---|
| Farm and operating rights | operating unit, parcel, block, usable area, irrigation, lease/right dates | Know exactly what FFL can operate and compare. | on change |
| Season and crop plan | crop allocation, cultivar, planned area, crop-stage calendar, accountable agronomist | Turns a farm into an executable season. | at plan; revise with reason |
| Work and field truth | work item, field signal, photo/voice/note, observed time, exception, reviewer | Makes on-ground execution visible and recoverable. | event-driven |
| Soil and water | laboratory result, sampling depth/date, method, baseline objective, irrigation event/source | Soil is a multi-season constraint, not one score. | baseline + checkpoints |
| Inputs and interventions | input lot, active ingredient/product label, purpose, rate/unit, operator, application evidence | Makes cost, residue risk, and outcome analysis possible. | every intervention |
| Harvest and quality | lot, measured quantity/unit, method, quality metrics, correction/evidence | Establishes the physical outcome. | every harvest/grade event |
| Commercial reality | buyer/market option, offer/contract reference, realised sale, transport/processing cost, payment state | Separates public mandi context from actual FFL economics. | quote/sale/payment event |
| Learning and governance | trial, confounder, season review, playbook version, decision and approver | Converts one season into a better next season. | review/season end |

Every record needs an ID, owner, observed time, received time, source/provenance, status, and evidence links. A correction is a linked new record, not an overwritten past.

## The first data pack: enough to operate, no more

Before a pilot starts, load only:

1. The farm/block map and operating-right dates.
2. People, roles, field-officer assignments, and manager fallback owners.
3. The active season, crop allocation, area, cultivar, crop-stage calendar, and defined success measure.
4. Baseline soil report(s), irrigation availability, and any known water/soil constraint.
5. The next 30 days of critical work and each work's required evidence.
6. The nearest relevant markets/buyers and their terms as private commercial records.
7. A short input list: only products/labels FFL is actually permitted and planning to use.

That produces the useful daily loop: **morning conditions → stage-critical work → field evidence/deviation → manager decision → cost/harvest/quality → season learning.**

## External context: narrow source stack

| Priority | Source | Use in FFL | Truth level / guardrail |
|---|---|---|---|
| 1 | FFL field team + lab + measured harvest | operations, soil, water, actual output and realised economics | primary evidence after review |
| 2 | IMD weather, rainfall, warnings and agromet bulletins | timing risk and manager watch items | official context; never a completion or crop instruction |
| 3 | data.gov.in / AGMARKNET | market, variety, arrival and dated price context | official context; never a buyer commitment or realised price |
| 4 | Copernicus Sentinel-2 | block-level vegetation/change context after geometry and cloud-quality checks | corroboration only; never proof of pest/disease or work completion |
| 5 | NASA POWER | historical/agroclimate baseline and a temporary weather cross-check | coarse gridded context; not a local forecast replacement |
| 6 | SoilGrids | starting regional soil hypothesis and sampling design | coarse baseline only; FFL lab results prevail |
| 7 | KVK/state-agriculture notices and crop-label/CIB records | human-reviewed reference material and permitted-use checks | document evidence; not automatic advice |

FFL's source registry records the source owner, purpose, licence/access status, coverage, freshness goal, mapping version, original URL/identifier, and failure state. New sources start disabled. An outage or missing credential is a visible `unavailable` result, never fabricated data.

## What not to ingest

- No scraped farmer-app database, pest/product catalogue, or proprietary advisory output.
- No AI recommendation as a fact or pesticide instruction.
- No precise farm boundary, lease, buyer terms, raw WhatsApp thread, or employee data in public dashboards or an external model by default.
- No public mandi price presented as a sale price, and no satellite value presented as a field diagnosis.

ACROP is a useful reference for a Hindi-first market and crop-protection experience, but not an FFL data source: its published terms restrict commercial/competitive use and systematic downloading of its database. Any partnership would require written rights and a separately reviewed adapter.

## Build sequence

1. **Operate:** enter the first data pack and enforce field evidence, ownership, review, and audit.
2. **Context:** enable one reviewed IMD feed and one reviewed AGMARKNET feed; show freshness and source links in the manager view.
3. **Observe:** add satellite only after parcel/block geometry and a field-ground-truth loop exist.
4. **Economics:** add input lots, actual intervention cost, harvest lots, buyer terms, realised sales, and payment status.
5. **Learn:** compare season/blocks only after soil, weather, practice, and harvest measurement context is complete enough to make the comparison honest.
6. **Assist:** let a model draft a cited summary or a review candidate only after the previous layers produce trustworthy history.

## Data-quality gates

- A field event cannot become a material operating fact without a known allocation, accountable actor, observed time, and required evidence.
- A soil value without a sampling date, method, unit, and land reference remains an attachment, not a baseline.
- A commercial record identifies whether it is an indicative market price, buyer offer, contract, realised sale, or payment.
- A source record becomes stale at its declared freshness target; a manager can see its last successful run and limitation.
- Any model output names its sources, uncertainty, reviewer, and disposition. It has no direct write or send authority.
