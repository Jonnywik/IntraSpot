# Sprint 14 — organization announcement interactions

Local fictional implementation, 2026-10-19. This extends the accepted Quiet
Heritage application, not the Penpot file. No new persistent navigation, comments,
forum, media uploads, real identities or broadcast notifications are introduced.

## Reading and reacting

- Open the existing Clubs organization profile (Settings → Clubs and membership
  on mobile). Announcements remain inside that organization, beneath its profile.
- Each post identifies Public or Members only, its Manila timestamp and, after
  a substantive edit, an Edited marker. Authored titles and body text remain in
  their original language; interface labels follow English/Filipino preferences.
- Guests see only public posts from approved organizations. Current eligible
  active members, including organization staff, can also read member-only posts.
  A platform role alone is not membership. These rules are enforced by the API,
  including direct identifiers, reactions, pagination and revision history.
- Six familiar reactions show aggregate counts only: Interested, Excited,
  Support, Kudos, Wow and Relate. Eligible authorized readers can select, replace
  or remove their one reaction. This never registers attendance or reserves a seat.
- Loading and failure states are explicit. A failed reaction retains the desired
  choice for retry. Older pages load explicitly and requests are scoped to the
  organization/account; changing accounts cannot reveal a previous member's data.
- The mobile shell retains Discover, My Events, Chat and Settings. Management
  controls are desktop-only. Larger text, contrast and reduced-motion settings
  continue to apply without translating authored content.

## Organization authoring

- The existing desktop organization workspace offers announcement management to
  an eligible active owner/admin of an approved organization. Members and
  moderators do not get authoring controls; pending organizations cannot publish.
- Publishing requires a title, body and explicit audience selection. There is no
  separate announcement draft workflow. A request key prevents duplicate posts
  on retries; uncertain outcomes keep the submitted content/key together.
- Edit/remove actions carry the version displayed to the manager. On a conflict,
  preserve their text and require review/reload of the latest manager record,
  rather than silently overwriting another person's change. No-op edits do not
  create a false Edited marker.
- Removal is confirmed and leaves a read-only tombstone/history, not a public
  body. Hidden posts cannot be edited back into visibility by their owner.
  Owners may remove a hidden post but cannot restore platform hiding.
- History is a separately authorized manager view with versions, action, actual
  actor ID and server time. Ordinary public detail never exposes hidden/removed
  records, even to a manager. Revision retention here is a local review mechanism,
  not an approved indefinite production-retention policy.

## Reporting and platform review

- Eligible signed-in readers can report another author's accessible post through
  a small Report announcement disclosure. A reason is required. Submission alone
  never hides the post, restricts its author or removes seats.
- A report receipt shows its identifier, status and deadline; it is not evidence
  access. Receipts remain available to their reporter after membership ends.
- The desktop platform page has a separate Announcement safety report queue.
  It does not alter the existing event/person report workflow or expose reports
  to organization staff. Reviewers see only the permitted evidence snapshot,
  versions, current state and decision/expiry audit history.
- Open evidence is the exact reported title/body/version, unaffected by later
  author edits or removal. It is available only before the 14-day deadline and
  purged on decision/expiry. Neither API nor UI reconstructs it from revisions.
- Available decisions are dismiss, hide, restore and permanent remove as allowed
  by current case/post state. Content actions use current versions. Only the case
  that actually hid a still-hidden post can restore it; removed posts cannot be
  restored. Stale review actions prompt refresh. Retries do not duplicate audits
  or generic in-app notices.
- Expiry is durable and processed by the existing explicit deadline worker;
  reads withhold evidence at the deadline even if that worker was stopped.

## Local review entry points

Use the labeled fictional-account selector, never real email entry. The additive
`app.local_announcements` helper creates two sample posts in the existing
Fictional Phase 2 Approved Organization without overwriting edits or history.
Fictional student 4 owns it; existing memberships/roles are preserved, not reset.
Actual test results and screenshots belong in the Sprint 14 acceptance record.
Participant, native-device, assistive-technology and release/security review
remain separate gates. Long-term deleted-content/revision retention remains open.
