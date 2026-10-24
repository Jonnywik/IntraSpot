import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {notificationCategory, notificationDestination} from '../Code/Frontend/features/notifications/inbox.ts';
import {
  captureSafetyCommand,
  DESKTOP_SAFETY_QUERY,
  eventReportActions,
  isUncertainSafetyFailure,
  matchesSafetyCommand,
  parseBoundedEventEvidence,
} from '../Code/Frontend/features/eventsafety/safety-helpers.mjs';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const feature = 'Code/Frontend/features/eventsafety';

test('safety notices keep their category and terminal notices lead to retained My Events history', () => {
  for (const kind of ['event_safety_report', 'organization_safety', 'event_safety_cancelled']) {
    assert.equal(notificationCategory(kind), 'safety');
  }
  assert.deepEqual(notificationDestination({kind: 'event_safety_cancelled', event_id: 'removed-event'}, null),
    {href: '/my-events', label: 'View My Events'});
});

test('safety commands freeze the request for exact retries and remain scoped to their account context', () => {
  const context = JSON.stringify(['event-a', 'account-token']);
  const command = captureSafetyCommand(context, '/events/event-a/safety', {
    action: 'hide', version: 4, client_key: 'stable-uuid',
  });

  assert.equal(DESKTOP_SAFETY_QUERY, '(min-width: 768px)');
  assert.equal(Object.isFrozen(command), true);
  assert.equal(Object.isFrozen(command.body), true);
  assert.equal(matchesSafetyCommand(command, context), true);
  assert.equal(matchesSafetyCommand(command, JSON.stringify(['event-b', 'account-token'])), false);
  assert.deepEqual(command.body, {action: 'hide', version: 4, client_key: 'stable-uuid'});
  const eventVersion = 4_294_967_291;
  const decision = captureSafetyCommand(context, '/moderation/event-reports/report-a/decision', {
    action: 'hide', version: 3, event_version: eventVersion, client_key: 'decision-uuid',
  });
  assert.equal(decision.body.event_version, eventVersion);

  for (const status of [null, 0, 408, 429, 500, 503]) assert.equal(isUncertainSafetyFailure(status), true);
  for (const status of [200, 400, 401, 403, 409]) assert.equal(isUncertainSafetyFailure(status), false);
});

test('event evidence is accepted as bounded plain text from only the frozen snapshot fields', () => {
  const htmlLike = '<img src=x onerror=alert(1)>';
  const evidence = parseBoundedEventEvidence(JSON.stringify({
    title: htmlLike.repeat(20), summary: 'A short summary', description: 'Details', venue_name: 'Room 1', venue_address: 'PLM courtyard',
    reporter_email: 'private@example.test', nested: {html: '<script>bad()</script>'},
  }));

  assert.deepEqual(Object.keys(evidence), ['title', 'summary', 'description', 'venue_name', 'venue_address']);
  assert.equal(evidence.title.length, 200);
  assert.equal(evidence.venue_name, 'Room 1');
  assert.equal(evidence.venue_address, 'PLM courtyard');
  assert.equal(evidence.title.startsWith(htmlLike), true);
  assert.equal(evidence.summary, 'A short summary');
  assert.equal(parseBoundedEventEvidence('not json'), null);
  assert.equal(parseBoundedEventEvidence('x'.repeat(4097)), null);
  assert.equal(parseBoundedEventEvidence(JSON.stringify(['title'])), null);
  assert.equal(parseBoundedEventEvidence(JSON.stringify({reporter_id: 'private'})), null);
});

test('report actions follow stage, open status, evidence, and deadline', () => {
  const now = Date.parse('2026-10-24T00:00:00Z');
  const report = {
    status: 'open', stage: 'organization', deadline: '2026-10-25T00:00:00Z', evidence: '{}',
  };
  assert.deepEqual(eventReportActions(report, now), ['dismiss', 'hide']);
  assert.deepEqual(eventReportActions({...report, stage: 'platform'}, now), ['dismiss', 'hide', 'remove', 'uphold']);
  assert.deepEqual(eventReportActions({...report, status: 'dismissed'}, now), []);
  assert.deepEqual(eventReportActions({...report, deadline: '2026-10-23T00:00:00Z'}, now), []);
  assert.deepEqual(eventReportActions({...report, evidence: null}, now), []);
  assert.deepEqual(eventReportActions({...report, stage: 'unknown'}, now), []);
});

test('components expose only Sprint 22 UI and use lazy desktop management with native dialogs', async () => {
  const [index, reporter, controls, suspension, queue, ui, dialog] = await Promise.all([
    read(`${feature}/index.ts`),
    read(`${feature}/EventReportButton.tsx`),
    read(`${feature}/EventSafetyControls.tsx`),
    read(`${feature}/OrganizationSuspensionPanel.tsx`),
    read(`${feature}/EventSafetyQueue.tsx`),
    read(`${feature}/use-safety-ui.ts`),
    read(`${feature}/SafetyDialog.tsx`),
  ]);

  for (const name of ['EventReportButton', 'EventSafetyControls', 'OrganizationSuspensionPanel', 'EventSafetyQueue', 'safetyMessages']) {
    assert.match(index, new RegExp(`export \\{[^}]*\\b${name}\\b[^}]*\\}`));
  }
  assert.match(reporter, /export function EventReportButton\(\{eventId, token\}/);
  assert.match(controls, /export function EventSafetyControls\(\{eventId, token\}/);
  assert.match(suspension, /export function OrganizationSuspensionPanel\(\{orgId, token\}/);
  assert.match(queue, /export function EventSafetyQueue\(\{token, orgId\}: \{token: string; orgId\?: string\}\)/);

  assert.match(reporter, /\/events\/\$\{encodeURIComponent\(eventId\)\}\/event-reports/);
  assert.match(controls, /\/events\/\$\{encodeURIComponent\(eventId\)\}\/safety/);
  assert.match(suspension, /\/organizations\/\$\{encodeURIComponent\(orgId\)\}\/suspension/);
  assert.match(queue, /\/moderation\/event-reports/);
  assert.match(queue, /org_id=\$\{encodeURIComponent\(orgId\)\}/);
  assert.match(queue, /slice\(0, 100\)/);

  for (const source of [controls, suspension, queue]) {
    assert.match(source, /useDesktopManagement\(\)/);
    assert.match(source, /if \(!isDesktop\) return null/);
    assert.match(source, /key=\{JSON\.stringify\(/);
    assert.match(source, /resourceEpoch/);
    assert.doesNotMatch(source, /useEffect\(\(\) => \{\s*set(?:Confirmation|Selected|Attempt|Feedback|Busy|Days)\(/);
  }
  assert.match(ui, /useSyncExternalStore\(subscribeDesktop, getDesktopSnapshot, \(\) => false\)/);
  assert.match(ui, /window\.matchMedia\(DESKTOP_SAFETY_QUERY\)/);
  assert.match(ui, /if \(!enabled\) return/);
  assert.match(ui, /void load\(\)/);
  assert.match(ui, /if \(fetching\)[\s\S]*?refreshQueued = true/);
  assert.match(ui, /requestRevision !== requiredRevision[\s\S]*?refreshQueued = true/);
  assert.doesNotMatch(ui, /loaderRef\.current\s*=/);

  assert.match(dialog, /<dialog/);
  assert.match(dialog, /dialog\.showModal\(\)/);
  assert.match(dialog, /onCancel=\{event =>/);
  assert.match(dialog, /event\.preventDefault\(\)/);
  assert.match(dialog, /cancelRef\.current\?\.focus\(\)/);
  assert.match(dialog, /const returnTarget = returnFocusRef\.current/);
  assert.match(dialog, /returnTarget\?\.isConnected/);
  assert.match(dialog, /returnTarget\.focus\(\)/);
  assert.doesNotMatch(dialog, /returnFocusRef\.current\.focus\(\)/);
  assert.match(dialog, /if \(dialog\.open\) dialog\.close\(\)/);
  assert.match(dialog, /if \(wasOpenRef\.current\)[\s\S]*?requestAnimationFrame/);
  assert.match(dialog, /t\('Cancel'\)/);
});

test('authority stays server-derived, stale decisions refresh, and retry payloads keep captured versions and UUIDs', async () => {
  const [reporter, controls, suspension, queue, helpers, types] = await Promise.all([
    read(`${feature}/EventReportButton.tsx`),
    read(`${feature}/EventSafetyControls.tsx`),
    read(`${feature}/OrganizationSuspensionPanel.tsx`),
    read(`${feature}/EventSafetyQueue.tsx`),
    read(`${feature}/safety-helpers.mjs`),
    read(`${feature}/types.ts`),
  ]);

  assert.match(controls, /current\.can_hide === true/);
  assert.match(controls, /current\.can_restore === true/);
  assert.match(controls, /current\.can_remove === true/);
  assert.match(controls, /current\.can_cancel === true/);
  assert.match(suspension, /current\.can_manage !== true/);
  assert.match(types, /components\['schemas'\]\['EventSafetyOut'\]/);
  assert.match(types, /components\['schemas'\]\['SuspensionOut'\]/);
  assert.match(types, /components\['schemas'\]\['EventReportReceipt'\]/);
  assert.match(types, /components\['schemas'\]\['EventReportReview'\]/);
  assert.match(types, /components\['schemas'\]\['EventReportCreateInput'\]/);
  assert.match(types, /components\['schemas'\]\['EventReportDecisionInput'\]/);
  assert.match(types, /components\['schemas'\]\['EventSafetyActionInput'\]/);
  assert.match(types, /components\['schemas'\]\['SuspensionActionInput'\]/);

  assert.match(reporter, /client_key: window\.crypto\.randomUUID\(\)/);
  assert.match(controls, /client_key: window\.crypto\.randomUUID\(\)/);
  assert.match(suspension, /client_key: window\.crypto\.randomUUID\(\)/);
  assert.match(queue, /client_key: window\.crypto\.randomUUID\(\)/);
  assert.match(queue, /version: reviewed\.reportVersion,[\s\S]*event_version: reviewed\.eventVersion/);
  assert.match(controls, /body: command\.body/);
  assert.match(suspension, /body: command\.body/);
  assert.match(queue, /body: command\.body/);
  assert.match(reporter, /body: command\.body/);
  assert.match(controls, /sendCommand\(visibleAttempt, true\)/);
  assert.match(suspension, /sendCommand\(visibleAttempt, true\)/);
  assert.match(queue, /sendDecision\(visibleAttempt\.command, visibleAttempt\.reportId, true\)/);
  assert.match(reporter, /sendReport\(visibleAttempt, true\)/);

  for (const source of [controls, suspension, queue]) {
    assert.match(source, /status === 409/);
    assert.match(source, /resource\.refresh\(\)/);
    assert.match(source, /isUncertainSafetyFailure\(status\)/);
  }
  assert.match(helpers, /Object\.freeze\(\{\.\.\.body\}\)/);
  assert.match(queue, /current\.version !== reviewed\.reportVersion/);
  assert.match(queue, /current\.event_version !== reviewed\.eventVersion/);
  assert.match(queue, /event_version: reviewed\.eventVersion/);
  assert.doesNotMatch(queue, /event_version\s*[+-]/);
});

test('queue presents bounded escaped text only and the feature never persists report state in browser storage', async () => {
  const paths = [
    `${feature}/EventReportButton.tsx`, `${feature}/EventSafetyControls.tsx`,
    `${feature}/OrganizationSuspensionPanel.tsx`, `${feature}/EventSafetyQueue.tsx`,
    `${feature}/use-safety-ui.ts`, `${feature}/SafetyDialog.tsx`, `${feature}/safety-helpers.mjs`,
  ];
  const sources = await Promise.all(paths.map(read));
  const joined = sources.join('\n');
  const queue = await read(`${feature}/EventSafetyQueue.tsx`);

  assert.match(queue, /parseBoundedEventEvidence\(chosen\.evidence\)/);
  assert.match(queue, /<dd>\{snapshot\[field\]\}<\/dd>/);
  assert.doesNotMatch(joined, /dangerouslySetInnerHTML/);
  assert.doesNotMatch(joined, /reporter_id/);
  assert.doesNotMatch(joined, /localStorage|sessionStorage|\bStorage\b/);
  assert.match(joined, /readControllerRef|controller\?\.abort\(\)/);
  for (const source of [
    await read(`${feature}/EventSafetyControls.tsx`),
    await read(`${feature}/OrganizationSuspensionPanel.tsx`),
    queue,
  ]) assert.match(source, /mutationRef\.current\?\.abort\(\)/);
  assert.match(sources[4], /controller\?\.abort\(\)/);
});

test('safety surfaces follow app theme tokens and strengthen borders in high contrast', async () => {
  const css = await read(`${feature}/eventsafety.module.css`);
  assert.match(css, /background: var\(--surface, var\(--paper\)\)/);
  assert.match(css, /color: var\(--ink\)/);
  assert.match(css, /var\(--success-bg\)/);
  assert.match(css, /var\(--danger-bg\)/);
  assert.match(css, /var\(--pending-bg\)/);
  assert.match(css, /html\[data-theme='dark'\]/);
  assert.match(css, /html\[data-high-contrast='true'\]/);
  assert.doesNotMatch(css, /#[\da-f]{3,8}\b|rgba?\(/i);
});

test('exact Sprint 22 backend safety notices have Filipino translations', async () => {
  const [backend, messages] = await Promise.all([
    read('Code/Backend/app/domains/eventsafety/service.py'),
    read(`${feature}/messages.ts`),
  ]);
  assert.match(backend, /message=f"An event safety report requires \{stage_label\} review\."/);
  const noticeKeys = [
    'An event safety report requires organization review.',
    'An event safety report requires platform review.',
    'Your event safety report was resolved.',
    'Your organization has been temporarily suspended from publishing new events.',
    'The organization safety suspension has ended.',
  ];
  for (const key of noticeKeys) {
    if (!key.startsWith('An event safety report requires ')) assert.ok(backend.includes(`"${key}"`), `Backend notice changed: ${key}`);
    assert.match(messages, new RegExp(`'${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}': '[^']+'`), `Missing Filipino translation: ${key}`);
  }
});

test('all UI translation keys used by direct labels and action maps have Filipino entries', async () => {
  const componentPaths = [
    `${feature}/EventReportButton.tsx`, `${feature}/EventSafetyControls.tsx`,
    `${feature}/OrganizationSuspensionPanel.tsx`, `${feature}/EventSafetyQueue.tsx`,
  ];
  const [messages, ...components] = await Promise.all([
    read(`${feature}/messages.ts`),
    ...componentPaths.map(read),
  ]);
  const messageKeyList = [...messages.matchAll(/^\s*'([^']+)':/gm)].map(([, key]) => key);
  const messageKeys = new Set(messageKeyList);
  assert.equal(messageKeys.size, messageKeyList.length, 'safetyMessages must not define duplicate English keys');
  const sources = components.join('\n');
  const usedKeys = new Set();

  for (const [, args] of sources.matchAll(/\bt\(([^)]{0,500})\)/g)) {
    for (const [, key] of args.matchAll(/'([^']+)'/g)) {
      if (!/^[a-z][a-z0-9_]*$/.test(key)) usedKeys.add(key);
    }
  }
  for (const name of ['reasonLabels', 'statusLabels', 'actionLabels', 'confirmationText']) {
    const match = sources.match(new RegExp(`const ${name}:[^=]+ = \\{([\\s\\S]*?)\\n\\};`));
    if (match) for (const [, key] of match[1].matchAll(/:\s*'([^']+)'/g)) usedKeys.add(key);
  }
  for (const [, key] of sources.matchAll(/return '([^']+)'/g)) usedKeys.add(key);

  const missing = [...usedKeys].filter(key => !messageKeys.has(key));
  assert.deepEqual(missing, []);
  assert.match(messages, /export const safetyMessages: Record<string, string>/);
  assert.match(messages, /'This event is not accepting new registrations\.': '[^']+'/);
});
