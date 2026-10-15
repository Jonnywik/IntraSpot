# Phase 2 — organizations and accreditation

Authorized 2026-10-12. Main chat orchestrates; no Sol coordinator subagent. Five GPT-6 Luna agents use max reasoning. The tool does not expose a fast-mode argument.

## Frozen scope and contracts

Sprint 2 completes organization applications and authorization, audited offline accreditation decisions, pending draft access, rejected read-only access, and fictional active memberships. Local PostgreSQL 17 only. No uploads, additional evidence, LinkedIn verification, appeals/reapplication, membership applications/invitations/removals/succession, frontend integration, cloud services, or Penpot changes.

Canonical rules were navigated using the existing Graphify graph and verified in the Obsidian `Functionality` (organization roles/access) and `Security & Operations` (accreditation and privacy) notes. The explicit local-MVP authorization supersedes only the prototype-only timing gate, not participant/security release gates. Unresolved Open Questions are not implemented.

- Verified actor and existing organization API response shapes remain as in `Contracts.md`. Roles and platform privileges come from current database state, never token/profile flags.
- Organization creation requires an eligible actor, persists pending status and one active owner grant atomically.
- Public organization information excludes creators, memberships, private profiles, and decision identities. Eligible active owner/admin grants authorize private workspaces. Moderator/member does not authorize management in this MVP.
- Pending owner/admin may save incomplete drafts and read private previews, but cannot publish. Approved accreditation enables the existing publishing boundary; this is not Sprint 3 acceptance. Rejected organizations retain private read access only.
- Only an active, eligible database-backed platform admin can decide a pending application. Outcome is approved/rejected; actual admin and aware UTC time are server-derived. Exactly one durable terminal decision per organization. Conflicting concurrent decisions return a controlled conflict, not a partial write or server error.
- Fixed local organization fixtures are distinct from legacy data, additive and idempotent. Existing decisions and membership edits must not be overwritten. No event/registration writes or database resets.

## Exclusive ownership

| Luna worker | Allowed edits |
|---|---|
| Identity/permissions | `app/core/auth.py`, `app/domains/identity/**`, `tests/identity/**` |
| Organizations/accreditation | `app/domains/organizations/**`, `tests/organizations/**` |
| Draft-access integration | `app/domains/events/**`, `tests/events/**`, only Sprint 2 policy boundaries |
| Fictional memberships | new `app/local_organizations.py`, new `tests/shared/test_local_organizations.py` |
| Quality assessor | new `tests/quality/test_sprint2_quality.py`, `docs/validation/phase2-quality-review.md`; targeted production fixes only after coordinator releases ownership |

Paths above are relative to `Code/Backend` except documentation. The coordinator owns shared files, integration demonstrations, test scheduling, and final handoff. Workers request shared changes; they do not spawn descendants or commit. Preserve unrelated dirty work. All source/document edits use apply_patch; shell commands start with RTK.

## Verification and stop condition

No simultaneous pytest runs: existing fixtures truncate the dedicated `intraspot_mvp_test` database per test. Workers supply focused regression tests and may perform non-database static checks. The coordinator runs the serialized PostgreSQL tests, returns failures for fixes, then runs independent live HTTP journeys against `intraspot_mvp` without truncation. The quality assessor must distinguish proven defects from speculative concerns and retest fixes.

Acceptance: pending creation/owner grant, private cross-organization isolation, current-role/privilege enforcement, approve/reject audit and concurrency, pending draft/publish denial, rejected read-only access, fictional active memberships, rollback safety, and persistence across backend restart. Sprint 1 regressions and migration drift are checked. Record exact outcomes and any blockers; do not claim production readiness or proceed to Sprint 3.

## Final checkpoint

Passed on 2026-10-12: 85 PostgreSQL regression tests, focused 8-test quality gate, 8 live HTTP check groups plus a distinct-instance persistence check, fixture rerun preservation, and migration drift check. See [independent acceptance evidence](../validation/sprint-2-acceptance-2026-10-12.md). All subsequent sprints remain paused. Fast mode was not configurable through the agent tool.
