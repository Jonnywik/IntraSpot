# Sprint 11 mobile attendee interaction handoff

## Preserved design

Use the established PLM Quiet Heritage tokens: warm paper, white/navy surfaces,
burgundy wordmark, blue interactions, functional gold focus/selection; Noto Serif
Georgian titles and Inter Tight controls. Keep image-led single-column discovery
and the approved artwork crop. No fifth navigation destination or archive tab.

## Mobile shell

- Below 768 px, persistent labeled Discover / My Events / Chat / Settings links
  use four equal columns, 56 px minimum height and wrapping labels. Header utility
  links remain 44 px targets. Event details belong to the Discover destination.
- Safe-area padding respects screen edges. A ResizeObserver measures actual
  navigation height so enlarged/wrapped labels cannot cover the last content.
- Primary actions stay at least 48 px; secondary touch controls at least 44 px.
  Long translations wrap rather than truncate. Content may scroll vertically.
- Keep the fictional-account controls visibly labeled, not real authentication.
  No staff workspace or publishing controls are introduced on mobile.

## Feedback and boundaries

- Explicit registration confirmation and server outcomes remain authoritative.
  Preserve retries using their original key, private profile gates, seat counts
  separate from reactions, and immediate waitlist position/no wait estimate.
- My Events keeps Pending / Confirmed / Waitlist / Past status groups. Waitlist
  badges use a light dotted border. Successful withdrawal has a visible status.
  Chat links require confirmed attendance and an unexpired 72-hour retention
  window; the backend still performs all access authorization.
- Revisiting event details restores the account's active registration from the
  private API. Do not offer another registration while that read is pending or
  failed; show loading/retry feedback. Past outcomes link to the Past group.
- Focus, pressed color and selected states do not rely on hover. Existing motion
  settings remove displacement/animation while keeping borders/colors/status.
- Preferences retain account isolation and guest-device persistence. Interface
  text is translated; member-authored content is not.
- Safety/report controls keep their understated text styling but provide 44 px
  mobile touch targets; expanded report content is bounded by its parent column.

## Verification boundary

Browser viewport and focus checks are developer evidence, not physical-device
keyboard, VoiceOver/TalkBack or participant validation. Do not claim the latter
from a resized desktop browser. The accepted release gate remains unchanged.

Final delivered behavior, screenshots and exact executed checks belong in the
Sprint 11 acceptance report, including any compatibility limits discovered.
