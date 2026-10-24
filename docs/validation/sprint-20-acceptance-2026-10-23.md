# Sprint 20 — manual ownership transfer

Date: 2026-10-23. **Implemented locally; final acceptance remains open.**
This is developer evidence, not participant or deployment approval. Sprint 19
was previously completed out of sequence; Sprint 18's remaining gates are not
silently closed by this sprint.

## Delivered

- An eligible active owner of an approved organization nominates a different
  eligible active admin from that organization's existing private roster.
- The named admin accepts or declines within seven days; the owner can revoke.
  Only one offer may be pending. History is scoped to the current owner or the
  named nominee, bounded to the latest 100 records. Guests and unrelated roles
  cannot obtain it.
- Acceptance atomically changes owner to member and admin to owner. Both
  memberships remain active. Historical creator metadata, registrations,
  waitlists, event chat and queued event-review work are preserved.
- Current roles and eligibility are rechecked after locking. Versioned decisions
  and stable request keys prevent duplicate effects or reversal of a terminal
  outcome. The former owner can recover their original request, not create a
  new one. Audits and deduplicated in-app notices commit with the role change.
- Existing desktop workspace gains localized nomination/history/decision UI,
  explicit confirmations, loading/error/conflict feedback and exact-deadline
  checks. Private state is account/context keyed and requests are aborted on
  context changes. Mobile management and navigation are unchanged.
- Workspace, membership grants, events and actor refresh after acceptance.
  Notices route using current permissions, not the historical creator field.

No automated inactivity succession, account deletion, credential sharing,
admin override, public member directory, external email or new cloud service.

## Database and preservation

Reviewed additive `mvp_0015` follows `mvp_0014` and was explicitly applied to both
isolated development databases. No startup migration was added. New transfer and
audit tables include a per-creator request-key constraint and one-pending-offer
index. A partial unique membership index enforces at most one active owner.
Creation/acceptance paths retain exactly one. Migration refuses legacy duplicate
owners without rewriting them; downgrade refuses to erase transfer history.

Aggregate hashes/counts matched every row of all **32 pre-existing tables**:

| Database | Preserved rows |
|---|---:|
| Fictional development `intraspot_mvp` | 76 |
| Real development `intraspot_real_dev` | 2 |

No development ownership transfer or role change was seeded. Test mutations and
rollback checks were confined to the named scratch databases. Penpot's database
and Supabase application SQL/storage were untouched. Alembic drift check passed.

Reads project expiry without writing. A successful replacement mutation seals
the expired offer once. An expired decision rejects with 409; its attempted seal
rolls back with that failed transaction. There is no claim of an expiry scheduler
or a durable expiry audit from a rejected request.

## Developer verification

Three GPT-6 Luna/max workers handled non-overlapping backend, frontend and
independent QA work. The coordinator owned shared integration, migration,
generated API contract/types and all serial PostgreSQL runs.

| Gate | Actual result |
|---|---|
| Ownership API/schema/races + independent QA + stale cached-role authorization + migration invariants | **36 passed** |
| Existing organizations, memberships, draft preconditions and review summaries | **47 passed** |
| Existing registration, capacity/retry/promotion, chat and persona behavior | **76 passed** |
| Sprint 18/19 migration/history chain | **5 passed** |
| Unique default PostgreSQL cases across those serial runs | **164 passed**; focused regression, not a full repository rerun |
| Separate synthetic Supabase/auth protocol suite | **50 passed**; not live PLM sign-in |
| Complete final frontend Node suite | **123 passed** |
| Final whole-frontend ESLint | Passed, no errors or warnings |
| TypeScript | Passed standalone and during both profile builds |
| Default frontend build/export | Passed, including final public/static asset guard; existing security upgrade reminder remains |
| Real-auth frontend build/export | Compiles/type-checks/generates 14 routes, then stops with the existing Next.js 16.4.0 security advisory; final build gate remains open |
| API smoke check | `/ready` returns `mvp_0015`; live OpenAPI includes ownership routes |
| Python syntax, migration drift, staged/unstaged whitespace checks | Passed |

The initial default build hit EPERM creating a generated notifications directory.
An approved-permission rerun succeeded without changing configuration or clearing
data. No security check was disabled and no dependency was upgraded.

Review fixed uncertain-create retries that became blocked after polling found
the committed offer, hidden nominee network-error feedback, a refresh dropped
behind an existing GET, and role refresh when a retry recovered an already
accepted offer. Confirmation now describes decline separately from acceptance.
Source/helper checks cover these seams; they are not browser interaction proof.

Early QA harness mismatches were corrected: create returns 201, expiry assertions
distinguish total audits from one expiry audit, and PostgreSQL lock observations
refresh their statistics snapshot and identify the actual blocker. The final
after-lock expiry test observes the wait before advancing expiry, then verifies
no transfer. Same-key creates, distinct offers and accept-versus-revoke races
also pass against PostgreSQL.

Ignored evidence: Backend `.cache/s20-final.xml`, `s20-regress.xml`,
`s20-participation.xml`, `s20-history.xml`, `s20-auth.xml` and the two preservation
baselines. See [independent source review](sprint20-quality-review.md),
[contract](../backend/Sprint-20.md) and
[interaction handoff](../design/sprint20-interaction-handoff.md).

## Remaining acceptance gates

1. **Live browser:** no Sprint 20 browser interaction or screenshot evidence.
   The earlier internal-error tab was policy denied; no alternate-browser or
   hidden-control workaround was used. The actual local application must be
   opened before the live ownership journey can be reviewed. Check owner/admin
   confirmation, keyboard/Escape/focus return, deadline/conflict feedback,
   uncertain retry, role refresh, mobile absence and account-switch cleanup.
   Sprint 18's live persona/blocking journeys remain pending too.
2. **Dependency security:** installed Next.js 16.4.0 remains unchanged. The real
   build stops on its advisory even after static generation; the default build's
   reminder and successful exit do not establish dependency safety. The minimal
   security patch previously requested has not been authorized/applied. No
   suppression or automatic upgrade was performed.
3. Participant/native-device/full language/dark/contrast/larger-text testing,
   live PLM-account sign-in and operational security/release review remain
   separate. Automated/source checks do not satisfy those gates.

Changes remain local. No commit, push, deployment, Penpot synchronization,
cloud application data migration or Sprint 21 implementation was performed.
