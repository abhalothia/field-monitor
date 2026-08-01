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

The product has three connected surfaces:

1. **Field capture:** a mobile-first, low-friction view of today’s assigned work and context-specific signal forms.
2. **Farm runtime:** a manager view of the farm calendar, open actions, current exceptions, and recent evidence.
3. **Leadership brief:** a concise view of readiness, blocked decisions, material risks, and progress against the season plan.

The field surface must work with short, structured inputs. It is not an attempt to put a full desktop management suite in an officer’s phone.

## Core model

The kernel owns these canonical records:

| Record | Purpose |
|---|---|
| Operating unit | The managed farm or defined operating entity. |
| Land unit | A plot/block with boundary, area, soil baseline, irrigation context, and active tenure relationship. |
| Season | A time-bound production cycle for one or more land units. |
| Crop plan | The crop/cultivar, stages, expected checkpoints, intended practices, and responsible agronomist for a land unit and season. |
| Person and role | Who is accountable for management, agronomy, field execution, or review. |
| Work item | A scheduled or ad-hoc action with owner, due date, status, and required evidence. |
| Signal | A field observation, completion, measurement, request, or exception captured against context. |
| Decision | A material choice, its rationale, approver, assumptions, and later outcome. |
| Evidence | Photo, note, document, measurement, or external observation attached to another record. |

Every signal and work item must resolve to an operating unit, land unit, season, and responsible person whenever those dimensions exist. The system may allow an unresolved signal, but it must make resolution visible.

## Requirements

### Farm and season setup

- An administrator can create an operating unit and land units, including geography, usable area, irrigation context, and soil-baseline references.
- An agronomist can create a season and attach crop plans to one or more land units.
- A crop plan can specify stages, checkpoints, planned work, required evidence, and escalation rules.
- A season uses a configuration version so changes made later do not rewrite the plan under which earlier work was performed.

### Work and ownership

- Managers can create, assign, reprioritize, and close work items.
- Work supports planned dates, due dates, dependencies, urgency, and a clear completion definition.
- A field user sees only work relevant to their role and farm context.
- Overdue, blocked, and unassigned work is conspicuous to the manager; it is never silently hidden by a reporting filter.

### Signals and evidence

- Administrators can configure a small set of signal templates with questions, required fields, evidence requirements, and follow-up rules.
- A template supports text, number/unit, choice, date/time, GPS point, photo, and document evidence.
- The system records observed time separately from submitted time.
- A signal can complete work, create an exception, or request review according to a declared rule.

### Decisions

- A material decision captures the choice, reason, alternatives considered, owner, approver, supporting evidence, and review date.
- A decision can create work and can be reviewed later against its actual result.
- The product does not label a decision “successful” until an accountable user records an outcome.

### Access and audit

- Roles distinguish administration, farm management, agronomy approval, field execution, and read-only leadership access.
- The product keeps a durable history of material changes, assignments, approvals, and corrections.
- Users cannot delete evidence or overwrite a prior approved decision without a linked correction record.

## Success criteria

- The pilot farm and season can be set up without code changes.
- Every planned field action has an owner and a completion definition.
- A manager can identify all open material work and exceptions in under two minutes.
- A leadership user can trace any material decision to its context and evidence.

## Non-goals

- Full land-lease legal workflow, procurement, payroll, accounting, or buyer-contract management.
- End-to-end farmer-facing WhatsApp flows.
- Satellite, IoT, or AI integrations as a prerequisite for a useful pilot.
