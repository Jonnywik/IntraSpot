# IntraSpot — Development Handoff

> **Current gate:** Build and validate the organizer-first clickable mock with simulated data. Do not build backend behavior until the guided event-authoring experience has been reviewed. This summary links to the detailed source notes; those remain authoritative.

## Product and first-release baseline

- **Audience and value:** Students and academic/professional organizations in Intramuros discover and organize in-person events.
- **Discovery:** An event-feed-first web app. Guests may browse public listings/details and public organization announcements. Google sign-in is required to personalize discovery, register, comment, or use event chat. A curated venue directory, map, and venue schedules are deferred.
- **Feed experience:** One constrained column across devices; default For You ranking is personalized relevance, with Upcoming and Newest sorting options. Nearby flash hangouts receive temporary priority and can be hidden/muted. Reasons include interest, coarse area, and free-time matches; area and manual availability windows are optional user-controlled inputs, with no live GPS or calendar integration. Cards show organization/event identity, summary/graphic, confirmed count, remaining spots, date, reactions/comment preview, and register/waitlist action.
- **Registration confirmation and My Events:** Register opens a compact confirmation sheet with date, venue, cost, and attendance mode. My Events separates Pending, Confirmed, Waitlist, and Past registrations.
- **Responsive experience:** Separate mobile and desktop layout shells with the same core capabilities and information hierarchy. Mobile navigation: Discover, My Events, Chat, Settings; Profile and Notifications remain outside it. Desktop uses compact top navigation and a utility area. The event feed is one constrained column.
- **Attendee profile:** At first registration, require nickname, age bracket, and at least one interest/vibe tag. Other persona fields and images are optional and hidden by default. Event and organization application visibility is separately opted into; event reviewers see opted-in persona before approval, and confirmed event attendees may see profile images. Membership reviewers never see profile images or Google email. Only organization owners/admins—not moderators—may view event registrants’ Google email, and every view is audited. Post-decision lifetime/scope of organization-scoped persona opt-in remains open.
- **Organizations:** A separate organization profile/account is created by a user. The LinkedIn field is checked for URL form only; ownership/authenticity is not verified in the pilot. Public membership requests are reviewed; an owner/admin invitation grants standard-member access when accepted. Each person has one effective role per organization: owner, admin, moderator, or member.
- **Organization roles and workspace:** Separate dashboards per role. The owner retains security-sensitive controls; admins handle general management and may publish announcements; moderators can make final membership/approval-registration decisions and review organization event reports; members receive organization event notices and read announcements. Only the owner/admin may materially edit or cancel a published event. The member roster is staff-only. When membership ends, cancel that person’s registrations/waitlist entries for that organization’s events and revoke access to those event chats.
- **Organization succession:** Two months without a qualifying organization action triggers an in-app notice; the owner has three days to respond or designate a successor. If the owner responds after that deadline but before transfer acceptance, normal owner control resumes. If succession proceeds, the designee must accept; then eligible admins/moderators are offered the role sequentially, ranked by organization activity and then site-wide activity, with one day each. Existing admins can still manage events but cannot add admins while this is pending. If all candidates decline/time out, the organization enters a two-week closure/claim period; first valid admin claim wins, otherwise the organization is deleted. Notices are in-app.
- **Organization Community:** Read-only announcements. Owner/admin publishers choose member-only or public visibility per post. Member-to-member discussion is deferred. Reports go directly to IntraSpot moderators; the post remains visible while reviewed.
- **Event authoring:** A short guided flow with draft saving. Publishing requires title, date/time, venue, description, capacity, registration mode, and event graphic/banner. Organizers enter venue name and full address, with an optional external map link. The graphic has a consistent preview crop/position, standard templates, and custom-upload support; structured event fields remain authoritative over banner text. Cost is informational; payments happen outside IntraSpot. Flash hangouts use instant acceptance. An organization may request a featured placement; IntraSpot staff approve it manually, with at most one featured event on the feed’s first screen until that event starts. Featured remains a normal feed item with a label, not a recommendation reason.
- **Registration:** Instant acceptance or organizer approval; hard capacity limit and server-received first-come order. Approval requests temporarily reserve a spot and use existing opted-in persona only—no free-text application note. Review windows are 15 minutes–48 hours and must end before event start; the settled warning, one equal-length extension, second-reviewer escalation, and release rules are in [[IntraSpot/Functionality]]. Full events use a waitlist; instant mode queues automatically and approval-mode requests are reviewed when a spot opens. Registration writes require a transaction and idempotency key.
- **Changes and social features:** Material changes to date/time, venue, capacity, or cost require confirmed attendees to reconfirm; their seats remain reserved until an organizer-set pre-event deadline. Cancellation closes registrations/waitlists and notifies affected people. For a capacity reduction, the organizer selects attendees and IntraSpot applies the reverse-confirmation rule (exact selection semantics remain a review gap). Any signed-in user may read/comment until the event starts; launch reactions express interest, not attendance. Confirmed attendees get event-specific group chat, which closes 72 hours after scheduled event end. Blocking mutually hides profiles and warns before registering where the blocked person is confirmed, but shared-chat messages remain visible. One-to-one DMs are deferred.
- **Safety and communication:** No pre-publication organization verification or event review gate. Organization moderators decide event safety/deception reports first; after they act, three distinct reporters within a rolling seven-day window trigger IntraSpot escalation. Reported events stay visible during review. Platform event actions may uphold the organization’s action, hide/remove the event, or temporarily suspend the organization; the action for an announcement itself remains open. Announcement reports go directly to IntraSpot moderators and do not auto-hide the post. Personal-user reports also go directly to IntraSpot moderators; while pending, the person cannot create events or send messages, but existing registrations remain valid. Durable in-app notifications only—no operational email or browser push in the $0 pilot.
- **Pilot scale:** Fewer than 10 organizations, fewer than 100 users, and under 10 simultaneous registration attempts.

## First prototype: simulated organizer journey

**Goal:** Test whether an organization creator can understand and complete event authoring before backend behavior exists.

1. Simulated organization creation.
2. Owner dashboard and a clear “Create event” entry point.
3. Short event wizard; a scheduled-event/flash-hangout choice adapts the shared flow (provisional layout recommendation).
4. Save draft, review a public-facing preview, and simulate publishing.
5. Check the same task on mobile and desktop shells.

Use simulated organization/event data only. Exclude real authentication, database persistence, registration, chat, and production permissions. A useful validation gate is that a target organizer can complete the flow and explain the published preview without needing the form’s author to interpret it; finalize the exact test participants and pass/fail measure before the test.

## Pilot architecture and operational posture

- Static Next.js/TypeScript frontend on Cloudflare Pages; browser requests go directly to one FastAPI modular monolith on Koyeb Free.
- Supabase Auth (Google OAuth only; no pilot password, email-confirmation, or reset flows), PostgreSQL, and Storage. FastAPI alone validates identity, enforces domain authorization, accesses PostgreSQL, and executes business rules. Browser origins use an explicit allowlist (production, local development, and deliberately added previews); no wildcard CORS.
- SQLAlchemy for normal database access; explicit transactions and client idempotency keys for capacity-sensitive registration. Versioned Alembic migrations are reviewed/applied as a deployment step, not at service startup. Supabase Storage holds media; private profile images are issued through short-lived URLs only after FastAPI authorizes access.
- Event chat and notifications use ordinary API endpoints and periodic client fetching; no WebSockets, browser push, or external operational email.
- Timed work runs in the existing FastAPI service and catches up after wake. Due business-state transitions run before the first relevant request is processed. Late notification delivery and physical cleanup during idle periods are accepted. Catch-up must be durable and safe to repeat after restart or overlapping requests.
- At scheduled end, events become historical and leave active discovery/registration. Event-chat access ends 72 hours later; messages are physically deleted except those retained for an unresolved report (organization review: one week; IntraSpot review: up to two additional weeks). Idle-period cleanup may lag under the accepted catch-up model.
- GitHub checks and reviewed merges to `main`; deploy after the explicit migration step. Sentry Free monitors frontend/backend errors alongside provider logs. Application logs are minimized to request/action metadata and internal IDs—never tokens, raw emails, profile data, chat text, or full payloads. Weekly encrypted PostgreSQL export outside Supabase and weekly Storage archive; restore testing is intentionally deferred until an actual data-loss incident.

## Known gaps to review later

These are known follow-ups, not new first-release commitments. Resolve each before implementing its affected feature or before expanding the pilot.

### Before implementing the affected feature

- **Organization invitations:** Define invite delivery, link expiry/revocation/reuse, and what happens if a link is forwarded. The direct-grant-on-accept policy is settled; token mechanics are not.
- **Organization exit and access:** The effect on registrations/chat is settled, but the self-service leave flow, who may remove a member, and the notice shown to the affected person are not fully specified.
- **Applicant and staff data:** Define when organization-scoped persona opt-in ends after approval/rejection and exactly which fields staff can see in the staff-only roster. Images and Google email are excluded from membership review under the current rule.
- **Public comment visibility:** The UI shows comment previews, while signed-in users are explicitly allowed to read/comment; confirm whether guests may see previews or comments.
- **Announcement moderation outcome:** Direct reports to IntraSpot moderators and the no-auto-hide rule are settled. Define the platform moderator’s post-specific action (remove/hide the announcement versus organization-level action), plus announcement edit/delete/retention behavior and whether a signed-out guest may report a public post.
- **Comment/chat reports:** Functionality permits organization moderators to remove or report unsuitable comments, and reported chat messages have a retention window. Define the report destination and resolution path for event comments/chat content, including how that differs from a report against the person.
- **Organization application form:** Whether applicants can include a note and whether/when a rejected applicant may reapply are not specified.
- **Capacity reduction wording:** Confirm how “organizer selects attendees” combines with reverse-confirmation order (exact selected set versus a larger candidate pool).
- **Succession scoring:** Before implementing succession, make “organization actions” and “site-wide activity” measurable and resolve any tie cases not already covered.
- **Discovery implementation:** Exact reaction names/eligibility, feed-ranking weights, flash-hangout priority duration, coarse-area matching, and the shape of manually entered availability windows remain prototype/implementation refinements. No live GPS or external calendar is in the first release.
- **Media and accessibility:** Set upload size/type limits and image-validation behavior; define keyboard/screen-reader, contrast, and browser/device acceptance checks.

### Accepted pilot risks to revisit before wider use

- Free hosting may sleep or cold-start; notifications and physical cleanup can be late. The catch-up path must preserve deadline state and be repeat-safe.
- Organization authenticity is not verified; server-side rate limits and Turnstile are intentionally absent. Revisit abuse controls before growth or monetization.
- No external email is used until a verified sender domain exists. External calendar integration, live device location, browser push, and payment processing are not in the pilot.
- Database/storage backups are scheduled, but restoration is not tested before a real loss incident. Revisit this risk before a larger or higher-reliability launch.
- Before wider public/commercial use, review privacy/consent, account/data deletion, terms, incident response, and hosting-plan suitability.

### Deliberately deferred product scope

Curated venue discovery/maps/schedules; one-to-one direct messages; member-to-member organization discussion; payment processing; calendar integration; precise location matching; browser push; organization verification; social badges, venue perks, and the other concepts in [[IntraSpot/Future Ideas]].

## Draft development timeline

**Indicative eight-week sequence for one developer working consistently; not a commitment. Re-estimate after the mock, because available weekly hours and implementation experience are not yet specified. Keep the order and exit gates even if the calendar stretches.**

| Week | Focus | Exit gate |
|---|---|---|
| 1 | Build the simulated organizer mock: organization setup, guided event wizard, draft, preview, simulated publish; check mobile and desktop. | Review feedback identifies confusing/missing event fields; adjust the authoring flow before backend work. |
| 2 | Application foundation: repository workflow, static frontend, FastAPI service, Google OAuth verification, Supabase connection, initial migrations, CORS, and error logging. | A signed-in browser request is independently authenticated and authorized by FastAPI; migration/deploy path is repeatable. |
| 3 | Organization vertical slice: organization profile, roles/dashboards, public membership request, owner/admin invitation, staff-only roster, and basic announcements. | Role boundaries and public/member-only announcement access behave as specified. |
| 4 | Event-authoring vertical slice: drafts, required-field validation, scheduled/flash mode, media, publish, and public event detail/feed. | An organizer can publish a valid event and a guest can browse its public details. |
| 5 | Registration core: instant/approval modes, capacity-safe transactions, idempotent retries, waitlist and approval states. | Test simultaneous registration attempts and timeout/retry paths without exceeding capacity or duplicating requests. |
| 6 | Attendee and social features: My Events, reactions, comments, confirmed-attendee chat, blocking, organization notifications, and report workflows. | Verify role/access boundaries, report routing, and chat availability/closure behavior. |
| 7 | Lifecycle and resilience: in-process catch-up, event completion, review/reconfirmation deadlines, succession, and retention behavior. | Repeated or concurrent catch-up does not duplicate side effects; due business state is applied before relevant actions. |
| 8 | Pilot hardening: critical-flow tests (added after implementation, per current decision), Sentry/log review, backups, mobile/desktop smoke checks, migration review, and deployment. | Reviewed merge, explicit migration, deployment, and manual smoke test pass; document accepted free-tier and restore-testing risks. |

## Canonical detail notes

- [[IntraSpot/Functionality]] — domain rules and feature scope
- [[IntraSpot/UI & UX]] — responsive layouts and screens
- [[IntraSpot/System Architecture]] — application and deployment boundaries
- [[IntraSpot/Security & Operations]] — privacy, abuse controls, retention, backups
- [[IntraSpot/Future Ideas]] — untriaged ideas only
