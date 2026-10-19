# Sprint 10 — desktop management interaction handoff

This extends the Sprint 9 Quiet Heritage tokens and preferences to the existing
organization and platform workflows. The desktop workspace uses up to 1440 px,
with 24 px page gutters, a 240 px contextual sidebar and flexible content.
Management remains unavailable below the existing desktop breakpoint; attendee
mobile navigation is unchanged.

## Draft editor

Draft creation is explicit. Existing drafts autosave about 900 ms after editing
pauses; the public-facing preview follows the local fields immediately. Incomplete
drafts remain supported. Saving, failed-save and conflict messages distinguish
what is local from what has been acknowledged by the server.

Saves are serialized. The acknowledged revision becomes clean only when that
particular input snapshot has been saved. Typing during a request remains editable
and is saved subsequently. Save errors retain the local fields and stop automatic
retry of that unchanged input. **Save draft** retries deliberately.

Each request uses the private content version in a quoted `If-Match` header.
The server compares it under the event lock. A stale save or publish receives
`409 draft_conflict`; it cannot change or publish newer stored content. Reloading
the saved draft requires confirmation because it replaces the local editor.
Existing API clients may omit the optional precondition; future editing clients
should adopt it to get the same conflict protection.

Publishing is explicit, requires a saved valid draft and approved organization,
and uses the same version guard. Pending organizations keep a visible disabled
Publish action and explanation. Rejected workspaces and published drafts are
read-only here; published material changes use their established separate flow.

Unsaved work installs a browser unload warning and a confirmation for internal
links and explicit fictional-account changes. Browser navigation support and
actual checks are recorded in the acceptance report.
Same-document back/forward confirmation uses Navigation API events only when
they are cancelable. Browsers can make some traversals noncancelable; this is a
compatibility limit, not a guarantee that all browser navigation can be blocked.
See the [HTML navigation standard](https://html.spec.whatwg.org/dev/nav-history-apis.html).

## Organization and platform work

Workspace selection establishes the organization and effective role. Event
filters and contained review/change sections keep long operational forms out of
the primary scan path. Approved staff event summaries include pending-review
counts and earliest deadlines without exposing registrant identities. Opening a
review still uses the established authorized detailed endpoint.

Platform application filters compose with search. The accreditation confirmation
states the selected organization and terminal outcome before sending a decision.
The stored deciding admin and timestamp come from the backend. Safety review
preserves existing evidence, permissions, review stages and permitted actions.

## Inbox

All/Unread composes with Registrations, Clubs, Chat and Safety. Counts and empty
states describe the currently fetched latest 100 notifications. Unknown authored
messages are displayed as received; exact known system copy is localized.
Mark as read changes only that notification after the server acknowledges it.

Destinations use the notice's event/organization context and the current actor's
roles. Staff review notices can select the relevant organization and event.
Membership notices open the club portal, chat opens its thread, and platform
safety notices open the platform workspace. Missing context never creates a link
containing a null event identifier.

## Feedback and accessibility

Reuse shared navy actions, burgundy identity, gold focus, warm surfaces, consistent
outline icons, soft borders, hover/pressed feedback and reduced-motion behavior.
Keep normal document scrolling and wrapping for long titles and Filipino text.
Account language/theme/text/contrast/motion preferences remain independent.

Developer browser checks and screenshots are evidence of implementation behavior,
not participant validation. See the sprint acceptance record for results and
known limitations; no public release is implied.
