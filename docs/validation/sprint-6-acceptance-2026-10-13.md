# Sprint 6 local acceptance and handoff

Date: 2026-10-13. Coordinator: main chat; four non-overlapping GPT-6 Luna/max
implementation workers plus an independent Luna/max quality assessor. All workers
are closed. The tool exposes no separate fast-mode switch, so none is claimed.

## Accepted local scope

- Approval event drafts and publishing settings, alongside existing instant events.
- Capacity-safe pending reservations, waitlists, organizer/admin/moderator decisions,
  one review extension, escalation excluding the first reviewer, and timeout release.
- An explicit restart-safe deadline worker; no migrations or timer at API startup.
- Optional per-event persona sharing, off by default. Authorized review omits email
  and images and hides persona after event end. Cross-organization reads/decisions
  are denied before catch-up mutations.
- Material changes with revision-bound reconfirmation, reserved seats, accept/decline,
  timeout release and promotion. In-app notices commit with state changes.
- Capacity reduction defaults to exact selected removals. The optional
  `newest_in_pool` mode cancels only the required number within the selected pool;
  unselected attendees are protected. Pending and reconfirming seats count as occupied.
- Desktop staff review/change screens and attendee desktop/mobile feedback, including
  direct result-specific Pending/Waitlist/Confirmed navigation in My Events.
- Additive fictional approval workshop fixture; existing development data preserved.

## Verification actually executed

| Gate | Observed result |
| --- | --- |
| Full serial PostgreSQL regression | 205 passed, two opt-in browser tests skipped, 143.29 s |
| Focused QA/infrastructure/events | 55 passed, 68.14 s |
| Final Sprint 6 browser + independent QA | 10 passed, 48.01 s |
| Earlier core browser/restart gate | One test passed, ten check groups, 49.67 s |
| Frontend contract tests | Nine passed |
| Frontend lint, TypeScript and static export | Passed after final fixes |
| Public/static credential scans | Passed before and after builds |
| Alembic drift check | No new upgrade operations detected |
| Development readiness | HTTP 200, migration `mvp_0004` |
| Database integrity | Three approval/revision checks present on development events |

Real browser testing used local Edge/Playwright and persisted scratch PostgreSQL,
not static outcomes. Sprint 6 covered eight journey groups: guest approval detail;
student opt-in and pending result; faculty opt-out and waitlist; owner decisions;
exact-default reduction; accept-current-revision; optional pool reduction; and saved
mobile decline with four tabs/moderator edit denial. The earlier gate rechecked
guest discovery, profile completion, instant registration, faculty waitlisting,
withdrawal/promotion, My Clubs/search, immutable retry, pending draft, accreditation,
approved publishing, five viewports and API restart. Representative first-card fit
at 1440×900 and approved artwork aspect ratio passed without shrinking text/artwork.

The backend includes ten concurrent approval attempts for three seats, durable
admission ordering, original retry preservation, stale revision/deadline rejection,
authorization/privacy, migration preservation/refused destructive rollback and
independent-process catch-up. Final QA also asserts warning delivery to exactly the
applicant and assigned reviewer, with repeat-run dedupe checks.

## Findings fixed during verification

- Capacity selector had an ambiguous accessible name; added an explicit label.
- My Events follow-up hid pending/waitlisted results under Confirmed; result links
  now select the corresponding validated tab, preserving static-compatible routes.
- Empty optional summaries created unnecessary space; absent summaries no longer
  render an empty block. No content, heading size or image aspect ratio was hidden.
- Draft-era duplicate event checks blocked scratch migration; integrity migration
  normalizes only the three known check names atomically before recreating them.
- Reviewer extension reminders are delivered separately and deduplicated.

Existing browser assertions were updated for the honest Join waitlist action and
equivalent cancellation copy. Assertions were not removed or relaxed for viewport
fit, privacy, retry safety or persisted outcomes.

## Runtime and reproduction

- Frontend: `http://127.0.0.1:3000`, restored to API port 8001 after scratch tests.
- API: `http://127.0.0.1:8001`, loopback-only, sanitized logging.
- PostgreSQL 17: dedicated `intraspot_mvp` on loopback 5433; never Penpot's database.
- Deadline polling: explicitly started at 30-second intervals. Keep it running for
  unattended processing; stopped processes delay catch-up but do not lose deadlines.
- The fixed account selector is local fictional authentication, not real sign-in.
  Choose an eligible sample attendee to request the Fictional Approval Workshop;
  Fictional student 4 owns its organization and can review it on desktop.
- Setup, test commands, token renewal and worker restart are in
  [backend README](../backend/README.md). Fixture tokens remain ignored backend data.
- Browser evidence: `sprint6-browser-evidence/results.json` and mobile screenshot;
  earlier journeys: `sprint5-browser-evidence/results.json` and viewport screenshots.

## Remaining gates and limits

This is a working local fictional-data MVP, not a deployment or production-security
approval. Participant testing remains outstanding. No cloud service, real OAuth,
email, chat, membership lifecycle or Penpot/mobile organization-management changes
were authorized. Dependency warnings (Starlette/httpx deprecation, Pydantic alias,
Node module inference) remain non-blocking; no broad dependency upgrade was performed.
The local worker is not a managed production scheduler. Canonical Obsidian notes
were not written because the vault is outside the writable workspace; synchronize
the capacity-selection decision recorded in Sprint-6.md during the next authorized
handoff update. No data reset or container-volume deletion was performed.
