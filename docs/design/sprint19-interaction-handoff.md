# Sprint 19 — Featured-event interactions

## Preserve the existing interface

Featured is an editorial label, not a recommendation reason, registration status,
paid promotion, reserved feed position or a separate spotlight. Do not move an
event above its normal Upcoming/Newest/For You position. Keep PLM styling and the
four mobile attendee destinations unchanged. Organization/platform management
remains desktop-only.

## Organization workspace

Approved-organization owners/admins can request a placement for a published event
that has not started. The event's existing management card shows request history,
pending/paused/scheduled/active/expired/rejected/revoked outcomes and a request
action only when there is no open request. A repeated submission returns the same
open request. Loading, retry, access loss and changed-data feedback must be clear.
No additional accreditation, attachment, appeal or free-text application is added.

## Platform review

Review current public event details and its audit history. Approval records an
immediate or future start and an end, displayed/entered in Asia/Manila but stored
as aware UTC. The placement must finish by event start. A conflict does not replace
another placement: refresh and choose a non-overlapping window. Rejection closes
pending/paused review; revocation removes an approved placement. Actor/time come
from the server, never an editable admin selector. Decisions use the version
reviewed by the administrator; stale actions cannot silently overwrite a newer
decision. Confirm before recording an action.

## Material change and time boundaries

Time, venue, banner/graphic, capacity and cost changes require fresh review. Pause
the request/placement atomically with a supported material edit, and never show a
badge when its approved fingerprint no longer matches. Preserve audit history.
Published banner replacement is still unavailable; do not imply this sprint adds
that workflow. Unrelated text changes do not pause placement.

Featured is effective only during `[start, end)` and strictly before event start.
Pending/paused requests expire at event start. Reads derive expiry without
depending on a running scheduler; restarting the service cannot revive a badge.
The public projection contains only the authoritative boolean badge, not request
or administrator identities. Screens reflect the latest successful API read;
revisit/refresh after a placement decision to obtain its current status.

## Accessibility and verification boundary

Use a labeled, noninteractive gold badge with the existing outline icon family.
Do not communicate any status by color alone. Preserve focus rings, readable
wrapping, centered action text, selected-language labels, theme/contrast settings
and reduced-motion behavior. No continuous animation is introduced.

See the Sprint 19 acceptance record for actual automated and browser evidence.
Developer/heuristic checks are not participant validation, physical-device
testing, Penpot synchronization or approval for public deployment.
