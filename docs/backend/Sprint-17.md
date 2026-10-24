# Sprint 17 — private saved events, calendar/list, conflict warnings

Authorized by "continue sprint", 2026-10-20. Canonical source:
Obsidian IntraSpot/Implementation Roadmap, Sprint 17 and Locked choices.
Preserve Sprint 16's uncommitted work and existing PLM identity/navigation.

## Frozen behavior

- Saving is private planning, not registration, a reaction, or a capacity hold.
  Any authenticated active account may save; guests receive sign-in guidance.
  Registration/social eligibility rules do not change. No guest server bookmarks.
- Save only currently public published events of approved organizations, including
  ended public events. Preserve original save time on retries. Save/remove are
  idempotent under concurrency. Reads/writes always use the verified caller,
  never an arbitrary user ID. No roster/profile/other-account data is returned.
- Existing saved references survive later unavailability. Lists return a null
  public event with generic unavailable copy (no cached private title/artwork);
  the caller can still remove it. Public-ended events remain readable. No
  automatic registration, expiry, export, external calendar or notification.
- My Events retains all existing status tabs, outcomes, reconfirmation, withdrawal,
  waitlist positions/messages and chat boundaries. Add Registrations/Saved sections
  within this page, plus List/Calendar toggle. List is the default; do not add a
  persistent navigation destination. Both desktop and attendee mobile are in scope;
  no mobile organization management. Calendar respects the active section/status.
- Calendar dates use Asia/Manila and half-open event intervals [start,end).
  Cross-midnight events appear on every intersecting day, but not the next day if
  ending exactly midnight. Use labeled status markers (confirmed solid, waitlist
  light dotted, pending/reconfirmation distinct) and a day-detail list; never only
  color. Month navigation, keyboard-accessible date buttons, empty/loading/retry,
  Filipino labels, large text, contrast/dark/reduced-motion must remain usable.
- Conflicts compare the target with the caller's other current confirmed published
  approved-organization events only. Ignore ended events, self, pending, waitlist,
  reconfirmation, cancelled and rejected. Strict interval overlap; touching times
  are not conflicts. Warnings do not prevent registration/reconfirmation and never
  change counts, ordering, retry outcomes or existing seats. Clearly state checking
  or failure, not "no conflict" on a failed request. Refresh after a registration
  outcome. My Events can derive same advisory warnings from its own private rows.

## Frozen interfaces

New domain app/domains/planning, using synchronous SQLAlchemy and existing auth,
errors and get_db (scope=function). No new dependency or configuration.

SavedEvent table `saved_events`: composite primary key user_id,event_id, both
String(36) foreign keys users.id/events.id; saved_at timezone-aware UTC, default
now. Public projections reuse Events' existing public visibility/counts; do not
duplicate a divergent event schema or allow arbitrary projections of drafts.

- GET /api/v1/me/saved-events -> list[SavedEventOut], saved_at DESC,event_id ASC.
- GET /api/v1/me/saved-events/{event_id} -> SavedEventState.
- PUT /api/v1/me/saved-events/{event_id} -> SavedEventState (200).
- DELETE /api/v1/me/saved-events/{event_id} -> SavedEventState (200).
- GET /api/v1/me/event-conflicts/{event_id} -> EventConflictsOut.

SavedEventOut: event_id:string,saved_at:datetime,event:EventPublic|null.
SavedEventState: event_id:string,saved:bool,saved_at:datetime|null.
ConflictEvent: event_id:string,title:string,organization_name:string,
starts_at:datetime,ends_at:datetime.
EventConflictsOut: event_id:string,conflicts:list[ConflictEvent].
Target public visibility required for conflict lookup (404 otherwise). Sort
conflicts starts_at,id. All IDs route-validated UUIDs. Existing error envelope.
Store only references/time, not snapshots. PostgreSQL insert-on-conflict or
equivalent serialization prevents duplicates; no SQLite substitution.

## Exclusive ownership

- Coordinator: existing backend router/migration/env/shared test-head assertions,
  event public-read seam if needed, OpenAPI/types, frontend i18n assembly/types,
  EventDetail and RegistrationAction integration, runtime/database/browser proof,
  docs and canonical notes. Migration mvp_0012 follows mvp_0011, additive only;
  safe downgrade refuses populated saved_events. No startup migration.
- Backend Luna/max: new app/domains/planning/** only; may request shared seam
  changes. No migration/shared files/DB suites. Exact model/interface above.
- Frontend Luna/max: new features/planning/**, existing registrations/MyEvents.tsx,
  and tests/sprint17-planning-ui.test.mjs only. Include own messages export and CSS.
  Implement/export SaveEventButton({eventId}), ConflictWarning({eventId,revision?}),
  SavedEvents({view}), EventCalendar for existing private registration rows, pure
  Manila calendar/overlap helpers with Node-testable module. Fetch through api,
  use generated schemas when available (coordinator supplies types); fence all
  private state/mutations by token/session and abort on change/unmount.
- QA Luna/max: new tests/planning/test_api.py and docs/validation/sprint17-quality-review.md
  only. Covers privacy, public-visibility changes, save retries/concurrency,
  boundaries/status exclusions, unchanged registration outcomes and profile/capacity
  rules. Inspect other code read-only; request fixes from its owner. No DB suite
  execution until coordinator grants the exclusive serial slot.

## Acceptance and stop

Explicit migration preserves pre-existing data in both local databases. Test
caller isolation, guests/inactive accounts, ineligible private saving without new
privileges, draft/unapproved-organization prevention and unavailable cleanup,
duplicate concurrent saves, boundary overlaps/status exclusions, restart
persistence. Test month/year/leap boundaries, Manila cross-midnight/midnight ends,
and responsive calendar/day details. Exercise actual existing fixture save/remove
and calendar/list via browser without creating new persistent demo organizations
or events. Run PostgreSQL tests serially; frontend tests, both builds and focused
lint. Report actual versus synthetic and deferred participant/native-device gates.
No deployment, cloud writes, Penpot edits, GitHub push or Sprint 18 implementation.

The existing Event model supports draft/published only; do not invent event
cancellation in this sprint. Unavailability checks cover drafts and organizations
that are not approved. Cancelled registrations remain excluded from conflicts.
