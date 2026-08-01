# First external-data lane: reviewed geography, then IMD dry run

This lane intentionally has two capabilities and no live import.

## 1. Village Finder reference geography

`ffl.external_data.geography` accepts only a `ReviewedVillageFinderRelease`:

- one of the five upstream state files: Andhra Pradesh, Telangana, Karnataka,
  Tamil Nadu, or Kerala;
- a full immutable Git SHA, a lowercase SHA-256 of the exact CSV, and a
  non-empty human `review_reference`;
- the fixed raw GitHub path from the public India Village Finder repository.

The fetcher verifies the hash before parsing. The parser emits a strict
district/subdistrict/village hierarchy, preserving textual LGD codes and PINs
(including leading zeroes), canonical/native names, and native-name provenance.
It rejects state drift, unsupported schema, malformed PINs/codes, and
conflicting hierarchy records.

The output is a **candidate import** only. PINs are location hints, not
coordinates. The lane never fetches map geometry, binds an `agro_operating_unit`,
or publishes a farm fact.

### Persistence handoff

After the Postgres source/import interfaces are available, the worker must:

1. register the disabled `village-finder-lgd` source in `agro.agro_source_registry`;
2. retain the verified CSV as private evidence, then create an
   `agro.agro_import_batches` row with the SHA-256, source ID, mapping version,
   and reviewer reference;
3. write each `GeographyImport.import_row_candidates()` record as a reviewed
   `agro.agro_import_rows` candidate;
4. require a named manager to select and bind a village to an operating unit.

The data retains LGD/GODL-India attribution via the upstream reviewed release.
No release, state, or hash is pre-approved in code or seed data.

### Required repository contract

This module is persistence-free. The Postgres adapter supplies the following
atomic operations in one private transaction after evidence retention:

- `get_or_create_source(source_key)` for `village-finder-lgd`;
- `create_import_batch(content_hash, source_id, mapping_version, owner_id, profile)`;
- `create_import_row(import_batch_id, row_number, raw, mapped, status)`.

The adapter must reject a replay with a different mapping/version or content
hash, and it must never publish the resulting rows or write a location binding
in that transaction.

## 2. IMD access dry run

IMD's official API page links to API documentation and IP-whitelisting, and
asks clients to attribute IMD and cache responses. `IMDAccessReview` records
only the non-secret access evidence: the `api.imd.gov.in` endpoint, selected
product identifier, approved Hetzner egress identity, review reference, and a
60–3600 second cache TTL.

`IMDDryRunAdapter` conforms to the existing source-adapter port but deliberately
never performs HTTP. A refresh records `unavailable / imd_network_not_enabled`.
This validates registry configuration and manager health without claiming an
IMD result, storing a provider payload, or starting a polling loop.

### Production handoff

The future IMD worker may replace this dry-run adapter only after the source is
reviewed and enabled, its exact official product schema is pinned, the selected
Hetzner egress IP is whitelisted, response caching/attribution are implemented,
and parser fixtures cover normal, stale, and schema-drift responses. Its outputs
may create regional `agro_regional_signals` and manager watches only—never a
work completion, automatic reschedule, or agronomic recommendation.

### Required source-adapter contract

The dry-run adapter uses the existing adapter shape:
`fetch(source, credential, now) -> AdapterRefreshResult`. The supplied source
must expose `source_key`, `authority_level`, and `endpoint`; the source-run
service must persist `SourceUnavailable(code)` as an `unavailable` source run.
The expected code is `imd_network_not_enabled`. The real worker must keep this
same error surface for missing approval, IP whitelist, cache, schema, or
attribution gates rather than fabricating a successful weather refresh.
