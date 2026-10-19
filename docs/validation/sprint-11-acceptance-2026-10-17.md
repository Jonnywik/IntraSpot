# Sprint 11 acceptance — mobile attendee completion

Status: Sprint 11 complete for the local fictional MVP, 2026-10-17.

## Delivered scope

- Preserved PLM Quiet Heritage styling and four labeled attendee navigation tabs.
  Event details keep Discover selected. Profile/Notifications stay in the header;
  no organization-management destination was added to mobile.
- Shared mobile shell uses safe-area padding, wrapping labels, measured bottom
  navigation height and 44/48 px touch targets, without shrinking chosen text size.
- Search/detail and confirmation-sheet controls wrap at narrow widths; the sheet
  remains scrollable with sticky actions and retains keyboard focus handling.
- Registration/My Events retain the server waitlist position and no-estimated-wait
  wording. A missing system waitlist message has the same translated fallback.
  Withdrawal has an explicit success status. Confirmed chat links disappear at
  the exact existing 72-hour retention boundary.
  Event details now fetch the current account's saved active registration after
  reload, instead of incorrectly offering Register/Join waitlist again. This uses
  the existing private registrations API and never introduces a public identity read.
- Mobile chat shows inbox OR selected thread, with a real route back and heading
  focus. Its mobile scroll/composer treatment clears the measured navigation;
  polling, authorization, retries and archived read-only/countdown remain intact.
- Profile adds completion progress and associated invalid-field feedback; entered
  values survive failed saves and fields cannot be overwritten by typing during
  a request. It preserves the original privacy notice and API validation limits.
- Settings and inbox filters/actions wrap for larger translated copy; a preference
  scope is described as saved only after persistence succeeds.

## Executed checks

| Check | Actual result |
|---|---|
| PostgreSQL identity/events/registrations/chat regression | 166 passed, 204.87 s |
| Frontend contracts/localization, including Sprint 11 focused checks | 27 passed |
| Full ESLint after integration | Passed |
| TypeScript and optimized export | Passed; 13 static pages; test API port 8002 |
| Static credential guards | Passed |
| Existing desktop management browser regression | Passed, 18 groups; final combined regression: 2 passed, 85.51 s |
| Sprint 11 actual mobile browser gate | 1 passed, 11 groups, 54.06 s on final app source |
| Existing communication/safety browser regression | Passed, 9 groups in the same final serial run |

The backend checks used only the existing isolated `intraspot_mvp_test` database.
Normal development data and Penpot data were not reset or used as test fixtures.
The stopped existing local PostgreSQL container was restarted with its volume
preserved; fixed fictional-account tokens were renewed without profile resets.

## Actual browser evidence

Final mobile evidence: [results](sprint11-browser-evidence/2026-10-17T12-02-54-362202Z/results.json),
[viewport measurements](sprint11-browser-evidence/2026-10-17T12-02-54-362202Z/geometry.json),
and 20 screenshots in that same timestamped folder. Checked guest search/club
composition, eligible and ineligible identities, faculty instant/approval paths,
profile validation/failure/retry, confirmation bounds/focus/escape restoration,
withdrawal, immediate/reloaded waitlist and confirmed outcomes, chat lost-response
retry without duplication, archived read-only/countdown, notifications and
account/device preference isolation. Profile failure and lost chat response are
deliberate client fault injections; successful outcomes use the real local API.

The geometry sweep covers all six other attendee surfaces at all four target
widths with Filipino extra-large text, plus Settings at those widths and short
390x568/landscape 667x375. Dark high-contrast body text measured 17.45:1; this is
not a blanket contrast certification of every element. The composer and a 320x568
confirmation sheet were operated, not merely checked for route existence.

Earlier failed harness runs exposed English-only localized selectors and a retry
assertion that matched textarea input before the result appeared. Those test
issues were corrected. Visual/source review separately found the real revisited
event Register-again defect; it was fixed and verified with actual reloads.
No threshold was relaxed to hide an app overflow or duplicate-registration issue.

Communication/safety evidence is separate under
`sprint11-browser-evidence/2026-10-17-safety/`; historical Sprint 7 evidence was
not overwritten. The final regression verifies comments/reactions and unchanged-key
retries, personal hide/restore, moderator removal, personal review/seat retention,
platform resolution, archived mobile chat and persisted notification reads.
Final desktop results and ten screenshots are preserved under
`sprint11-browser-evidence/2026-10-17-desktop/`.

Four disjoint Luna/max workers delivered events/registration, chat,
Profile/Settings and the mobile harness. All four are closed. The coordinator
integrated shared navigation/My Events/inbox, centralized translation strings,
removed a duplicate translation helper, corrected test-only selectors/races,
fixed the saved-registration display defect, and reviewed rendered screenshots.
Canonical Obsidian index, roadmap, UI & UX and handoff now record Sprint 11.

## Restored local runtime

The normal optimized export was rebuilt for API port 8001 after test teardown.
Frontend `http://127.0.0.1:3000`, backend readiness, public upcoming events and the
fictional-account catalog all returned HTTP 200. Readiness remains `mvp_0007`.
The existing database volume was preserved and one 30-second deadline worker was
restored after confirming there was no duplicate. No test server on port 8002 is
needed to use the app. Static bundles point to the normal development backend.

## Evidence and limits

The new mobile browser harness is developer-operated verification, not participant
testing or physical iOS/Android/assistive-technology testing. Viewport reduction
does not prove native virtual-keyboard behavior. No deployment, real sign-in,
media integration, recommendations, flash events, new database migration or Penpot
sync belongs to this sprint. Existing dirty Sprint 9/10 work remains preserved.

Next planned scope: Sprint 12 explainable For You discovery, not implemented here.

See [Sprint 11 contract](../backend/Sprint-11.md) and
[interaction handoff](../design/sprint11-interaction-handoff.md).
