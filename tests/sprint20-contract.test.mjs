import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');

test('ownership routes and strict request schemas are in the reviewed API contract', async () => {
  const schema = JSON.parse(await read('docs/backend/openapi.json'));
  const collection = schema.paths['/api/v1/organizations/{org_id}/ownership-transfers'];
  assert.ok(collection.get);
  assert.ok(collection.post.responses['201']);
  assert.ok(schema.paths['/api/v1/organizations/{org_id}/ownership-transfers/{transfer_id}/decision'].post);
  for (const name of ['OwnershipTransferCreate', 'OwnershipTransferDecision']) {
    assert.equal(schema.components.schemas[name].additionalProperties, false);
  }
  assert.deepEqual(Object.keys(schema.components.schemas.OwnershipTransferCreate.properties).sort(), ['client_key', 'nominee_id']);
  const decision = schema.components.schemas.OwnershipTransferDecision;
  assert.deepEqual(decision.properties.action.enum, ['accept', 'decline', 'revoke']);
  assert.equal(decision.properties.version.minimum, 1);
  const output = schema.components.schemas.OwnershipTransferOut.properties;
  assert.ok(output.from_user_id && output.nominee_id && output.expires_at);
  assert.equal(output.client_key, undefined);
  assert.equal(output.email, undefined);
});

test('ownership is additive and cannot silently discard transfer history', async () => {
  const migration = await read('Code/Backend/migrations/versions/mvp_0015_ownership.py');
  assert.match(migration, /down_revision = 'mvp_0014'/);
  assert.match(migration, /uq_org_memberships_active_owner/);
  assert.match(migration, /Multiple active owners exist/);
  assert.match(migration, /transfer history exists/);
  assert.doesNotMatch(migration, /UPDATE organizations|UPDATE org_memberships|drop_column/);
});

test('workspace refreshes authoritative grants after ownership changes without new navigation', async () => {
  const workspace = await read('Code/Frontend/features/organizations/workspace-page.tsx');
  assert.match(workspace, /<OwnershipTransferPanel/);
  assert.match(workspace, /onOwnershipChanged=\{async \(\) => \{\s*organizations\.reload\(\);\s*workspace\.reload\(\);\s*events\.reload\(\);\s*await refreshActor\(\);/);
  const shell = await read('Code/Frontend/components/application-shell.tsx');
  assert.doesNotMatch(shell, /ownership-transfers|OwnershipTransferPanel/);
});

test('mutation refresh is queued behind an existing read and recovered accepts refresh roles', async () => {
  const panel = await read('Code/Frontend/features/ownership/OwnershipTransferPanel.tsx');
  assert.match(panel, /if \(fetching\) \{\s*refreshQueued = true;\s*return;/);
  assert.match(panel, /finally \{\s*fetching = false;\s*if \(refreshQueued && !disposed && !stopped\)/);
  const createResult = panel.slice(panel.indexOf('async function submitOffer'), panel.indexOf('function reviewLatestOffer'));
  assert.match(createResult, /notifyRoleRefresh\(result\)/);
  assert.match(createResult, /result\.status === 'accepted'/);
});
