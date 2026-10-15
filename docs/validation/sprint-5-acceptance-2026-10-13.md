# Sprint 5 acceptance — 2026-10-13

The local frontend integration gate passed. This is a fictional-data MVP, not
approval for real users, cloud services or deployment. Penpot and its database
were not changed. Existing development profiles, decisions and registrations
were preserved; browser acceptance used only `intraspot_mvp_test`.

## Working journeys

- Guests browse published events, search titles/organization names and open
  `/events?eventId=…`, including events published after the static build.
- Eligible students/faculty complete private profiles, confirm registration or
  join a waitlist, see position/no-estimate copy, and find current results in
  My Events. Withdrawal promotes the earliest waiter and exposes the persisted
  promotion notification. Pending approval registrations and chat remain disabled.
- Eligible organization creators apply, prepare incomplete pending drafts and
  preview privately. Publishing stays disabled until approval. Owners/admins
  use desktop management; moderator/member grants do not grant manager controls.
- Platform admins record offline accreditation decisions; identity and timestamp
  come from the backend. Rejected workspaces remain read-only, without appeals,
  uploads or reapplication. Published material edits remain unsupported.

Domain screens use FastAPI data, generated OpenAPI types and shared feedback.
No browser database connection or static substitute registration outcomes exist.
The single-column PLM feed uses ivory/white, burgundy identity, navy actions,
blue interaction accents and gold focus/selection. Font-family fallbacks remain
local; no external font service is contacted. Full Penpot feature/motion parity
is not claimed by this four-journey integration milestone.

## Independent evidence

| Gate | Result |
|---|---|
| PostgreSQL regression suite | 176 passed, 1 intentionally skipped opt-in browser gate; 135.61 s |
| Frontend contract checks | 9 passed; API transport/path guards, local flags, dates, resource/session isolation and schema aliases |
| Opt-in real-browser gate | 1 passed in 28.80 s; ten journey/presentation groups, followed by API restart persistence |
| Static export / TypeScript | Passed; all eleven application routes export without per-event path generation |
| Frontend lint | Passed without findings |
| Public/static credential scans | Passed before build and on exported output |
| Alembic drift check | No new upgrade operations |

The browser gate used the real FastAPI server and PostgreSQL scratch database,
not mocked domain responses. Its lost-response test lets the original request
commit, drops that response, and verifies that retry reuses its idempotency key
and creates only one registration. The faculty's promoted registration survives
termination and restart of the isolated API process.

Rendered checks cover 1280×720, 1366×768, 1440×900, 1920×1080 and 390×844:
no horizontal overflow, labeled buttons, the 2.88 artwork ratio, a complete first
card at 1440×900, four mobile tabs and hidden direct mobile manager editing.
Desktop/mobile screenshots were visually inspected. Browser page-error count
was zero. These are heuristic checks, not participant testing.

Evidence: [browser results](sprint5-browser-evidence/results.json),
[browser harness](sprint5-browser-check.mjs),
[independent quality review](sprint5-quality-review.md).

## Repairs made during integration

- Local credentials moved recoverably out of public frontend assets. The
  backend catalog verifies the existing fifteen fixed signed tokens and permits
  only explicit local mode, loopback peers and allowlisted hosts/origins.
- Static `.txt` route data now has the proper content type: internal Next.js
  links no longer hard-reload and silently clear the memory-only account.
- Profile/draft initialization no longer triggers synchronous effect resets;
  account changes still clear private page state. Profile-save success survives
  refreshing the same actor. Labels remain concise for assistive technology.
- My Clubs includes all active role grants, composes with search, and is not a
  venue search. Draft authorization uses the actual draft organization.
- Manila conversion rejects impossible calendar dates. The API helper rejects
  decoded traversal segments, backslashes and fragments before sending tokens.
- Registration dialog traps keyboard focus, restores it on close and respects
  start-time closure. Counts refresh after success without removing the outcome.
- Cropped artwork preserves the approved ratio; discovery spacing and controls
  were refined without shrinking text or the browser viewport.

Docker's stopped local engine was restarted; no containers, volumes or data were
deleted. One upstream Starlette/httpx deprecation and a non-fatal Node helper
module-format warning remain; neither caused a failed acceptance check.

## Handoff and release limits

Normal API: `http://127.0.0.1:8001`; normal frontend: `http://127.0.0.1:3000`.
The normal build was restored after scratch testing. Live readiness reports
`mvp_0002`, the frontend returns HTTP 200, all fifteen fixed accounts are
available, and public discovery returns the existing development events.
Tokens stay in memory and intentionally clear on a hard reload. Renew the fixed
catalog with `app.local_identities` after its eight-hour expiry. See the
[local setup guide](../backend/README.md) for reproducible commands.

Use the milestone evidence rather than stale prototype-only stage text in older
briefs. The canonical product notes still own settled behavior; this sprint did
not invent unresolved roadmap decisions. Approval-mode capacity semantics,
communication/safety rules, cloud authentication/media, participant validation
and security/operational release review remain prerequisites for later sprints.
