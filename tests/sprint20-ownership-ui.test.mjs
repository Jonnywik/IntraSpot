import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {
  canLoadOwnershipData,
  captureDecision,
  decisionPayload,
  getOrCreateOfferAttempt,
  isBeforeExpiry,
  isDecisionCurrent,
  matchesOfferAttempt,
  parseExactTimestamp,
  shouldShowAdminOwnershipPanel,
} from '../Code/Frontend/features/ownership/ownership-helpers.mjs';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');

test('ownership reads are desktop-scoped and use the existing private roster route', async () => {
  const panel = await read('Code/Frontend/features/ownership/OwnershipTransferPanel.tsx');
  assert.equal(canLoadOwnershipData({isDesktop: false, role: 'owner', actorEligible: true, token: 'token'}), false);
  assert.equal(canLoadOwnershipData({isDesktop: true, role: 'owner', actorEligible: true, token: 'token'}), true);
  assert.equal(canLoadOwnershipData({isDesktop: true, role: 'admin', actorEligible: true, token: 'token'}), true);
  assert.equal(canLoadOwnershipData({isDesktop: true, role: 'admin', actorEligible: false, token: 'token'}), false);
  assert.equal(canLoadOwnershipData({isDesktop: true, role: 'moderator', actorEligible: true, token: 'token'}), false);
  assert.match(panel, /useSyncExternalStore\(subscribeDesktop, getDesktopSnapshot, \(\) => false\)/);
  assert.match(panel, /if \(!canRead\) return null/);
  assert.match(panel, /`\$\{organizationPath\}\/members`/);
  assert.match(panel, /`\$\{organizationPath\}\/ownership-transfers`/);
  assert.doesNotMatch(panel, /\/memberships/);
  assert.match(panel, /member\.role === 'admin' && member\.eligible/);
  assert.match(panel, /transfer\.nominee_id === actorId/);
  assert.match(panel, /window\.setInterval\(refreshWhenActive, 15_000\)/);
  assert.match(panel, /document\.visibilityState === 'visible' && document\.hasFocus\(\)/);
  assert.doesNotMatch(panel, /localStorage|sessionStorage|Storage/);
});

test('decisions preserve the reviewed offer id/version and never silently adopt a refreshed version', async () => {
  const offer = {id: 'transfer-a', version: 4, status: 'pending'};
  const review = captureDecision(offer, 'accept');
  offer.version = 5;
  assert.deepEqual(review, {transferId: 'transfer-a', version: 4, action: 'accept'});
  assert.deepEqual(decisionPayload(review), {action: 'accept', version: 4});
  assert.equal(isDecisionCurrent(review, offer), false);
  assert.equal(isDecisionCurrent(review, {...offer, version: 4, status: 'declined'}), false);
  assert.equal(isDecisionCurrent(review, {...offer, version: 4, status: 'pending'}), true);

  const panel = await read('Code/Frontend/features/ownership/OwnershipTransferPanel.tsx');
  assert.match(panel, /captureDecision\(offer, action\)/);
  assert.match(panel, /body: decisionPayload\(review\.reviewed\)/);
  assert.match(panel, /if \(!isDecisionCurrent\(review\.reviewed, latest\) \|\| review\.stale\)/);
  assert.match(panel, /stale: apiStatus\(error\) === 409/);
  assert.match(panel, /reviewed: captureDecision\(latest, review\.reviewed\.action\)/);
  assert.doesNotMatch(panel, /version:\s*latest\.version/);
});

test('uncertain creates reuse the exact in-memory nominee and client key, including after polling finds a pending offer', async () => {
  const context = {};
  let generated = 0;
  const createKey = () => `client-key-${++generated}`;
  const first = getOrCreateOfferAttempt(null, context, 'admin-a', createKey);
  const retry = getOrCreateOfferAttempt(first, context, 'admin-a', createKey);
  assert.equal(retry, first);
  assert.equal(generated, 1);
  assert.equal(matchesOfferAttempt(retry, context, 'admin-a'), true);
  assert.equal(matchesOfferAttempt(retry, {}, 'admin-a'), false);
  assert.equal(matchesOfferAttempt(retry, context, 'admin-b'), false);
  assert.deepEqual(retry.payload, {nominee_id: 'admin-a', client_key: 'client-key-1'});

  const definitiveNewAttempt = getOrCreateOfferAttempt(null, context, 'admin-a', createKey);
  assert.equal(definitiveNewAttempt.clientKey, 'client-key-2');

  const panel = await read('Code/Frontend/features/ownership/OwnershipTransferPanel.tsx');
  assert.match(panel, /const isRetry = matchesOfferAttempt\(existingAttempt, contextIdentity, nomineeId\)/);
  assert.match(panel, /if \(!isRetry && \(pendingOffer \|\| !candidates\.some/);
  assert.match(panel, /Boolean\(pendingOffer\) \|\| !candidateForSelection/);
  assert.match(panel, /body: attempt\.payload/);
  assert.match(panel, /retryAttemptRef\.current = null/);
  assert.doesNotMatch(panel, /if \(pendingOffer \|\| !candidates/);
});

test('a nominee can retry after uncertainty; admins stay quiet only before data or when not nominated', async () => {
  assert.equal(shouldShowAdminOwnershipPanel({dataLoaded: false, notNominee: false, requestFailed: false, hasOwnOffer: false}), false);
  assert.equal(shouldShowAdminOwnershipPanel({dataLoaded: true, notNominee: true, requestFailed: true, hasOwnOffer: false}), false);
  assert.equal(shouldShowAdminOwnershipPanel({dataLoaded: true, notNominee: false, requestFailed: false, hasOwnOffer: false}), false);
  assert.equal(shouldShowAdminOwnershipPanel({dataLoaded: true, notNominee: false, requestFailed: true, hasOwnOffer: false}), true);
  assert.equal(shouldShowAdminOwnershipPanel({dataLoaded: true, notNominee: false, requestFailed: false, hasOwnOffer: true}), true);

  const panel = await read('Code/Frontend/features/ownership/OwnershipTransferPanel.tsx');
  assert.match(panel, /requestFailed: Boolean\(data\?\.transferError\)/);
  assert.match(panel, /!data\?\.transferError && offer\.nominee_id === actorId/);
  assert.match(panel, /Could not check ownership offers\./);
  assert.match(panel, /onClick=\{\(\) => refreshRef\.current\?\.\(\)\}/);
  assert.match(panel, /activeRetryNominee && \(data\?\.transferError \|\| data\?\.rosterError\)/);
});

test('expiry checks fail closed at the exact deadline and for invalid timestamps', () => {
  const expiry = '2026-10-30T12:34:56.789Z';
  const timestamp = Date.parse(expiry);
  assert.equal(isBeforeExpiry(expiry, timestamp - 1), true);
  assert.equal(isBeforeExpiry(expiry, timestamp), false);
  assert.equal(isBeforeExpiry('not-a-time', timestamp - 1), false);
  assert.equal(isBeforeExpiry('', timestamp - 1), false);
  assert.equal(parseExactTimestamp('2026-10-30'), null);
  const microsecondExpiry = '2026-10-30T12:34:56.789123Z';
  const millisecondFloor = Date.parse(microsecondExpiry);
  assert.equal(isBeforeExpiry(microsecondExpiry, millisecondFloor), true);
  assert.equal(isBeforeExpiry(microsecondExpiry, millisecondFloor + 1), false);
});

test('confirmation is a native accessible dialog with Cancel focus, Escape handling, and focus return', async () => {
  const panel = await read('Code/Frontend/features/ownership/OwnershipTransferPanel.tsx');
  assert.match(panel, /<dialog[\s\S]*?aria-labelledby="ownership-confirmation-title"/);
  assert.match(panel, /node\.showModal\(\)/);
  assert.match(panel, /cancelButtonRef\.current\?\.focus\(\)/);
  assert.match(panel, /onCancel=\{handleDialogCancel\}/);
  assert.match(panel, /event\.preventDefault\(\);\s*closeDialog\(\)/);
  assert.match(panel, /restoreFocusRef\.current\.focus\(\)/);
  assert.match(panel, /ref=\{cancelButtonRef\} onClick=\{closeDialog\}/);
  assert.match(panel, /If you decline, the offer ends and the current owner stays the owner\./);
});

test('all panel and ownership-notification copy has Filipino translations', async () => {
  const [panel, messages] = await Promise.all([
    read('Code/Frontend/features/ownership/OwnershipTransferPanel.tsx'),
    read('Code/Frontend/features/ownership/messages.ts'),
  ]);
  const keys = new Set();
  for (const call of panel.matchAll(/\bt\(([^)]*)\)/gs)) {
    for (const literal of call[1].matchAll(/'([^']+)'/g)) keys.add(literal[1]);
  }
  for (const internalValue of ['create', 'decision', 'accept', 'decline', 'revoke']) keys.delete(internalValue);
  for (const match of panel.matchAll(/const statusMessages:[\s\S]*?=\s*\{([\s\S]*?)\n\};/g)) {
    for (const literal of match[1].matchAll(/:\s*'([^']+)'/g)) keys.add(literal[1]);
  }
  for (const key of keys) assert.ok(messages.includes(`'${key}':`), `Missing Filipino message: ${key}`);
  for (const key of [
    'You have an organization ownership transfer offer.',
    'Organization ownership was transferred. Review your current role.',
    'An organization ownership transfer offer was declined.',
    'An organization ownership transfer offer was revoked.',
    'An organization ownership transfer offer expired.',
  ]) assert.ok(messages.includes(`'${key}':`), `Missing backend notification translation: ${key}`);
});
