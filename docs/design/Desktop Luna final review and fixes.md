# IntraSpot desktop — Luna final review and fixes

## Scope and review method

Four GPT-6 Luna subagents at **max** reasoning reviewed visual/responsive fit, accessibility and interaction states, student/club-member/faculty journeys, and organizer/admin operations. The parent owns live Penpot inspection and all edits; reviewers do not write to the shared design concurrently.

Preserve the approved PLM identity, centered button labels, constrained feed, existing navigation and actions, and canonical eligibility, capacity, privacy and offline-only accreditation rules. This pass targets the existing desktop prototype. Mobile and application/backend code remain unchanged.

Evidence: verified exported images and the fresh live `penpot-final-review-live-before.json` snapshot. Hidden ancestors exclude legacy material from findings. Screenshots and route inspection are heuristic checks, not participant testing or live pointer/keyboard testing.

## Fix plan — accepted first tranche

| Finding | Minimal change | Verification |
| --- | --- | --- |
| Faculty-inclusive eligibility has a student-only action label | Change “Continue as sample student” to “Continue as sample PLM attendee,” including its hover appearance. Keep the existing destination. | Copy, centering, label fit and identical click destination. |
| Archived/read-only state is 12 px | Raise the state label to 14 px in inbox, active/archived threads, and their viewport/access copies. Keep countdown and read-only behavior. | Adequate text-box height, no overlap, routes unchanged. |
| 1280×720 event-sheet section heading crosses the footer boundary | Move its divider and heading upward slightly, without resizing artwork or moving footer/actions. Full details remain available through the existing vertical-access companion. | Heading stays above the body edge and footer with breathing room; screenshot and geometry check. |
| Larger-text helper renders two lines outside a one-line text box | Increase the Filipino stress example's helper box to fit two lines and separate it from the preceding metadata. | Full copy retained; no collision with adjacent centered actions. |

## Fix plan — accessibility and operations tranche

All four reviews are complete. Additional accepted fixes:

| Finding | Minimal change | Verification |
| --- | --- | --- |
| Five board-based reference button specimens missed the rectangle-based centering pass | Center their labels in both directions and align specimens to the approved 48 px height / 12 px corners. | Render the reference board; inspect bounds and centering. |
| Chat dots appear actionable but have no simulated action | Keep the subtle dots beside others' messages, but make their unavailable prototype state explicit. Use a 44×44 label/target frame, disabled visual treatment, and a visible “message actions not simulated” note. Do not invent content-report destinations/resolution. | No click or misleading hover interaction; note visible in active-chat and QA copies. |
| “Edit event” sends the selected ready draft to the new-event type chooser | Route the existing approved-draft edit action to the populated scheduled essentials step. Update its labels, face and hover equivalents together. | Click and hover share the resume-draft destination; publish approval gate unchanged. |
| “Events” sidebar label opens new-event creation | Rename this prototype action to “Create event,” matching its actual destination. Existing Overview continues to expose the sample draft. Do not fabricate a complete event-management list during this polish pass. | Consistent copy on source/QA organizer states; new-event chooser remains the destination. |
| “Decisions” and “Audit trail” are duplicate links to the same decision-record view | Consolidate into “Decisions & audit” and hide the duplicate Audit trail entry, without deleting it. | A single clear sidebar destination; existing decision outcome/admin/date-time records retained. |
| Some viewport detail copies retain text-symbol date/venue icons | Replace only the remaining symbol prefixes with the same outline clock/pin treatment used in the current source details. | Same text content and crop; consistent icon anchors, no new overflow. |

Post-edit visual verification also found the reference board's state captions were one space-padded string, misaligned beneath the four buttons. Replace that strip with four separately centered captions directly beneath their matching state examples.

### Triage decisions

- The QA-only vertical-access links are on separated viewport review boards, not the 71 user-journey source boards. Keep them: they expose below-fold material where native independent scrolling is not demonstrated. Participant sessions should start from the source journey flows, not the QA flow.
- The decoration side change is an intentional adaptation into unused space; preserve it rather than obstructing content.
- The current centered buttons, separate attendance/reaction counts, pending versus confirmed copy, waitlist position/no estimate, independent preferences and offline-only accreditation do not need redesign.
- Keyboard, screen-reader, pointer entry/exit, nested scrolling and actual reduced-motion behavior remain manual/implementation validation gates, not demonstrated Penpot defects.
- Chat content-report destination/resolution is unresolved in the canonical Open Questions note. The disabled prototype affordance is honest design treatment, not an implementation of that unresolved workflow. A functional menu requires that decision and a subsequent explicit prototype task.

## Already checked / not a redesign

- The live 71-journey baseline has no invalid geometry, horizontal overflow, hidden/missing destinations, interactive disabled controls, or application-board timed loops.
- Hover/click destinations match in the baseline.
- Button centering in older screenshots is stale; the current labels are centered.
- The heritage decoration moves into unused space at narrower widths to avoid the feed and controls. Do not force a fixed side when that would create collisions.
- Keep approval requests distinct from confirmed attendance; waitlist position/no estimated wait copy, My Clubs plus search, and confirmed-only chat remain settled behavior.

## Recovery and acceptance

Before edits: live geometry/style/route snapshot and named Penpot version **Before Luna final desktop review fixes • 2026-10-11**.

After edits: inspect changed frames, compare all existing click destinations, recheck button centering, typography and horizontal bounds, and save a named final review version. Record native effects separately from handoff-only effects.

Still required: presentation-mode pointer/keyboard/scroll checks and participant validation across guest, eligible attendee, organization creator and platform admin journeys. These are not replaced by subagent review. The canonical Development Handoff remains the authority for the frontend implementation gate.

Accessibility reference checks use the [W3C text-contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) and [minimum-target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html); this review does not certify WCAG conformance.

## Execution and verification — completed 2026-10-11

Both accepted fix tranches and the reference-caption alignment correction are implemented. The named Penpot version **Desktop • Luna reviewed and refined • 2026-10-11** was saved at 08:18:29 UTC, with the canvas returned to member Discover.

- Checked all 8,148 existing desktop shapes across the baseline; no missing shapes, invalid geometry, horizontal overflow in the checked journey bounds, or unexpected route changes were found.
- Verified 900 button labels are centered. The five board-based reference specimens and four separately aligned state captions also pass.
- The 20 intended draft-edit links now resume the populated scheduled essentials screen. Other existing destinations remain unchanged.
- The small-viewport sheet heading has 10 px clearance above its footer boundary; the larger-text helper fits its two-line frame.
- Exported-image review verified the corrected reference components and compact Chat composition. This is not an exhaustive post-edit visual inspection of every screen.
- All 3,127 mobile shapes match the unchanged baseline. No mobile or application/backend changes were made.

Detailed results are recorded in [Desktop Luna final review evidence.json](./Desktop%20Luna%20final%20review%20evidence.json).

Status: **review-ready prototype, not deployment-approved**. Presentation-mode pointer, keyboard and scrolling checks, followed by participant validation, remain required. Chat message actions are explicitly not simulated while canonical report routing and resolution remain unresolved. The existing interaction handoff still distinguishes native Penpot demonstrations from intended implementation effects.
