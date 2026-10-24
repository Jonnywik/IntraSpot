import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const read = path => readFile(new URL('../' + path, import.meta.url), 'utf8');

test('featured API DTOs use generated OpenAPI schema aliases', async () => {
  const source = await read('Code/Frontend/features/featured/types.ts');
  assert.match(source, /import type \{components\} from '@\/lib\/api\.generated'/);
  assert.match(source, /FeaturedRequest = components\['schemas'\]\['FeaturedRequestOut'\]/);
  assert.match(source, /FeaturedDecision = components\['schemas'\]\['FeaturedDecisionOut'\]/);
});

test('manager control uses the authorized organization history and event request endpoints', async () => {
  const source = await read('Code/Frontend/features/featured/FeaturedControls.tsx');
  assert.match(source, /FeaturedRequestControl\(\{eventId, eventStartsAt, orgId, token\}/);
  assert.match(source, /eventStartsAt: string \| null/);
  assert.match(source, /\/organizations\/\$\{encodeURIComponent\(orgId\)\}\/featured-requests/);
  assert.match(source, /\/events\/\$\{encodeURIComponent\(eventId\)\}\/featured-requests/);
  assert.doesNotMatch(source, /useApiResource<FeaturedEventPublic>/);
  assert.match(source, /This event has started\. No featured request was submitted\./);
  assert.match(source, /Event start time is unavailable\. Request eligibility cannot be confirmed\./);
  assert.match(source, /Date\.now\(\) >= eventStart/);
  assert.match(source, /eventStartKnown && !eventStarted && !openRequest/);
  assert.match(source, /history\.data && !history\.error && !eventRequests\.length/);
  assert.match(source, /history\.data \?\? \[\]/);
  assert.match(source, /request\.event_id === eventId/);
  assert.match(source, /history\.reload\(\)/);
  assert.match(source, /mutationInFlight/);
});

test('admin queue loads public event details and sends only versioned contract decisions', async () => {
  const source = await read('Code/Frontend/features/featured/FeaturedControls.tsx');
  assert.match(source, /useApiResource<FeaturedRequest\[]>\('\/platform-admin\/featured-requests', token\)/);
  assert.match(source, /\/events\?eventId=\$\{encodeURIComponent\(request\.event\.id\)\}/);
  assert.match(source, /\/platform-admin\/featured-requests\/\$\{encodeURIComponent\(request\.id\)\}\/decisions/);
  assert.match(source, /version: request\.version/);
  assert.match(source, /starts_at: schedule!\.starts_at, ends_at: schedule!\.ends_at/);
  assert.match(source, /<dialog ref=\{confirmationDialog\}/);
  assert.match(source, /dialog\.showModal\(\)/);
  assert.match(source, /const \{action, schedule, version\} = confirmation/);
  assert.doesNotMatch(source, /window\.confirm/);
  assert.match(source, /request\.requested_by/);
  assert.match(source, /decision\.actor_id/);
  assert.doesNotMatch(source, /email|@example\./i);
});

test('approval scheduling is Manila-aware and expired or paused states follow the frozen lifecycle', async () => {
  const source = await read('Code/Frontend/features/featured/FeaturedControls.tsx');
  assert.match(source, /timeZone: 'Asia\/Manila'/);
  assert.match(source, /Date\.parse\(`\$\{value\}:00\+08:00`\)/);
  assert.match(source, /ends_at: new Date\(endTime\)\.toISOString\(\)/);
  assert.match(source, /now >= Math\.min\(endsAt, eventStartsAt\)/);
  assert.match(source, /request\.starts_at === null \? now : Date\.parse\(request\.starts_at\)/);
  assert.match(source, /status === 'paused'/);
  assert.match(source, /canRevoke = status === 'approved' \|\| status === 'scheduled' \|\| status === 'active'/);
  assert.match(source, /error\.status === 409/);
  assert.match(source, /queue\.reload\(\)/);
});

test('badge and UI feedback are accessible, and every translated label has Filipino copy', async () => {
  const [controls, badge, messages, css] = await Promise.all([
    read('Code/Frontend/features/featured/FeaturedControls.tsx'),
    read('Code/Frontend/features/featured/FeaturedBadge.tsx'),
    read('Code/Frontend/features/featured/messages.ts'),
    read('Code/Frontend/features/featured/featured.module.css'),
  ]);
  assert.match(badge, /export function FeaturedBadge\(\)/);
  assert.match(badge, /<Icon name="star"\s*\/>/);
  assert.match(controls, /role=\{feedback\.error \? 'alert' : 'status'\}/);
  assert.match(controls, /aria-invalid=\{Boolean\(errorKey\)\}/);
  assert.match(css, /\.badge/);
  assert.match(css, /var\(--surface\)/);
  assert.match(css, /var\(--pending-bg\)/);
  assert.match(css, /var\(--success-bg\)/);
  assert.match(css, /var\(--danger-bg\)/);
  assert.doesNotMatch(css, /#[\da-f]{3,8}\b/i);
  const keys = new Set([...controls.matchAll(/\bt\(\s*(['"])(.*?)\1/g)].map(match => match[2]));
  for (const match of controls.matchAll(/const (?:statusMessages|actionMessages):[^=]+=[\s\S]*?\n\};/g)) {
    for (const label of match[0].matchAll(/:\s*'([^']+)'/g)) keys.add(label[1]);
  }
  for (const match of controls.matchAll(/setErrorKey\('([^']+)'/g)) keys.add(match[1]);
  for (const key of [
    'Your sign-in or organization access has ended.',
    'The featured request history could not be loaded.',
    'The featured request queue could not be loaded.',
    'Your platform review access has ended.',
  ]) keys.add(key);
  for (const key of keys) assert.ok(messages.includes(`'${key}':`), `Missing Filipino message: ${key}`);
  for (const key of ['Requested', 'Pending review', 'Paused — review required', 'Scheduled', 'Active', 'Expired', 'Rejected', 'Revoked']) {
    assert.ok(messages.includes(`'${key}':`), `Missing Filipino status message: ${key}`);
  }
});
