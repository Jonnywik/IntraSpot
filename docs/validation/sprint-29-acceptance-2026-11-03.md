# Sprint 29 acceptance — 2026-11-03

Approved layouts and four-tab mobile navigation are unchanged. The checkpoint
adds translated throttling/cold-start recovery feedback, request-preserving
retries and focused, announced outcomes after explicit user actions.

| Check | Result |
| --- | --- |
| Frontend contract/recovery/localization suite | 178 passed |
| Lint, TypeScript and local static export | Passed |
| Guarded hosted export | Passed with synthetic public configuration in clean staging |
| New rendered event/registration/waitlist/recovery journey | 41 checks passed, zero failures or uncaught browser errors |
| Existing rendered accessibility matrix | 52 checks passed, zero failures or uncaught browser errors |
| Combined browser harness | 2 passed in 94.44 s |

Microsoft Edge automation used the fictional scratch PostgreSQL database and
temporary loopback servers. All six viewports were exercised: 1280×720,
1366×768, 1440×900, 1920×1080, 390×844 and 320×740. The matrix included Filipino,
extra-large text, dark/high contrast and reduced motion. Main visually inspected
the desktop details and narrow confirmation-dialog captures as a supplementary
check; this is developer inspection, not participant validation.

Rendered checks cover dialog naming, keyboard containment/return, reachable
actions, live outcomes, immediate waitlist position/no-estimate copy and its
repetition in My Events. Recovery faults verify Retry-After visibility, a
focused temporary-unavailability error, focus on the loaded heading and an
unchanged registration key **and payload** across transport failure. Successful
My Events withdrawal retains focus on its named status after refresh.

The independent Luna/max reviewer identified lost focus after My Events actions
and incomplete retry-payload verification; both were corrected. Source checks
also cover reconfirmation acceptance/decline. The browser harness creates fresh
signed fictional credentials in a temporary private catalog rather than
renewing or overwriting the existing development catalog. An earlier fault
fixture omitted the real API's CORS exposure for Retry-After; the fixture was
corrected and the complete gate rerun. Failed setup runs are not counted passes.

Raw screenshots remain in unique ignored `.cache/s29/run-*` directories; the
tracked compact [evidence](sprint29-browser-results.json) contains no tokens or
personal account data. Human participant tasks and separate physical Android,
iOS, NVDA and VoiceOver checks are prepared in the
[protocol](sprint29-participant-protocol.md) and remain pending. Live positive
PLM verification remains deferred. No public deployment or paid upgrade occurred.
