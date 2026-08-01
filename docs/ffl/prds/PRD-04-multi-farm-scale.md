# PRD 04 — Multi-Farm Scale and Replication

**Status:** V2

## Objective

Allow FFL to reproduce a validated operating playbook across multiple farms, geographies, crops, and commercial arrangements while preserving local context and accountability.

## Scope

This PRD begins only after the V0 farm loop is in active use and FFL can name the repeatable decisions it wants to standardize.

## Operating-unit model

The product supports three clearly separated arrangements:

| Arrangement | FFL role | Product requirement |
|---|---|---|
| Self-operated / leased farm | Operator bearing production risk | Full operating plan, execution, and learning loop. |
| Managed farm | Manager operating for an owner or partner | Scoped permissions, service commitments, and owner reporting. |
| Partner-farmer program | Protocol, extension, and/or procurement partner | Programme-specific signal templates, engagement, and compatibility with existing Fortune systems. |

The commercial and legal terms are configuration and evidence, not assumptions embedded in one workflow.

## Requirements

### Portfolio control

- Leadership can see operating readiness, material risks, and unresolved decisions by operating unit, geography, crop, and season.
- Comparisons normalize for relevant context: crop, stage, area, irrigation, soil baseline, weather exposure, and operating arrangement.
- The product never ranks people or farms on a raw metric that is materially distorted by incomparable context.

### Playbook replication

- Approved playbooks are reusable modules with scope, prerequisites, version, owner, and evidence of prior outcomes.
- A farm manager can adopt a playbook with local adaptations; the product preserves both the original and adaptation rationale.
- FFL can compare implementation fidelity and outcomes to learn which conditions make a playbook transferable.

### Governance

- Data access is scoped to the operating relationship: farm teams, FFL management, partner staff, and any external party receive only the information required for their role.
- Shared reporting uses aggregation or explicit consent; detailed farm data is not exposed merely because farms belong to the same portfolio.
- Portfolio-level changes to SOPs and crop programs require named accountable owners and approval history.

## Success criteria

- A new operating unit can be configured from an approved playbook without code changes.
- Leadership can distinguish a genuine operating risk from a comparison artifact.
- A local adaptation becomes reusable organisational learning only after its context and outcome are documented.

## Non-goals

- Franchising the software as an external SaaS product.
- Assuming all farms, landowners, farmer partners, and buyers use the same commercial terms.
- Building a global commodity-trading system.
