# Sprint 18 — persona controls and blocking

Date: 2026-10-23. Status: **implemented locally; final browser and dependency-build
acceptance gates remain open**. No deployment or release approval.

## Implemented

- Optional clearable pronouns/icebreaker and explicit broad text visibility in
  the existing Profile form. Required profile fields and private defaults remain.
- Separate confirmed-attendee event-only text sharing, expiring at event end;
  reviewer consent is not silently converted to attendee consent.
- Event-context text-persona lookup, eligibility/scope checks and uniform hidden,
  blocked, inactive or unknown-persona responses. No directory, email or images.
- Mutual persona/label hiding for either block direction, including authorized
  event-registration and organization-membership review projections. Only the
  caller's outgoing block references are listed; unblocking is idempotent.
- Anonymous warning for the caller's outgoing blocked people currently confirmed
  at an event, with explicit proceed/cancel. The server checks before durable
  admission and acknowledgement is part of the stored idempotency payload.
- Shared event-chat messages, existing registrations, memberships, moderation
  evidence and notifications remain intact. No direct messages introduced.
- Current author-label maps refresh already-loaded content without discarding
  older messages/pages. Local block actions invalidate names immediately; visible
  chat refreshes every 5 seconds and comments/open persona panels every 30 seconds
  or focus. No claim of instant remote invalidation or erasing already-read data.
- Generated OpenAPI/types, English/Filipino strings, existing responsive styles,
  four mobile attendee destinations and accessible in-page block confirmation.

## Preservation and runtime

Applied reviewed additive `mvp_0014` after `mvp_0013` explicitly to both local
development databases. No migration at startup. Before/after aggregate hashes
match **all 30 pre-existing tables**: **76 fictional-development rows and 2
real-development rows**, including Featured request/audit history. The new receipt
acknowledgement column defaults false; comparisons exclude only that new column.
No development profile, registration, event, block or sharing choice was seeded
for Sprint 18. Existing fictional account tokens were refreshed in ignored files.
Supabase remains Auth-only; no cloud SQL/storage or Penpot changes.

Docker's stale runtime-socket issue was recovered with socket-folder backups,
not deletion/reset; see `docker-repair-2026-10-23.md`. PostgreSQL is healthy on
127.0.0.1:5433 with its preserved volume. Local fictional API `/ready` returned
`mvp_0014`; the existing static frontend `/profile` returned HTTP 200. This HTTP
check is not a live interaction test.

## Automated evidence

PostgreSQL suites ran serially on the named isolated scratch databases.

| Gate | Actual result |
|---|---|
| Initial migration/Sprint 19 preservation regressions | 5 passed |
| Broad default regression | 573 passed, 2 failed, 10 historical opt-in gates skipped |
| Corrected final privacy/warning/independent QA/migration/schema slice | 32 passed |
| Final chat/social/membership/identity regression on integrated code | 144 passed |
| Optional text save/clear, required-only preservation and no privilege escalation | 1 passed |
| Unique passing default cases across broad and corrected runs | 582; not one entirely green broad rerun |
| Separate synthetic Supabase/auth protocol regression | 50 passed; not live PLM sign-in |
| Complete final frontend test suite | 111 passed |
| Changed-file ESLint | Passed after keyed account/context reset correction |
| TypeScript | Passed; both frontend profiles compile and generate 14 static routes |
| Final build/export gate | Open: existing Next.js 16.4.0 security advisory stops completion |
| Alembic drift check | Passed: no new upgrade operations detected |
| Git whitespace check | Passed |

The broad failures were an OpenAPI snapshot produced while the new label schema
was still being integrated, and a reviewer fixture confusing an owner ID with a
User object. Both pass in the corrected run. Earlier focused fixture issues
(missing approval review window, unauthorized reviewer, and a page-level map
asserted on an item) were corrected without weakening authorization or privacy.
The final label-metadata test also proves hidden/removed-only comment authors and
non-confirmed chat authors cannot leak nicknames through metadata.

Evidence files are ignored Backend `.cache/s18-regression.xml`,
`.cache/s18-final-corrected.xml`, `.cache/s18-communication-final.xml`,
`.cache/s18-profile-final.xml`, `.cache/s18-auth.xml` and preservation baselines.
See `sprint18-quality-review.md`.

## Open gates — do not call this release-ready

1. **Live browser:** the old in-app tab was an internal error page. Browser
   policy denied authority to observe it. No workaround, alternate browser or
   hidden browser/API interaction was used. The user was asked to open the actual
   local app. No Sprint 18 browser screenshots or live desktop/mobile journeys
   have been verified. Required: optional-field save/clear, block/unblock,
   unchanged shared chat, current-label refresh across accounts, event-only
   sharing, registration warning/proceed/cancel and account-switch cleanup.
2. **Dependency security/build:** the existing installed Next.js 16.4.0 is flagged
   by its build tool. Compilation/type checks/static generation succeed, but
   final commands stop on the advisory. One earlier default build passed before
   the final copy clarification; it is not the final gate. The user was asked to
   approve the minimal 16.4.1 patch with matching lint package. No dependency
   changes or security-check suppression were performed. Official advisory:
   https://nextjs.org/blog/nextjs-security-update-october-14-2026
3. Participant/native-device/full language/dark/contrast/large-text testing, live
   PLM-account sign-in and operational security/release checks remain separate.

No commit, push, new cloud service, deployment, personal images, DM capability,
organization mobile management or Sprint 20 work is included.
