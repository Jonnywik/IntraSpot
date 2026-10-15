// Sprint 2 live demonstration only: additive fictional records, no reset or registrations.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '../..');
const base = 'http://127.0.0.1:8001';
const args = process.argv.slice(2);
assert.ok(args.length === 1 && ['before', 'after'].includes(args[0]), 'Use before or after only');
const phase = args[0];
const snapshotFile = path.join(root, 'Code/Backend/.local/phase2-restart.json');
const outputFile = path.join(root, 'docs/validation/phase2-live-results.json');
const checks = [];
function passed(check) { checks.push({ check, pass: true }); }

async function request(route, { token, method = 'GET', body, expected = 200 } = {}) {
  const response = await fetch(`${base}${route}`, {
    method,
    signal: AbortSignal.timeout(20000),
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const json = await response.json();
  const allowed = Array.isArray(expected) ? expected : [expected];
  assert.ok(allowed.includes(response.status), `${method} ${route.replace(/[a-f0-9-]{36}/g, '{id}')} returned ${response.status}, expected ${allowed}`);
  if (response.status >= 400) assert.ok(json.error?.code && json.error?.message && json.request_id, 'Sanitized error contract required');
  return json;
}
const api = (route, options) => request(`/api/v1${route}`, options);
const health = await request('/health');
assert.equal(health.environment, 'local', 'This checker only runs against the explicitly local API');
assert.equal((await request('/ready')).status, 'ready');
const manifest = JSON.parse(await readFile(path.join(root, 'Code/Backend/.local/accounts.json'), 'utf8'));
function account(label) {
  const token = manifest.find(row => row.label === label)?.token;
  assert.ok(token, 'Expected fixed fictional identity is missing');
  return token;
}
const owner = account('Fictional organizer');
const admin = account('Fictional platform admin');
const outsider = account('Fictional student 10');
const visitor = account('Fictional visitor (not PLM)');
const adminActor = await api('/me', { token: admin });
assert.ok(adminActor.eligible && adminActor.platform_admin, 'Predefined admin must retain verified database privileges');
passed('Local health, migration readiness and trusted fictional admin');

if (phase === 'before') {
  const tag = randomUUID().slice(0, 8);
  const create = name => api('/organizations', { token: owner, method: 'POST', body: { name: `Fictional Sprint 2 ${name} ${tag}`, description: 'Local accreditation demonstration, not a real organization.' }, expected: 201 });
  await api('/organizations', { method: 'POST', body: { name: 'Fictional denied application' }, expected: 401 });
  await api('/organizations', { token: visitor, method: 'POST', body: { name: 'Fictional denied application' }, expected: 403 });
  await api('/platform-admin/organizations', { token: owner, expected: 403 });
  const approved = await create('approval');
  assert.equal(approved.accreditation_status, 'pending');
  const initial = await api(`/organizations/${approved.id}/workspace`, { token: owner });
  assert.equal(initial.role, 'owner');
  assert.deepEqual(initial.decisions, []);
  const grant = (await api('/me/organizations', { token: owner })).grants.find(row => row.org_id === approved.id);
  assert.equal(grant?.role, 'owner');
  assert.equal(grant?.accreditation_status, 'pending');
  passed('Eligible application atomically yields pending organization and owner grant');

  const publicOrg = await api(`/organizations/${approved.id}`);
  assert.deepEqual(Object.keys(publicOrg).sort(), ['id', 'name', 'description', 'accreditation_status', 'created_at'].sort());
  await api(`/organizations/${approved.id}/workspace`, { expected: 401 });
  await api(`/organizations/${approved.id}/workspace`, { token: outsider, expected: 403 });
  await api(`/organizations/${approved.id}/workspace`, { token: visitor, expected: 403 });
  passed('Public organization projection is private-data-free; private workspace is isolated');

  const draft = await api(`/organizations/${approved.id}/events`, { token: owner, method: 'POST', body: { title: `Fictional incomplete draft ${tag}` }, expected: 201 });
  assert.equal(draft.status, 'draft');
  assert.equal(draft.starts_at, null);
  await api(`/events/${draft.id}/draft`, { token: owner, method: 'PATCH', body: { description: 'Fictional private preview' } });
  await api(`/events/${draft.id}/draft`, { token: owner });
  await api(`/events/${draft.id}`, { expected: 404 });
  await api(`/events/${draft.id}/draft`, { expected: 401 });
  await api(`/events/${draft.id}/draft`, { token: outsider, expected: 403 });
  await api(`/events/${draft.id}/publish`, { token: owner, method: 'POST', expected: 403 });
  passed('Pending incomplete draft saves/previews privately but cannot publish');

  const decisionRoute = `/platform-admin/organizations/${approved.id}/accreditation-decision`;
  await api(decisionRoute, { token: owner, method: 'POST', body: { outcome: 'approved' }, expected: 403 });
  await api(decisionRoute, { token: admin, method: 'POST', body: { outcome: 'approved', admin_id: 'spoofed', decided_at: '2000-01-01T00:00:00Z' }, expected: 422 });
  const race = await Promise.all(['approved', 'rejected'].map(outcome => api(decisionRoute, { token: admin, method: 'POST', body: { outcome }, expected: [200, 409] })));
  assert.equal(race.filter(row => row.error?.code === 'accreditation_decision_closed').length, 1);
  let terminal = await api(`/organizations/${approved.id}/workspace`, { token: owner });
  assert.equal(terminal.decisions.length, 1);
  assert.equal(terminal.decisions[0].admin_id, adminActor.id);
  assert.equal(terminal.decisions[0].outcome, terminal.accreditation_status);
  assert.ok(/(?:Z|\+00:00)$/.test(terminal.decisions[0].decided_at));
  assert.ok(Math.abs(Date.now() - Date.parse(terminal.decisions[0].decided_at)) < 60000);
  passed('Conflicting concurrent decisions yield one audited terminal result and one controlled conflict');

  // Race winner is intentionally nondeterministic; use a separate approval when rejection won.
  let publishOrg = approved;
  let publishDraft = draft;
  if (terminal.accreditation_status === 'rejected') {
    publishOrg = await create('approved boundary');
    publishDraft = await api(`/organizations/${publishOrg.id}/events`, { token: owner, method: 'POST', body: {}, expected: 201 });
    await api(`/platform-admin/organizations/${publishOrg.id}/accreditation-decision`, { token: admin, method: 'POST', body: { outcome: 'approved' } });
  }
  await api(`/events/${publishDraft.id}/draft`, { token: owner, method: 'PATCH', body: {
    title: `Fictional approval boundary ${tag}`, description: 'Sprint 2 publishing authorization boundary only.',
    starts_at: new Date(Date.now() + 86400000).toISOString(), ends_at: new Date(Date.now() + 90000000).toISOString(),
    venue_name: 'Fictional campus venue', venue_address: 'Fictional local address', capacity: 3, banner_key: 'heritage',
  } });
  await api(`/events/${publishDraft.id}/publish`, { token: owner, method: 'POST' });
  await api(`/events/${publishDraft.id}`);
  passed('Approved organization enables existing publishing boundary (not Sprint 3 acceptance)');

  const rejected = await create('rejection');
  const rejectedDraft = await api(`/organizations/${rejected.id}/events`, { token: owner, method: 'POST', body: { title: `Fictional rejected draft ${tag}` }, expected: 201 });
  await api(`/platform-admin/organizations/${rejected.id}/accreditation-decision`, { token: admin, method: 'POST', body: { outcome: 'rejected' } });
  await api(`/platform-admin/organizations/${rejected.id}/accreditation-decision`, { token: admin, method: 'POST', body: { outcome: 'approved' }, expected: 409 });
  await api(`/organizations/${rejected.id}/workspace`, { token: owner });
  await api(`/events/${rejectedDraft.id}/draft`, { token: owner });
  await api(`/organizations/${rejected.id}/events`, { token: owner, method: 'POST', body: {}, expected: 409 });
  await api(`/events/${rejectedDraft.id}/draft`, { token: owner, method: 'PATCH', body: { title: 'Forbidden change' }, expected: 409 });
  await api(`/events/${rejectedDraft.id}/publish`, { token: owner, method: 'POST', expected: 403 });
  assert.equal((await api(`/events/${rejectedDraft.id}/draft`, { token: owner })).title, rejectedDraft.title);
  passed('Rejected application is terminal and private drafts are readable but immutable');

  const memberships = await api('/me/organizations', { token: account('Fictional faculty') });
  assert.ok(memberships.grants.some(row => row.org_name.startsWith('Fictional Phase 2') && row.role === 'member'), 'Faculty needs an active fixed fictional club membership');
  assert.ok(memberships.owned_workspaces.every(row => ['owner', 'admin'].includes(row.role)));
  passed('Fixed fictional faculty memberships appear without management access');
  const ids = [...new Set([approved.id, publishOrg.id, rejected.id])];
  const workspaces = await Promise.all(ids.map(id => api(`/organizations/${id}/workspace`, { token: owner })));
  const rejectedPreview = await api(`/events/${rejectedDraft.id}/draft`, { token: owner });
  await writeFile(snapshotFile, JSON.stringify({ instance_id: health.instance_id, workspaces, rejectedPreview, checks }, null, 2));
  await writeFile(outputFile, JSON.stringify({ date: new Date().toISOString(), method: 'Live loopback HTTP checks; fictional data only; not participant testing', phase: 'before restart', checks }, null, 2));
  console.log(JSON.stringify({ phase, checks: checks.length, pass: true, note: 'Additive fictional organizations/drafts retained for restart verification; no credentials logged.' }));
} else {
  const before = JSON.parse(await readFile(snapshotFile, 'utf8'));
  assert.notEqual(health.instance_id, before.instance_id, 'A distinct backend instance is required');
  for (const old of before.workspaces) {
    assert.deepEqual(await api(`/organizations/${old.id}/workspace`, { token: owner }), old, 'Organization/role/decision persisted unchanged');
  }
  assert.deepEqual(await api(`/events/${before.rejectedPreview.id}/draft`, { token: owner }), before.rejectedPreview, 'Private draft persisted unchanged');
  passed('Backend restart preserves organizations, owner grants, audit decisions and private drafts');
  await writeFile(outputFile, JSON.stringify({ date: new Date().toISOString(), method: 'Independent live loopback HTTP checks and distinct-instance restart; no participant testing', phase: 'complete', checks: [...before.checks, ...checks.filter(row => row.check !== before.checks[0].check)] }, null, 2));
  console.log(JSON.stringify({ phase, restart: 'pass', note: 'Durable Sprint 2 records verified; credentials not logged.' }));
}
