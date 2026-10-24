# Sprint 24 — end-to-end testing and usability fixes

Authorized by the user's acceptance of the proposed next sprint, 2026-10-24.
Resume after the interrupted read-only setup; Sprint 23 remains the baseline.

## Scope and acceptance

- Execute the ten previously opt-in browser gates serially against the existing
  named scratch PostgreSQL database. Preserve both development datasets and real
  provider configuration. The fictional browser export targets test API 8002;
  restore the normal export/API connection afterward. Never reset a development
  database or overwrite unrelated running services.
- Exercise the guest, eligible attendee, organization and platform-admin journeys.
  Verify representative desktop/mobile fit, keyboard focus, larger text,
  Filipino labels, contrast and reduced motion. Reproduce before fixing; retain
  approved navigation, styling and domain policy. Fix stale test adapters without
  weakening their intended behavioral assertions.
- Ask the user to perform live PLM sign-in at the existing separate real-development
  app. Never handle their credentials or claim success from synthetic tokens.
- Record pass/fail/skip/blocked separately, exact exercised viewports and features,
  screenshots and fixes. Automated tests/model reviews are not participant studies
  or complete physical-device/accessibility certification.
- Run affected regression checks and final frontend gates after fixes. Update the
  canonical handoff/roadmap with the newly authorized sprint and actual results,
  commit and push the verified developer checkpoint. No deployment or invented
  new product features. Participant and operational/release gates remain separate.
