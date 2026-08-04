# Manager browser access

AGRO CEO has two deliberately separate browser gates:

1. `FFL_LAUNCH_PASSWORD` gates the Fortune pilot shell. It is not manager authority.
2. `FFL_MANAGER_SESSION_SECRET` unlocks manager-only actions for the one configured manager person in a short-lived, server-signed cookie session.

`agro_access_memberships` separately records the Fortune app team: owners and
admins are not inferred from a person's field role. The initial three records
are identity-pending until a verified email/Auth subject is attached; do not
invent credentials from display names. The current session gate remains a
single configured transitional manager binding, so choose one active approved
person for `FFL_MANAGER_PERSON_ID` until the named Supabase Auth hand-off is
enabled.

Set these only as encrypted server environment variables:

```text
FFL_MANAGER_PERSON_ID=<existing people.id for the approved farm manager>
FFL_MANAGER_SESSION_SECRET=<strong random secret, never a launch password>
FFL_MANAGER_SESSION_MAX_AGE_SECONDS=900
FFL_LAUNCH_COOKIE_SECURE=true
```

`FFL_MANAGER_SESSION_MAX_AGE_SECONDS` may be 60–3600 seconds and defaults to 900. Invalid or incomplete manager configuration fails closed: the browser cannot unlock manager actions.

The manager unlock form sends its secret only to `POST /api/v1/manager-session/login`. The server checks it against deployment configuration and sets a signed, HttpOnly, SameSite cookie containing only an opaque configured-person binding, purpose, issued time, and expiry. The secret, manager API token, and person ID are not written to JavaScript storage, URLs, browser request headers, or the cookie payload. The browser can call `POST /api/v1/manager-session/logout` to remove manager authority; its expiry also removes authority.

`FFL_MANAGER_API_TOKEN` remains a legacy server-to-server/test bearer seam. Never place it in the dashboard, browser storage, Vercel public variables, query strings, or a user device. It is not needed for the browser manager session.

On Vercel, the app marks sessions `Secure` automatically. Do not deploy a real manager session without HTTPS, a configured launch password, and a real existing manager record with an approved manager role.
