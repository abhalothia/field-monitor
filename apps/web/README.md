# AGRO CEO web

This is the Next.js App Router product surface for AGRO CEO. It deliberately
does not connect directly to Supabase and it does not contain database,
evidence, provider, or WhatsApp credentials.

The browser calls same-origin `/api/v1/*`; `next.config.ts` rewrites those
requests to the FastAPI operating kernel configured by `FFL_API_ORIGIN`. This
preserves FastAPI's signed launch and manager sessions while allowing the web
experience to evolve independently.

## Local development

In one terminal, start the kernel from the repository root:

```bash
.venv/bin/uvicorn index:app --reload --port 8000
```

In another terminal:

```bash
cd apps/web
cp .env.example .env.local
pnpm install
pnpm dev
```

## Vercel cutover contract

Create a **new** Vercel project with root directory `apps/web`. Configure only:

```text
FFL_API_ORIGIN=https://api.agroceo.co
```

Keep the existing FastAPI project as the API project and attach
`api.agroceo.co` to it. Attach `www.agroceo.co` and `agroceo.co` to this Next
project only after preview and production checks pass. The Next project has no
database, Supabase service, evidence-store, launch-password, or LoopMessage
secrets; those remain in the API project.
