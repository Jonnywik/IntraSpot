# Sprint 12 acceptance — explainable For You discovery

Status: complete locally, 2026-10-17. Developer verification only; not a release.

## Scope and compatibility

Add deterministic, server-ranked For You discovery while preserving explicit
Upcoming/Newest, public browsing, composed search/My Clubs and the established
PLM desktop/mobile layout. Private optional broad-area/weekly-Manila inputs stay
separate from display preferences; interests reuse private Profile tags. Public
event topics/area are optional draft metadata, not a publishing requirement.

Rank before pagination: active eligible clubs, distinct normalized interests,
exact normalized area, whole-event weekly availability; start/ID break ties.
Only matched controlled reason labels appear. Do not infer metadata from titles
or addresses, disclose private inputs, or substitute static frontend outcomes.
No GPS, external calendar, Flash events, cloud sign-in, deployment or commit.

## Executed checks

| Check | Actual result |
|---|---|
| Shared normalization/window and migration preservation/rollback guard | 5 passed, 18.99 s |
| Earlier migration/readiness and additive local-fixture regressions | 35 passed, 72.72 s |
| Private discovery preferences API, validation, isolation, concurrent partial upsert | 26 passed, 42.82 s |
| Focused event metadata/ranking/global-pagination tests | 8 passed, 23.27 s |
| Default backend regression suite | 383 passed, 8 opt-in gates skipped, 2 Windows temporary-folder setup errors; 545.84 s |
| Affected local-demo module rerun with a fresh workspace temporary folder | 3 passed, 11.20 s; both setup errors resolved without changing application behavior (385 distinct default-suite tests passed across the runs) |
| Frontend contracts and English/Filipino localization | 38 passed; final run 6.58 s |
| ESLint, TypeScript, static export and public-asset credential guard | Passed on the final source |
| Sprint 12 live Edge gate | 11 journey groups passed; final run 1 pytest gate passed, 62.57 s; no uncaught browser errors |
| Desktop management and mobile attendee regression gates | 2 passed serially, 195.66 s; 18 desktop + 11 mobile journey groups |
| Explicit development upgrade and preservation proof | `mvp_0008` applied; counts and sorted row-content fingerprints of every pre-existing table unchanged |
| Alembic model/schema drift | No new upgrade operations detected |

Database suites run serially against `intraspot_mvp_test`, not the development
database or Penpot database. The additive migration is `mvp_0008`; it expands
existing rows to []/null and refuses a data-bearing downgrade. Old omitted sort
requests stay Upcoming; old draft writers omit optional metadata without clearing
it. Existing active draft content versions may require the normal conflict/reload
flow across the schema transition rather than overwriting newly saved metadata.

## Delivered behavior and review fixes

Signed-in For You ranks globally before limit/offset, with eligible active clubs
first, then distinct normalized interest overlap, exact broad-area match, and
whole-event Manila free-time fit. Stable start/ID ordering resolves ties. Guest
fallback, missing preferences, distinct tags, full-week and Sunday/Monday windows,
and a 52-event pagination case are exercised. Explicit chronology remains intact.

Settings saves, reloads and clears private optional discovery inputs separately
from display preferences. No-row defaults do not claim to be saved. Save failures
retain the editor draft and offer retry. The availability editor supports explicit
24:00 via an end-at-midnight checkbox and at most 28 recurring windows. Interests
remain in Profile; no personal inputs are put in guest browser storage.

Draft metadata is optional, normalized, versioned, previewed, and saved/published
through the real frontend/API. Unauthorized writes and stale versions are denied.
Public detail exposes event metadata, not private preferences or personalized
reason codes. Only controlled matched reason labels appear in signed-in For You.

Rendered review found concatenated accessible names on Sort by and the two new
metadata inputs. Explicit concise labels now separate names from option/helper
text, and the complete browser journey passed afterward. The longer explanation
is a collapsed native disclosure, while matched reasons stay visible on cards.

The initial Windows pytest temp-folder error was resolved by using a fresh path
inside `.cache`, not by weakening tests. A generated OneDrive-marked build cache
was preserved in `.cache/sprint12-next-preserved-01a149ea` to unblock cleanup;
later builds passed. No user data or source files were deleted. Existing upstream
HTTP test-client deprecation and Node module-format notices remain non-blocking.

## Browser evidence

- [Final Sprint 12 results](sprint12-browser-evidence/2026-10-17T13-06-11-086081Z/results.json):
  actual Settings save/clear/reload, account switching, matched reason groups,
  Upcoming/Newest overrides, search/My Clubs, and owner draft save/publish.
- [Desktop viewport](sprint12-browser-evidence/2026-10-17T13-06-11-086081Z/desktop-discover-1440-viewport.png)
  and [mobile viewport](sprint12-browser-evidence/2026-10-17T13-06-11-086081Z/mobile-discover-390-viewport.png).
  Settings/discovery checks at 320 and 390 px and Filipino extra-large at 390 px
  show no horizontal overflow and retain four mobile destinations. Desktop is
  captured at 1440×900 with standard text after asynchronous sidebars settle.
- [Desktop regression results](sprint12-desktop-regression-evidence-2026-10-17/results.json):
  four desktop viewports, approval, autosave/retry/two-tab conflicts, staff scope
  and inbox. Evidence copied from this run's generated temporary folder.
- [Mobile regression results](sprint11-browser-evidence/2026-10-17T13-04-00-504148Z/results.json):
  registration, faculty approval, waitlists, same-key chat retry, retention,
  profile validation, preferences and 320/360/390/430 px/short/landscape cases.

Viewport images are the clean layout reference. Tall full-page or named-region
captures can include sticky-header/skip-link capture artifacts mid-image; those
are not proof of live viewport overlap. Earlier failed-run evidence is retained
under its own timestamps and is not the final acceptance evidence.

## Restored local runtime

The final normal frontend export targets API8001 and passed TypeScript/export
and credential guards. Frontend `http://127.0.0.1:3000`, API health/readiness,
public discovery, current fictional-account credentials, authenticated private
discovery preferences, and private/no-store For You all passed live smoke checks.
Readiness reports `mvp_0008`. The explicit deadline worker is running at its
existing 30-second interval. Fictional tokens were renewed for eight hours using
the existing local-only helper, without overwriting existing profiles. Development
data and prior uncommitted source changes are preserved; no commit/push occurred.

## Remaining validation boundary

Developer-operated browser checks are not participant/native-device testing.
The accepted participant/release gate remains deferred. Native phone keyboards,
screen readers and browser variants without the Navigation API were not newly
validated. The existing native-beforeunload fallback limitation is unchanged.
Later roadmap sprints are not implicitly executed. No GPS, external calendar,
real sign-in, cloud, Penpot sync, deployment or Git commit was performed. Existing
tagless/area-less events are not backfilled; new fixture metadata applies only
when a predefined fictional event is created for the first time.

See [execution contract](../backend/Sprint-12.md) and
[interaction handoff](../design/sprint12-interaction-handoff.md).
