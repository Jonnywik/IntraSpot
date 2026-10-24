# Sprint 21 backend attendance acceptance

- Attendance is protected by current active owner/admin/moderator membership in
  the event's approved organization. Roster and history reads are staff-only and
  do not create or update attendance rows.
- The roster contains only currently confirmed registrations in stable
  admission-order/registration-id order. Its manual-match label includes the
  full registration UUID and no attendee profile fields; it is an identifier,
  not proof of identity.
- Attendance open/close and mark/correction writes are versioned, idempotent,
  audited, and independent of registration/capacity/waitlist/chat/consent state.
  Writes remain allowed after event end until staff close check-in.
- The current event schema/API has no cancellation or removal lifecycle flags.
  Sprint 21 does not invent that workflow or claim those states are gated;
  writes fail closed for unpublished events, unapproved organizations, closed
  check-in, and registrations that are not currently confirmed. Full event
  cancellation/removal integration remains an explicit Sprint 22 dependency.
- Three PostgreSQL concurrency tests cover same-key replay, close-vs-mark stale
  version serialization, and role revocation/retry authority. They are authored
  for the main task's isolated database run and were not run by this worker.
