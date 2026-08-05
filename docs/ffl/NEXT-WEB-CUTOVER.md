# AGRO CEO Next.js cutover

AGRO CEO now uses two Vercel projects by design. The split keeps the product
experience fast and easy to evolve without putting database or evidence access
in a browser-oriented runtime.

```text
www.agroceo.co / agroceo.co  → agro-ceo-web (Next.js)
api.agroceo.co               → agro-ceo (FastAPI operating kernel)
fortune.agroceo.com          → agro-ceo (existing customer portal compatibility)
```

## Already configured

- `agro-ceo-web` is connected to `dakshbhatia/agro-ceo`, branch `main`, with
  root directory `apps/web`.
- It has `FFL_API_ORIGIN=https://api.agroceo.co` in Production and Preview.
- Vercel Web Analytics is enabled for `agro-ceo-web`.
- `api.agroceo.co` is attached to the existing `agro-ceo` FastAPI project and
  responds to `/health`.

The Next project holds **no** database URL, Supabase secret, evidence-store
credential, launch password, manager secret, or communication credential. All
of those stay in the API project.

The Next project also retains the native `/field` capture shell through tightly
scoped rewrites to FastAPI (`/assets/field.css`, `/assets/field.js`, the rice
mark, and its service worker). This preserves the signed field-capture PWA on
the same public web origin while the manager command centre has moved to Next.

## Pre-cutover checks

1. Confirm the latest `main` deployment of `agro-ceo-web` is ready.
2. Open its Vercel URL. Confirm `/`, `/login`, `/home`, `/fields`, `/farmers`,
   `/actions`, and `/settings` render.
3. Sign in through `/login`; the FastAPI session must authorize the Next API
   rewrite. Confirm the Home view says only what the operating record supports.
4. In Settings, unlock manager access and confirm reviewed geometry remains
   absent until there is reviewed geometry—never a substitute map pin.

## Domain switch

Only after all four checks pass, move `www.agroceo.co` and `agroceo.co` from
`agro-ceo` to `agro-ceo-web`. Keep `api.agroceo.co` and
`fortune.agroceo.com` on `agro-ceo`.

The Next app rewrites same-origin `/api/v1/*` to `api.agroceo.co`, so browser
requests retain FastAPI's signed launch/manager cookie flow. Never set
`FFL_API_ORIGIN` to `www.agroceo.co`; after the switch that would create a
self-proxy loop.

## Rollback

Reattach `www.agroceo.co` and `agroceo.co` to `agro-ceo`. No data migration or
rollback is required because the system of record never moved from FastAPI and
the private `agro` schema.
