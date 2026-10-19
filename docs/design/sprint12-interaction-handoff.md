# Sprint 12 — explainable discovery interaction handoff

Keep the approved PLM desktop/mobile layouts. Signed-in discovery defaults to
For You; guests keep Upcoming. Explicit Upcoming/Newest are chronological, not
personalized order. Search and the eligibility-gated My Clubs filter compose.

For You ranks by club membership, distinct interest-tag overlap, chosen broad
area and whole-event recurring availability, in that priority order. Ties use
start time then stable ID. This is deterministic matching, not a predictive AI
score. Reasons use controlled labels: from your clubs, matches your interests,
matches your chosen area, fits your free time. They are never a Featured badge.

Settings provides optional named-area and weekly Manila free-time inputs. Users
can save or clear these independently of language/theme/accessibility settings.
Interests reuse the private Profile fields. Do not ask for precise coordinates,
street addresses, GPS, calendar access or a new profile requirement to browse.
An overnight window is two adjacent-day rows, with an explicit end-of-day value.
Whole-event fit includes contiguous windows across midnight/week boundaries; a
start-only overlap must not produce a fit reason.

Organizers may add public topic tags and a broad area to an incomplete draft.
Neither is required to publish. Their preview/save states use the existing
autosave/version guard. Existing tagless/area-less events are not inferred from
their titles, artwork or street addresses. Published metadata stays read-only.

Reason wording must not reveal the actual private tags, area or schedule. Show
only the current requesting account's reasons; chronological/guest results have
none. Private preference inputs must not be cached as guest preferences.

Matched reason chips stay visible on cards. The longer ranking explanation uses
a native, collapsed "How For You works" disclosure with a Settings link, keeping
the discovery controls compact. Sort and optional metadata controls have concise
explicit accessible names; helper descriptions remain associated separately.
An account with no saved preferences is labeled not-yet-saved, not saved. Failed
preference writes retain editable values and offer a retry; clearing does not
reset theme, language, accessibility or private Profile interests.

Maintain 44/48 px targets, wrapping English/Filipino, gold focus, high contrast,
larger text and reduced-motion feedback. Retain the same four mobile destinations.
Actual developer browser evidence is separate from participant/native-device
validation. No Penpot synchronization or deployment is included.
