# Sprint 13 acceptance — Flash events

Status: complete locally, 2026-10-18. Developer verification only; not a release.

## Scope

Reuse the existing event, discovery, registration and preference boundaries.
Flash starts within 24 hours of publication, uses instant acceptance, and has
temporary matching-area priority inside the existing club priority groups.
Explicit chronology remains unchanged. The user confirmed a saved Show Flash
events switch, on by default, affecting discovery only. No notifications, My
Events, detail access, registrations or chat are muted/removed by that switch.

## Checks executed

| Check | Result |
|---|---|
| Additive migration preservation, guarded rollback, DB Flash constraints | 9 passed, 18.40 s |
| Focused event/preference/local-fixture checks | 23 passed, 117.14 s |
| Default backend regression suite, real PostgreSQL | 418 passed, 9 opt-in gates skipped, 1202.70 s; no failures/errors |
| Frontend contracts, executable request/checklist tests, localization and static serving | 49 passed, 3.05 s |
| ESLint, TypeScript, static export and public-asset credential guard | Passed; normal API 8001 export restored |
| Actual Sprint 13 Edge gate | 1 passed, 69.28 s; nine journey groups, zero console/uncaught errors or failed requests |
| Existing desktop management, mobile attendee and For You Edge regressions | 3 passed serially, 248.28 s; 18 + 11 + 11 journey groups |
| Explicit development migration and preservation | `mvp_0009` applied; all pre-existing tables/rows unchanged |
| Alembic model/schema drift | No new upgrade operations detected |
| Restored local runtime | Frontend 3000, API 8001 ready at `mvp_0009`, deadline worker at 30 s; read-only HTTP and rendered Edge smoke checks passed with zero browser errors |
| Reviewed API contract freshness | Exported OpenAPI equals the final app schema; generated types passed contract checks |

The dedicated PostgreSQL container was found stopped and restarted using its
existing `intraspot-mvp_mvp-data` volume. No reset/factory reset, volume deletion,
Penpot database access or cloud connection occurred. Tests run serially only
against the allowlisted `intraspot_mvp_test` database.

## Delivered behavior and fixes

Scheduled/Flash is part of the existing versioned draft editor. Choosing Flash
atomically selects instant registration and removes the review window. The
publish checklist explains and checks the 24-hour start window; the server
independently enforces it using the same timestamp assigned to publication.
Incomplete saves remain supported. Material reschedules remain inside the
original publication window; no boost renewal or new duration cap is added.

For You applies exact normalized chosen-area Flash priority within existing
club groups, before pagination. It expires strictly at three hours or start.
Absent area, nonmatches, expired boosts and explicit chronology retain their
existing fallback/order. Flash type badges remain separate from controlled
priority reasons and Featured. Visible signed-in For You polls every 30 seconds;
the server boundary is exact but display refresh can lag up to that interval.

Show Flash defaults on. It saves per account or in the existing versioned guest
record, composes with all discovery filters, and never removes public detail,
existing registration, My Events, chat or notifications. Partial writes preserve
other preferences. Old records/responses without the field decode as true;
malformed present values fail validation. Reset restores the default on.

Independent review caught a duplicate request property that overwrote the chosen
Flash type with scheduled. It was removed and a test now executes the actual
request-building function, not just source-text matching. The client publishing
checklist also has executable exact-24-hour and over-boundary tests.

The stricter browser gate found an inherited static-server compatibility issue:
Next requests flattened segment-prefetch names while this export emits nested
files. A guarded fallback now serves the actual exported file. A real HTTP test
covers prefetch, normal query routes, HEAD, missing files, disallowed writes and
encoded traversal. No favicon is configured; its absent implicit request returns
204 without inventing a media asset. Other missing files still return 404.

Browser harness fixes scope the duplicate event heading by level, install waits
before navigation, and wait for asynchronous content before screenshots. The
account changes for positive mobile checks happen outside the owner-only editor;
the explicit non-manager publishing denial is still verified. Final console and
HTTP-error checks are enabled and report zero, not suppressed.

Earlier unsuccessful runs are retained as diagnostic history, not acceptance.
The first browser attempt lost its fixtures while an older suite was finishing;
subsequent gates were serialized and API/catalog preflight checks were added.
Expired fixed fictional credentials were renewed with the guarded existing
identity helper. A cold Windows worker import took about 24 seconds; the old
30-second subprocess harness budget was raised to a bounded 90 seconds. Worker
polling and business deadlines were not changed; the full recovery suite passed.
An affected generated Next cache was preserved recoverably under
`.cache/next-s13-preserved-01a14d50`, with no source/data deletion.

One fixed fictional Flash sample was added through the existing approved-owner
publishing policy. Its helper preserves existing records and never renews old
publication times. The development migration preservation proof ran before this
explicit additive fixture and normal deadline-worker restoration.

## Browser evidence

- [Final Sprint 13 results](sprint13-browser-evidence/2026-10-18T05-26-56-357853Z/results.json):
  guest/account persistence, controlled ranking, chronology, search/My Clubs,
  registration/waitlist, hidden My Events, account isolation and real publishing.
- [Desktop viewport](sprint13-browser-evidence/2026-10-18T05-26-56-357853Z/desktop-flash-discover-1440-viewport.png),
  [English mobile](sprint13-browser-evidence/2026-10-18T05-26-56-357853Z/english-flash-discover-390-viewport.png),
  and [Filipino extra-large](sprint13-browser-evidence/2026-10-18T05-26-56-357853Z/filipino-xl-discover-390-viewport.png)
  were visually inspected. Geometry checks at desktop 1440 and mobile 320/390
  show no horizontal overflow and retain four attendee destinations.
- [Desktop management regression](sprint13-management-regression-evidence-2026-10-18/results.json)
  covers four desktop viewports, pending/approved authoring, version conflicts,
  retry, admin decisions, inbox routing and staff authorization.
- [Mobile attendee regression](sprint11-browser-evidence/2026-10-18T05-30-49-136214Z/results.json)
  covers guest/faculty/profile/approval/waitlist/chat/retention journeys, independent
  preferences and 320/360/390/430 px, short-height and landscape layouts.
- [Recommendation regression](sprint12-browser-evidence/2026-10-18T05-32-08-279139Z/results.json)
  covers optional area/windows, account isolation, explicit chronology, composed
  search/My Clubs and owner-only metadata save/publish.

The browser uses active and already-expired fixtures; exact expiry/start
boundaries are verified in PostgreSQL/API checks rather than pretending a
three-hour live wait occurred. Viewport images are the layout reference; tall
full-page captures may have sticky-header capture artifacts. The local fictional
account selector is a development utility, not proposed production sign-in UI.

The final frontend export targets API 8001, not the isolated 8002 gate. A clean
Edge context rendered the additive Flash fixture with Show Flash checked and
zero browser errors. Read-only health/readiness, verified fictional actor,
preferences, filter/detail and My Events checks also passed. No demonstration
registrations or preference edits were written to the development database.
The canonical Obsidian index, handoff, roadmap, UI/UX and functionality notes
record Sprint 13 and the user's visibility decision; Sprint 14 is not started.
Existing upstream HTTP-client deprecation and Node module-format notices are
non-blocking; no dependency upgrade was added to this sprint.

## Boundaries

Changes preserve prior uncommitted work. No automatic startup migration, real
sign-in, GPS/calendar, new media handling, announcements, Penpot sync, deployment
or commit/push. Later sprints are not implicitly executed. Developer-operated
browser checks do not replace participant, screen-reader or native-device tests.

See [frozen contract](../backend/Sprint-13.md) and
[interaction handoff](../design/sprint13-interaction-handoff.md).
