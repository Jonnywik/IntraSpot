# Sprint 29: critical-flow accessibility and recovery

The existing layout and four-tab attendee navigation are preserved. Shared
feedback distinguishes request throttling from temporary unavailability. A 429
uses the validated Retry-After value; a 503 explains that the service may be
starting or temporarily unavailable. Neither case silently repeats a write.
Registration retries reuse the original operation key and payload.

Initial errors announce without stealing focus. An explicit retry, completed
registration or waitlist outcome returns focus to the relevant status or action.
The confirmation dialog remains labelled, keyboard-contained and scrollable.
Filipino translations accompany the recovery messages.

## Reproducible checks

Run the frontend tests, lint, type check and static export. The rendered gate in
`tests/shared/test_sprint29_browser.py` is opt-in with
`RUN_SPRINT29_BROWSER=1`. It uses the guarded scratch PostgreSQL database,
fictional identities, a frontend export configured for API port 8002 and free
loopback ports 8002/3000. It starts and stops its own temporary servers.

The browser matrix covers 1280×720, 1366×768, 1440×900, 1920×1080, 390×844 and
320×740, including Filipino, extra-large text, dark/high contrast and reduced
motion. Network fault injection is confined to the recovery scenario; successful
registration and waitlisting otherwise use the real local API.

Desktop emulation and automated accessibility checks do not establish physical
Android/iOS behavior, NVDA/VoiceOver behavior or participant usability. Use the
[participant protocol](../validation/sprint29-participant-protocol.md) to collect
those results separately. Live positive PLM verification remains deferred.
