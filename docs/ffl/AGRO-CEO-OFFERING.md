# AGRO CEO: the Fortune operating offer

AGRO CEO is Fortune Farms' private operating system for running a real farm
with more clarity, speed, and discipline. It is not an information portal, a
government dashboard, a generic farmer CRM, or an autonomous agronomy bot.

## The promise

For the company: **see what matters, decide who owns it, and learn what
changed.**

For the field team: **a short, clear, local-language prompt that fits the work
already being done.**

The product earns the right to be called a command centre only when every
important item can answer:

1. What happened, where, and when was it observed?
2. What supports it: field evidence, lab result, official context, or an
   explicitly labelled hypothesis?
3. Who owns the next action or decision?
4. What happened afterwards, and what should the next season retain?

## The two experiences, one record

| User | Default language | Job | What AGRO CEO must feel like |
|---|---|---|---|
| Field operator / extension lead | Hindi first, English available | Report a small field fact or see the next assigned job | Clear, respectful, fast, usable under sun and weak connectivity |
| Farm manager / agronomist | English first, Hindi-aware | Turn material evidence into owned work, exceptions, and decisions | Calm, precise, evidence-forward |
| CEO / operations leadership | English first | Steer across farms, risk, execution, quality, and learning | A field ledger—not a vanity analytics wall |

Hindi is not a translation afterthought. The field experience uses simple,
task-specific language; names, dates, units, and evidence requirements remain
unambiguous across both languages. English is the management and governance
language for the initial company surface. Both views resolve to the same
canonical operating record.

## Uttar Pradesh pilot: what we deliberately build

1. **Foundation** — real farm, people, land/right evidence, current season,
   administrative context, soil evidence, and the first critical work loop.
2. **Execution** — work ownership, field observations, exceptions, decision
   audit, measured harvest, and season review.
3. **Context** — one official source at a time: UP administrative reference
   from LGD, then IMD weather/warnings after access review. Public context is
   labelled as context, never an order or completion.
4. **Steering** — a company-level action ledger: overdue field work, open
   exceptions, source freshness, evidence gaps, and learning status.

The protected `POST /api/v1/pilot/setup/validate` endpoint is the first input
gate. It validates an UP proposal and produces a reviewable write order, but it
does not seed the company database. That separation is intentional: a farm is
not born from a partial form submission.

## Non-negotiable product ethics

- No fictional farm data in production.
- No PIN, village name, or satellite pixel presented as a parcel boundary or a
  right to operate.
- No public source treated as a local observation, buyer commitment, work
  completion, or agronomic prescription.
- No evidence link, delivery status, or AI summary closes field work.
- No model writes the operating record or sends a farm instruction by itself.
- No WhatsApp/LoopMessage activation until its separate consent, evidence,
  review, template, recovery, and account-capability PRD is approved.

## What comes after the pilot core

Once the UP operating loop is genuinely used, AGRO CEO can add economics
(inputs, realised sales, payments), then controlled trials and playbooks. Only
after the native field PWA, evidence lifecycle, and named-role boundary are
proven should we draft the separate LoopMessage request. Chat may assist the
loop; it will never replace the ledger.
