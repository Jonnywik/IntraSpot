import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {
  canLoadAttendance,
  captureAttendanceCommand,
  DESKTOP_ATTENDANCE_QUERY,
  filterAttendanceAttendees,
  isUncertainAttendanceFailure,
  matchesAttendanceCommand,
  registrationReferenceFromLabel,
} from '../Code/Frontend/features/attendance/attendance-helpers.mjs';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');

test('attendance reads are lazy, desktop-only, and private to the active event/account context', async () => {
  assert.equal(DESKTOP_ATTENDANCE_QUERY, '(min-width: 768px)');
  assert.equal(canLoadAttendance({isDesktop: true, isExpanded: true, eventId: 'event-a', token: 'token-a'}), true);
  assert.equal(canLoadAttendance({isDesktop: false, isExpanded: true, eventId: 'event-a', token: 'token-a'}), false);
  assert.equal(canLoadAttendance({isDesktop: true, isExpanded: false, eventId: 'event-a', token: 'token-a'}), false);
  assert.equal(canLoadAttendance({isDesktop: true, isExpanded: true, eventId: 'event-a', token: ''}), false);

  const panel = await read('Code/Frontend/features/attendance/AttendancePanel.tsx');
  assert.match(panel, /useSyncExternalStore\(subscribeDesktop, getDesktopSnapshot, \(\) => false\)/);
  assert.match(panel, /const active = canLoadAttendance\(\{isDesktop, isExpanded: expanded, eventId, token\}\)/);
  assert.match(panel, /if \(!active\) return/);
  assert.match(panel, /key=\{`\$\{eventId\}\\u0000\$\{token\}`\}/);
  assert.match(panel, /readControllerRef\.current\?\.abort\(\)/);
  assert.match(panel, /mutationControllerRef\.current\?\.abort\(\)/);
  assert.doesNotMatch(panel, /localStorage|sessionStorage|\bStorage\b/);
});

test('uncertain attendance retries preserve the exact frozen request and original session state', async () => {
  const context = Object.freeze({eventId: 'event-a', token: 'actor-token'});
  const command = captureAttendanceCommand({
    context,
    eventId: 'event/a',
    token: 'actor-token',
    kind: 'mark',
    registrationId: 'registration/a',
    value: true,
    sessionOpen: true,
    version: 7,
    clientKey: 'client-key-1',
  });

  assert.equal(Object.isFrozen(command), true);
  assert.equal(Object.isFrozen(command.body), true);
  assert.equal(command.path, '/events/event%2Fa/attendance/registrations/registration%2Fa');
  assert.deepEqual(command.body, {attended: true, version: 7, client_key: 'client-key-1'});
  assert.equal(matchesAttendanceCommand(command, context), true);
  assert.equal(matchesAttendanceCommand(command, {}), false);

  const refreshedResource = {attendance: {is_open: false, version: 9}};
  const idempotentReplay = {
    event_id: 'event/a',
    registration_id: 'registration/a',
    is_open: true,
    attended: true,
    version: 8,
  };
  assert.equal(idempotentReplay.is_open, command.sessionOpen);
  assert.notEqual(idempotentReplay.is_open, refreshedResource.attendance.is_open);

  assert.equal(isUncertainAttendanceFailure(null), true);
  assert.equal(isUncertainAttendanceFailure(0), true);
  assert.equal(isUncertainAttendanceFailure(408), true);
  assert.equal(isUncertainAttendanceFailure(429), true);
  assert.equal(isUncertainAttendanceFailure(503), true);
  assert.equal(isUncertainAttendanceFailure(400), false);
  assert.equal(isUncertainAttendanceFailure(409), false);

  const panel = await read('Code/Frontend/features/attendance/AttendancePanel.tsx');
  assert.match(panel, /result\.is_open !== command\.sessionOpen/);
  assert.doesNotMatch(panel, /result\.is_open !== resource\?\.attendance\.is_open/);
  assert.match(panel, /onClick=\{\(\) => void sendCommand\(retryableAttempt, true\)\}/);
  assert.match(panel, /body: command\.body/);
  assert.match(panel, /clientKey: window\.crypto\.randomUUID\(\)/);
});

test('registration reference search matches the full opaque participant label without searching other attendee data', async () => {
  const attendee = {
    registration_id: 'internal-registration-key',
    participant_label: 'Registration · FULLREGUUID-1234',
    attended: false,
    email: 'private@example.test',
  };
  assert.equal(registrationReferenceFromLabel(attendee.participant_label), 'FULLREGUUID-1234');
  assert.equal(registrationReferenceFromLabel('FULLREGUUID-1234'), 'FULLREGUUID-1234');
  assert.deepEqual(filterAttendanceAttendees([attendee], 'fullreguuid-1234'), [attendee]);
  assert.deepEqual(filterAttendanceAttendees([attendee], 'private@example.test'), []);

  const panel = await read('Code/Frontend/features/attendance/AttendancePanel.tsx');
  const css = await read('Code/Frontend/features/attendance/attendance-panel.module.css');
  const messages = await read('Code/Frontend/features/attendance/messages.ts');
  assert.match(panel, /Search confirmed attendees by registration reference/);
  assert.match(panel, /t\('Registration reference: \{reference\}'/);
  assert.match(panel, /registrationReferenceFromLabel\(attendee\.participant_label\)/);
  assert.match(css, /\.label\s*\{[\s\S]*?overflow-wrap: anywhere/);
  assert.match(messages, /'Registration reference: \{reference\}': 'Sanggunian ng rehistrasyon: \{reference\}'/);
});

test('session confirmation, roster status/counts, and revision-safe history are accessible and translated', async () => {
  const [panel, messages, types] = await Promise.all([
    read('Code/Frontend/features/attendance/AttendancePanel.tsx'),
    read('Code/Frontend/features/attendance/messages.ts'),
    read('Code/Frontend/features/attendance/types.ts'),
  ]);
  assert.match(panel, /<dialog[\s\S]*?onCancel=\{cancelConfirmation\}/);
  assert.match(panel, /cancelRef\.current\?\.focus\(\)/);
  assert.match(panel, /focusReturnRef\.current\?\.isConnected/);
  assert.match(panel, /Checked in \{checked\} of \{confirmed\} confirmed attendees\./);
  assert.match(panel, /data-checked-in=\{attendee\.attended\}/);
  assert.match(panel, /entry\.actor_id/);
  assert.match(panel, /entry\.previous_value/);
  assert.match(panel, /entry\.value/);
  assert.match(panel, /refreshQueued = true/);
  assert.match(panel, /revision !== requiredRevisionRef\.current/);
  assert.match(panel, /setReadStatus\(current => current === 'ready' \? 'ready' : 'loading'\)/);
  assert.doesNotMatch(panel, /current === 'ready' && resource/);
  assert.match(types, /components\['schemas'\]\['AttendanceOut'\]/);
  assert.match(types, /components\['schemas'\]\['AttendanceAuditOut'\]/);
  assert.match(types, /components\['schemas'\]\['AttendanceMutationOut'\]/);
  assert.match(types, /components\['schemas'\]\['AttendanceSessionInput'\]/);
  assert.match(types, /components\['schemas'\]\['AttendanceMarkInput'\]/);

  const keys = new Set([...panel.matchAll(/\bt\(\s*'([^']+)'/g)].map(([, key]) => key));
  for (const key of [
    'Open',
    'Closed',
    'Close check-in',
    'Open check-in',
    'Check in',
    'Clear check-in',
    'Checked in',
    'Not checked in',
    'Check-in session opened',
    'Check-in session closed',
    'Open check-in?',
    'Close check-in?',
    'This opens staff check-in for confirmed attendees.',
    'This closes staff check-in. Confirmed check-ins remain recorded.',
    'Attendance change recorded.',
    'The attendance change could not be confirmed. Retry the same request.',
    'The attendance changed while you were reviewing it. Current state, roster, and history have been refreshed. Review before making another change.',
    'The attendance change was rejected. Current state, roster, and history are refreshing.',
    'A secure request key could not be created. Please use an updated browser.',
    'Refresh attendance',
    'Search confirmed attendees by registration reference',
    'No confirmed attendees match this registration reference.',
    'Staff reference: {reference}',
    'Changed from {previous} to {current}',
    'Check in registration {reference}',
    'Clear check-in for registration {reference}',
    'Retrying reuses the original version and request key.',
  ]) keys.add(key);
  for (const key of keys) assert.ok(messages.includes(`'${key}':`), `Missing Filipino message: ${key}`);
  assert.match(panel, /status === 409\)[\s\S]*?setAttempt\(null\)[\s\S]*?refreshAfterResponse\(\)/);
});
