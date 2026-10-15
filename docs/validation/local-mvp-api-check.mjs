// Independent live API journeys. Creates only explicitly fictional local demo data.
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

const args = process.argv.slice(2);
const base = args.find(x => x.startsWith('--base='))?.slice(7) || 'http://127.0.0.1:8001';
const accountsFile = args.find(x => x.startsWith('--accounts='))?.slice(11);
const origin = new URL(base);
assert.equal(origin.protocol, 'http:');
assert.ok(['127.0.0.1', 'localhost'].includes(origin.hostname), 'This checker may only contact loopback services');
if (args.includes('--self-test')) {
  assert.equal(new URL('/api/v1/events', base).hostname, origin.hostname);
  console.log('API QA local-origin self-check passed');
  process.exit(0);
}
assert.ok(accountsFile, 'Supply --accounts=<ignored local demo-account manifest>');
const raw = JSON.parse(await readFile(accountsFile, 'utf8'));
const records = Array.isArray(raw) ? raw : Array.isArray(raw.accounts) ? raw.accounts : Object.values(raw.accounts || raw);
const tokens = [...new Set(records.map(r => typeof r === 'string' ? r : r.token || r.access_token).filter(Boolean))];
const evidence = [];
async function api(route, { token, method = 'GET', body, key, expected = 200 } = {}) {
  const response = await fetch(new URL(`/api/v1${route}`, base), {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(key ? { 'Idempotency-Key': key } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const json = await response.json();
  const allowed = Array.isArray(expected) ? expected : [expected];
  assert.ok(allowed.includes(response.status), `${method} ${route.replace(/[a-f0-9-]{36}/g, '{id}')} returned ${response.status}, expected ${allowed}`);
  if (response.status >= 400) assert.ok(json.error?.code && json.error?.message, 'Stable machine-readable error required');
  return json;
}
const actors = [];
for (const token of tokens) {
  const actor = await api('/me', { token });
  actors.push({ token, ...actor });
}
const admin = actors.find(a => a.platform_admin);
const eligible = actors.filter(a => a.eligible && !a.platform_admin);
assert.ok(admin && eligible.length >= 3, 'Need one fictional platform admin and at least three fictional eligible accounts');
const [owner, ...others] = eligible;
const attendeePool = [owner, ...others].slice(0, 10);
for (const actor of attendeePool) {
  if (!actor.profile_complete) await api('/me/profile', { token: actor.token, method: 'PATCH', body: { nickname: 'Fictional MVP attendee', age_bracket: '18-24', tags: ['community'] } });
}
await api('/me', { expected: 401 });
await api('/me', { token: 'invalid.local.token', expected: 401 });
await api('/me/profile', { token: owner.token, method: 'PATCH', body: { platform_admin: true }, expected: 422 });
assert.equal((await api('/me', { token: owner.token })).platform_admin, false);
const ineligible = actors.find(a => !a.eligible);
evidence.push({ check: 'anonymous/invalid token and profile privilege escalation rejected', pass: true });

const tag = randomUUID().slice(0, 8);
const organization = await api('/organizations', { token: owner.token, method: 'POST', body: { name: `Fictional MVP club ${tag}`, description: 'Independent local verification fixture, not a real organization.' }, expected: [200, 201] });
assert.equal(organization.accreditation_status, 'pending');
await api(`/organizations/${organization.id}/workspace`, { token: others[0].token, expected: [403, 404] });
const start = new Date(Date.now() + 86400000).toISOString();
const end = new Date(Date.now() + 90000000).toISOString();
const capacity = attendeePool.length === 10 ? 3 : 1;
const draft = await api(`/organizations/${organization.id}/events`, {
  token: owner.token, method: 'POST', expected: [200, 201], body: {
    title: `Fictional verification event ${tag}`, description: 'Local test event for capacity and permission checks.',
    starts_at: start, ends_at: end, venue_name: `Unique fixture venue ${tag}`,
    venue_address: 'Fictional local fixture address', capacity, banner_key: 'heritage', cost_label: 'Free',
  },
});
await api(`/events/${draft.id}`, { expected: 404 });
await api(`/events/${draft.id}/publish`, { token: owner.token, method: 'POST', expected: [403, 409] });
await api(`/platform-admin/organizations/${organization.id}/accreditation-decision`, { token: owner.token, method: 'POST', body: { outcome: 'approved' }, expected: 403 });
await api(`/platform-admin/organizations/${organization.id}/accreditation-decision`, { token: admin.token, method: 'POST', body: { outcome: 'approved' }, expected: [200, 201] });
const workspace = await api(`/organizations/${organization.id}/workspace`, { token: owner.token });
assert.equal(workspace.accreditation_status, 'approved');
assert.ok(workspace.decisions.some(d => d.admin_id === admin.id && d.outcome === 'approved' && Date.parse(d.decided_at)));
await api(`/events/${draft.id}/publish`, { token: owner.token, method: 'POST', expected: [200, 201] });
await api(`/events/${draft.id}/draft`, { token: owner.token, method: 'PATCH', body: { capacity: capacity + 1 }, expected: [403, 409] });
const detail = await api(`/events/${draft.id}`);
assert.equal(detail.confirmed_count, 0);
assert.equal(detail.remaining_spots, capacity);
const publicJson = JSON.stringify(detail);
assert.ok(!/"(?:email|tags|pronouns|icebreaker|user_id|created_by)"/.test(publicJson), 'Public event must not expose private identity fields');
assert.ok((await api(`/events?q=${encodeURIComponent(organization.name)}`)).some(e => e.id === draft.id));
assert.deepEqual(await api(`/events?q=${encodeURIComponent(`Unique fixture venue ${tag}`)}`), []);
assert.ok((await api(`/events?q=${tag}&my_clubs=true`, { token: owner.token })).some(e => e.id === draft.id));
await api('/events?my_clubs=true', { expected: [401, 403] });
evidence.push({ check: 'pending draft/private preview → admin approval audit → publication → guest discovery and My Clubs', pass: true });
if (ineligible) await api(`/events/${draft.id}/registrations`, { token: ineligible.token, method: 'POST', key: randomUUID(), expected: 403 });

const attempts = attendeePool.map(actor => ({ actor, key: randomUUID() }));
const results = await Promise.all(attempts.map(async attempt => ({
  ...attempt,
  result: await api(`/events/${draft.id}/registrations`, { token: attempt.actor.token, method: 'POST', key: attempt.key, expected: [200, 201] }),
})));
const confirmed = results.filter(r => r.result.status === 'confirmed');
const waitlisted = results.filter(r => r.result.status === 'waitlisted').sort((a, b) => a.result.admission_order - b.result.admission_order);
assert.equal(confirmed.length, capacity);
assert.equal(waitlisted.length, attendeePool.length - capacity);
assert.ok(waitlisted.every(r => r.result.waitlist_position > 0 && /no estimated wait time/i.test(r.result.waitlist_message)));
const afterRace = await api(`/events/${draft.id}`);
assert.equal(afterRace.confirmed_count, capacity);
assert.equal(afterRace.remaining_spots, 0);
for (const item of results) {
  assert.deepEqual(await api(`/events/${draft.id}/registrations`, { token: item.actor.token, method: 'POST', key: item.key, expected: [200, 201] }), item.result);
  const own = await api('/me/registrations', { token: item.actor.token });
  assert.ok(own.some(r => r.id === item.result.id && r.event_id === draft.id));
}
const first = confirmed[0];
const duplicate = await api(`/events/${draft.id}/registrations`, { token: first.actor.token, method: 'POST', key: randomUUID(), expected: [200, 201] });
assert.equal(duplicate.id, first.result.id);
await api(`/events/${draft.id}/registrations/me`, { token: first.actor.token, method: 'DELETE' });
await api(`/events/${draft.id}/registrations/me`, { token: first.actor.token, method: 'DELETE' });
const promoted = waitlisted[0];
const current = await api('/me/registrations', { token: promoted.actor.token });
assert.equal(current.find(r => r.id === promoted.result.id).status, 'confirmed');
assert.deepEqual(await api(`/events/${draft.id}/registrations`, { token: promoted.actor.token, method: 'POST', key: promoted.key, expected: [200, 201] }), promoted.result);
const notifications = await api('/me/notifications', { token: promoted.actor.token });
assert.equal(notifications.filter(n => n.event_id === draft.id && n.kind === 'waitlist_promoted').length, 1);
assert.equal((await api(`/events/${draft.id}`)).confirmed_count, capacity);
evidence.push({ check: 'concurrent capacity, same/different-key retries, My Events, FIFO promotion and one notification', pass: true, attempts: attendeePool.length, capacity });

const rejected = await api('/organizations', { token: owner.token, method: 'POST', body: { name: `Fictional rejected club ${tag}` }, expected: [200, 201] });
await api(`/platform-admin/organizations/${rejected.id}/accreditation-decision`, { token: admin.token, method: 'POST', body: { outcome: 'rejected' }, expected: [200, 201] });
await api(`/platform-admin/organizations/${rejected.id}/accreditation-decision`, { token: admin.token, method: 'POST', body: { outcome: 'approved' }, expected: [403, 409] });
evidence.push({ check: 'rejection is terminal and recorded, not an invented appeal', pass: true });
const out = path.resolve('docs/validation/local-mvp-api-evidence');
await mkdir(out, { recursive: true });
await writeFile(path.join(out, 'live-results.json'), JSON.stringify({ method: 'Independent live loopback API checks with fictional data; no participant testing', evidence }, null, 2));
console.log(JSON.stringify({ checks: evidence.length, pass: true, output: out, note: 'Created fictional local verification organizations/events; credentials not logged' }));
