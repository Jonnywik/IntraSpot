# Sprint 22 — event safety and temporary organization suspension

Date: 2026-10-24. **Implemented locally; final acceptance remains open.**
Developer evidence only. No deployment, participant approval or Penpot sync.

## Delivered

- Eligible signed-in readers can report events for safety or deception. Initial
  organization review lasts seven days; after its first decision, three distinct
  reporters within the rolling seven-day window route new reports to fourteen-day
  platform review. Duplicate active reports/retries do not inflate that count.
  Reporting alone never hides an event. Snapshots contain bounded public event
  text, valid JSON and no private profile/email fields; evidence expires durably.
- Eligible same-organization owners/admins/moderators may dismiss reports and hide
  or restore their organization's hide. Platform admins control a separate hide,
  permanent removal and organization suspension. Restoring one channel or ending
  suspension cannot clear another channel or a terminal cancellation/removal.
- Platform suspension supports 1–30 days, default seven, automatic exact expiry,
  audited early restoration and deduplicated notices after catch-up/restart.
  Accreditation is unchanged. Publishing, discovery and new registrations/waitlist
  admissions are blocked while suspended, including direct requests.
- **User choices 1B/2A:** Existing approval reviews, deadlines, reconfirmation,
  withdrawal, FIFO waitlist promotion and confirmed-attendee chat continue during
  hides/suspension. No frozen/rebased deadlines. Active eligible participants and
  organization staff retain nonterminal details; guests/outsiders do not.
- Discovery, My Clubs, Featured badges and saved-event public projections exclude
  restricted events. Private bookmarks and existing participation remain. Public
  event responses include authoritative `registration_available`; existing outcome
  and withdrawal controls remain usable.
- Owner/admin cancellation and platform removal atomically cancel all active
  participation, clear review/reconfirmation fields, seal unprocessed receipts and
  notify affected registrants/active eligible members without duplicates. Original
  completed intake responses remain retrievable. Terminal events cannot publish,
  change materially, accept new attendance writes or promote waiters. Registration,
  attendance, chat and audit rows remain. Authorized private banner history remains
  available through the existing manager path; public access is denied.
- Commands recheck current authority, use captured versions, actor-bound request
  keys and PostgreSQL locks. Report-review event versions detect both material and
  safety-state changes. Exact retries preserve original outcomes; incompatible or
  stale commands conflict rather than silently adopting newer state.
- Existing desktop workspaces/admin views contain lazy safety controls, review
  queues, restoration, suspension and history. Attendee event reporting supports
  mobile without new management navigation. English/Filipino, native confirmation,
  focus return, request cleanup and existing theme/contrast tokens are included.
  No report/command state is stored in browser persistence.

## Database preservation

Explicit additive `mvp_0017` follows `mvp_0016`, creating `event_controls`,
`organization_suspensions`, `event_reports` and `safety_audits`. No startup
migration or development safety seed. Downgrade refuses any nonempty safety
table. Aggregate hashes matched **all 37 pre-existing tables**, with **76 fictional
development rows and 2 real-development rows** preserved in their separate local
databases. No Penpot database or cloud application SQL/storage was touched.

## Actual verification

Four GPT-6 Luna/max workers owned non-overlapping backend, UI, boundary-integration
and independent QA files. The coordinator integrated shared policy/migration,
parent views, notifications, OpenAPI/types and serial database verification.

| Check | Result |
|---|---|
| Existing identity/organization/event/registration suite | 232 passed initially; one public-field assertion updated for the additive availability boolean and passed in focused rerun |
| Final safety domain + migration + visibility suite | 37 passed, including three PostgreSQL races |
| Independent QA + affected planning/media/social/Featured/chat/attendance regression | 87 passed initially; corrected QA expectations rerun separately |
| Final independent HTTP QA | 7 passed: six functions, one parameterized terminal journey |
| Distinct passing default PostgreSQL cases across recorded runs | **359**, deduplicated; no unresolved failures, not a full repository rerun |
| Separate synthetic authentication suite | **50 passed**; not live PLM-account sign-in |
| Final complete frontend Node suite | **140 passed** |
| Whole frontend ESLint and TypeScript | Passed |
| Default/real-auth export | Both compile, type-check and generate all 14 pages; final exports stop on the unchanged Next.js 16.4.0 security advisory |
| Alembic drift and seven new/shared Python syntax checks | Passed |
| Live local API | `/health` ok, `/ready` reports `mvp_0017`, seven safety paths in OpenAPI, guest discovery returns four existing public events |
| Development data hashes | Passed for both profiles |

Review corrected stale report tokens, repeat-reporter escalation, parseable bounded
JSON, retained terminal banner authorization, terminal draft/media writes, evidence
venue-field mapping, platform restoration reachability and frontend lifecycle/theme
issues. Initial QA fixture mistakes (missing approval review window and a nested
registration response) were fixed without weakening production rules. One upload
returned a transient 500 during the larger run and passed in the full corrected QA
rerun; its cause was not established, so no general media reliability claim follows.
An accidentally overlapping test invocation was stopped; final recorded suites ran
serially. Intermediate failed/incomplete runs are not counted as passing evidence.

## Open gates

- Live browser presentation/keyboard/mobile checks remain unavailable after the
  previously blocked internal-error tab. No alternate browser bypass, screenshots
  or new live click-through pass is claimed. API/helper checks are not UI testing.
- The installed Next.js 16.4.0 security advisory remains unresolved. One earlier
  default export succeeded after a Windows permission retry; later final exports
  stop at the advisory. No dependency patch or security-check suppression was
  performed. A successful compilation does not close the security/release gate.
- Participant validation, physical-device/full accessibility and localization
  matrix, live PLM-account sign-in, operational/security review and release approval
  remain separate. No pilot, cloud app-data migration or Sprint 23 is authorized by
  this checkpoint. Retained historical content still needs its prior retention/
  operational decisions before hosting.

Per standing user instruction, publish the verified checkpoint to GitHub while
keeping these gates explicit; pushing is not deployment or release approval.
