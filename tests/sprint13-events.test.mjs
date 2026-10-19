import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';

const [feed, detail, draft, attendeeStyles, draftStyles] = await Promise.all([
  readFile(new URL('../Code/Frontend/features/events/DiscoverFeed.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/EventDetail.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/DraftEditor.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/attendee-events.module.css', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/draft-editor.module.css', import.meta.url), 'utf8'),
]);

const ts = createRequire(new URL('../Code/Frontend/package.json', import.meta.url))('typescript');
const parsed = ts.createSourceFile('DraftEditor.tsx', draft, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function helper(name) {
  const declaration = parsed.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === name);
  assert.ok(declaration, `${name} exists`);
  return declaration.getText(parsed);
}
const requestHelpers = ts.transpileModule(
  [helper('tagsFromText'), helper('inputFromForm')].join('\n'),
  {compilerOptions: {target: ts.ScriptTarget.ES2022}},
).outputText;
const inputFromForm = new Function('toUtcFromManila', `${requestHelpers}; return inputFromForm;`)(
  value => `${value}:00+08:00`,
);

test('the actual draft request body preserves the selected Flash type', () => {
  const form = {
    title: ' Campus gathering ', summary: '', description: 'Meet the community',
    startsAt: '2026-10-18T16:00', endsAt: '2026-10-18T17:00',
    venueName: 'PLM', venueAddress: 'Intramuros', capacity: '8',
    bannerKey: 'community', eventType: 'flash', costLabel: 'Free',
    registrationMode: 'instant', reviewWindowMinutes: '',
    tagsText: ' community, arts ', coarseArea: ' intramuros ',
  };
  const request = inputFromForm(form);
  assert.equal(request.event_type, 'flash');
  assert.equal(request.registration_mode, 'instant');
  assert.equal(request.review_window_minutes, null);
  assert.deepEqual(request.tags, ['community', 'arts']);
  assert.equal(request.coarse_area, 'intramuros');
  assert.equal(inputFromForm({...form, eventType: 'scheduled'}).event_type, 'scheduled');
});

test('the publish checklist enforces the Flash window without limiting scheduled events', () => {
  const code = ts.transpileModule(helper('publishIssues'), {
    compilerOptions: {target: ts.ScriptTarget.ES2022},
  }).outputText;
  const publishIssues = new Function('toUtcFromManila', 'SUMMARY_MAX_LENGTH', 'MAX_CAPACITY',
    `${code}; return publishIssues;`)(value => `${value}:00+08:00`, 200, 2147483647);
  const form = {
    title: 'Campus gathering', summary: '', description: 'Meet the community',
    startsAt: '2026-10-19T16:00', endsAt: '2026-10-19T18:00',
    venueName: 'PLM', venueAddress: 'Intramuros', capacity: '8',
    bannerKey: 'garden', eventType: 'flash', costLabel: 'Free',
    registrationMode: 'instant', reviewWindowMinutes: '',
  };
  const now = Date.parse('2026-10-18T08:00:00Z');
  assert.deepEqual(publishIssues(form, now), []);
  assert.deepEqual(publishIssues({...form, startsAt: '2026-10-19T16:01'}, now),
    ['Flash events must start within 24 hours of publication.']);
  assert.deepEqual(publishIssues({...form, eventType: 'scheduled', startsAt: '2026-10-19T16:01'}, now), []);
});

test('Show Flash is a saved discovery preference composed with server filters', () => {
  assert.match(feed, /if \(search\) parameters\.set\("q", search\)/);
  assert.match(feed, /parameters\.set\("sort", sort\)/);
  assert.match(feed, /if \(myClubsActive\) parameters\.set\("my_clubs", "true"\)/);
  assert.match(feed, /if \(!preferences\.show_flash\) parameters\.set\("include_flash", "false"\)/);
  assert.match(feed, /checked=\{preferences\.show_flash\}/);
  assert.match(feed, /disabled=\{!preferencesReady\}/);
  assert.match(feed, /setPreference\("show_flash", event\.currentTarget\.checked\)/);
  assert.match(feed, /aria-label=\{t\("Show Flash events"\)\}/);
  assert.match(feed, /preferencesStatus === "saving"/);
  assert.match(feed, /preferencesStatus === "error" && preferencesError/);
  assert.match(feed, /role="alert"/);
  assert.match(feed, /t\(preferencesError\)/);
  assert.match(feed, /onClick=\{retryPreferences\}/);
  assert.match(feed, /query\.trim\(\) \|\| myClubsActive \|\| !preferences\.show_flash/);
  assert.match(feed, /const pollInterval = token && sort === "for_you" \? 30_000 : 0/);
  assert.match(feed, /useApiResource<PublicEvent\[]>\(eventsPath, token, pollInterval\)/);
  assert.doesNotMatch(feed, /\.slice\s*\(/);
  assert.doesNotMatch(feed, /\.sort\s*\(/);
});

test('For You accepts only controlled reasons in the contract order', () => {
  const reasonOrder = feed.match(/const RECOMMENDATION_REASONS:[\s\S]*?= \[([\s\S]*?)\];/)?.[1];
  assert.ok(reasonOrder, 'reason order must come from the feed implementation');
  assert.deepEqual(
    [...reasonOrder.matchAll(/"([a-z_]+)"/g)].map((match) => match[1]),
    ['club', 'flash', 'interests', 'area', 'availability'],
  );
  assert.match(feed, /flash: "Flash priority in your area"/);
  assert.match(feed, /RECOMMENDATION_REASONS\.filter\(\(reason\) => matched\.has\(reason\)\)/);
  assert.match(feed, /t\(RECOMMENDATION_LABELS\[reason\]\)/);
  assert.match(feed, /Your clubs come first, then active Flash events in your area/);
  assert.match(feed, /event\.event_type === "flash"[\s\S]*?t\("Flash event"\)/);
  assert.match(detail, /event\.event_type === "flash"[\s\S]*?t\("Flash event"\)/);
  assert.match(draft, /event\.event_type === "flash"[\s\S]*?t\("Flash event"\)/);
  assert.match(attendeeStyles, /\.eventTypeBadge\s*\{/);
  assert.match(draftStyles, /\.eventTypeBadge\s*\{/);
});

test('draft event type round-trips, defaults legacy events to scheduled, and enforces Flash registration', () => {
  const formFromDraft = draft.slice(draft.indexOf('function formFromDraft'), draft.indexOf('function inputFromForm'));
  const inputFromForm = draft.slice(draft.indexOf('function inputFromForm'), draft.indexOf('function blankForm'));
  const updateEventType = draft.slice(draft.indexOf('function updateEventType'), draft.indexOf('async function createDraft'));

  assert.match(formFromDraft, /eventType: draft\.event_type === "flash" \? "flash" : "scheduled"/);
  assert.match(inputFromForm, /event_type: form\.eventType/);
  assert.match(inputFromForm, /form\.registrationMode === "approval" && form\.reviewWindowMinutes\.trim\(\)/);
  assert.match(draft, /aria-label=\{t\("Event type"\)\}/);
  assert.match(draft, /value=\{form\.eventType\}/);
  assert.match(draft, /<option value="scheduled">\{t\("Scheduled event"\)\}<\/option>/);
  assert.match(draft, /<option value="flash">\{t\("Flash event"\)\}<\/option>/);
  assert.match(updateEventType, /if \(eventType === "flash"\)/);
  assert.match(updateEventType, /nextForm\.registrationMode = "instant"/);
  assert.match(updateEventType, /nextForm\.reviewWindowMinutes = ""/);
  assert.match(updateEventType, /updateForm\(nextForm\)/);
  assert.match(draft, /aria-label=\{t\("Registration mode"\)\}/);
  assert.match(draft, /disabled=\{form\.eventType === "flash"\}/);
  assert.match(draft, /form\.eventType !== "flash" && <option value="approval">/);
  assert.match(draft, /Flash events use instant registration and have no review window\./);
  assert.match(draft, /event=\{\{ banner_key: form\.bannerKey \|\| null, event_type: form\.eventType, title: previewTitle \}\}/);

  const publishIssues = draft.slice(draft.indexOf('function publishIssues'), draft.indexOf('function isDraftConflict'));
  assert.match(publishIssues, /Flash events must start within 24 hours of publication/);
  assert.match(draft, /tags: tagsFromText\(form\.tagsText\)/);
  assert.match(draft, /coarse_area: form\.coarseArea\.trim\(\) \|\| null/);
});
