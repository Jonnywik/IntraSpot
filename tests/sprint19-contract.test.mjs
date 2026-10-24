import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');

test('Featured routes are included in the reviewed API contract, not a frontend-only label', async () => {
  const schema = JSON.parse(await read('docs/backend/openapi.json'));
  for (const [path, method] of [
    ['/api/v1/events/{event_id}/featured-requests', 'post'],
    ['/api/v1/organizations/{org_id}/featured-requests', 'get'],
    ['/api/v1/platform-admin/featured-requests', 'get'],
    ['/api/v1/platform-admin/featured-requests/{request_id}/decisions', 'post'],
  ]) assert.ok(schema.paths[path]?.[method], path);
  assert.equal(schema.components.schemas.EventPublic.properties.is_featured.type, 'boolean');
  assert.equal(schema.components.schemas.MyRegistration.properties.is_featured.type, 'boolean');
  assert.ok(schema.components.schemas.FeaturedRequestOut);
});

test('Existing event surfaces consume the authoritative badge field without sorting by it', async () => {
  for (const file of ['features/events/DiscoverFeed.tsx', 'features/events/EventDetail.tsx',
    'features/registrations/MyEvents.tsx', 'features/planning/SavedEvents.tsx']) {
    const source = await read(`Code/Frontend/${file}`);
    assert.match(source, /is_featured/);
    assert.match(source, /FeaturedBadge/);
  }
  const discover = await read('Code/Frontend/features/events/DiscoverFeed.tsx');
  assert.doesNotMatch(discover, /\.sort\([^;]*is_featured/);
  const shell = await read('Code/Frontend/components/application-shell.tsx');
  assert.doesNotMatch(shell, /featured-requests/);
});

test('Native PostgreSQL exclusion is additive and downgrade refuses feature history loss', async () => {
  const migration = await read('Code/Backend/migrations/versions/mvp_0013_featured.py');
  assert.match(migration, /down_revision = 'mvp_0012'/);
  assert.match(migration, /create_exclude_constraint/);
  assert.match(migration, /tstzrange/);
  assert.match(migration, /preserve it before downgrading/);
  assert.doesNotMatch(migration, /CREATE EXTENSION|drop_column|drop_table\('events'/i);
});
