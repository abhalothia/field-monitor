# Fortune Farm Labs Product Roadmap

**Status:** Directional PRD set — ready for product review

## The product

Fortune Farm Labs (FFL) is building the operating system for professionally managed farms. It gives a small, high-skill team a shared view of land, crop seasons, work, field evidence, risks, decisions, and outcomes so that a farm can be run deliberately rather than by memory, fragmented tools, or reactive calls.

This is not farm-management software sold as a generic SaaS product. It is an internal operating advantage for FFL first. It may eventually support Fortune's partner-farmer network, but it must prove itself on FFL-managed farms.

## Product thesis

Agriculture is variable. Soil improvement takes time, weather is uncertain, and a crop plan is only as good as the people and capabilities available to execute it. The product should therefore make uncertainty, evidence, ownership, and learning visible. It should not pretend that a dashboard or an AI model removes agronomic judgment.

The core loop is:

1. Establish the farm and season context.
2. Plan work and decision checkpoints.
3. Capture a small number of high-value signals from the field.
4. Turn material signals into owned actions or decisions.
5. Record the outcome and reuse what was learned on the next farm or season.

## Product boundaries

FFL should build eight connected layers, in this order:

| PRD | Layer | Outcome |
|---|---|---|
| [PRD 00](prds/PRD-00-pilot-mandate.md) | Pilot Mandate | A sharp definition of the first operating loop, its users, and what success proves. |
| [PRD 01](prds/PRD-01-farm-operating-kernel.md) | Farm Operating Kernel | One durable shared model of farms, plots, seasons, people, work, evidence, and decisions. |
| [PRD 02](prds/PRD-02-season-execution-and-learning.md) | Season Execution & Learning | A team can run a crop season, resolve exceptions, and learn from what happened. |
| [PRD 03](prds/PRD-03-data-and-intelligence-fabric.md) | Data & Intelligence Fabric | External data and documents enrich decisions with source provenance; optional AI is safe and useful. |
| [PRD 04](prds/PRD-04-multi-farm-scale.md) | Multi-Farm Scale | FFL can compare, replicate, and govern operating playbooks across farms and deal structures. |
| [PRD 05](prds/PRD-05-regional-conditions-service.md) | Regional Conditions Service | A trustworthy, privacy-safe FFL signal product built from public and verified operating data. |
| [PRD 06](prds/PRD-06-controlled-trials-and-playbooks.md) | Controlled Trials & Playbooks | FFL can run disciplined experiments and promote only evidence-backed practices. |
| [PRD 07](prds/PRD-07-field-communications-whatsapp.md) | Field Communications & WhatsApp | An opted-in field team can capture and receive time-critical operating context through WhatsApp without turning chat into the operating record. |

## Delivery shape

**V0 — one FFL farm, one season, one operating team**

Build PRD 00, PRD 01, and the essential execution slice of PRD 02. The team must be able to set up the pilot farm, define crop-stage checkpoints and SOPs, create/assign work, record field evidence, resolve exceptions, and review the season in one place.

**V1 — repeatable farm operating system**

Complete PRD 02 and introduce the useful parts of PRD 03: a few trusted external feeds, document-backed soil records, configurable signal templates, and human-reviewed advisory/playbooks. Add the narrow, opted-in operating loop in PRD 07 only after FFL can preserve field evidence and resolve it to a farm, allocation, and accountable person.

**V2 — portfolio and network scale**

Implement PRD 04 once FFL has more than one operating unit and has evidence that comparisons and shared playbooks are changing decisions. Implement PRD 06 where FFL is ready to run a controlled operating trial. Consider PRD 05 only after the internal source and governance model has earned trust.

## Explicit non-goals

- Rebuilding a generic FieldData clone, a generic farmer CRM, or a generic accounting suite.
- Rebuilding Fortune's existing TraceRice traceability product, satellite partner systems, or any vendor system before a specific integration need is proven.
- Making a PDF dashboard the product.
- Treating a WhatsApp conversation, delivery receipt, or AI summary as proof that field work happened.
- Assuming an arbitrary uploaded document is correct, structured data.
- Autonomous agronomic recommendations or an AI system that writes operational records.
- Building for every crop and every geography before one operating loop is proven.

## Shared product invariants

- **Configurable, not hard-coded:** crops, stages, SOPs, signal templates, and review rules must be editable without a release.
- **Evidence over assertion:** important observations, recommendations, and changes carry a source, time, responsible person, and relevant farm/plot/season.
- **Human authority:** an accountable operator or agronomist owns important actions and decisions.
- **Learnable operations:** completed work records the observed result, not merely a closed checkbox.
- **Smallest useful input:** field users answer a short, context-specific prompt; they should never recreate office paperwork in a field.
- **Modular monolith first:** clear module boundaries and interfaces, one coherent product and data model. Do not begin with microservices.

## Research grounding

Fortune Rice already has a mature contract-farming, extension, procurement, processing, traceability, and sustainability operation. The FFL product must complement those strengths rather than recreate them. The following first-party sources informed this roadmap:

- [Fortune Rice — contract-farming model](https://fortunerice.in/our-model)
- [Fortune Rice — operations](https://fortunerice.in/operations)
- [Fortune Rice — food safety and traceability](https://fortunerice.in/food-safety)
- [Fortune Rice — sustainability programs](https://fortunerice.in/sustainability)
- [IMD API reference](https://api.imd.gov.in/public/api_reference.html)
- [AGMARKNET service](https://services.india.gov.in/service/detail/agmarknet-portal)
