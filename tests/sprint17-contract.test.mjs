import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');

test('planning API uses caller-scoped paths and keeps its own event projection schema', async () => {
  const contract = JSON.parse(await read('docs/backend/openapi.json'));
  for (const path of ['/api/v1/me/saved-events', '/api/v1/me/saved-events/{event_id}', '/api/v1/me/event-conflicts/{event_id}']) {
    assert.ok(contract.paths[path], path);
  }
  const saved = contract.components.schemas.SavedEventOut.properties;
  assert.ok(saved.event_id && saved.saved_at && saved.event);
  assert.equal(saved.event.anyOf.find(item => item.$ref)?.$ref, '#/components/schemas/EventPublic');
  assert.ok(!saved.user_id && !saved.email && !saved.nickname);
});

test('planning stays within existing attendee destinations and confirmation behavior', async () => {
  const detail = await read('Code/Frontend/features/events/EventDetail.tsx');
  const action = await read('Code/Frontend/features/registrations/RegistrationAction.tsx');
  const header = await read('Code/Frontend/app/site-header.tsx');
  assert.match(detail, /SaveEventButton/);
  assert.match(detail, /ConflictWarning/);
  assert.match(action, /ConflictWarning/);
  assert.match(action, /idempotencyKey: savedAttempt.key/);
  assert.match(action, /Confirm your registration/);
  assert.doesNotMatch(header, /href=["']\/(saved|calendar)/);
});
