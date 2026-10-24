import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {
  captureSafetyCommand,
  eventReportActions,
  eventReportDecisionOutcome,
  matchesSafetyCommand,
  parseBoundedEventEvidence,
} from '../Code/Frontend/features/eventsafety/safety-helpers.mjs';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const feature = 'Code/Frontend/features/eventsafety';

test('review decisions use the scoped report and event versions and preserve the exact retry', async () => {
  const [queue, types, generated] = await Promise.all([
    read(`${feature}/EventSafetyQueue.tsx`),
    read(`${feature}/types.ts`),
    read('Code/Frontend/lib/api.generated.ts'),
  ]);

  assert.match(queue, /JSON\.stringify\(\[orgId \?\? null, token\]\)/);
  assert.match(queue, /moderation\/event-reports\?org_id=\$\{encodeURIComponent\(orgId\)\}/);
  assert.match(queue, /return result\.slice\(0, 100\)/);
  assert.match(queue, /setSelected\(\{contextKey, reportId: report\.id\}\)/);
  assert.match(queue, /reportVersion: report\.version/);
  assert.match(queue, /eventVersion: report\.event_version/);
  assert.match(queue, /version: reviewed\.reportVersion,[\s\S]*event_version: reviewed\.eventVersion/);
  assert.match(queue, /eventReportDecisionOutcome\(result, reportId, command\.body\.action, command\.body\.version\)/);
  assert.match(queue, /sendDecision\(visibleAttempt\.command, visibleAttempt\.reportId, true\)/);
  assert.match(queue, /The pending decision for report \{reportId\}/);

  for (const schema of [
    'EventReportReview', 'EventReportDecisionInput', 'EventSafetyOut', 'SuspensionOut',
  ]) assert.match(types, new RegExp(`components\\['schemas'\\]\\['${schema}'\\]`));
  assert.match(generated, /EventReportReview: \{[\s\S]*?event_version: number/);

  const scope = JSON.stringify(['org-a', 'account-a']);
  const command = captureSafetyCommand(scope, '/moderation/event-reports/report-a/decision', {
    action: 'hide', version: 8, event_version: 12, client_key: 'stable-key',
  });
  assert.equal(Object.isFrozen(command.body), true);
  assert.equal(matchesSafetyCommand(command, scope), true);
  assert.equal(matchesSafetyCommand(command, JSON.stringify(['org-b', 'account-a'])), false);
  assert.equal(command.body.event_version, 12);
});

test('an HTTP 200 deadline sweep is expired rather than an applied decision', () => {
  for (const action of ['dismiss', 'hide', 'remove', 'uphold']) {
    assert.equal(eventReportDecisionOutcome({id: 'report-a', version: 9, status: 'expired'}, 'report-a', action, 8), 'expired');
  }
});

test('an applied decision requires the exact requested action status, report ID, and next version', () => {
  const statuses = {dismiss: 'dismissed', hide: 'hidden', remove: 'removed', uphold: 'upheld'};
  for (const [action, appliedStatus] of Object.entries(statuses)) {
    for (const status of ['open', 'escalated', ...Object.values(statuses)]) {
      assert.equal(
        eventReportDecisionOutcome({id: 'report-a', version: 9, status}, 'report-a', action, 8),
        status === appliedStatus ? 'applied' : 'uncertain',
        `${action} returned ${status}`,
      );
    }
  }
});

test('malformed or mismatched decision responses remain uncertain for the original frozen retry', () => {
  const command = captureSafetyCommand('scope-a', '/moderation/event-reports/report-a/decision', {
    action: 'hide', version: 8, event_version: 12, client_key: 'original-key',
  });
  for (const status of ['hidden', 'expired']) {
    for (const result of [
      null, undefined, [], {},
      {id: 'report-b', version: 9, status},
      {id: 'report-a', version: 8, status},
      {id: 'report-a', version: 10, status},
      {id: 'report-a', version: '9', status},
      {id: 'report-a', version: NaN, status},
      {id: 'report-a', version: 9},
    ]) {
      assert.equal(eventReportDecisionOutcome(result, 'report-a', command.body.action, command.body.version), 'uncertain');
    }
  }
  for (const action of [undefined, 'constructor', 'unknown']) {
    assert.equal(eventReportDecisionOutcome({id: 'report-a', version: 9, status: 'expired'}, 'report-a', action, 8), 'uncertain');
  }
  assert.equal(eventReportDecisionOutcome({id: 'report-a', version: 9, status: 'hidden'}, 'report-a', 'hide', '8'), 'uncertain');
  assert.deepEqual(command.body, {action: 'hide', version: 8, event_version: 12, client_key: 'original-key'});
  assert.equal(matchesSafetyCommand(command, 'scope-a'), true);
});

test('deadline checks close actions at the exact boundary and evidence stays bounded plain text', async () => {
  const queue = await read(`${feature}/EventSafetyQueue.tsx`);
  const atDeadline = Date.parse('2026-10-24T12:00:00Z');
  const report = {
    status: 'open', stage: 'organization', deadline: '2026-10-24T12:00:00Z', evidence: '{}',
  };

  assert.deepEqual(eventReportActions(report, atDeadline - 1), ['dismiss', 'hide']);
  assert.deepEqual(eventReportActions(report, atDeadline), []);
  assert.match(queue, /setInterval\(\(\) => setNow\(Date\.now\(\)\), 30_000\)/);
  assert.match(queue, /Date\.parse\(chosen\.deadline\)/);

  const htmlLike = '<img src=x onerror=alert(1)>';
  const snapshot = parseBoundedEventEvidence(JSON.stringify({
    title: htmlLike.repeat(20), venue_name: 'Room 1', venue_address: 'Campus', reporter_email: 'omit',
  }));
  assert.deepEqual(Object.keys(snapshot), ['title', 'venue_name', 'venue_address']);
  assert.equal(snapshot.title.length, 200);
  assert.equal(snapshot.title.startsWith(htmlLike), true);
  assert.match(queue, /<dd>\{snapshot\[field\]\}<\/dd>/);
  assert.doesNotMatch(queue, /dangerouslySetInnerHTML|reporter_email/);
});

test('native confirmations retain Escape and focus-return behavior; management remains desktop-only', async () => {
  const [dialog, reporter, controls, suspension, queue, css] = await Promise.all([
    read(`${feature}/SafetyDialog.tsx`),
    read(`${feature}/EventReportButton.tsx`),
    read(`${feature}/EventSafetyControls.tsx`),
    read(`${feature}/OrganizationSuspensionPanel.tsx`),
    read(`${feature}/EventSafetyQueue.tsx`),
    read(`${feature}/eventsafety.module.css`),
  ]);

  assert.match(dialog, /dialog\.showModal\(\)/);
  assert.match(dialog, /onCancel=\{event =>/);
  assert.match(dialog, /event\.preventDefault\(\)/);
  assert.match(dialog, /returnTarget\?\.isConnected/);
  assert.match(dialog, /returnTarget\.focus\(\)/);
  for (const source of [controls, suspension, queue]) {
    assert.match(source, /useDesktopManagement\(\)/);
    assert.match(source, /if \(!isDesktop\) return null/);
  }
  assert.doesNotMatch(reporter, /useDesktopManagement|desktopOnly/);
  assert.match(css, /html\[data-theme='dark'\]/);
  assert.match(css, /html\[data-high-contrast='true'\]/);
  assert.match(css, /@media \(max-width: 767px\)/);
});

test('conflict feedback asks for a refresh and names the pending queue target in Filipino', async () => {
  const [controls, queue, messages] = await Promise.all([
    read(`${feature}/EventSafetyControls.tsx`),
    read(`${feature}/EventSafetyQueue.tsx`),
    read(`${feature}/messages.ts`),
  ]);

  assert.match(controls, /Refresh and review the latest safety status/);
  assert.match(queue, /Refresh the queue and review the latest status/);
  assert.match(messages, /'This event changed while you were reviewing it\. Refresh and review the latest safety status before making another change\.': '[^']+'/);
  assert.match(messages, /'This report or event changed while you were reviewing it\. Refresh the queue and review the latest status before deciding again\.': '[^']+'/);
  assert.match(messages, /'The pending decision for report \{reportId\} could not be confirmed\. Retry will resend that exact request\.': '[^']+'/);
  assert.match(queue, /if \(outcome === 'expired'\) \{[\s\S]*?No decision was saved\.[^\n]*tone: 'warning'/);
  assert.match(messages, /'This report expired before your decision was applied\. No decision was saved\. Refresh the queue to review the latest status\.': '[^']+'/);
  assert.doesNotMatch(controls + queue, /latest (?:safety status|queue) is loaded/);
});
