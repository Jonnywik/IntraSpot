# Preliminary UAT provisioning

Status: in progress, 2026-11-03. No verified live application link yet.

The user authorized hosting for preliminary UAT and explicitly selected Render
Free as the API host. Cloudflare Pages and a new isolated Supabase project remain
the frontend and data/auth/media providers. General-public release, paid plans,
and importing either local development dataset are outside this authorization.

## Observed resources

| Resource | Observed state |
| --- | --- |
| Supabase IntraSpot UAT | Healthy, project `vhxlszpsqfsjuqhmplbv`, Tokyo; no migrations at inspection |
| Supabase Data API | Disabled; dashboard explicitly warns client database queries are unavailable |
| Supabase media | `intraspot-media` created with public access off, 5 MB limit, normalized `image/webp` only; no browser policies |
| Cloudflare Pages | `intraspot-uat` name created; upload step reached, no assets deployed |
| Render | Signed in to Mikael Carl's workspace; new web-service source form reached; no service deployed |
| Existing Supabase development project | Left untouched |

## Remaining before a usable link

1. Complete the pending authorization for Render to read/build the public
   `Jonnywik/IntraSpot` repository. Do not request GitHub write access.
2. Privately supply the UAT database password and server-only Storage key in
   `Code/Backend/.local/uat/bootstrap.env`. This path is Git-ignored. Never paste
   those values into chat, logs, source, or frontend configuration.
3. Inspect the empty application schema; establish separate runtime/migration
   roles, explicitly apply reviewed migrations, harden grants, and prove runtime
   schema changes and browser reads are denied. Use verified database TLS.
4. Configure the free Render Docker service and actual assigned API hostname;
   inject only runtime credentials, with maintenance and rate limits enabled.
5. Configure the new project's Google provider and exact frontend callback with
   user-controlled credential entry. Do not copy the older project's secrets or
   resume the deferred positive PLM verification implicitly.
6. Build the guarded hosted frontend from clean sources with actual public
   origins; upload the static export and deploy Cloudflare Pages.
7. Verify live frontend/API connectivity, CORS, guest/private boundaries,
   trusted-proxy spoof resistance, cold-start feedback, and maintenance. Record
   exact deployed revisions and evidence before distributing the UAT link.

The current Render code checks pass: 31 focused cases; combined with existing
Sprint 25 configuration checks, 70 passed. These are local checks, not live
provider, database, OAuth, or participant evidence. Human/device/accessibility
and positive PLM gates remain outstanding for release.
