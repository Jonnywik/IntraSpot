# Sprint 9 quality review

Scope is the accepted Sprint 9 attendee desktop polish and persistent
preferences contract, including the selected DiscoveryLayout: clubs and route
shortcuts on the left, upcoming registration/status on the right, and a single
680px feed column. It does not approve future-sprint behavior or real-user
release.

## Code inspection

Status: read-only inspection of the current shared-tree snapshot. Code
inspection and static tests are not browser/runtime evidence.

Review the frozen preferences interface and its callers for:

- authenticated, account-scoped reads and writes; guest state remains scoped to
  this browser device;
- partial saves that preserve omitted fields, retryable failed saves, serialized
  rapid edits, and stale-response protection during account changes;
- no guest-to-account copy and no cross-account settings or private UI leakage;
- guest public-club discovery without private registration API requests, and
  account-specific upcoming registration/status without cross-account leakage;
- desktop workspace capped at 1440px, 3 columns at 1180px and wider, 2 columns
  from 1000–1179px, feed-only below 1000px, with the feed capped at 680px;
- English and Filipino coverage for attendee-facing controls, status/error copy,
  and accessibility labels, while authored event and organization text stays
  untouched;
- resolved light/dark/system theme, high-contrast and text-size root state, and
  reduced motion that honors both the app choice and operating-system setting;
- keyboard operation of the registration sheet, including initial focus,
  contained Tab/Shift+Tab movement, Escape, and focus return;
- desktop composition at 1440×900, 1280×720, 1366×768, and 1920×1080, without
  changing the four-tab mobile navigation or registration/chat routes.

Record concrete defects with file and line references. Distinguish a code
inspection finding from a behavior observed in a browser.

### Resolved by code inspection

- `Code/Frontend/lib/session.tsx:22` initializes `authLoading` to true. Its
  asynchronous bootstrap reads the saved account
  label before resolving guest state and keeps loading active through fresh
  catalog retrieval and `/me` verification; no-demo, storage-error, no-label,
  and failed-verification paths resolve loading without retaining a token.
  `PreferencesProvider` withholds a scope while this is active
  (`Code/Frontend/lib/preferences.tsx:144`).
- `Code/Frontend/lib/i18n.ts:14-16` selects the requested language from
  `messages` first and uses Filipino-only `sharedMessages` only when
  `language === 'fil'`, avoiding Filipino fallback text under English.
- The preferences reset path replaces corrupt guest storage with complete
  defaults and marks the guest scope loaded before saving. Browser recovery
  verification remains pending.
- The browser harness uses locale-independent account controls: account
  options are selected by value, session status is matched by the fictional
  account label, and settings controls map preference keys to stable IDs,
  radio names, and checkbox section IDs. No English accessible-name selector
  is used by these helpers.

### Coordinator verification update — 2026-10-16

The main chat completed the serial PostgreSQL and browser runs after this
worker's source review. Preference restoration/isolation, corrupt-storage reset,
rapid saves and stale responses, retry, app/OS theme and motion, Filipino root
language, contrast/text size, keyboard sheets, responsive columns and private
sidebars passed. A separate screenshot/geometry review found and fixed short-
desktop chat overlap; header, log, textarea and send action are now checked
together. Full participant accessibility and translation evaluation remain open.

## Automated browser evidence

Status: passed by the coordinator. Microsoft Edge via bundled Playwright,
static frontend on port 3000 and API port 8002 against isolated PostgreSQL
`intraspot_mvp_test`; no participant test and no development-data reset.

Run `tests/shared/test_sprint9_quality.py` with `RUN_SPRINT9_BROWSER=1`, after
building the frontend for port 8002. Final result: 1 passed in 99.26 seconds.
The runner contains two scripts: a geometric/interaction check and the ten-group
preferences/responsive journey. Authenticated B has a confirmed fixture event;
A/guest must not see its private registration data. The coordinator owns the
test slot and closed all workers after integration.

Final evidence folders under `docs/validation/sprint9-browser-evidence/`:

- `2026-10-16T04-03-51-535Z/`: ten groups, zero page errors, four desktop viewport
  screenshots; 1180/1179/1000/999 column boundaries for guest/account, mobile
  four-tab check, settings races/retry and keyboard sheet behavior.
- `2026-10-16T04-03-41-310Z-geometry/`: a card with summary fits 1440×900; hover preserves the
  target while animating surface/art; focus is tested using actual keyboard
  modality; chat header/log/composer do not overlap at 1280×720 and 1440×900.

Earlier folders capture intermediate failures and are not the acceptance
baseline. One corrupt-storage setup timeout was not reproduced on the final
run; diagnostic capture was added without weakening its readiness assertion.
The initial full-page guest image is a visual helper, not gate evidence. See
`sprint-9-acceptance-2026-10-16.md` for backend/build/regression results and limits.

## Deferred participant validation

Not performed, as directed by the Sprint 9 authorization. A developer-operated
browser journey is not participant testing and cannot establish whether
attendees understand the settings, translated copy, focus behavior, or desktop
layout in real use. Participant review remains a separate later gate requested
by the user.

## English strings requiring dictionary additions

Status: none detected by the current static localization suite. The latest
`node --test tests/sprint9-localization.test.mjs` run passed 3/3, including
nonblank Filipino translations with matching placeholders and coverage of
attendee-interface literal `t()` messages. This supersedes the older static
inventory, which predates dictionary reconciliation.
Organization and event names remain user-authored data and must not be
translated. Rendered language switching was browser-checked; professional
translation quality and participant comprehension have not been assessed.
