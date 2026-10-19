# Sprint 14 acceptance — organization announcements and reactions

Status: complete locally, 2026-10-19.
Local fictional MVP only. This is not a real-user release or participant test.

## Scope and coordination

The main chat coordinated four non-overlapping GPT-6 Luna/max workers: core
announcements/reactions, announcement safety/platform review, organization UI,
and independent cross-domain/browser QA. Shared configuration, migration,
generated contracts, serial database verification and runtime remain coordinator
owned. Existing Sprint 9–13 dirty work was preserved; no commit/push was requested.

The Graphify/canonical-note check established the accepted Sprint 14 behavior.
Existing organization, membership, six-reaction, communication-restriction,
notification, error and UI patterns were reused. Dedicated report rows avoid
fake event IDs and preserve prior event/person moderation behavior.

## Verification record

| Check | Result |
|---|---|
| Additive migration rollback/re-upgrade preservation and guarded rollback | 2 passed |
| Additive local sample fixture preservation and guard checks | 4 passed |
| Concurrent create retries and competing versioned edits | Passed in focused PostgreSQL checks |
| Full PostgreSQL regression suite | 451 passed, 10 opt-in browser gates skipped, 748.27 s; zero failures/errors |
| Additional oversized/malformed version-header checks after final review | 6 passed, 2.61 s |
| Frontend contracts and localization | 63 passed, 3.57 s |
| ESLint / TypeScript / isolated static build and credential guard | Passed |
| Actual Sprint 14 Edge journeys | 1 passed, final 44.08 s; seven groups, zero unexpected JavaScript/HTTP/network failures |
| Affected desktop/mobile/Flash browser regressions | 3 passed serially, 182.53 s; 18 + 11 + 9 journey groups |
| Explicit development migration and model/schema drift | `mvp_0010` applied; all pre-existing row contents preserved; no new upgrade operations detected |
| Normal local frontend/API/deadline runtime | Frontend 3000 and API 8001 ready at `mvp_0010`; explicit 30-second worker restored; read-only API and clean Edge smoke checks passed |

Tests are serialized against allowlisted `intraspot_mvp_test`, never the
development database or Penpot database. Earlier failed checks are diagnostic
history, not acceptance. The six header cases were added after the default
regression run and executed separately; do not describe that default run as
containing them. Opt-in gates above were run separately, not enabled in the
default regression run. No application dependency upgrade was added. The existing
Starlette test-client deprecation and Node module-format notices are non-blocking.

## Delivered behavior

- Public and current-member-only organization posts, filtered before pagination.
  Public detail/reaction routes reveal no private/hidden/removed post information.
  Effective membership and trusted eligibility are rechecked server-side.
- Approved eligible owner/admin publishing, version-checked edits/removal,
  original create-key conflict protection and manager-only revision history.
  No-op edits avoid a false Edited marker; removal is an authorized retry-safe
  tombstone. Hidden text cannot be edited into visibility by an owner.
- The same six aggregate reactions, independently replaceable/removable, with
  no attendance, waitlist or interest-count side effects. Organization-first
  locks serialize writes and membership lifecycle operations.
- Direct platform reporting/review with exact per-case evidence, no automatic
  hiding or personal restriction, separate metadata-only caller receipts,
  dismiss/hide/restore/remove, real deciding actors and idempotent notices/audits.
  Only the case that actually hid a post may restore it. Removal is permanent.
- Evidence is withheld at the 14-day deadline even before worker catch-up, then
  purged on decision/expiry without reconstructing it from revision history.
  Independent open cases retain their own snapshots after edits/removal.
- Existing organization profile reader and desktop owner/admin workspace;
  desktop platform queue; English/Filipino, larger text, inherited theme/contrast
  and reduced-motion support. Four mobile tabs and desktop-only management stay
  unchanged. Explicit load-older controls avoid truncating older announcements.

## Review corrections

Coordinator integration review corrected communication-restriction checks for
new/changed announcement content, lost-response removal retries, strict public
detail hiding even for managers, and the private reaction authorization order.
Another case cannot acquire restoration authority merely by hiding an already
hidden post. Shared localization typing, error rendering, scope-aborted requests,
and older manager pages were checked during frontend integration.

QA assertions were reconciled with the frozen contract: managers retain their
authorized hidden/removed revision history, and an owner removal remains
attributed to that owner even if a platform report decision occurs afterward.
Browser harness corrections distinguish selected-case reuse from a new fetch,
use UI preference saves, and scope status labels without relying on CSS-module
class names. These harness corrections are not product feature changes.

Final review also bounded malformed report version headers before integer
conversion, preventing oversized values from becoming server errors. A pure
executed frontend test verifies that network-error copy does not display a
dropped `{action}` placeholder. Theme-aware announcement headings use relative
sizes rather than fixed dark colors or fixed 20 px text.

## Browser and runtime evidence

- [Final announcement results](sprint14-browser-evidence/2026-10-19T02-07-47-246928Z/results.json):
  guest public-only browsing, member-only reading, reactions/receipt, owner
  create/edit/history/remove, desktop-only management, platform hide/restore/
  remove, Filipino XL, and dark/high-contrast/reduced-motion settings.
- [Owner edit and history](sprint14-browser-evidence/2026-10-19T02-07-47-246928Z/owner-desktop-edited-history.png)
  and [platform review](sprint14-browser-evidence/2026-10-19T02-07-47-246928Z/platform-queue-hide-restore-remove.png)
  were visually inspected.
- [Filipino XL mobile](sprint14-browser-evidence/2026-10-19T02-07-47-246928Z/member-filipino-xl-390.png)
  and [dark/contrast mobile](sprint14-browser-evidence/2026-10-19T02-07-47-246928Z/member-dark-contrast-xl-390.png)
  were visually inspected after reaction totals finished loading. The selected
  member reaction survives reload; 320/390 px have no horizontal overflow and
  retain four attendee destinations. Earlier captures that still show loading
  states are diagnostic history, not the final layout reference.
- [Desktop-management regression](sprint14-management-regression-evidence-2026-10-19/results.json)
  covers four desktop sizes, pending/approved draft workflows, stale versions,
  inbox/staff access and platform decisions. This suite's original evidence was
  copied from its exact temporary output directory without changing the results.
- [Mobile-attendee regression](sprint11-browser-evidence/2026-10-19T02-01-20-660744Z/results.json)
  covers registration, faculty eligibility, waitlists, chat, profile and independent
  preferences; [Flash regression](sprint13-browser-evidence/2026-10-19T02-02-22-665364Z/results.json)
  covers ranking/filtering, publishing, account scopes and existing participation.

The final browser gate records canceled navigation/prefetch/cleanup requests
separately. They are not unexpected transport failures; its unexpected HTTP,
JavaScript/console and non-abort network error arrays are empty. Explicit negative
authorization API checks are recorded separately rather than hidden from those
assertions. Evidence contains fictional content/IDs only, not bearer tokens.

Docker Desktop and its existing dedicated PostgreSQL container/volume were
restarted, not reset. The development migration compared counts and hashes of
all existing tables' complete rows before/after upgrade, then two fictional
announcement samples were added through existing domain authorization. No
existing profiles, roles, memberships, posts or history were overwritten.
The ordinary 30-second deadline runner is explicitly restored, not a startup
migration/timer. Read-only API checks confirm health/readiness, verified fictional
identity, preferences, My Events, public/private announcement isolation and
reactions without creating development registrations or changing preferences.
The final normal frontend export targets API 8001 (not the scratch 8002 gate).
A fresh Edge context rendered the public sample, excluded the member-only sample,
fit the desktop viewport and reported zero browser/HTTP errors.

The canonical Obsidian AI Index, Development Handoff, Implementation Roadmap,
Functionality and UI/UX notes record this checkpoint and preserve open release
decisions. Sprint 15 is next and has not been started. All four workers are closed.

## Boundaries and release gates

No comments/forum, new persistent navigation, broadcast announcement notices,
uploads/media handling, real Google/Supabase authentication, cloud connection,
Penpot synchronization, deployment, broad seeding/data reset or Sprint 15.
No external messages or operational email. Application requests do not migrate
automatically. The explicit deadline worker is required for timely background
catch-up after idle periods.

Local revision/tombstone history is preserved for review; long-term retention
and account/deleted-content handling are still open production decisions.
Participant, native-device, assistive-technology, security and release validation
remain separate. Automated Edge checks do not close those gates.

See [contract](../backend/Sprint-14.md) and
[interaction handoff](../design/sprint14-interaction-handoff.md).
