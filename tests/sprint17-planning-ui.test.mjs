import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {
  eventsForManilaDay,
  getManilaDateKey,
  intervalIncludesManilaDay,
  intervalsOverlap,
  manilaMonthDays,
  shiftCalendarMonth,
} from '../Code/Frontend/features/planning/calendar.ts';

const read = path => readFile(new URL('../' + path, import.meta.url), 'utf8');

test('Manila date keys and month grids respect calendar boundaries', () => {
  assert.equal(getManilaDateKey('2026-01-01T15:59:59Z'), '2026-01-01');
  assert.equal(getManilaDateKey('2026-01-01T16:00:00Z'), '2026-01-02');
  assert.equal(getManilaDateKey('not-a-date'), null);

  const leapFebruary = manilaMonthDays(2024, 2);
  assert.equal(leapFebruary.length, 35);
  assert.ok(leapFebruary.includes('2024-02-29'));
  assert.equal(leapFebruary[0], '2024-01-28');
  assert.equal(leapFebruary.at(-1), '2024-03-02');
  assert.deepEqual(shiftCalendarMonth(2026, 12, 1), {year: 2027, month: 1});
  assert.deepEqual(shiftCalendarMonth(2027, 1, -1), {year: 2026, month: 12});
  assert.deepEqual(manilaMonthDays(2026, 13), []);
});

test('calendar intervals include every Manila day touched, but exclude an exact-midnight end day', () => {
  const exactMidnight = {
    starts_at: '2026-05-01T23:30:00+08:00',
    ends_at: '2026-05-02T00:00:00+08:00',
  };
  assert.equal(intervalIncludesManilaDay(exactMidnight.starts_at, exactMidnight.ends_at, '2026-05-01'), true);
  assert.equal(intervalIncludesManilaDay(exactMidnight.starts_at, exactMidnight.ends_at, '2026-05-02'), false);

  const crossesMidnight = {...exactMidnight, ends_at: '2026-05-02T01:00:00+08:00'};
  assert.deepEqual(eventsForManilaDay([crossesMidnight], '2026-05-02'), [crossesMidnight]);
  assert.equal(intervalIncludesManilaDay('2026-05-02T01:00:00+08:00', '2026-05-02T01:00:00+08:00', '2026-05-02'), false);
  assert.equal(intervalIncludesManilaDay('invalid', '2026-05-02T02:00:00+08:00', '2026-05-02'), false);
});

test('conflict helper uses strict half-open overlap and rejects invalid intervals', () => {
  assert.equal(intervalsOverlap(
    '2026-05-01T09:00:00+08:00',
    '2026-05-01T10:00:00+08:00',
    '2026-05-01T10:00:00+08:00',
    '2026-05-01T11:00:00+08:00',
  ), false);
  assert.equal(intervalsOverlap(
    '2026-05-01T09:00:00+08:00',
    '2026-05-01T10:00:00+08:00',
    '2026-05-01T09:59:59+08:00',
    '2026-05-01T11:00:00+08:00',
  ), true);
  assert.equal(intervalsOverlap('2026-05-01T10:00:00Z', '2026-05-01T10:00:00Z', '2026-05-01T09:00:00Z', '2026-05-01T11:00:00Z'), false);
});

test('planning components remain caller-scoped, removable, localized, and integrated without dropping statuses', async () => {
  const [save, conflict, saved, calendar, session, messages, myEvents] = await Promise.all([
    read('Code/Frontend/features/planning/SaveEventButton.tsx'),
    read('Code/Frontend/features/planning/ConflictWarning.tsx'),
    read('Code/Frontend/features/planning/SavedEvents.tsx'),
    read('Code/Frontend/features/planning/EventCalendar.tsx'),
    read('Code/Frontend/features/planning/use-planning-session.ts'),
    read('Code/Frontend/features/planning/messages.ts'),
    read('Code/Frontend/features/registrations/MyEvents.tsx'),
  ]);

  assert.match(save, /\/me\/saved-events\//);
  assert.match(save, /method: remove \? 'DELETE' : 'PUT'/);
  assert.match(conflict, /\/me\/event-conflicts\//);
  assert.match(conflict, /revision = 0/);
  assert.match(conflict, /current\.error/);
  assert.match(conflict, /No schedule conflicts found/);
  assert.match(saved, /\/me\/saved-events/);
  assert.match(saved, /event\?\.title \?\? t\('Event unavailable'\)/);
  assert.match(saved, /method: 'DELETE'/);
  assert.match(saved, /renderSavedEvent=\{renderSavedEvent\}/);
  assert.match(calendar, /onKeyDown=\{\(event\) => moveFocus\(event, day\)\}/);
  assert.match(calendar, /dayButtons\.current\.get\(focusDay\)\?\.focus\(\)/);
  assert.match(calendar, /Calendar status legend/);
  assert.match(session, /controller\.abort\(\)/);
  assert.match(session, /String\(version\).+token/);
  assert.match(myEvents, /const \[view, setView\] = useState<'list' \| 'calendar'>\('list'\)/);
  assert.match(myEvents, /const \[section, setSection\] = useState<'registrations' \| 'saved'>\('registrations'\)/);
  assert.match(myEvents, /registrationTabOrder: RegistrationTab\[\] = \['pending', 'confirmed', 'waitlist', 'past'\]/);
  assert.match(myEvents, /futureCancellations\.length/);
  assert.match(myEvents, /intervalsOverlap\(first\.starts_at, first\.ends_at, second\.starts_at, second\.ends_at\)/);

  const source = [save, conflict, saved, calendar].join('\n');
  const keys = new Set([...source.matchAll(/\bt\(\s*(['"])(.*?)\1/g)].map((match) => match[2]));
  for (const key of keys) assert.ok(messages.includes("'" + key + "':"), 'Missing Filipino message key: ' + key);
});
