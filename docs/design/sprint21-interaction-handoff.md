# Sprint 21 — desktop manual attendance

Reuse the existing event cards and Quiet Heritage controls in owner/admin and
moderator workspaces. No new navigation or mobile-management surface. Expand
Attendance to load current staff-only state, confirmed roster and recent audit.
Show closed/open with text as well as color, confirmed and checked-in counts,
and a local search of opaque participant labels. No email or persona disclosure.

Check-in is closed by default. A session confirmation explains the chosen
open/close action, starts on Cancel, supports Escape and restores focus. Marking
and Clear check-in are staff records only: they must not register/withdraw a
person, reserve/release seats or change chat. An unchecked row is not a no-show
decision. Check-in may stay open after the event until staff close it.

Capture the exact event, registration, version, value and request key for each
command. An uncertain retry preserves those values in memory; no browser storage.
Refresh after success or conflict. A conflict requires fresh review, not silent
version replacement. Token/event changes discard private snapshots and abort old
requests. Closed/unavailable state disables new marks. Keep failures visible and
recoverable; never show a false saved state or silently drop a refresh.

Recent history is read-only and records actor/time, previous/new value. Keep
historical marks when participation later cancels; the current roster/count is
confirmed-only. Staff use their own current server-authorized account; former
roles or platform-admin status alone do not grant attendance access.

English and Filipino reuse existing localization. Do not claim live keyboard,
responsive or participant proof from source/helper tests. Earlier browser-policy
and Next.js security gates remain separate. Event-level cancellation/removal is
not yet represented in the backend; its attendance-write integration is an
explicit Sprint 22 dependency, not certified here.
