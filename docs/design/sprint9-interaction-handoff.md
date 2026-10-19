# Sprint 9 desktop interaction handoff

Accepted direction: Quiet Heritage A, expanded with useful desktop sidebars.
This describes the working local app, not a Penpot synchronization or production
release. Existing event, membership, moderation and eligibility rules are intact.

## Composition

- Warm ivory canvas, white surfaces, burgundy identity, navy actions, blue links
  and selection surfaces, functional gold keyboard focus and selected underlines.
- Noto Serif Georgian for major headings/event titles; Inter Tight for controls,
  body copy and metadata. Fonts are built into local static assets by Next.js.
- Discover uses a single feed capped at 680px. The workspace expands to 1440px:
  club shortcuts on the left and the current account's upcoming confirmed events,
  pending/reconfirmation count and waitlist count on the right. No calendar,
  recommendations, saved events or new notification categories were invented.
- At 1180px and wider, show both sidebars; at 1000–1179px retain only the right
  sidebar; below 1000px use the feed alone. Existing destinations remain available
  through navigation. Four mobile tabs remain unchanged.
- Long content scrolls vertically. Larger text can wrap controls or extend a page;
  do not shrink fonts or hide content to fit a viewport.

## Feedback implemented in the app

| Surface | Behavior |
|---|---|
| Buttons | Centered labels, hover tint/elevation and 2px lift; pressed feedback; disabled controls have no lift |
| Event cards | Pointer target stays stationary; background surface lifts 4px and artwork scales to 1.025 inside its crop over 220ms |
| Navigation/tabs | Soft hover tint, visible selected gold underline, separate keyboard focus |
| Registration sheet | Right-hand panel, 240ms opening slide/fade, scrollable content and sticky action area; Tab containment, Escape and focus return |
| Loading/failure | Labeled progress, explicit retry, no optimistic fabricated outcomes |
| Preferences | Immediate display update, serialized account saves, saving/saved/error feedback and retryable intent |
| Discover linework | Stationary architecture with foliage moving at most 3px on a 12-second cycle; labeled pause/resume |

The current sheet unmounts on close; it does not demonstrate a reverse closing
animation or a spring simulation. Do not describe those intended future effects
as implemented. Hover/focus never changes registrations, filters or publication.

## Accessibility and language

English/light/standard are defaults. Filipino, dark/system theme, larger text,
high contrast, reduced motion and decoration pause are independent preferences.
Account choices use the authenticated API; guests use a versioned local record.
Guest settings never overwrite account settings. Authored content stays unchanged.

System reduced motion always wins. Reduced motion removes animation, lift and
image zoom while preserving static positioning and immediate color/border/status
feedback. Focus remains distinct from hover; essential information does not rely
on motion or a pointer. Contrast checks are targeted developer checks, not a
claim of full accessibility certification or professional translation review.

## Scope and evidence

Desktop attendee views, shared shell and existing attendee social/notification
copy are refined. Organizer/admin bodies remain the Sprint 8 baseline, with
dedicated workflow polish planned for Sprint 10. Mobile-specific refinement is
Sprint 11. Real authentication, cloud deployment and participant review are not
part of this sprint. See the Sprint 9 acceptance report for actual test results.
