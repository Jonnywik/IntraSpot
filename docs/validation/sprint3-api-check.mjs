// Additive fictional Sprint 3 HTTP demonstration. No resets or registration writes.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '../..');
const base = 'http://127.0.0.1:8001';
const phase = process.argv[2];
assert.ok(process.argv.length === 3 && ['before', 'after'].includes(phase), 'Use before or after only');
const snapshotFile = path.join(root, 'Code/Backend/.local/sprint3-restart.json');
const resultsFile = path.join(root, 'docs/validation/sprint3-live-results.json');
const checks = [];
const pass = check => checks.push({ check, pass: true });
async function request(route, { token, method = 'GET', body, expected = 200, idempotencyKey } = {}) {
  const response = await fetch(`${base}${route}`, {
    method, signal: AbortSignal.timeout(20000),
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const json = await response.json();
  assert.equal(response.status, expected, `${method} ${route.replace(/[a-f0-9-]{36}/g, '{id}')} returned ${response.status}, expected ${expected}`);
  if (expected >= 400) assert.ok(json.error?.code && json.error?.message && json.request_id);
  return json;
}
const api = (route, options) => request(`/api/v1${route}`, options);
const health = await request('/health');
assert.equal(health.environment, 'local', 'This checker only accepts the explicitly local API');
assert.equal((await request('/ready')).status, 'ready');
const accounts = JSON.parse(await readFile(path.join(root, 'Code/Backend/.local/accounts.json'), 'utf8'));
function token(label) {
  const value = accounts.find(row => row.label === label)?.token;
  assert.ok(value, 'Predefined fictional account is missing');
  return value;
}
const owner = token('Fictional student 4');
const pendingOwner = token('Fictional organizer');
const member = token('Fictional faculty');
const outsider = token('Fictional student 10');
const visitor = token('Fictional visitor (not PLM)');
const actor = await api('/me', { token: owner });
assert.ok(actor.eligible);
pass('Local health, readiness and verified fictional identities');

if (phase === 'before') {
  const grant = actor.grants.find(row => row.org_name === 'Fictional Phase 2 Approved Organization');
  assert.equal(grant?.role, 'owner');
  assert.equal(grant?.accreditation_status, 'approved');
  const tag = randomUUID().slice(0, 8);
  const pendingOrg = await api('/organizations', { token: pendingOwner, method: 'POST', body: {
    name: `Fictional Sprint 3 Pending ${tag}`, description: 'Local demonstration only.',
  }, expected: 201 });
  const pending = await api(`/organizations/${pendingOrg.id}/events`, {
    token: pendingOwner, method: 'POST', body: {}, expected: 201,
  });
  assert.equal(pending.status, 'draft');
  assert.equal(pending.title, null);
  assert.equal(pending.summary, '');
  await api(`/events/${pending.id}/draft`, { token: pendingOwner, method: 'PATCH', body: { title: `Fictional private ${tag}` } });
  const pendingPreview = await api(`/events/${pending.id}/draft`, { token: pendingOwner });
  await api(`/events/${pending.id}/publish`, { token: pendingOwner, method: 'POST', expected: 403 });
  await api(`/events/${pending.id}`, { expected: 404 });
  await api(`/events/${pending.id}/draft`, { expected: 401 });
  await api(`/events/${pending.id}/draft`, { token: outsider, expected: 403 });
  assert.deepEqual(await api(`/events?q=${encodeURIComponent(`Fictional private ${tag}`)}`), []);
  pass('Incomplete pending drafts save privately and cannot publish or leak into discovery');

  const create = body => api(`/organizations/${grant.org_id}/events`, { token: owner, method: 'POST', body, expected: 201 });
  const incomplete = await create({ title: `Fictional incomplete approved ${tag}` });
  const invalid = await api(`/events/${incomplete.id}/publish`, { token: owner, method: 'POST', expected: 422 });
  assert.equal(invalid.error.code, 'event_fields_required');
  await api(`/events/${incomplete.id}/draft`, { token: owner, method: 'PATCH', body: { starts_at: '2030-01-01T10:00:00' }, expected: 422 });
  await api(`/events/${incomplete.id}/draft`, { token: owner, method: 'PATCH', body: { capacity: 0 }, expected: 422 });
  await api(`/events/${incomplete.id}/draft`, { token: owner, method: 'PATCH', body: { banner_key: 'remote-upload' }, expected: 422 });
  await api(`/events/${incomplete.id}/draft`, { token: owner, method: 'PATCH', body: { event_type: 'flash' }, expected: 422 });
  pass('Approved publishing still requires complete valid scheduled/instant event data');

  const fields = day => ({
    description: 'Fictional local event, not an actual campus activity.',
    starts_at: new Date(Date.now() + day * 86400000).toISOString(),
    ends_at: new Date(Date.now() + day * 86400000 + 7200000).toISOString(),
    venue_name: `Fictional unsearchable venue ${tag}`, venue_address: 'Fictional address, Manila',
    capacity: 3, banner_key: 'heritage', cost_label: 'Informational: fictional free admission',
  });
  const later = await create({ title: `Fictional Sprint3 ${tag} 100% workshop`, ...fields(3) });
  const earlier = await create({ title: `Fictional Sprint3 ${tag} design_session`, ...fields(2) });
  const publishedEarlier = await api(`/events/${earlier.id}/publish`, { token: owner, method: 'POST' });
  const publishedLater = await api(`/events/${later.id}/publish`, { token: owner, method: 'POST' });
  const publicFields = ['id', 'org_id', 'organization_name', 'title', 'summary', 'description', 'starts_at', 'ends_at', 'venue_name', 'venue_address', 'capacity', 'confirmed_count', 'remaining_spots', 'interest_count', 'banner_key', 'cost_label', 'status', 'published_at'];
  for (const event of [publishedLater, publishedEarlier]) {
    assert.deepEqual(Object.keys(event).sort(), publicFields.sort());
    assert.equal(event.summary, '');
    assert.equal(event.status, 'published');
    assert.equal(event.confirmed_count, 0);
    assert.equal(event.remaining_spots, 3);
    assert.equal(event.interest_count, 0);
    assert.ok(/(?:Z|\+00:00)$/.test(event.starts_at));
    assert.ok(/(?:Z|\+00:00)$/.test(event.published_at));
    assert.deepEqual(await api(`/events/${event.id}`), event);
  }
  pass('Approved publishing returns safe public details, empty optional summary and separate seat/reaction counts');

  const q = `Fictional Sprint3 ${tag}`;
  const search = params => api(`/events?${new URLSearchParams(params)}`);
  const upcoming = await search({ q });
  assert.deepEqual(upcoming.map(row => row.id), [earlier.id, later.id]);
  assert.deepEqual((await search({ q, sort: 'newest' })).map(row => row.id), [later.id, earlier.id]);
  assert.deepEqual((await search({ q: `${tag} 100%` })).map(row => row.id), [later.id]);
  assert.deepEqual((await search({ q: `${tag} design_` })).map(row => row.id), [earlier.id]);
  assert.deepEqual(await search({ q: `Fictional unsearchable venue ${tag}` }), []);
  const orgResults = await search({ q: grant.org_name.toLowerCase() });
  assert.ok(orgResults.some(row => row.id === later.id) && orgResults.some(row => row.id === earlier.id));
  pass('Guest discovery searches literal titles and organization names, not venues; Upcoming/Newest compose');

  const clubRoute = `/events?${new URLSearchParams({ q, my_clubs: 'true', sort: 'newest' })}`;
  assert.deepEqual((await api(clubRoute, { token: member })).map(row => row.id), [later.id, earlier.id]);
  assert.deepEqual(await api(clubRoute, { token: outsider }), []);
  await api(clubRoute, { expected: 401 });
  await api(clubRoute, { token: visitor, expected: 403 });
  pass('Faculty My Clubs composes with search/sort; guests, ineligible accounts and nonmembers remain bounded');

  await api(`/events/${later.id}/draft`, { token: owner, method: 'PATCH', body: { capacity: 4 }, expected: 409 });
  await api(`/events/${later.id}/publish`, { token: owner, method: 'POST', expected: 409 });
  await api(`/events/${later.id}`, { token: owner, method: 'DELETE', expected: 405 });
  await api(`/events/${later.id}/draft`, { token: outsider, expected: 403 });
  assert.deepEqual(await api(`/events/${later.id}`), publishedLater);
  pass('Published events stay immutable; unsupported cancellation and cross-organization private access are denied');

  const approvedDraft = await api(`/events/${incomplete.id}/draft`, { token: owner });
  await writeFile(snapshotFile, JSON.stringify({ instance_id: health.instance_id, checks, published: [publishedLater, publishedEarlier], approvedDraft, pendingPreview }, null, 2));
  await writeFile(resultsFile, JSON.stringify({ date: new Date().toISOString(), method: 'Live loopback HTTP, fictional local data only; not participant testing', phase: 'before restart', checks }, null, 2));
  console.log(JSON.stringify({ phase, checks: checks.length, pass: true, note: 'Fictional event records retained; no credentials logged.' }));
} else {
  const before = JSON.parse(await readFile(snapshotFile, 'utf8'));
  assert.notEqual(health.instance_id, before.instance_id, 'A distinct backend instance is required');
  for (const event of before.published) assert.deepEqual(await api(`/events/${event.id}`), event);
  assert.deepEqual(await api(`/events/${before.approvedDraft.id}/draft`, { token: owner }), before.approvedDraft);
  assert.deepEqual(await api(`/events/${before.pendingPreview.id}/draft`, { token: pendingOwner }), before.pendingPreview);
  pass('Distinct-instance backend restart preserves published event fields/counts and incomplete private drafts');
  await api(`/events/${before.approvedDraft.id}/draft`, { token: owner, method: 'PATCH', body: { capacity: 2147483648 }, expected: 422 });
  assert.deepEqual(await api(`/events/${before.approvedDraft.id}/draft`, { token: owner }), before.approvedDraft);
  pass('Final source rejects capacity beyond PostgreSQL integer storage with a controlled error and no draft mutation');
  const draftAttempt = await api(`/events/${before.approvedDraft.id}/registrations`, {
    token: member, method: 'POST', idempotencyKey: 'private-draft-live-check', expected: 404,
  });
  assert.equal(draftAttempt.error.code, 'event_not_found');
  assert.deepEqual(await api(`/events/${before.approvedDraft.id}/draft`, { token: owner }), before.approvedDraft);
  pass('Final live API denies registration against a private draft without changing its public visibility or private fields');
  await writeFile(resultsFile, JSON.stringify({ date: new Date().toISOString(), method: 'Live loopback HTTP plus distinct-instance restart; not participant testing', phase: 'complete', checks: [...before.checks, ...checks.slice(1)] }, null, 2));
  console.log(JSON.stringify({ phase, restart: 'pass', pass: true, note: 'Durable Sprint 3 records verified without credentials in output.' }));
}
