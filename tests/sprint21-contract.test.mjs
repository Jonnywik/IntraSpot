import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');

test('manual attendance uses reviewed protected routes without a public roster', async () => {
  const schema = JSON.parse(await read('docs/backend/openapi.json'));
  for (const [suffix, method] of [['', 'get'], ['/history', 'get'], ['/session', 'post'], ['/registrations/{registration_id}', 'put']]) {
    assert.ok(schema.paths[`/api/v1/events/{event_id}/attendance${suffix}`]?.[method]);
  }
  const out = schema.components.schemas.AttendanceOut.properties;
  assert.ok(out.version && out.writable && out.attendees && out.checked_in_count);
  const publicEvent = schema.components.schemas.EventPublic.properties;
  assert.equal(publicEvent.attendees, undefined);
  assert.equal(publicEvent.attendance, undefined);
});

test('attendance is integrated in both existing staff workspaces, not attendee navigation', async () => {
  const workspace = await read('Code/Frontend/features/organizations/workspace-page.tsx');
  assert.equal([...workspace.matchAll(/<AttendancePanel\b/g)].length, 2);
  const shell = await read('Code/Frontend/components/application-shell.tsx');
  assert.doesNotMatch(shell, /AttendancePanel|attendance\/session/);
  const migration = await read('Code/Backend/migrations/versions/mvp_0016_attendance.py');
  assert.match(migration, /down_revision = 'mvp_0015'/);
  assert.match(migration, /Attendance data exists; preserve it before downgrading/);
  assert.doesNotMatch(migration, /add_column|drop_column|UPDATE registrations/);
});

test('confirmed attendees can present their own matching registration reference without a roster', async () => {
  for (const path of ['MyEvents.tsx', 'RegistrationAction.tsx']) {
    const source = await read(`Code/Frontend/features/registrations/${path}`);
    assert.match(source, /Registration reference: \{reference\}/);
    assert.match(source, /overflowWrap: 'anywhere'/);
    assert.doesNotMatch(source, /\/attendance\/history|\/attendance\/session/);
  }
});
