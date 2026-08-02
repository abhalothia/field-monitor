# AGRO CEO Vercel pilot

Vercel is the authenticated Fortune pilot web/API runtime and custom-domain
edge. Its server functions connect only to the private `agro` schema through
Supabase's transaction pooler. No LoopMessage or scheduled-source worker is
enabled in this pilot deployment; those capabilities remain deliberately off
until their separate product gates are complete.

## What this repository deploys

`vercel.json` routes every request to the existing FastAPI entrypoint at
`api/index.py` and includes `ffl/static/**`. The public root is intentionally
data-free: it exists so links have a branded title, favicon, and `1200×630`
Open Graph image. `/manager`, `/field`, and every FFL API remain behind the
Fortune launch-password session.

## One-time Vercel setup

1. In team **dakshbhatia1's projects**, import this repository as a new project
   named `agro-ceo`. Keep the repository root as the Root Directory and let
   Vercel use `requirements.txt` and `vercel.json`.
2. Attach `agroceo.co` and `www.agroceo.co` in **Project → Settings → Domains**.
   Make `agroceo.co` primary and redirect `www` to it. Add the exact DNS records
   Vercel presents; do not copy generic records from another project.
3. Set `FFL_PUBLIC_ORIGIN=https://agroceo.co` in **Production**. This is the
   only authority for canonical and social-card URLs; it prevents a request
   header from changing cached link-preview metadata.
4. Add the production-only secrets in Vercel's encrypted environment store:
   `FFL_DATABASE_URL`, `FFL_POSTGRES_SCHEMA=agro`, `FFL_LAUNCH_PASSWORD`, and
   `FFL_LAUNCH_COOKIE_SECURE=true`. `FFL_DATABASE_URL` must use Supabase's
   transaction-pooler endpoint and the dedicated `agro_vc_runtime` role. That
   role has DML access to the private `agro` tables and no schema-creation
   privilege. Never use a browser key, Supabase secret key, or a
   migration/superuser URL in Vercel.
   During the short initial-farm handoff only, add a separate sensitive
   `FFL_PILOT_SETUP_APPROVAL_TOKEN`. It is required together with the launch
   session to accept the first real farm; it is not a browser credential.
   Rotate and remove it immediately after the one-time acceptance succeeds.
5. Configure a durable private evidence-store integration before permitting
   evidence uploads. For the initial setup, use the private Supabase bucket
   `agro-evidence` with `FFL_EVIDENCE_STORE=supabase`,
   `FFL_EVIDENCE_STORAGE_URL`, `FFL_EVIDENCE_STORAGE_KEY`, and
   `FFL_EVIDENCE_STORAGE_BUCKET=agro-evidence` as Production-only encrypted
   variables. The bucket must remain private; FFL writes immutable SHA-256
   object paths with overwrite disabled and keeps only a `supabase://` reference
   in its operating schema. Do not place any of these Storage values in Preview
   or a browser bundle. The current direct API path accepts at most 3 MiB per
   object; larger field media needs a later named-user resumable upload flow.
   If this configuration is absent, Vercel rejects upload requests rather than
   using `/tmp`.

## Preview policy

- Git pull requests get Vercel Preview deployments automatically. Give Preview
  its own `FFL_LAUNCH_PASSWORD`; do **not** set `FFL_DATABASE_URL`, Supabase
  keys, a LoopMessage secret, or production evidence credentials there.
- Preview's SQLite state is intentionally ephemeral and can be used only for
  visual/authentication smoke checks with non-sensitive test records.
- Keep operational previews behind Vercel Deployment Protection for the team.
  The production domain may remain publicly fetchable because the root contains
  no operating data and needs to be readable by link-preview crawlers; the
  application launch gate still protects every operational route.
- Use a Preview deployment URL for internal review. Share the production domain
  only after the launch gate, database role, evidence store, and backup check
  are all verified.

## Verification after each deploy

1. `GET /health` returns `{"service":"ffl-operating-kernel","status":"ok"}`.
2. An anonymous `GET /manager` redirects to `/login`; an anonymous API request
   returns `401`.
3. `GET /` contains `og:title`, `og:image`, `twitter:card`, and canonical URLs
   rooted at `FFL_PUBLIC_ORIGIN`; `/favicon.png` and
   `/static/brand/agro-ceo-social.png` return successfully.
4. Use the Slack/WhatsApp/X preview inspector appropriate to the recipient to
   refresh its cache after changing the social card. Social platforms cache
   previews independently, so deploy success alone does not guarantee an
   instant refresh.

## Deliberate boundary

Vercel is currently a request/response pilot surface. Do not enable the
LoopMessage worker or source-fetch scheduler in this deployment. They require
their own reviewed execution, retry, alerting, and credential boundary before
they are switched on. This is a product-safety gate, not a reason to mirror
the API elsewhere.
