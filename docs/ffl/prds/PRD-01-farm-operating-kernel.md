# PRD 01 — FFL Farm Operating Kernel

**Status:** V0 foundation

## Objective

Create one shared operational model for an FFL-managed farm so that the team always knows: what farm and season they are operating, what must happen next, who owns it, what evidence exists, and what decisions remain open.

## Primary users

| User | Job to be done |
|---|---|
| Farm manager | Run the weekly operating plan, assign work, and escalate blockers. |
| Agronomist | Define crop-stage checkpoints and approve material interventions. |
| Field operator | Receive a small, clear list of work and submit field evidence or an exception. |
| Operations lead | See what is late, at risk, or unsupported by evidence across the pilot. |
| FFL leadership | Understand operating readiness and the few decisions requiring attention. |

## V0 user experience

The product has three connected surfaces, with a governed communications bridge added in V1:

1. **Field capture:** a mobile-first, low-friction view of today’s assigned work and context-specific signal forms.
2. **Farm runtime:** a manager view of the farm calendar, open actions, current exceptions, and recent evidence.
3. **Leadership brief:** a concise view of readiness, blocked decisions, material risks, and progress against the season plan.
4. **Field communications bridge (V1):** an opted-in WhatsApp path for concise work prompts, structured deviations, and evidence handoff. It links to the same canonical records as the PWA; it is never a parallel farm-management system.

The field surface must work with short, structured inputs in Hindi and English. It is not an attempt to put a full desktop management suite in an officer’s phone.

The field experience is offline-first. An operator can complete assigned work or report an exception with a photo and GPS without connectivity. The product visibly distinguishes pending, failed, and synced submissions; it never implies that a locally captured action has reached the manager when it has not.

WhatsApp adds reach, not a different truth model. A message is represented as a provider-attributable communication event and may create a reviewable signal or exception candidate. Required structured fields, evidence, allocation resolution, validation, and any approval still apply before FFL changes the operating record.

## Core model

The kernel owns these canonical records:

| Record | Purpose |
|---|---|
| Operating unit | The managed farm or defined operating entity. |
| Land parcel | The stable legal/physical parcel boundary and area reference. |
| Operational block | The contiguous area the FFL team manages as one operating unit; it may span or divide land parcels. |
| Right to operate | The active tenure or operating arrangement, term, evidence, and status for a parcel or block. |
| Season | A time-bound production cycle for one or more land units. |
| Season crop allocation | The area within an operational block committed to one crop/cultivar in a season. |
| Crop plan | The stages, expected checkpoints, intended practices, and responsible agronomist for a season crop allocation. |
| Person and role | Who is accountable for management, agronomy, field execution, or review. |
| Work item | A scheduled or ad-hoc action with owner, due date, status, and required evidence. |
| Signal | A field observation, completion, measurement, request, or exception captured against context. |
| Decision | A material choice, its rationale, approver, assumptions, and later outcome. |
| Evidence | Photo, note, document, measurement, or external observation attached to another record. |
| Communication event (V1) | An attributed inbound or outbound WhatsApp interaction, consent context, delivery state, and links to its resulting draft/evidence. It is not itself a work completion or decision. |

Crop plans, work, signals, outcomes, and decisions bind to a season crop allocation. This preserves history when a parcel changes, a block is combined or split, a partial area is planted, or a tenure arrangement expires. The product flags overlapping active allocations rather than silently merging them.

Every signal and work item must resolve to an operating unit, allocation, season, and responsible person whenever those dimensions exist. The system may allow an unresolved signal, but it must make resolution visible.

## Requirements

### Farm and season setup

- An administrator can create land parcels, operational blocks, and rights to operate, including geography, usable area, irrigation context, status, and soil-baseline references.
- An administrator can create a season crop allocation for a defined area of an operational block; the product prevents unreviewed overlaps and preserves a retired allocation’s history.
- An agronomist can create a season and attach crop plans to one or more season crop allocations.
- A crop plan can specify stages, checkpoints, planned work, required evidence, and escalation rules.
- A season uses a configuration version so changes made later do not rewrite the plan under which earlier work was performed.

### Work and ownership

- Managers can create, assign, reprioritize, and close work items.
- Work supports planned dates, due dates, dependencies, urgency, and a clear completion definition.
- A field user sees only work relevant to their role and farm context.
- Overdue, blocked, and unassigned work is conspicuous to the manager; it is never silently hidden by a reporting filter.
- Work follows the states `planned`, `in_progress`, `blocked`, `submitted`, `accepted`, `rejected`, and `cancelled`. Every transition records actor, time, and reason.

### Signals and evidence

- Administrators can configure a small set of signal templates with questions, required fields, evidence requirements, and follow-up rules.
- A template supports text, number/unit, choice, date/time, GPS point, photo, and document evidence.
- The system records observed time, captured time, submitted time, and received time separately when they differ.
- A signal can complete work, create an exception, or request review according to a declared rule.
- Offline replay is idempotent: a locally captured signal becomes exactly one server-side signal when connectivity returns.
- A WhatsApp-delivered signal is also idempotent by provider message identifier. It is a candidate until it passes the same template, identity, allocation, and evidence checks as a PWA submission.

### Decisions

- A material decision captures the choice, reason, alternatives considered, owner, approver, supporting evidence, and review date.
- A decision can create work and can be reviewed later against its actual result.
- The product does not label a decision “successful” until an accountable user records an outcome.
- Decisions follow the states `draft`, `approval`, `approved`, `superseded`, `outcome_due`, and `reviewed`.

### Exceptions and escalation

- Exceptions follow the states `reported`, `triaged`, `owned`, `mitigated`, `monitoring`, `resolved`, `accepted_risk`, and `reopened`.
- Every material exception has severity, a response target, primary owner, fallback supervisor, and next action.
- A missed response target alerts the owner first and the fallback supervisor next; acknowledgement does not close the exception.
- An exception may become resolved only after the defined monitoring/follow-up checkpoint is recorded, unless an authorised user explicitly accepts the risk with a reason.

### Capability and readiness

- A crop plan and stage-critical work item can declare required capabilities: qualified role, agronomist review, machinery, irrigation availability, input dependency, or other prerequisite.
- The farm runtime surfaces unmet prerequisites before the affected crop-stage window.
- V0 records readiness status and evidence; it does not implement inventory, payroll, or hiring workflows.

### Access and audit

- Roles distinguish administration, farm management, agronomy approval, field execution, and read-only leadership access.
- The product keeps a durable history of material changes, assignments, approvals, and corrections.
- Users cannot delete evidence or overwrite a prior approved decision without a linked correction record.

## Success criteria

- The pilot farm and season can be set up without code changes.
- Partial planting, block split/combination, boundary correction, and an expired right-to-operate can be represented without rewriting historical work or evidence.
- Every planned field action has an owner and a completion definition.
- A manager can identify all open material work and exceptions in under two minutes.
- A leadership user can trace any material decision to its context and evidence.
- An operator can capture a task completion and exception with photo/GPS offline; sync preserves one canonical signal and all distinct timestamps.

## Non-goals

- Full land-lease legal workflow, procurement, payroll, accounting, or buyer-contract management.
- A generic chatbot, contact-list sync, group-chat scraping, or an unapproved outbound WhatsApp campaign.
- Treating a message receipt, read receipt, button tap, or free-form text as an automatic work completion, decision, or agronomic instruction.
- Satellite, IoT, or AI integrations as a prerequisite for a useful pilot.
