# Sprint 10 — desktop management, draft autosave and organized inbox

Authorized by the user's request to proceed to the next sprint, 2026-10-16.
The canonical Implementation Roadmap places this after the completed Sprint 9.

## Scope and frozen contracts

- Extend the approved Quiet Heritage desktop language to organization selection,
  role-specific workspaces, event management, membership operations, accreditation
  applications and safety review. Use existing authorized data and actions.
- Use clear workspace context, scoped navigation, manageable sections, readable
  status/counts, loading/empty/error feedback and accessible decision confirmation.
  Management remains desktop-only; mobile attendee behavior is preserved.
- Existing event drafts autosave after a short editing pause. Creation remains an
  explicit action. Show unsaved/saving/saved/error/conflict states, retain failed
  edits and offer manual Save draft/retry. Do not automatically publish.
- Serialize editor saves, preserve edits made while saving, and warn before leaving
  unsaved work. Failed saves must not cause unlimited background retries.
- Private event projections add `draft_version`, a deterministic content version
  derived from draft fields and status (no database migration). Autosave PATCH and
  publish POST send a quoted `If-Match` header. Compare under the existing event
  row lock; mismatch returns 409 `draft_conflict` without writing/publishing.
  Existing API callers omitting the header retain their existing behavior.
- The shared `api` helper accepts optional `ifMatch`; it quotes the version once.
  CORS permits this header. Public projections never expose private draft fields.
- Organize the current user's notification inbox with All/Unread and category
  filters/counts, contextual destinations and per-notice read feedback. Filtering
  applies to the latest 100 notifications supplied by the existing endpoint; state
  that boundary. Do not invent push/email, bulk read, deletion or new permissions.
- Staff use organization-scoped published-event review summaries (pending count
  and earliest deadline), independent of the public feed's limit. Reuse existing
  approved-organization staff authorization; return no attendee identities.
  Notifications include their event's organization context, including legacy
  records enriched on read, so review links can select the correct workspace.
- Preference settings, theme, larger text, high contrast and reduced motion apply.
  Translate new interface copy in English/Filipino; never translate authored text.

## Ownership

The coordinator owns shared infrastructure, backend preconditions, API helper and
generated types, common layout, the contract, integration tests and acceptance.
Luna/max workers have disjoint files for organization UI, platform/safety UI,
draft editor, and notifications. A separate Luna/max assessor reviews the outcome
and authors scoped regression checks; database suites run serially.

## Acceptance

1. Pending owner saves/previews a private draft; publishing stays disabled.
2. Approved owner/admin edits, autosaves, reloads persisted content and publishes
   only saved content. Rejected organizations remain read-only.
3. Edits during a save remain dirty until their own save completes. Failed saves
   retain input. A stale tab cannot overwrite or publish a changed draft.
4. Owner/admin/moderator/member and platform-admin screens expose only established
   role actions; no roster/private queue leaks through attendee navigation.
5. Accreditation confirmation records the actual server-side deciding admin and
   time. Safety decisions retain existing evidence and deadline behavior.
6. Inbox filters compose; unread state refreshes after read; destinations have
   appropriate event/club/chat/workspace context and no null identifiers.
7. Review at 1280×720, 1366×768, 1440×900 and 1920×1080, plus larger-text,
   Filipino, dark/high-contrast/reduced-motion and mobile management restriction.
8. Backend tests, generated contract, frontend type/lint/build and automated
   browser journeys pass. Record actual evidence and limitations separately.

Participant testing, Sprint 11, Penpot synchronization, real sign-in and public
deployment are outside this sprint's implementation scope.

## Result

Complete locally, 2026-10-16. The broad backend run passed 342 checks; later
context/read-boundary changes passed 25 focused checks. Frontend contracts passed
16 checks; lint, TypeScript, optimized exports, credential guards and schema drift
checks passed. Actual Sprint 10 browser verification passed 18 groups, and the
communication/safety regression passed nine. See the
[acceptance record](../validation/sprint-10-acceptance-2026-10-16.md) for exact
coverage, environment repairs, evidence and compatibility limits.
