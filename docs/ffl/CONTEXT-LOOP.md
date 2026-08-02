# FFL context loop

## What is live in the application contract

The first data loop is deliberately small:

```text
Verified operating location
  + reviewed soil-lab evidence
  + approved district context
  → deterministic morning brief
  → manager judgment / normal FFL work flow
```

`PUT /api/v1/operating-units/{id}/location` stores an India administrative
context: state, district, optional village/PIN, and FFL's `district_context_key`.
It is **not** a survey boundary, a land-right assertion, or a precise location.
For the western-UP pilot, use `field_verified` until an authoritative UP LGD
reference dataset is separately admitted; do not force the five-state Village
Finder data into this farm.

`POST /api/v1/operating-units/{id}/soil-baselines` accepts only reviewed,
evidence-linked, finite measurements with units. The original lab document must
first exist as an FFL evidence artifact. A baseline is append-only; newer
verified locations supersede the prior administrative binding with audit history.

`GET /api/v1/operating-units/{id}/morning-brief` composes the current location,
latest soil baseline, due field work/checkpoints, open exceptions, and already
normalised district context. Its response is deterministic JSON for the manager
surface; it makes no provider call and has no model dependency.

## IMD admission remains a production gate

The brief will render IMD context only after an approved `imd-weather` source
has been registered, enabled, and populated by a private worker. The required
path is:

```text
Official IMD access + fixed future-worker egress/IP review
  → private source worker + cache/attribution
  → source run + normalised regional signal
  → brief candidate with provenance
```

The Vercel pilot serves the protected manager/field experience. IMD polling is
not enabled there yet: IP allow-listing, durable retries, and source caching
need their own reviewed worker execution boundary. External context can raise a
review item only; it never proves a field condition, closes work, or prescribes
an intervention.

## Brain/new-model boundary

No model is needed for this loop. A later model integration may render a cited,
read-only draft from the brief JSON after a retrieval/evaluation gate. It must
not mutate records, make an agronomic recommendation, or become the source of
truth.
