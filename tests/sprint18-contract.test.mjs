import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');

test('Sprint 18 adds explicit local persona and block endpoints, not a user directory', async () => {
  const contract = JSON.parse(await read('docs/backend/openapi.json'));
  for (const path of [
    '/api/v1/events/{event_id}/personas/{user_id}',
    '/api/v1/events/{event_id}/persona-visibility',
    '/api/v1/events/{event_id}/blocks/{user_id}',
    '/api/v1/me/blocks', '/api/v1/me/blocks/{user_id}',
    '/api/v1/events/{event_id}/registration-block-warning',
  ]) assert.ok(contract.paths[path], path);
  assert.equal(contract.paths['/api/v1/users'], undefined);
  const input = contract.components.schemas.RegistrationInput.properties;
  assert.equal(input.blocked_attendee_acknowledged.type, 'boolean');
  assert.equal(input.blocked_attendee_acknowledged.default, false);
});

test('Sprint 18 migration follows Sprint 19 and refuses destructive privacy rollback', async () => {
  const migration = await read('Code/Backend/migrations/versions/mvp_0014_personas.py');
  assert.match(migration, /down_revision = 'mvp_0013'/);
  assert.match(migration, /'user_blocks'/);
  assert.match(migration, /'event_persona_visibility'/);
  assert.match(migration, /blocked_attendee_acknowledged/);
  assert.match(migration, /preserve them before downgrading/);
  assert.doesNotMatch(migration, /DROP DATABASE|TRUNCATE|UPDATE users/i);
});
