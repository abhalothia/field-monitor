# PRD 03 — Data and Intelligence Fabric

**Status:** V1

## Objective

Enrich the FFL operating kernel with trusted external context and useful imported records, without allowing vendor feeds, uploaded documents, or AI to corrupt the operational truth.

## Product principle

Data can be useful without being authoritative. Every imported fact must preserve who supplied it, what it describes, when it was observed, when FFL received it, what transformation was applied, and whether a person approved it.

## Source types

| Type | Examples | Role in FFL |
|---|---|---|
| FFL primary evidence | Field signals, FFL soil tests, work completion, manager decisions | Operational truth when approved. |
| Existing enterprise systems | Field-force vendor, CRM, traceability, lab or IoT vendors | Referenced/imported through explicit contracts. |
| Official public context | IMD weather and warnings, IMD agromet bulletins, AGMARKNET trends | Context, candidate risk, and planning input. |
| Remote-sensing context | Existing satellite partner outputs, Bhuvan/Bhoonidhi products | Context or corroboration; never the sole proof of a field event. |
| Documents | Soil reports, field reports, lease records, supplier documents | Evidence until mapped and approved. |

## V1 source capabilities

### Source registry

- An administrator registers every source with owner, purpose, authority level, credentials reference, permitted data classes, expected freshness, licensing notes, and mapping version.
- The source health view shows last success, freshness, coverage, failed runs, and unresolved records.

### Import workbench

- Support CSV, XLSX, and Parquet for named import purposes such as roster, field visit, land register, or lab measurement.
- Preserve the immutable original artifact and its content hash.
- Profile headers, dates, units, and source identifiers; suggest a saved mapping but require confirmation for a new or changed schema.
- Preview proposed creates, updates, skips, and row-level validation errors before publishing.
- Match identities only with stable identifiers or an explicit human confirmation. Ambiguous names, phones, and plots enter a review queue.
- Publish corrections as linked new versions; never erase the raw input or prior approved record.

### Documents

- V1 accepts PDF, DOCX, images, and pasted text as securely stored, searchable evidence.
- Assisted extraction is allowed only for named document classes, beginning with soil-lab reports and field-visit reports.
- Each candidate extracted value displays the page/region source and confidence; a user confirms the target record before publishing.
- Arbitrary document uploads never create farm facts automatically.

### India-specific sources

- IMD is the first live integration: official forecast, observation, warning, rainfall, and nowcast context attached to a farm geography and source timestamp.
- IMD agromet advisories are captured as dated, crop/district-specific reference material; they are not transformed into unsupervised farm instructions.
- AGMARKNET data is stored as mandi context with market, variety, grade, unit, price date, and arrival data. It is never substituted for an FFL realised price or buyer commitment.
- FFL-owned soil sampling and laboratory results are the soil truth. Government Soil Health Cards can be attached as historical evidence.

## Intelligence and Brain.new boundary

The intelligence layer is optional. It is admitted only when FFL has enough reliable context to evaluate it.

An intelligence provider, including a future Brain.new integration, may:

- Retrieve approved contextual records.
- Summarize a farm status or draft a recommendation with linked source evidence.
- Suggest a document mapping or classify a signal for human review.

It may not:

- Write or alter operational facts, identity matches, work completion, or approved decisions.
- Send crop interventions to field users without a responsible human approval.
- Receive raw lease documents, personal data, precise GPS data, or proprietary buyer terms by default.

Admission criteria for an intelligence provider are a documented data-processing agreement, source-cited outputs, role-aware data filtering, evaluation against representative historical cases, and a measurable improvement in operator review time or decision quality.

## Success criteria

- A manager can identify the provider, observed time, coverage, and freshness of every external measurement used in a decision.
- A structured import can be previewed, corrected, and safely re-run without creating duplicate operational records.
- An ambiguous identity match or invalid row remains visible in a review queue rather than being guessed or discarded.
- A soil-lab document can be retained as evidence and, when approved, linked to the correct land unit and sampling date.
- No intelligence provider can publish a farm fact, task completion, or recommendation without the approval path defined by the operating kernel.

## Non-goals

- Generic “upload anything and build the database.”
- UI scraping of third-party tools.
- Bidirectional writes, deletion propagation, or unrestricted AI database access.
- Presenting public weather or market data as a guarantee of farm outcome.
