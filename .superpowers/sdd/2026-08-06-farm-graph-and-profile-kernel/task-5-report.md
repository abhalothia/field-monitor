# Task 5 Report: Farm-first Web Shell

## Outcome

Replaced the Fields view's operational-block-as-farm model with a manager-gated Farm directory backed by the canonical Task 4 entity routes. The directory reads `GET /api/v1/farms`, and its visible state, name-query, start-date, and end-date filters are represented in the `/fields` URL with `URLSearchParams` and native history entries.

## Contextual entity shell

- Farm cards open `GET /api/v1/farms/{id}` in one contextual panel.
- The Farm panel contains the four required sections: **Now**, **People**, **Updates**, and **Context**.
- Field links replace the panel with `GET /api/v1/fields/{id}`.
- Farmer and Field Worker links replace the panel with `GET /api/v1/people/{kind}/{id}`.
- A small in-panel history restores the preceding Farm, Field, or Person context and returns keyboard focus to the link that opened it. Closing the root Farm panel restores focus to its directory control.
- Crop-season chips are rendered only in Field context.
- Disease findings render as dated reported events with declared severity and an explicit statement that the event is not a diagnosis.

## Boundaries and responsive behavior

- Canonical directory and entity requests are made only while the browser has an authenticated manager session. A `403` expires the local manager state and returns the user to the manager-access boundary.
- Reported source candidates remain outside the canonical Farm directory. The existing reported-farmer context remains visibly labelled as reported.
- The muted, non-interactive **WhatsApp updates — Coming soon** row is unchanged.
- Directory filters and cards collapse to a single column on narrow screens; contextual panels and their entity rows also use a one-column mobile layout.

## Contract coverage

Updated the command-centre source contract to assert the Task 4 Farm directory, Farm, Field, and Person routes, the four Farm panel headings, manager gating, focus restoration, the muted WhatsApp row, Field/Person contexts, and safe disease-event wording.

## Verification

- `/Users/dakshbhatia/Documents/field-monitor/.venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k 'farm_first_entity_profiles or command_centre'`: `3 passed, 21 deselected`.
- `/Users/dakshbhatia/Documents/field-monitor/.venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py`: `24 passed`.
- `cd apps/web && pnpm typecheck`: passed.
- `cd apps/web && pnpm build`: passed; all 11 Next.js routes generated successfully.
- `git diff --check`: passed.

Pytest continues to report the repository's existing FastAPI/TestClient deprecation warning; no new warning or failure was introduced.
