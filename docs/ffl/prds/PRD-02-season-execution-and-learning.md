# PRD 02 — Season Execution and Learning

**Status:** V0 extension / V1 core

## Objective

Turn a crop plan into a disciplined operating rhythm: work is executed, changes in the field become visible early, material exceptions receive a decision, and the team learns what to repeat or change next season.

## Why this matters

The scarce asset is not merely data. It is skilled attention at the right crop stage. Soil condition, weather, labour capability, timing, and crop-specific practices all interact. The product must route the right context to the responsible person before an issue becomes expensive.

## Core workflow

1. The agronomist configures crop-stage checkpoints, expected evidence, and escalation triggers.
2. The farm manager turns those checkpoints into the weekly work plan.
3. Field operators complete work or submit a structured signal when reality differs from the plan.
4. A material signal becomes an exception with a named owner and response deadline.
5. The owner records an intervention or decision; an approver reviews it when required.
6. The team records the observed outcome at the appropriate future checkpoint.
7. At season close, the team reviews what worked, what failed, and which playbook changes are justified.

An opted-in field operator may begin Step 3 in WhatsApp, but the resulting information must land in the identical FFL validation and review path. The channel reduces friction; it does not bypass the operating loop.

## Signal templates

V0 starts with five configurable template families. The exact wording is per crop and farm; the families are stable:

| Signal family | Intended use |
|---|---|
| Planned-work completion | Confirm a specific scheduled action and the required evidence. |
| Crop-stage check | Record stage, condition, and deviation from expectation. |
| Exception | Escalate a pest, disease, water, weather, labour, machinery, or quality issue. |
| Input/application record | Record what was applied, where, when, by whom, and supporting evidence. |
| Milestone/harvest quality record | Record material outcomes at predefined stages, including quality observations. |

Templates must be configurable by crop plan. For example, a crop-stage check may require different questions, photos, thresholds, and escalation rules for rice, barley, potato, or mint.

For WhatsApp, templates are rendered as short bilingual prompts, approved quick replies, or a provider-supported structured flow. They must name the farm context and the requested action, and must never turn an ambiguous free-text response into a material operating event without review.

## Requirements

### Operating calendar

- Show the current stage and next checkpoint for every active land unit.
- Allow managers to shift planned work with a recorded reason when weather, labour, or field conditions require it.
- Surface conflicts such as work due after its supporting precondition or work that misses the relevant crop-stage window.

### Exception management

- An exception has severity, category, location, observed time, supporting evidence, owner, response deadline, and status.
- An exception can be assigned to a field manager, agronomist, or operations lead.
- Material exceptions require a documented resolution or a documented decision to accept the risk.
- A closed exception records a follow-up checkpoint rather than assuming the intervention worked.

### WhatsApp-assisted field loop (V1)

- The channel supports only named operational intents: acknowledge an assigned work item, submit a crop-stage check, report a deviation, attach evidence, request a call-back, or confirm receipt of a non-material update.
- An inbound message creates a durable, provider-attributable communication event. FFL deduplicates webhook retries by provider message ID and retains the received time separately from the field-observed time.
- A photo, voice note, location, quick reply, or free text can produce a signal or exception **candidate**. It cannot complete a work item, resolve an exception, approve a decision, or apply an agronomic instruction until the canonical record meets its configured requirements and the accountable user accepts it.
- The system shows ambiguity instead of guessing. An unresolved sender, farm, allocation, language, or intent routes to a manager review queue with the original evidence and no automatic operational side effect.
- A pre-approved operational reminder may be sent only to a contact with the corresponding current consent. Material decisions, intervention drafts, and all free-form outbound text require a named human sender/approver.
- A failed, undelivered, or opt-out-suppressed work prompt leaves the underlying work open and conspicuous; a delivery/read status is never completion evidence.

### Soil as a managed long-term constraint

- A land unit can hold an initial soil profile, sampling dates, lab results, and named soil-improvement objectives.
- Soil objectives become planned practices and measurement checkpoints, not a one-time score.
- The product distinguishes direct measurement from inferred condition and preserves the source of each value.

### Outcome capture

- A harvest/output record binds to a season crop allocation and captures harvest window, quantity and canonical unit, measurement method, grade/quality measures, loss/quality evidence, and preliminary or final status.
- A finalised output record may be corrected only through a linked version with an accountable actor and reason.
- V0 captures operating outcome and quality context; it does not become a general financial ledger.

### Learning loop

- At any checkpoint, a manager can record “expected versus observed” and link the relevant signals, work, and decisions.
- A season review produces a short list of confirmed practices, invalidated assumptions, unresolved questions, and proposed playbook changes.
- A playbook change requires a named owner and approval before it becomes a default for the next season.

## Success criteria

- The manager can see the next two weeks of crop-stage-critical work by land unit.
- A serious field exception cannot disappear without an owner, resolution, or accepted-risk decision.
- The team can reconstruct why a material intervention was made and what happened afterwards.
- The next season starts from explicit learning rather than memory alone.
- A material harvest/output record can be traced to its allocation, measurement method, evidence, and any later correction.
- A WhatsApp-originated report can be traced from the resulting FFL record to consent, provider event identifier, sender, received time, and retained evidence without exposing the conversation as general farm data.

## Non-goals

- Automated diagnosis from a photo.
- Automatic pesticide or irrigation instructions.
- A universal crop knowledge base before the pilot produces validated playbooks.
- An always-on agronomy chatbot, autonomous message replies, or a workflow that relies on a WhatsApp read receipt as proof of execution.
