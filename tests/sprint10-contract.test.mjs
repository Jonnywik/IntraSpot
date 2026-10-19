import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {api, ApiError} from '../Code/Frontend/lib/api.ts';
import {notificationCategory, notificationDestination} from '../Code/Frontend/features/notifications/inbox.ts';

const originalFetch = globalThis.fetch;
const originalUrl = process.env.NEXT_PUBLIC_API_URL;
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
  else process.env.NEXT_PUBLIC_API_URL = originalUrl;
});

test('draft saves and publishing send the same quoted version precondition', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8001';
  const requests = [];
  const version = 'a'.repeat(64);
  globalThis.fetch = async (url, options) => {
    requests.push({url: String(url), options});
    return Response.json({id: 'fictional-event'});
  };
  await api('/events/fictional-event/draft', {method: 'PATCH', body: {title: 'Saved title'}, ifMatch: version});
  await api('/events/fictional-event/publish', {method: 'POST', ifMatch: version});
  for (const {options} of requests) {
    assert.equal(options.headers['If-Match'], `"${version}"`);
    assert.equal(options.credentials, 'omit');
  }
  assert.equal(requests[0].options.method, 'PATCH');
  assert.equal(requests[1].options.method, 'POST');
  assert.equal(requests[1].options.body, undefined);
});

test('a conflict stays a machine-readable error so the editor can preserve input', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8001';
  globalThis.fetch = async () => Response.json({error: {
    code: 'draft_conflict', message: 'This draft changed in another window.',
  }}, {status: 409});
  await assert.rejects(api('/events/fictional-event/draft', {method: 'PATCH', body: {title: 'Local edits'}}),
    error => error instanceof ApiError && error.status === 409 && error.code === 'draft_conflict');
});

test('inbox categories preserve membership-related attendance and safety context', () => {
  assert.equal(notificationCategory('membership_attendance_ended'), 'registrations');
  assert.equal(notificationCategory('membership_invitation'), 'clubs');
  assert.equal(notificationCategory('chat_message'), 'chat');
  assert.equal(notificationCategory('report_escalated'), 'safety');
  assert.equal(notificationCategory('waitlist_promoted'), 'registrations');
});

test('inbox destinations select authorized workspace context and never invent null event links', () => {
  const notice = {kind: 'registration_review_requested', event_id: 'event-one', org_id: 'org-one'};
  const staff = {platform_admin: false, grants: [{org_id: 'org-one', role: 'moderator'}]};
  const member = {platform_admin: false, grants: [{org_id: 'org-one', role: 'member'}]};
  assert.equal(notificationDestination(notice, staff).href, '/workspace?orgId=org-one&eventId=event-one');
  assert.equal(notificationDestination(notice, member).href, '/events?eventId=event-one');
  assert.equal(notificationDestination({...notice, org_id: 'another-org'}, staff).href, '/events?eventId=event-one');
  assert.equal(notificationDestination({kind: 'membership_invitation', event_id: null, org_id: 'org-one'}, member).href,
    '/organizations?orgId=org-one');
  assert.equal(notificationDestination({kind: 'chat_message', event_id: null, org_id: null}, member), null);
  assert.equal(notificationDestination({kind: 'report_received', event_id: null, org_id: null}, {platform_admin: true}).href,
    '/admin');
});
