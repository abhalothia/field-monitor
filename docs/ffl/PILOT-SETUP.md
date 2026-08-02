# AGRO CEO pilot setup pack

AGRO CEO is live as a private Vercel pilot, but no fictional farm facts are
seeded into production. The first setup is a short evidence-led handoff, not a
database import exercise.

## Bring these six facts, in this order

1. **Farm and people** — the operating-unit name plus the named farm manager,
   field operator, and fallback decision owner.
2. **Land and right to operate** — parcels, usable hectares, operating blocks,
   and the dated lease/ownership/management evidence. A village or PIN does not
   prove a land right.
3. **Active season** — season dates, crop, cultivar if known, allocated block
   area, and the accountable owner.
4. **Administrative context** — state, district, optional subdistrict, village,
   and six-digit PIN, verified by a named FFL person. This is a context key for
   relevant public sources, not a GPS boundary or parcel survey.
5. **Soil evidence** — the original lab report, sampling date/depth, lab name,
   units, and a reviewer. A PDF alone stays evidence; it is not silently turned
   into a soil baseline.
6. **The next field loop** — one critical work item, due time, owner, and the
   minimum evidence required to review its result.

The protected manager surface exposes `GET /api/v1/pilot/readiness` so the
team can see only aggregate completion counts and the next missing foundation.
It does not expose people, evidence contents, land rights, or a conversation
archive.

`POST /api/v1/pilot/setup/validate` accepts the same structured pack and
returns a normalised, reviewable UP-only proposal. It **does not write** the
farm, people, land, rights, or work: a named manager must review and accept a
later write flow. This prevents an incomplete form or HTTP retry from creating
a fictional operating record.

## Geography and public data

Village Finder is a reference candidate for Andhra Pradesh, Telangana,
Karnataka, Tamil Nadu, and Kerala only. It preserves LGD hierarchy and PIN
text after a reviewed immutable release is pinned. It is not a farm geocoder
and must not be forced onto a farm in another state, including Uttar Pradesh.

For the UP pilot, the correct follow-on source is the Ministry of Panchayati
Raj's official Local Government Directory (LGD) Download Directory. Its
human-facing download uses CAPTCHA, so FFL will retain a manager-reviewed
snapshot with hash/date/mapping provenance; we will not scrape CAPTCHA or
pretend the directory proves a parcel boundary or land right.

IMD is the next official context source, still disabled. Before any request,
we need a reviewed product, approved runtime egress, cached parser fixtures,
attribution, and a source owner. A forecast or advisory can raise a manager
watch item; it never completes work or makes an agronomic decision.

## Explicitly not in this step

- No live WhatsApp number, credentials, or sends.
- No background worker/scheduler deployment.
- No model-generated advice, automatic crop action, or fabricated demo data.
- No Supabase browser/service key in the application.
