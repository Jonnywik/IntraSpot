# Preliminary UAT provisioning

Status: guest UAT preview live, 2026-11-03. Signed-in UAT remains blocked on
Google provider configuration in the new Supabase project.

Frontend: https://intraspot-uat.pages.dev

API: https://intraspot-uat-api.onrender.com

The user authorized hosting for preliminary UAT and explicitly selected Render
Free as the API host. Cloudflare Pages and a new isolated Supabase project remain
the frontend and data/auth/media providers. General-public release, paid plans,
and importing either local development dataset are outside this authorization.

## Observed resources

| Resource | Observed state |
| --- | --- |
| Supabase IntraSpot UAT | Healthy, project `vhxlszpsqfsjuqhmplbv`, Tokyo; explicitly migrated to `mvp_0020`, 48 application tables, zero accounts |
| Supabase Data API | Disabled; dashboard explicitly warns client database queries are unavailable |
| Supabase media | `intraspot-media` created with public access off, 5 MB limit, normalized `image/webp` only; no browser policies |
| Cloudflare Pages | `intraspot-uat`, all 111 static files uploaded, deployment `95499d3d-3738-4860-9cd7-d8d26ad1d9b0` live |
| Render | `intraspot-uat-api`, Docker/Free/Singapore, `/ready`, auto-deploy Off; deploy `dep-dbksqfp5efls73firumg` succeeded/live at code revision `0def970055303fa049142f9fa66d633c2207c770` |
| Existing Supabase development project | Left untouched |

## Remaining before signed-in UAT

1. Configure the new project's Google provider with
   user-controlled credential entry. Do not copy the older project's secrets or
   resume the deferred positive PLM verification implicitly.
2. Add the new Supabase provider callback to the selected Google OAuth client's
   allowed redirects, preserving existing development callbacks. The frontend
   site URL and its exact `/auth/callback` are already saved in UAT Supabase.
3. Perform user-controlled sign-in and provision actual consented UAT content
   and roles through an explicitly reviewed bootstrap process. Only the labeled
   sample content described below is seeded. Do not claim registration or
   administrator journeys have been tested live against the sample dataset.
4. Complete participant, physical-device, screen-reader and release gates;
   configure hosted backup operations before broader use. The free evaluation
   service is not a production availability or recovery promise.

## Verified provisioning evidence

The empty target was inspected before DDL. Connection to Supabase's session
pooler succeeded with `sslmode=verify-full` and the provider CA. Separate
`app_runtime` and `app_migrator` roles were created; explicit Alembic upgrade and
application grant hardening completed. A runtime `CREATE TABLE` attempt was
rejected, and neither browser role had SELECT access to public application
tables. The private bucket and normalized WebP restriction were independently
verified through the Storage server API. Both local datasets matched their
preservation baselines: 76 fictional rows and two real-development rows across
the original 41 tables. No local accounts were imported.

The backend's `/health`, `/ready` and guest event listing returned 200. Profile,
notifications and operations requests without authentication returned 401.
Exact frontend CORS preflight passed; an untrusted origin was denied. Changing
X-Forwarded-For alone retained the same pseudonymous limiter identity; forged
CF-Connecting-IP requests were rejected with 403 at the provider edge and
created no additional buckets. Maintenance recorded success without an error.

The guarded hosted frontend build passed TypeScript, static generation and
credential scans. An initial restricted Windows build hit EPERM creating a
generated Next directory; the normal-permission build succeeded. Cloudflare
confirmed 111/111 uploads and successful publication. The live browser loaded
Discover with its genuine empty-state result, search controls, and signed-out
My Events instructions. A separate non-browser HTTP probe to Pages received
403; this is not recorded as an HTTP smoke-test pass. Browser navigation was
verified directly. Supabase's public auth settings reported Google disabled;
the visible sign-in button is not proof authentication is ready.

## User-authorized sample content, 2026-11-03

After publication the user explicitly requested dummy events on the live site.
Six upcoming scheduled events and four fictional organizations were added only
to UAT, all named `[SAMPLE]` with descriptions explaining that no real activity,
venue booking or PLM accreditation is represented. Events cover design, coding,
music, volunteering, heritage and campus introductions. They use existing artwork
and genuine zero attendance/reaction counts. One inactive, unverified, non-admin
attribution record with a reserved `.example` address satisfies foreign keys;
no Supabase identity, usable login, membership or authentication bypass was added.
Deterministic IDs make the seed repeat-safe. No local dataset was imported.
The live API returned the sample events and the live browser displayed all six.

The current Render code checks pass: 31 focused cases; combined with existing
Sprint 25 configuration checks, 70 passed. These are local checks, not live
provider, database, OAuth, or participant evidence. Human/device/accessibility
and positive PLM gates remain outstanding for release.
