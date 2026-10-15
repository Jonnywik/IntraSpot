# Sprint 2 local backend acceptance — 2026-10-12

**Result: Sprint 2 automated/local acceptance passed. Stop at this milestone.** This is fictional local backend verification, not participant testing, deployment approval, or acceptance of Sprints 3–5.

## Completed behavior

- Eligible users create pending organization applications with an atomic active owner grant.
- Public organization profiles expose only id, name, description, accreditation status, and creation time. Eligible active owner/admin grants authorize private workspaces; guests, other organizations, moderators, members, and inactive grants cannot manage them.
- Current database membership roles and accreditation status are reflected with the same valid identity token. Browser/token/profile claims cannot grant platform privileges.
- Platform admins record approved/rejected outcomes after offline assessment. Actual deciding admin and aware UTC time are derived server-side. Terminal decisions are immutable, including concurrent conflicting attempts.
- Pending owner/admin can create/update incomplete drafts and read private previews, but cannot publish. Approval enables the existing publication boundary. Rejection preserves private read access and forbids draft changes or publication.
- Added three fixed fictional organizations, twelve active owner/admin/moderator/member grants, and two audited terminal decisions, including faculty membership for My Clubs. The local fixture command preserves existing edits and never seeds events, registrations, or frontend tokens.

## Bugs corrected and regression proof

- Locked organization reads now refresh cached ORM state. An accreditation decision or draft write cannot proceed using a stale pre-lock accreditation value.
- Platform-admin authorization reloads database identity/eligibility rather than trusting cached privilege state.
- Both publish and draft PATCH refresh/lock the event after locking its organization. Waiting callers cannot publish the same draft twice or materially edit an event that has just been published.
- Corrected new test defects: missing `make_event` fixture, incorrect sessionmaker context construction, and a direct-call test retaining a row lock after an expected denial.
- Failed accreditation commits roll back both terminal status and audit record; no success response is inferred from a flush alone.

## Independent coordinator verification

All pytest executions were serialized against the dedicated `intraspot_mvp_test` database. The local live checks used `intraspot_mvp` without truncation.

| Check | Observed result |
|---|---|
| Initial integration run | 42 passed, 1 failed (new test omitted fixture); fixed before acceptance |
| Focused race/access/rollback regressions | 8 passed, 1 upstream warning, 14.15 seconds |
| Final Sprint 1/2 and event-boundary regression suite | **85 passed**, 1 upstream warning, 44.70 seconds |
| Alembic drift | No new upgrade operations detected; existing `mvp_0001` remains head |
| Live HTTP before restart | 8 check groups passed, including conflicting decisions and rejected read-only drafts |
| Distinct-instance restart | Passed; exact organization/workspace/audit/private-draft snapshots unchanged |
| Live fixture rerun | 3 organizations, 12 grants, 2 decisions unchanged |
| Static checks | Python compilation/test collection, live checker syntax, and organization API shape checks passed |
| Secret isolation | Local manifest, signing key, environment file and virtual environment confirmed ignored |

The final suite includes pre-existing event tests as integration regressions; this does **not** accept the entire events sprint. The warning is Starlette's upstream deprecation of its httpx-based TestClient. Runtime interpreter relocation diagnostics were non-fatal; command exit codes and test outcomes above were verified.

Evidence: [live result groups](phase2-live-results.json), [repeatable live checker](phase2-api-check.mjs), [independent Luna quality review](phase2-quality-review.md), [Docker repair](docker-repair-2026-10-12.md).

## Reproduce

From `Code/Backend`, with the existing ignored local configuration and isolated PostgreSQL 17 service:

```powershell
rtk proxy .mvp-venv/Scripts/python.exe -m pytest -q tests/identity tests/organizations tests/events tests/shared/test_foundation.py tests/shared/test_local_identities.py tests/shared/test_local_organizations.py tests/quality
rtk proxy .mvp-venv/Scripts/python.exe -m alembic check
rtk proxy .mvp-venv/Scripts/python.exe -m app.local_identities
rtk proxy .mvp-venv/Scripts/python.exe -m app.local_organizations
```

The fixture command accepts no custom identity or database arguments and requires explicit local fixture configuration. For the live check, launch the API on loopback port 8001, run `rtk proxy node docs/validation/phase2-api-check.mjs before` from the project root, restart that owned API instance, then run the same checker with `after`. It creates clearly fictional additive organization/draft demonstration records and retains them for durability proof. Tokens/snapshots remain in ignored `.local` files; no credentials are included in the evidence.

## Boundaries and remaining gates

No proof uploads, extra accreditation evidence, LinkedIn checks, appeals/reapplication, membership applications/invites/removals/succession, frontend integration, real email collection, cloud connection, or deployment was added. Existing later-domain scaffold is preserved, not accepted. Management remains a backend API at this milestone; the approved Penpot design is unchanged.

The main chat orchestrated five GPT-6 Luna/max agents with disjoint initial ownership and controlled quality-fix handoffs. No Sol coordinator subagent was created. Fast-mode selection is not exposed by the tool and was not claimed. Canonical Obsidian decisions were read and preserved; this document is the local implementation checkpoint supplement.

Participant validation and security/release checks still gate any real-user release. Privilege revocation during an already-authorized in-flight request is not a proven defect here and was not stress-tested; new requests do re-read current authority. The loopback API and separate database are left running for local demonstrations only.
