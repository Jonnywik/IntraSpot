# Sprint 7 local acceptance and handoff

Date: 2026-10-15 (Asia/Manila). Authorized 2026-10-14. The main chat coordinated
six non-overlapping GPT-6 Luna/max workers: social, chat, moderation, attendee UI,
management UI, and independent quality review. All workers are closed. No separate
Flash/fast-mode setting was exposed by the tools; none is claimed.

## Accepted local scope

- Published-event comments are guest-readable. Eligible fictional PLM accounts
  can post before event start, with safe same-key retries and author removal.
  Bodies are plain text; private profiles and emails are not public author data.
- Six reactions: Interested, Excited, Support, Kudos, Wow and Relate. One active
  reaction per person/event; switching replaces and clearing removes. Interested
  totals stay synchronized. No reaction registers anyone or reserves a seat.
- Confirmed-attendee-only event chat, including staff. Pending, waitlisted,
  withdrawn and reconfirming attendees have no chat access. Visible-view polling,
  paging, safe send retries and account-change cleanup use the local APIs.
- Chat becomes read-only at scheduled end, remains in the same inbox with Archived
  and a deletion countdown, and is inaccessible exactly 72 hours after end.
  The explicit local worker physically deletes original expired messages.
- Reporter-only hide/restore, one active report per person/target, organization
  review for content, and platform review for escalated or explicit personal
  reports. Reporting alone does not remove content. Authorized decisions are
  server-recorded; resolved/expired evidence is cleared and closed audits remain.
- Open personal review pauses new comments/chat and event creation/publication,
  not reads, reactions, registrations or existing seats. Dismissal, warning or
  expiry restores access. No automatic permanent ban was introduced.
- Generic, durable, in-app notifications with caller-only reads and idempotent
  mark-read feedback. No email, push, real identities, DMs or uploads.
- Desktop staff review and attendee desktop/mobile surfaces retain PLM styling
  and the four mobile tabs. Mobile organization management remains unavailable.

## Verification actually executed

| Gate | Observed result |
| --- | --- |
| Complete serial PostgreSQL backend suite | 257 passed, three opt-in browser tests skipped, 214.94 s |
| Sprint 7 browser gate | One passed, nine journey groups, 33.45 s; repeated successfully in the combined gate |
| Earlier approval/reconfirmation browser gate | Eight journey groups passed in the combined gate |
| Earlier core journeys, restart and viewport gate | One passed, ten journey groups including five viewport checks, 40.50 s |
| Frontend contract tests | Nine passed |
| Frontend lint | Passed |
| TypeScript, static export and public/static credential scans | Passed for isolated tests and the restored normal-port 8001 build |
| Development Alembic schema check | No new upgrade operations detected |
| Normal local runtime | Health/readiness HTTP 200, migration `mvp_0005`; worker running at 30-second intervals |

Backend coverage includes concurrent idempotency/report deduplication, chat access
revocation, event-start/end/retention boundaries, personal restriction without seat
loss, organization/platform role isolation, evidence cleanup, notification
deduplication, restart catch-up, migration preservation and existing registration
capacity/order tests. One upstream Starlette/httpx deprecation warning remains;
frontend contract tests also emit a non-blocking Node module-inference warning.

Browser testing used local Edge/Playwright and persisted scratch PostgreSQL, not
mocked outcomes or participant research. Sprint 7 checks actual lost-response
comment recovery, all six reaction replacements/clears, confirmed chat, waitlist
denial, reversible personal hide, moderator removal, platform personal-review
resolution, mobile archive/countdown/four tabs, and persisted notification reads.
The earlier gates cover the original four journeys, approval/reconfirmation,
capacity reduction, account privacy, multiple viewports and API restart.
The final core rerun verified complete first-card fit at 1440×900, the unchanged
2.88 artwork ratio, no horizontal overflow at all five viewports, and retained
four-tab mobile navigation. Earlier failure screenshots are diagnostic history;
the latest `results.json` and `discover-*.png` capture the passing core gate.

## Findings fixed during integration

- Same-key comments/chat recover their original outcome under a newly imposed
  personal restriction; new writes remain denied and withdrawn chat access is not
  restored by a retry. Write clocks are sampled after the authoritative locks.
- Active report retries recover the reporter's existing receipt before a newly
  hidden target is rechecked, while message-report access remains confirmed-only.
- Chat event IDs use UUID request validation and mutations commit before success.
- User metadata uses PostgreSQL `NO KEY UPDATE` locks, retaining serialization
  while avoiding foreign-key lock cycles during cross-event notification writes.
  Durable admission-order assertions remain intact.
- Manual escalation gets fourteen days from the action; automatic catch-up uses
  the stored organization deadline rather than extending it at restart time.
- Polling clears already-cached message bodies after global moderation removal.
  Decision controls and notification headings match actual API outcomes.
- The independent QA test's foreign-organization fixture was corrected: access
  to one's own empty queue is allowed; access to the other organization is denied.
- Feed social counts and comment access sit outside the card's main link, avoiding
  nested interactive controls. Desktop counts/comment access share a compact row.
  Redundant heading/fact spacing was removed without reducing text size, changing
  artwork aspect ratio, hiding information or relaxing viewport assertions.

The independent review and coordinator follow-up are in
[Sprint 7 quality review](sprint7-quality-review.md). The shared interfaces and
user decisions are recorded in [Sprint 7 contract](../backend/Sprint-7.md).

## Runtime and reproduction

- Normal frontend: `http://127.0.0.1:3000`, using local API port 8001 after the
  scratch browser build is restored. API binds to `127.0.0.1:8001` only.
- PostgreSQL 17 uses the dedicated `intraspot_mvp` database on loopback 5433.
  Browser and backend tests reset only guarded `intraspot_mvp_test`. Penpot's
  database and cloud services are not used.
- Readiness requires reviewed migration `mvp_0005`; migrations never run at API
  startup. The additive migration's downgrade refuses to discard communication
  data or notification read states.
- Docker had stopped across the interruption. Docker Desktop and the existing
  container were restarted without volume removal or data reset. Expired fixed
  fictional tokens were renewed in the ignored backend manifest only.
- `app.local_communication` additively supplies Fictional Community Meetup, owned
  by Fictional student 4. Choose sample attendees, register them, then use their
  confirmed chat. The helper creates no fake comments, reports or attendance and
  preserves existing edits on rerun.
- The explicit worker runs at 30-second intervals for stored registration/report
  deadlines and chat cleanup. Stopping it delays unattended processing, not durable
  outcomes; restart catches up from stored deadlines. Read access still enforces
  chat/report retention boundaries while cleanup is delayed.
- Setup, token renewal, serial test gates and worker commands are in the
  [backend README](../backend/README.md). Browser evidence is under
  `sprint7-browser-evidence`, with earlier checks under `sprint5-browser-evidence`
  and `sprint6-browser-evidence`.

## Remaining limits and release gates

This is a local fictional-data MVP, not production or deployment approval.
Participant validation and security/release review remain required. No cloud,
real OAuth, uploads, email, membership lifecycle or Penpot redesign was performed.
The smallest in-scope implementation was retained; no dependency upgrade or broad
refactor was needed. The local worker is not a managed production scheduler.

The explicit `ChatThread.removed_ids` refinement returns all retained tombstone
IDs so old cached bodies cannot persist after moderation. The payload grows with
removals in the 72-hour window: it is an acknowledged local-pilot limit, not a
production scalability claim. Replace it with bounded cursor-based invalidation
before meaningful cloud traffic; do not truncate IDs silently and leave stale
content visible.

Canonical Obsidian notes were read but not changed because the vault is outside
the writable workspace. Synchronize the implemented Sprint 7 decisions from the
contract during an authorized vault update. No broad seed/reset, container-volume
deletion, public token manifest or real-user data collection was performed.
