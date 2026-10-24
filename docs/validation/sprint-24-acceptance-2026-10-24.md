# Sprint 24 — end-to-end testing and usability fixes

Started 2026-10-24. **Developer checkpoint verified; not release approval.**
The user authorized this sprint after the original roadmap ended at Sprint 23.

## Reproduced defects and corrections

- Skip-to-content activated the main anchor but left actual keyboard focus on
  `BODY`. The main landmark now has `tabIndex={-1}`; the rendered check observes
  `MAIN#main-content` after Enter.
- Discover lacked its Filipino navigation translation; both copies now expose
  `Tuklasin` through the existing translation lookup.
- The representative first card ended below the 1440×900 viewport after later
  feed additions. Keep the event-title size and 2.88 artwork crop. Put the
  registration mode beside existing date/venue metadata, share the For You
  explanation/count row, trim unused heading space and fit the decorative arch
  above its existing pause control. No content is hidden or removed.
- A closing review panel's delayed native `toggle` event could clear the newer
  Material Changes selection. Closing now clears only its own active key;
  apply the same rule to manager and moderator review panels. The existing
  approval/reconfirmation browser journey reproduces and verifies the switch.
- A token alone displayed “Google session active” even if the API could not
  verify its actor. Feedback now distinguishes pending/failed verification from
  a verified session and visibly shows server-derived PLM eligibility. Rendered
  component checks cover loading, stale actor, API error, rejected token,
  eligible/ineligible results and credential omission. English/Filipino provided.
- Update older browser adapters for current accreditation wording/confirmation,
  native publishing confirmation, review decisions, accessible select names,
  moderator navigation and collapsed membership panels. Retain the original
  persisted outcomes, privacy, capacity, retries, navigation and geometry checks.

## Verification ledger

| Check | Result |
|---|---|
| Ten historical opt-in browser gates | All ten passed across serial runs; no unresolved failures |
| New rendered accessibility matrix | Passed, all 52 checks; zero uncaught browser errors |
| Frontend Node suite | Final full suite: 150 passed, including three new rendered auth-feedback cases |
| ESLint | Passed |
| Standalone TypeScript check | Passed after final builds |
| Test export targeting API 8002 | Passed after targeted UI fixes |
| Normal fictional and real-development exports | Both final exports passed: 14 generated pages each plus public/static credential guard |
| Dependency audit | Zero known vulnerabilities, including development dependencies; no dependency changes in this sprint |
| Existing-data preservation | Fictional: all 41 tables/76 rows match. Real: row count stays two; 40 table aggregates match, with only the existing user-preferences record changing while the user used the real app; its current choice was left intact |
| Live PLM sign-in | User confirmed sign-in but observed the non-PLM result; positive PLM verification explicitly deferred by user |

The first whole browser sweep finished with six passes and four failures. An
earlier restricted Edge launch could not initialize its temporary profile; the
same requested test workflow was then executed successfully with normal process
access. A generated Next page-directory write also required a permitted retry.
No browser/product security setting or eligibility rule was weakened.

Subsequent focused executions corrected the demonstrated UI defects and stale
test adapters. The last five-case run passed membership, management and the
new matrix; the next run passed the four-journey gate and matrix. The final
preference gate passed after updating its complete default-record assertion for
the existing `show_flash=true` setting, selecting an unregistered account for its
registration-sheet check, and waiting for the later-added block-warning check to
enable confirmation before asserting the keyboard loop. No participation was
withdrawn to force that check, and no focus-trap assertion was removed.

The final preference run passed in 91.23 seconds. The [de-duplicated gate ledger](sprint24-browser-evidence/gates.json)
records **11 distinct passing gates, zero unresolved failures and zero skips**
across the retained serial executions. Deselected cases are not counted. This is
not represented as one clean whole-suite invocation. The unchanged Sprint 23
688-case default backend and 50-case synthetic-auth results were not rerun as
full suites here; this sprint changes frontend behavior and browser tests only.
Non-failing Node module-type warnings remain recorded maintenance work.

The new matrix checks six attendee routes at 1280×720, 1366×768, 1440×900,
1920×1080, 390×844 and 320×740 with Filipino, extra-large text, dark theme and
high contrast combined; four mobile tabs, measured bottom clearance, actual skip
focus and reduced motion are checked separately. It is a rendered Edge desktop
emulation check, not physical-device, screen-reader or participant certification.
The historical gates include persisted guest, attendee, organization/admin,
membership, approval/reconfirmation, communication, settings, discovery, Flash
and announcement journeys. Results must be de-duplicated across serial reruns;
failed or incomplete runs are not passing evidence.

Selected evidence: [desktop discovery](sprint24-browser-evidence/desktop-discover.png),
[Filipino extra-large/high-contrast mobile discovery](sprint24-browser-evidence/mobile-filipino-xl.png),
[geometry results](sprint24-browser-evidence/geometry-results.json) and
[52-check matrix results](sprint24-browser-evidence/accessibility-results.json).
The representative standard card and Chat composer fit checks pass without
shrinking text, altering the artwork ratio or moving the hover hitbox.

## Live identity boundary

The isolated app at 3001/API 8011 stayed running while port 3000 was temporarily
used for scratch browser tests. The user initially revisited 3000 during the
server transitions; HTTP checks confirmed 3001/8011 remained available. The
correct separate app was opened for them.

After the new status UI was built, the user reported `Not eligible for PLM-only
actions.` A read-only aggregate check found one active real-development identity,
a verified email and zero PLM-domain matches. No address, user ID or token was
printed; no eligibility fields/provider settings were changed. This verifies
the negative case, not a successful PLM check. Further live PLM checking is
deferred at the user's explicit request. See the
[privacy-safe verification checklist](sprint24-plm-verification.md).

## Delivery and open boundaries

Two GPT-6 Luna/max workers supplied a bounded accessibility source review and
the auth/checklist follow-up. The coordinator owns browser execution, root-cause
fixes, shared build/test configuration, results and Git delivery. See the
[source review](sprint24-accessibility-review.md).

No backend/domain policy, schema, cloud application data or Penpot change.
Participant studies, real physical-device/screen-reader testing, positive live
PLM verification, recorded retention/media/hosting/recovery work and release
approval remain separate gates. No deployment is authorized by this checkpoint.

The normal port-3000 export was rebuilt for API 8001 and its server restarted
after tests. The real-development export remains separate on 3001/8011. No
development database reset or eligibility override was used. A real preference
record changed during user-run app activity; its content was not inspected or
reset to manufacture snapshot equality. All other real table aggregates match.

Final live smoke checks: twelve static routes return 200, API is ready, the four
existing public events remain available, private guest reads are denied, both
allowed mutation preflights pass and an external origin is denied.

Automatic approval review rejected broad historical-artifact cleanup because it
could discard local changes. The safer alternative copied only selected passing
evidence into a new Sprint 24 folder. Historical/generated test outputs were left
locally and excluded from the checkpoint; no cleanup workaround was attempted.
