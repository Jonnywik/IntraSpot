# Sprint 18 — text personas and blocking

## Frozen implementation contracts

This is a local application slice, not a redesign, release or personal-image
feature. Sprint 19 remains intact. Existing profile text fields and
`persona_visible` are reused; new personas remain hidden by default.

- `GET /api/v1/events/{event_id}/personas/{user_id}` returns only nickname,
  age bracket, tags, pronouns and icebreaker to an eligible signed-in viewer in
  an authorized event context. Hidden, blocked and unknown personas use the same
  unavailable response. No email, image, birth date, account-search directory or
  incoming-block information is exposed.
- Broad visibility permits text sharing in existing event-comment and authorized
  shared-event-chat contexts;
  event-only sharing additionally requires both people to be currently confirmed
  and the event not ended. Pending approval applicants are never exposed to
  attendees through broad visibility. Existing reviewer-only consent remains
  separate and is not silently converted into attendee consent.
- `GET/PUT /events/{event_id}/persona-visibility`: confirmed attendees can opt in
  or out of event-only text sharing. PUT `{visible: boolean}` is strict; GET
  returns `{visible, expires_at}`. Sharing expires at event end and grants no
  attendance, membership or reviewer privilege.
- `PUT /events/{event_id}/blocks/{user_id}` blocks a member encountered in visible
  event comments or an accessible shared chat (not arbitrary account discovery).
  `GET /me/blocks` returns the caller's outgoing `{user_id, created_at}` rows;
  `DELETE /me/blocks/{user_id}` is an idempotent unblock. No target nickname is
  exposed by the block list. Either block direction hides both text personas,
  including reviewer projections, but does not remove shared-chat messages,
  registrations, memberships, moderation evidence or notifications.
- `GET /events/{event_id}/registration-block-warning` returns
  `{warning: boolean}` only for eligible signed-in callers. It reports only the
  caller's outgoing blocks whose target is currently confirmed; no identities,
  counts or inbound blockers. Registration POST adds strict
  `blocked_attendee_acknowledged: boolean = false`. A current warning without
  acknowledgement returns `409 blocked_attendee_warning` before admission.
  Explicit acknowledgement permits normal registration, not a reserved seat.
  Receipt payload comparison includes the acknowledgement, and stored retries
  retain their original outcomes despite later changes to blocks/attendance.
- Comment pages and chat threads carry a current `author_labels` map for existing
  authors in that authorized content context. Incremental chat polls return it
  even with no new messages, so cached older nicknames can be anonymized after a
  block or visibility change without dropping messages or resetting scrolling.
  No email, new roster, block direction or other persona fields are added.

## Ownership and safeguards

Coordinator owns router assembly, model imports, additive `mvp_0014` migration
(after `mvp_0013`, because Sprint 19 ran first), generated API artifacts,
localization assembly, test orchestration and preservation proof. Domain workers
must not edit shared files. PostgreSQL tests run serially, on scratch databases
only. Existing development rows and Featured audit history must be preserved.

Acceptance covers private defaults, optional-field clearing, mutual hiding,
scope/expiry, hidden-reviewer personas, no block identity leaks, unchanged shared
chat access/content, warning/proceed/cancel, stable retries/FIFO/capacity and
account-switch cleanup. Browser evidence is developer verification, not
participant validation.
