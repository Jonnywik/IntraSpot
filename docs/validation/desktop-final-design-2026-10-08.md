# Desktop final design pass — 8 October 2026

## Live artifact

Penpot file: `2714a049-ae7d-81a2-8008-b3966a11b138`.
Page: **Desktop • System & Journeys**, `2714a049-ae7d-81a2-8008-b3966a11b139`.
Begin with the **Desktop — Start here** prototype flow, board **03 • Desktop / Final prototype start**.

75 visible desktop boards. Mobile was not modified during this pass. Three obsolete accreditation-proof boards remain hidden for recovery; active journeys do not target them. Desktop flow metadata was backed up in the page's `desktop-final-flow-backup` plugin data before removing automatically named flows.

## Finished refinements

- Retained PLM-centered burgundy identity, navy actions, warm surfaces, image-led content, airy spacing, soft corners, and the approved serif/interface-font pairing.
- Standardized attendee navigation and click targets; retained Profile and Notifications as utilities. Guest utilities lead to simulated sign-in rather than member-only pages.
- Completed member, My Clubs, composed search, guest search, empty search, and event-comment sample states.
- Separated confirmed attendance, remaining spots, and interest counts. Registration results link directly to My Events. Waitlisting immediately shows position #4, no estimated wait time, and confirmed-only chat eligibility.
- Aligned all eight My Events list/calendar detail destinations with Pending, Confirmed, Waitlist, and Past status. Past details retain an ended-event marker with disabled registration. Waitlist markers use fine blue dots.
- Refined active and archived chat, profile privacy copy, and notifications. Archived chats remain in the same inbox with read-only/deletion cues.
- Kept organization publishing and admin assessment desktop-only. Accreditation assessment is offline; the interface records the decision rather than requesting proof uploads.
- Strengthened functional gold focus/selection indicators to #A97018; retained decorative gold #C9933A. Improved muted status text contrast. This is a sampled color check, not a complete accessibility certification.
- Added independent larger-text and Filipino settings previews; changing either from default no longer enables high contrast or reduced motion. The combined accessibility screen is explicitly labeled a combined preview.
- Added a four-journey start board and seven clearly named prototype flows.

## Verification evidence

Final structural audit: 75 visible boards, 3,643 shapes, 1,138 navigation interactions; no missing destinations, hidden destinations, conflicting button/label destinations, or text boxes outside board boundaries detected by the audit.

Fourteen core route checks passed. Student registration, faculty-inclusive eligibility, organizer draft/publish, admin approval/rejection, immediate waitlist copy, seat-count separation, and archived-inbox cues passed structural/content checks. Guest-to-member transitions are limited to the explicit eligible sample-account onboarding action.

Additional final-state checks cover all eight list/calendar links, separate language/text-size controls, unchanged default contrast/motion in those previews, and disabled registration for past events.

Visual PNG review covered the feed, event details, organizer, admin assessment, chat, profile, search, comments, waitlist/calendar, start board, past-event detail, and Filipino settings examples. Relevant exported previews are retained in the workspace.

## Handoff limits and gate

This is an editable, static, simulated Penpot prototype—not a deployed application. Search illustrates sample matching, not arbitrary typed queries; accounts, registrations, moderation, and publishing do not run against a backend. Secondary controls are not proof of implemented behavior.

The settings examples demonstrate selected states, not every combination or persistent preferences across every screen. The Filipino settings sample is not a complete translation of every desktop page. Remaining implementation must preserve independent preferences and complete localization. Sample event artwork is illustrative, not verified PLM photography.

Verification was a heuristic visual and structural review using the live Penpot artifact, not a browser-operated click-through or participant usability study. Participant testing and the canonical Development Handoff gate remain required before frontend implementation. Canonical product decisions still live in the Obsidian IntraSpot notes; this report does not replace them.
