import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {eventChatAvailable} from '../Code/Frontend/features/registrations/presentation.ts';

test('My Events only offers confirmed chat before the exact retention boundary', () => {
  const endsAt = '2026-10-17T10:00:00Z';
  const boundary = Date.parse(endsAt) + 72 * 60 * 60 * 1000;
  assert.equal(eventChatAvailable('confirmed', endsAt, boundary - 1), true);
  assert.equal(eventChatAvailable('confirmed', endsAt, boundary), false);
  assert.equal(eventChatAvailable('confirmed', endsAt, boundary + 1), false);
  for (const status of ['pending', 'waitlisted', 'reconfirmation_required', 'cancelled', 'rejected']) {
    assert.equal(eventChatAvailable(status, endsAt, boundary - 1), false);
  }
  for (const invalid of [null, '', 'not-a-date']) {
    assert.equal(eventChatAvailable('confirmed', invalid, boundary - 1), false);
  }
  assert.equal(eventChatAvailable('confirmed', endsAt, null), false);
});

test('mobile navigation stays at four routes with measured, safe-area-aware clearance', async () => {
  const root = new URL('../Code/Frontend/', import.meta.url);
  const header = await readFile(new URL('app/site-header.tsx', root), 'utf8');
  const tabs = header.slice(header.indexOf('const tabs ='), header.indexOf('export function'));
  assert.deepEqual([...tabs.matchAll(/href: '([^']+)'/g)].map(match => match[1]), ['/', '/my-events', '/chat', '/settings']);
  assert.match(header, /ResizeObserver/);
  const css = await readFile(new URL('app/mobile.css', root), 'utf8');
  assert.match(css, /var\(--mobile-nav-height, 96px\)/);
  assert.match(css, /safe-area-inset-bottom/);
  assert.match(css, /repeat\(4, minmax\(0, 1fr\)\)/);
});
