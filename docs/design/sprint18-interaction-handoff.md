# Sprint 18 — persona and blocking interactions

Preserve the approved Quiet Heritage layout, four attendee navigation destinations
and desktop-only organization management. Text-only feature; no personal images,
new directory, direct messages or Penpot changes.

## Profile

Required nickname, age bracket and tags retain the existing completion rules.
Pronouns and icebreaker are optional, bounded and clearable. Broad text visibility
is explicit and off for a new profile; explain that it may disclose the age
bracket and interests as well as nickname. Saving required fields must not erase
optional text or an existing visibility preference. Reviewer-specific consent
does not automatically enable attendee sharing.

Outgoing blocks are manageable here, using opaque member references rather than
leaking names from a hidden persona. Unblocking changes only the caller's block;
it cannot override the other person's independent block or privacy choice.

## Event context

Eligible signed-in readers can explicitly request a comment/chat author's text
persona. Hidden, inactive, blocked or inaccessible personas all use the same
unavailable message. No profile preview on hover or automatic private prefetch.
Do not present the absence of a persona as proof of a block.

Confirmed attendees can separately enable event-only sharing, ending at the
event's end. This grants no membership, registration or reviewer privilege.
Existing reviewer consent and approval-state boundaries remain authoritative.

## Blocking

Use an accessible in-page confirmation with a non-destructive cancel choice,
visible keyboard focus, Escape dismissal, and focus return. Explain that blocking
hides both personas but does not remove comments/shared event-chat messages,
registrations or memberships. No direct messages are introduced. Preserve report
and Hide for me as distinct actions.

Clear cached private details after block/unblock or account/context changes.
Abort old requests and ignore late responses; provide loading, success and
retryable-error feedback without implying a failed request succeeded.

## Registration

Show an anonymous warning if someone the caller blocked is currently confirmed.
No nickname, count or inbound-block disclosure. Require an explicit proceed
choice; cancel has no registration effect. The server rechecks at intake, so a
late warning returns to confirmation instead of silently proceeding. Keep the
same key and payload on an uncertain retry. A deliberate changed acknowledgement
uses a new key only after a definitive non-admitted warning. Capacity and ordinary
waitlist/approval rules still apply after proceeding.

## Verification boundary

Component/source checks and API tests do not establish live interaction behavior.
Record actual browser tests and any untested language, contrast, large-text,
physical-device or participant cases in the acceptance record. Reduced motion
and keyboard feedback reuse the existing design system, not new ambient effects.
