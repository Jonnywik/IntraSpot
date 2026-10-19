import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const component = await readFile(new URL('../Code/Frontend/features/preferences/DiscoveryPreferences.tsx', import.meta.url), 'utf8');
const settings = await readFile(new URL('../Code/Frontend/app/settings/page.tsx', import.meta.url), 'utf8');
const ts = createRequire(new URL('../Code/Frontend/package.json', import.meta.url))('typescript');
const parsed = ts.createSourceFile('DiscoveryPreferences.tsx', component, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

function declaration(name) {
  let found;
  const visit = node => {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) found = node;
    if (!found) ts.forEachChild(node, visit);
  };
  visit(parsed);
  assert.ok(found, name + ' exists');
  return found.getText(parsed);
}

const helpers = ts.transpileModule([
  declaration('minuteToTime'),
  declaration('timeToMinute'),
  declaration('parseAvailabilityRows'),
].join('\n'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;
const { minuteToTime, timeToMinute, parseAvailabilityRows } = new Function(
  helpers + '; return { minuteToTime, timeToMinute, parseAvailabilityRows };',
)();

test('availability inputs convert minutes without treating 24:00 as a browser time', () => {
  assert.equal(timeToMinute('00:00'), 0);
  assert.equal(timeToMinute('23:59'), 1439);
  assert.equal(timeToMinute('24:00'), null);
  assert.equal(timeToMinute('9:00'), null);
  assert.equal(minuteToTime(0), '00:00');
  assert.equal(minuteToTime(1440), '24:00');
});

test('weekly windows use Monday zero and support an explicit end at midnight', () => {
  assert.deepEqual(parseAvailabilityRows([{
    id: 'window-1',
    weekday: 0,
    startTime: '23:30',
    endTime: '23:59',
    endsAtMidnight: true,
  }]), {
    windows: [{ weekday: 0, start_minute: 1410, end_minute: 1440 }],
    error: null,
  });
});

test('availability validation rejects invalid times, non-positive lengths, and invalid weekdays', () => {
  assert.equal(parseAvailabilityRows([{
    id: 'window-1', weekday: 1, startTime: '10:00', endTime: '10:00', endsAtMidnight: false,
  }]).error, 'End time must be later than start time.');
  assert.equal(parseAvailabilityRows([{
    id: 'window-1', weekday: 1, startTime: '23:00', endTime: '00:00', endsAtMidnight: false,
  }]).error, 'End time must be later than start time.');
  assert.equal(parseAvailabilityRows([{
    id: 'window-1', weekday: 1, startTime: '9:00', endTime: '17:00', endsAtMidnight: false,
  }]).error, 'Enter valid times for each window.');
  assert.equal(parseAvailabilityRows([{
    id: 'window-1', weekday: 7, startTime: '09:00', endTime: '17:00', endsAtMidnight: false,
  }]).error, 'Choose a weekday for each window.');
});

test('availability editor enforces the 28-window limit', () => {
  const rows = Array.from({ length: 29 }, (_, index) => ({
    id: 'window-' + index,
    weekday: 0,
    startTime: '09:00',
    endTime: '17:00',
    endsAtMidnight: false,
  }));
  assert.equal(parseAvailabilityRows(rows).error, 'You can add up to 28 windows.');
});

test('private preferences use generated API schemas and never persist guest availability locally', () => {
  assert.match(component, /import type \{ AvailabilityWindow, DiscoveryPreferences as DiscoveryPreferencesData \} from '@\/lib\/types'/);
  assert.match(component, /components\['schemas'\]\['DiscoveryPreferencesResponse'\]/);
  assert.match(component, /components\['schemas'\]\['DiscoveryPreferencesPatch'\]/);
  assert.match(component, /api<DiscoveryPreferencesResponse>\('\/me\/discovery-preferences'/);
  assert.match(component, /method: 'PATCH'/);
  assert.match(component, /if \(!actor \|\| !token \|\| !scopeKey\)/);
  assert.doesNotMatch(component, /activeScope\.current\s*=/);
  assert.match(component, /if \(controller\.signal\.aborted \|\| !active\) return/);
  assert.match(component, /controller\.abort\(\)/);
  assert.doesNotMatch(component, /localStorage|sessionStorage|navigator\.geolocation|calendar/i);
  assert.match(component, /href="\/profile"/);
  assert.match(component, /hasSavedPreferences: preferences\.updated_at !== null/);
  assert.match(component, /if \(parsed\.windows === null\)/);
});

test('failed saves keep the editor draft and retry the same discovery action', () => {
  assert.match(component, /setEditor\(current => current\.scopeKey === requestScope \? \{\s*\.\.\.current,\s*loaded: true,\s*status: 'error'/);
  assert.match(component, /editor\.retryAction === 'save'\) void save\(\)/);
  assert.match(component, /editor\.retryAction === 'clear'\) void clear\(\)/);
  assert.match(component, /persist\('clear', \{ coarse_area: null, availability: \[\] \}\)/);
});

test('settings keeps its existing display preferences and adds discovery separately', () => {
  assert.match(settings, /id="settings-language"/);
  assert.match(settings, /settings-accessibility-heading/);
  assert.match(settings, /resetPreferences/);
  assert.match(settings, /<DiscoveryPreferences \/>/);
});
