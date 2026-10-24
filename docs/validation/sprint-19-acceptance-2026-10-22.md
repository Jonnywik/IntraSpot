# Sprint 19 acceptance — 2026-10-22

## Outcome and scope

Featured-event requests/decisions are complete locally. The user explicitly chose
Sprint 19; Sprint 18 persona/blocking remains unbuilt. Three non-overlapping
GPT-6 Luna/max workers implemented the domain, UI and independent tests; the main
chat coordinated contracts, migration, integration, execution and final fixes.

Eligible organization owners/admins can request for their own published future
events. Platform admins approve a bounded window, reject, or revoke, with
server-derived actor/time and append-only application audit. Stale decisions
cannot overwrite current versions. Only a public boolean badge is exposed; no
feed reordering, reserved position, spotlight, registration or notification change.

The user's 2026-10-22 decision is implemented: supported material event changes
pause Featured until fresh platform review. Time, venue, banner/graphic, capacity
and cost form the fingerprint; unrelated fields do not pause. Published banner
replacement remains unavailable rather than inventing a new media workflow.

## Database and data preservation

- Reviewed/applied additive `mvp_0013` over `mvp_0012`, explicitly, in both local
  development databases. No startup migration or extension installation.
- Native PostgreSQL range exclusion forbids overlapping approved placement
  windows globally, including direct conflicting inserts. Adjacent windows pass.
- Empty migration roundtrip preserves existing events; populated downgrade
  refuses to discard feature history. Reads derive expiry without mutating rows.
  A new-request command may seal a previously expired row as stored `expired`.
- Before/after aggregate hashes match for **all 28 pre-existing tables**:
  **72 fictional-development rows and 2 real-development rows**. Final comparison
  includes the browser workflow and fixture-token refresh. Private values were
  never printed by the preservation helper.
- Browser verification intentionally added one fictional request and three audit
  rows (requested, approved, revoked), all in the new tables. The placement is
  revoked at handoff; no live feature window remains. No pre-existing event was
  edited, no real account seeded, and no notification created for this workflow.
- Docker Desktop and the existing IntraSpot database container were started;
  its volume was retained. Penpot's database was not accessed or modified.

## Automated evidence

Database suites ran serially against the isolated named PostgreSQL test databases.

| Gate | Actual result |
|---|---|
| First focused feature/migration run | 26 passed, 1 failed; exposed no-op pausing, corrected |
| Corrected focused feature/migration run | 27 passed |
| Broad default regression | 546 passed, 2 failed, 10 historical opt-in gates skipped |
| Corrected expectations + new regression proof | 4 passed: both old failures plus 2 new tests |
| Unique default cases passing across final runs | **550**; not a claim of one wholly green full rerun |
| Isolated synthetic Supabase protocol/auth regression | **50 passed**; not live Google/PLM sign-in |
| Final complete frontend suite | **100 passed** |
| Final targeted frontend/localization check | 11 passed |
| Default + real-development static builds | Both passed after final in-page dialog change; credential guards passed |
| Changed frontend files ESLint | Passed |
| TypeScript | Passed through both final builds |
| Git whitespace check | Passed |
| Alembic schema consistency | Passed: no new upgrade operations detected |

The two broad-regression failures were expectations, not ignored assertions:
the public-field allowlist now includes `is_featured`; the bounded-query check
still requires constant query count for 1 and 10 events, now **3** statements
(event rows, attendance aggregate, one Featured batch), rather than 2.
The two additional regression tests prove freshly appended audit entries appear
in mutation responses and approval rechecks time after waiting for the global
schedule lock. Upstream Starlette/Pydantic/Node warnings remain nonfatal.

Ignored local evidence: Backend `.cache/s19-featured-final.xml`,
`.cache/s19-regression.xml`, `.cache/s19-final-regressions.xml`,
`.cache/s19-auth-regression.xml`, and per-database preservation baselines. The long
full run included a workstation/tool stall; elapsed time is not performance data.

## Live browser evidence (actual served app, not Penpot/old HTML drafts)

1. Existing fictional student 4, the actual organization owner, submitted a
   Featured request for the existing Community Heritage Walk. Pending status and
   requested audit appeared. Switching to an unrelated account hid the workspace.
2. Fictional platform admin opened the queue, entered an aware Manila end time,
   and reviewed the in-page confirmation. **Go back** receives initial focus;
   Escape cancels without a mutation and returns focus to Approve. Confirm recorded
   approval and loaded the current outcome. Native confirmation was replaced
   after it blocked browser automation; native date input was verified using
   segmented keyboard entry, not a scripted value injection.
3. A guest saw one Featured badge in the ordinary four-event Upcoming order.
   The desktop viewport was **1440×900**, no horizontal overflow.
4. Restarted the actual default API, then reloaded the guest feed: the approved
   badge persisted. Verified **390×844** feed and **320×740** detail, no horizontal
   overflow. The four mobile destinations remain Discover/My Events/Chat/Settings.
5. Admin confirmed revocation; the UI showed Revoked plus all three audit entries.
   Returning to the guest feed produced zero Featured badges. Temporary viewport
   override was reset. The normal local app tab remains available.

Screenshots in `docs/validation/sprint19-browser-evidence/`:
`request-pending.png`, `approval-confirmation.png`, `featured-desktop.png`,
`featured-mobile-390.png`, `featured-detail-320.png`, `revoked-audit.png`.
Badge screenshots show the temporary approved stage, not the final revoked state.

## Fixes made during verification

- Skip no-op/nonmaterial fingerprints; fail closed on a drifted material snapshot.
- Return newly recorded audit entries immediately, not a stale relationship cache.
- Re-sample time after the global placement lock before approving.
- Batch review-queue attendance counts and public Featured lookups.
- Prevent requests for started events in the UI; preserve server-side enforcement.
- Use generated API DTOs, existing outline icons and theme/status tokens.
- Use an accessible in-page confirmation, capturing the reviewed version and
  schedule so a later update cannot silently approve unreviewed data.
- Repair the known Windows generated-cache lock by recoverably moving only the
  old `.next` cache into ignored `.cache/next-s19-recovery-20261022`; no source or
  existing static export was deleted.

## Handoff limits

Material pause/reapproval, rejection, competing approvals, exact expiry edges,
Saved/My Events badge projections and nonmaterial stability are API/helper test
evidence, not all live browser journeys. Existing production-code published banner
mutation is still denied. The complete Filipino/extra-large/dark/high-contrast
browser matrix, screen-reader/native-device testing, participant testing and live
PLM-account sign-in remain pending. Management remains desktop-only. Public badge
timing is authoritative on each API read; an already-open feed is not a realtime
push subscription. No deployment, Penpot sync, cloud application SQL/storage,
commit or GitHub push was performed. Sprint 20 is not started.

Runtime split is unchanged: fictional frontend/API 3000/8001,
real-development frontend/API 3001/8011. Supabase remains Auth-only.

The platform queue is intentionally bounded to the latest 100 requests; there is
no older-page control in this local slice. Add pagination/triage before workloads
can exceed that limit so older pending requests cannot become inaccessible.
