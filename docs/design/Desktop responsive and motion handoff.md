# IntraSpot — desktop responsive and motion handoff

Approved scope: desktop Penpot prototype and interaction specifications only. Mobile, backend, eligibility, capacity, privacy, registration, accreditation, and archival rules are unchanged. This is not an implementation of a website.

## Layout contract

Primary viewport: **1440 × 900**, at readable 100% sizing. The other review sizes are **1280 × 720**, **1366 × 768**, and **1920 × 1080**. Long content scrolls vertically; fitting does not mean concealing information or reducing browser zoom.

- Fixed top navigation: 72 px. Page gutters: at least 24 px. Centered workspace: at most 1200 px.
- Discover: a single approximately 680 px column. Search and My Clubs compose; guests retain global event/organization search. Venue search is not added.
- Event sheet: right aligned, approximately 540 px. Reachable close control, a fixed action footer, and a body that scrolls independently in the future implementation.
- Chat: persistent conversation list, thread header, and reachable composer; messages scroll. Archived conversations stay in the same inbox, read only, with their deletion countdown.
- Organizer/admin: 240 px sidebar, flexible main content. Wrap labels and fields rather than clipping them.

Penpot constraints and flexible layout groups provide editable geometry. Viewport examples are explicit design checkpoints, not evidence that a browser implementation already adapts dynamically. Independently scrolling nested panels require implementation and live review; Penpot's fixed-at-scroll facility does not by itself prove that behavior.

## Visual system

Keep warm ivory `#FBF8F2`, white surfaces, burgundy identity `#A91422`, navy actions `#0E3473`, interaction blue `#2C67C8`, and decorative gold `#C9933A`. Functional selection/focus gold remains `#A97018`; do not lower its visibility to match decorative linework.

Noto Serif Georgian: major headings and prominent event titles. Inter Tight: controls, metadata, chat, and operational copy. Default page heading ≈32 px, event title 28 px, body 16 px / 24 px line height, metadata 14 px. Penpot represents a 24 px line height on 16 px text as a **1.5 line-height multiplier**, not 24.

Spacing: 8, 12, 16, 24, 32, 48 px. Primary controls: 48 px high / 12 px radius. Cards: 16 px radius. Sheets/overlays: 20 px radius. Preserve image aspect ratios; never scale text or an entire screen to achieve horizontal fit.

Button labels are centered horizontally and vertically inside their controls, including default, hover, disabled, loading, and reusable component appearances. Search and text-entry fields retain left-aligned text.

Use one rounded outline icon language. My Clubs has a filter icon and an explicit selected state. Keep contextual metadata outside artwork. Attendance and remaining capacity are not the Interested reaction count.

## Interaction specification

| Element | Normal motion | Reduced motion |
| --- | --- | --- |
| Buttons | Darker tint, stronger shadow, 2 px hover lift; slight pressed compression; 120–160 ms | Immediate tint/border; no lift or compression animation |
| Clickable event surface | 4 px lift, stronger depth; image 1.025× within its original crop; text is not scaled; 220 ms | Immediate border/color; no lift or image zoom |
| Navigation/tabs | Soft hover tint; selected underline transition; 180 ms | Immediate tint/underline |
| Event sheets/menus | 240 ms open, 180 ms close; consistent opening/closing direction | Immediate appearance/dismissal |
| Toggles/confirmation | Clear state change and one settling/check response; 180–220 ms | Immediate state and readable status |
| Loading | Labelled progress, unchanged control width, simulated result | Same label/status, no decorative movement |

Hover must never register, save, publish, or select a filter. It changes appearance only. Every hover overlay must retain the underlying click action and destination. Close hover overlays on leaving the overlay, not merely on leaving the element covered by it; check for flicker in presentation mode.

Disabled controls have no activation or misleading elevation. Focus is separate from hover: use the stronger gold ring with clear separation from the control edge. Essential information must remain available without hover.

Penpot's current native triggers are click, mouse-enter, mouse-leave, and after-delay; after-delay is a board trigger. It supports overlays and dissolve/slide transitions. True mouse-down states, keyboard focus behavior, continuous image transforms, system preference detection, and spring physics are **handoff specifications**, not claims about native Penpot execution. The component-state matrix documents their appearance. See [Penpot prototyping guidance](https://help.penpot.app/user-guide/prototyping-testing/prototyping/).

## Heritage decoration

Place one low-opacity gold arch/campus-linework treatment beside the Discover heading, outside text, controls, and event imagery. Architecture is stationary. Only foliage/detail accents may move, by approximately 3 px over a slow 12-second cycle. Keep decoration out of Chat, forms, event sheets, and operational tools.

Provide labelled Pause decoration / Resume decoration controls. Reduced motion makes decoration static and removes lift, zoom, slide, and spring effects while retaining immediate color, border, and status feedback. Respect the future browser's system reduced-motion preference as well as the independent IntraSpot preference.

The isolated Penpot preview approximates motion with a 5,750 ms hold and 250 ms dissolve per half-cycle between matching architecture and two foliage positions: a 12-second full cycle. This is a **proxy**, not true interpolated foliage translation. The Discover placement is static; its pause/resume controls demonstrate the intended state. Movement is demonstrated only in the isolated preview. Never put after-delay loops on application journey boards; they could reset scroll, selections, or an open sheet. A paused/reduced preview has no automatic transition.

Continuous nonessential motion must be controllable independently of pointer focus. References: [W3C Pause, Stop, Hide](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html) and [W3C reduced-motion technique](https://www.w3.org/WAI/WCAG22/Techniques/css/C39.html). These references do not constitute an accessibility conformance certification.

## Review and handoff gate

Inspect four viewport examples at readable size, long event titles, Filipino labels, and larger-text cases. Check horizontal clipping, overlaps, reachable close/footer/composer controls, and access to the full vertical content.

Retest guest browsing and eligibility, pending/confirmed/waitlisted outcomes, List/Calendar, confirmed-only event chat, archived read-only chat, independent preferences, organizer drafts and approved publishing, and admin offline accreditation decisions. Retain visibly disabled registration/publishing where the existing rules require it.

Record separately:

1. Geometry, text rendering, and route checks actually performed through MCP.
2. Effects wired into the native prototype and inspected in presentation mode.
3. Effects only specified for future implementation.
4. Participant-testing findings and unresolved issues.

A route graph or exported screenshot alone is not live interaction testing. Participant testing remains required by the canonical Obsidian Development Handoff before frontend implementation. The canonical project notes remain the product source of truth; this file is a desktop interaction handoff, not a replacement for those notes.

## Recovery

A named Penpot version and local geometry/style/route snapshot were captured before this pass. A separate mobile snapshot supports an unchanged-mobile check. Preserve existing hidden legacy boards and unrelated user work. If a bridge request times out, inspect saved frame markers before retrying: a late request can still have modified the live file.

## Execution status

The desktop refinement pass is saved for review. All 71 original journey boards received the shared layout/style pass; all 75 original visible root boards were retained. Mobile was compared against the pre-edit snapshot: all 3,127 shapes unchanged. No application or backend implementation was made.

### Saved review material

- **80 • QA / Responsive & Motion Guide:** eight reusable, labelled primary-control appearance components and native-versus-specified effect notes.
- **84 • QA / Viewport & Motion Index:** links to 20 viewport checkpoints: Discover, event details, Chat, organizer, and admin at the four approved sizes. The **QA • Responsive & Motion Review** flow starts here.
- Twenty same-width full-height companions expose below-fold content. These are QA access views, not evidence of native independent nested scrolling.
- Nine native right-aligned event-detail overlay variants retain canonical destinations. Registration outcomes remain their original screen transitions.
- Ninety-four localized hover appearances support the shared controls; seven event-card hover examples preserve the image crop and use a 1.025× image appearance. Native dissolves approximate the appearance change; they are not continuous browser transforms.
- Isolated normal/paused/reduced motion previews, plus a long Filipino-title/larger-text stress board. Discover decoration remains static in the application journey boards.

### Verification actually performed

The [structural evidence report](Desktop%20responsive%20and%20motion%20evidence.json) records 14 passing journey steps and 10 passing rule checks. It found no invalid geometry, horizontal bounds overflow in original journey boards or the 20 viewport checkpoints, hidden route targets, hover/click destination mismatches, interactive disabled controls, or application-board motion loops. Viewport sheet footers and chat send controls passed vertical-bounds checks. All viewport checkpoints have same-width full-height access companions.

Exported PNGs were visually reviewed for Discover, event details, Chat, organizer, admin, the component-state guide, a card-hover appearance, and the larger-text/Filipino example. Representative reviews covered all four target sizes. The review corrected collapsed sorting labels in viewport examples, small-viewport operational-card clipping, sender-label clipping, and icon anchoring. Original file snapshots and named versions remain available for recovery; newly retired temporary overlays are hidden, not deleted.

### Outstanding acceptance gates

**Not yet a completed live presentation review or participant-tested design.** MCP route and geometry checks and exported PNGs do not test actual pointer entry/exit, hover-overlay flicker, keyboard operation, scroll behavior, or screen-reader behavior. Review these in Penpot presentation mode, including all guest, attendee, organizer, and admin journeys and independent preferences, before sign-off. Participant testing remains required by the canonical Development Handoff before frontend implementation.

True mouse-down and keyboard-focus triggers, continuous image/foliage transforms, spring settling, system reduced-motion detection, and independent scrolling of nested panels remain documented implementation requirements. The prototype demonstrates static state appearances or native transition proxies where noted; it does not claim those browser behaviors already exist.
