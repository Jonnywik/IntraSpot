# Sprint 17 — personal event planning

## Agreed presentation

Reuse the existing Quiet Heritage desktop/mobile app; no Penpot synchronization.
Preserve the four attendee destinations and desktop-only management boundary.

- Event details: explicit Save event/Saved control, separate from Interested and
  registration. A guest receives sign-in guidance, not a pretend saved outcome.
  Use visible busy/error/retry feedback; do not announce success before the API.
- My Events: Registrations/Saved sections within the page, List/Calendar view
  switch, list default. Retain Pending/Confirmed/Waitlist/Past and all existing
  result, deadline, withdrawal, reconfirmation, and authorized chat actions.
- Calendar: month navigation, labeled date buttons, selected-day details and a
  textual status legend. Show every intersecting Manila date for overnight events;
  an event ending at midnight does not occupy the following day. Light dotted
  waitlist markers remain distinct from solid confirmations. Do not rely only on
  color or hover. Larger text and Filipino labels must wrap within mobile width.
- Saved items: private to the account, with normal public event details only while
  currently available. A no-longer-public event has generic unavailable copy and
  can still be removed, including in calendar view. No cached private title or art.
- Conflict warnings: advisory text naming only the caller's overlapping confirmed
  events, shown in event details/registration confirmation and My Events. Strict
  half-open overlap means back-to-back events do not conflict. Never call pending
  or waitlisted places confirmed. Show checking/failure/retry states honestly;
  warnings do not change capacity, registration, reconfirmation, or retry keys.
- Account changes: discard/abort prior private requests and results; don't flash
  one account's saved list or conflict names to the next. Media privacy and
  temporary-object-URL cleanup from Sprint 16 remain unchanged.

No calendar export, external synchronization, new persistent navigation, reminder
notifications or automatic conflict resolution is part of this sprint. Actual
verification is recorded in the [Sprint 17 acceptance report](../validation/sprint-17-acceptance-2026-10-20.md),
not inferred from these intended interactions. It distinguishes live browser
observations from API/helper tests and the deferred accessibility/participant matrix.
