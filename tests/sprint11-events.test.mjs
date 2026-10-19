import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';

const [feed, detail, registration, styles] = await Promise.all([
  readFile(new URL('../Code/Frontend/features/events/DiscoverFeed.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/EventDetail.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/registrations/RegistrationAction.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/attendee-events.module.css', import.meta.url), 'utf8'),
]);

test('discovery composes search with My Clubs and keeps reactions separate from attendance', () => {
  assert.match(feed, /parameters\.set\(["']q["'], search\)/);
  assert.match(feed, /parameters\.set\(["']my_clubs["'], ["']true["']\)/);
  for (const label of ['Interested', 'Confirmed', 'Reserved', 'Remaining']) {
    assert.ok(feed.includes(`t("${label}")`), `feed count is missing ${label}`);
    assert.ok(detail.includes(`t("${label}")`), `detail count is missing ${label}`);
  }
});

test('registration keeps the request key across retry and routes waitlisted outcomes to My Events', () => {
  assert.match(registration, /attemptKey\.current\?\.eventId === event\.id/);
  assert.match(registration, /idempotencyKey: savedAttempt\.key/);
  assert.ok(registration.includes("result.status === 'waitlisted' ? 'waitlist'"));
  assert.ok(registration.includes("result.waitlist_message ?? 'You are on the waitlist. No estimated wait time is available.'"));
  assert.match(registration, /useApiResource<AttendeeRegistration\[\]>/);
  assert.match(registration, /item\.event_id === event\.id/);
  assert.match(registration, /registrations\.loading/);
  assert.match(registration, /registrations\.error/);
});

test('mobile confirmation stays scrollable, safe-area aware, and keyboard contained', () => {
  assert.match(styles, /\.clearSearch\s*\{[^}]*min-height:\s*44px/s);
  assert.match(styles, /\.registrationSheet \.registrationSheetPanel\s*\{[^}]*100dvh[^}]*safe-area-inset-top[^}]*safe-area-inset-bottom/s);
  assert.match(styles, /@media \(max-width: 767px\)\s*\{[^}]*\.registrationSheet\s*\{[^}]*overflow:\s*hidden/s);
  assert.match(styles, /\.registrationSheetPanel \.sheetActions\s*\{[^}]*position:\s*sticky/s);
  assert.match(styles, /\.detailNavigation \.text-action\s*\{[^}]*min-height:\s*44px/s);
  assert.match(registration, /role="dialog"[\s\S]*?aria-modal="true"/);
  assert.match(registration, /event\.key !== 'Tab'[\s\S]*?first\.focus\(\)/);
  assert.match(registration, /returnFocus\?\.isConnected[\s\S]*?returnFocus\.focus\(\)/);
});
