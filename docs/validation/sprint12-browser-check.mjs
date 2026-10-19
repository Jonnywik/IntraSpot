// Bounded Sprint 12 local discovery journeys; evidence is developer-operated, not participant validation.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.SPRINT12_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT12_FIXTURES);
const apiBase = process.env.SPRINT12_API_BASE_URL.replace(/\/+$/, '');
const appBase = 'http://127.0.0.1:3000';
const output = path.resolve(process.env.SPRINT12_EVIDENCE_DIR);
await mkdir(output, {recursive: true});

let browser;
let context;
let page;
let stage = 'launch';
let activeToken = null;
const passed = [];
const browserErrors = [];
const geometry = [];
const screenshots = [];
const evidence = name => path.join(output, name);
const visible = locator => locator.waitFor({state: 'visible'});

async function capturePair(name) {
  await page.waitForFunction(() => ![
    ...document.querySelectorAll('.loading-indicator, .discovery-sidebar [role="status"]'),
  ].some(element => element.getClientRects().length > 0));
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const [kind, fullPage] of [['viewport', false], ['fullpage', true]]) {
    const file = `${name}-${kind}.png`;
    await page.screenshot({path: evidence(file), fullPage});
    screenshots.push(file);
  }
}

async function useAccount(label) {
  // These exact picker names match the existing local account control.
  await page.getByLabel('Choose a fictional local account', {exact: true}).selectOption({label});
  await page.getByRole('button', {name: 'Use fictional account', exact: true}).click();
  await visible(page.getByText(`Local session: ${label}`, {exact: true}));
  const catalog = await api('/local-demo/accounts');
  assertStatus(catalog, 200, 'Local fictional-account catalog');
  assert.ok(Array.isArray(catalog.body), 'The local account catalog returns a list');
  const selected = catalog.body.find(account => account.label === label);
  assert.ok(selected && typeof selected.token === 'string' && selected.token.length > 0,
    'The selected fictional account is present in the local demo catalog');
  activeToken = selected.token;
  return activeToken;
}

function requestUrl(pathname) {
  return `${apiBase}${pathname.startsWith('/') ? pathname : `/${pathname}`}`;
}

async function api(pathname, {method = 'GET', token = null, body, headers = {}} = {}) {
  const response = await context.request.fetch(requestUrl(pathname), {
    method,
    headers: {
      ...(token ? {Authorization: `Bearer ${token}`} : {}),
      ...headers,
    },
    ...(body === undefined ? {} : {data: body}),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // A status-only failure is enough for this harness; never retain response text.
  }
  return {status: response.status(), body: payload};
}

function assertStatus(result, expected, label) {
  assert.equal(result.status, expected, `${label} returns HTTP ${expected}`);
}

function eventPath({sort, q, my_clubs} = {}) {
  const query = new URLSearchParams();
  if (sort !== undefined) query.set('sort', sort);
  if (q !== undefined) query.set('q', q);
  if (my_clubs !== undefined) query.set('my_clubs', String(my_clubs));
  const suffix = query.toString();
  return `/events${suffix ? `?${suffix}` : ''}`;
}

async function events(options = {}, token = null) {
  const result = await api(eventPath(options), {token});
  assertStatus(result, 200, 'Event discovery');
  assert.ok(Array.isArray(result.body), 'Event discovery returns a list');
  return result.body;
}

function eventIds(rows) {
  return rows.map(row => row.id);
}

function assertNoReasons(rows, label) {
  for (const row of rows) {
    assert.deepEqual(row.recommendation_reasons, [], `${label} has no personalized reason codes`);
  }
}

function waitForEventsResponse(expected = {}) {
  return page.waitForResponse(response => {
    const request = new URL(response.url());
    if (!request.pathname.endsWith('/events')) return false;
    return Object.entries(expected).every(([key, value]) => request.searchParams.get(key) === value);
  }, {timeout: 15000});
}

async function renderedEventIds() {
  return page.locator('#public-event-results a[href*="eventId="]').evaluateAll(links => {
    const ids = links.map(link => new URL(link.href).searchParams.get('eventId')).filter(Boolean);
    return [...new Set(ids)];
  });
}

async function waitForRenderedEventIds(expectedIds) {
  await page.waitForFunction(expected => {
    const links = [...document.querySelectorAll('#public-event-results a[href*="eventId="]')];
    const ids = [...new Set(links.map(link => new URL(link.href).searchParams.get('eventId')).filter(Boolean))];
    return JSON.stringify(ids) === JSON.stringify(expected);
  }, expectedIds, {timeout: 15000});
}

const reasonLabels = {
  club: 'From one of your clubs',
  interests: 'Matches your interests',
  area: 'Matches your broad area',
  availability: 'Fits your free time',
};

async function assertRenderedReasons(expectedReasons, eventFixtures) {
  for (const [key, expected] of Object.entries(expectedReasons)) {
    const id = eventFixtures[key].id;
    const card = page.locator('article.event-card').filter({
      has: page.locator(`a[href$="eventId=${encodeURIComponent(id)}"]`),
    });
    assert.equal(await card.count(), 1, `The rendered ${key} fixture has one event card`);
    const groups = card.locator('ul[aria-label="Why this event appears"]');
    if (expected.length === 0) {
      assert.equal(await groups.count(), 0, `${key} has no unmatched reason group`);
      continue;
    }
    assert.equal(await groups.count(), 1, `${key} has one accessible reason group`);
    const group = groups.first();
    await visible(group);
    const labels = (await group.locator('li').allTextContents()).map(label => label.trim());
    assert.deepEqual(labels, expected.map(code => reasonLabels[code]), `${key} shows its matched reason labels`);
  }
}

async function waitForDiscoveryPreferencesReady() {
  await page.waitForFunction(() => {
    const heading = [...document.querySelectorAll('h2')]
      .find(element => element.textContent?.trim() === 'Discovery preferences');
    const panel = heading?.closest('section');
    return panel?.getAttribute('aria-busy') === 'false' && Boolean(panel.querySelector('form'));
  }, null, {timeout: 15000});
}

async function waitForSettingsReady() {
  await page.locator('#settings-language').waitFor({state: 'visible'});
  await page.waitForFunction(() =>
    document.querySelector('section[aria-labelledby="settings-preferences-heading"]')
      ?.getAttribute('aria-busy') === 'false',
  null, {timeout: 15000});
  await waitForDiscoveryPreferencesReady();
}

async function selectedTheme() {
  return page.locator('input[name="settings-theme"]:checked').getAttribute('value').catch(() => null);
}

async function assertMobile(width, height) {
  await page.setViewportSize({width, height});
  const metrics = await page.evaluate(() => ({
    innerWidth,
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    navCount: document.querySelectorAll('.mobile-nav a').length,
  }));
  assert.ok(metrics.scrollWidth <= width + 1, `The ${width}px page has no horizontal overflow`);
  assert.equal(metrics.navCount, 4, 'The four attendee destinations remain present');
  geometry.push({width, height, ...metrics});
}

function sanitizedMessage(error) {
  return String(error?.message ?? 'Browser check failed')
    .replace(/Bearer\s+[^\s"']+/gi, 'Bearer [redacted]')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[redacted-email]')
    .replace(/https?:\/\/[^\s)]+/gi, '[redacted-url]')
    .replace(/\b[0-9a-f]{8}-[0-9a-f-]{27,}\b/gi, '[redacted-id]')
    .replace(/\b[A-Za-z0-9_-]{24,}\b/g, '[redacted-value]')
    .split(/\r?\n/, 1)[0]
    .slice(0, 300);
}

try {
  browser = await chromium.launch({channel: 'msedge', headless: true});
  context = await browser.newContext({viewport: {width: 1440, height: 900}});
  page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on('pageerror', () => browserErrors.push('pageerror'));

  stage = 'guest fallback and search';
  await page.goto(`${appBase}/`, {waitUntil: 'networkidle'});
  const sort = page.getByLabel('Sort by', {exact: true});
  await visible(sort);
  assert.equal(await sort.inputValue(), 'upcoming', 'Guests start with Upcoming');
  const guestDefault = await events({q: fixtures.titleSearch});
  assert.deepEqual(eventIds(guestDefault), fixtures.expectedUpcoming, 'Omitted guest sort keeps Upcoming order');
  const guestForYou = await events({sort: 'for_you', q: fixtures.titleSearch});
  assert.deepEqual(eventIds(guestForYou), eventIds(guestDefault), 'Guest For You falls back to Upcoming');
  assertNoReasons(guestForYou, 'Guest fallback');
  const guestSearch = await events({q: fixtures.titleSearch});
  assert.deepEqual(eventIds(guestSearch), fixtures.expectedUpcoming, 'Guest search matches the published fixture titles');
  const waitGuestSearch = waitForEventsResponse({q: fixtures.titleSearch});
  await page.locator('#event-search').fill(fixtures.titleSearch);
  await waitGuestSearch;
  await waitForRenderedEventIds(fixtures.expectedUpcoming);
  assert.deepEqual(await renderedEventIds(), fixtures.expectedUpcoming, 'The rendered guest search matches the API results');
  passed.push('Guest Upcoming fallback and title search');

  stage = 'signed-in For You ranking and reasons';
  const waitForPersonalFeed = waitForEventsResponse({sort: 'for_you'});
  const studentToken = await useAccount('Fictional student 1');
  await waitForPersonalFeed;
  assert.equal(await sort.inputValue(), 'for_you', 'Signed-in discovery defaults to For You');
  assert.equal((await sort.locator('option:checked').textContent()).trim(), 'For You',
    'The default sort control exposes its current For You option');
  const personalized = await events({sort: 'for_you', q: fixtures.titleSearch}, studentToken);
  assert.deepEqual(eventIds(personalized), fixtures.expectedForYouDefault,
    'Club and distinct-interest ranks apply before optional preferences are set');
  await waitForRenderedEventIds(fixtures.expectedForYouDefault);
  for (const [key, expected] of Object.entries(fixtures.expectedReasonsDefault)) {
    const row = personalized.find(event => event.id === fixtures.events[key].id);
    assert.ok(row, `The ${key} fixture remains in For You discovery`);
    assert.deepEqual(row.recommendation_reasons, expected, `${key} exposes only its matched reason codes in contract order`);
  }
  const summary = page.getByText('How For You works', {exact: true});
  const explainer = page.locator('details').filter({has: summary});
  assert.equal(await explainer.count(), 1, 'The For You explainer uses the native details element');
  assert.equal(await explainer.evaluate(element => element.open), false,
    'The For You explainer starts collapsed');
  const firstCardTop = await page.locator('article.event-card').first()
    .evaluate(element => element.getBoundingClientRect().top);
  assert.ok(firstCardTop < 900, 'The first For You card begins within the initial desktop viewport');
  await assertRenderedReasons(fixtures.expectedReasonsDefault, fixtures.events);
  await summary.click();
  const settingsLink = explainer.getByRole('link', {
    name: 'Manage optional preferences in Settings', exact: true,
  });
  await visible(settingsLink);
  assert.equal(new URL(await settingsLink.getAttribute('href'), appBase).pathname, '/settings',
    'Optional discovery preferences link to standard Settings');
  await settingsLink.click();
  await page.waitForURL('**/settings');
  passed.push('Signed-in For You default, collapsed explainer, and matched reason groups');

  stage = 'discovery preference update, persistence, clear, and theme';
  const defaults = await api('/me/discovery-preferences', {token: studentToken});
  assertStatus(defaults, 200, 'Default discovery preferences');
  assert.equal(defaults.body.coarse_area, null, 'Missing area defaults to null');
  assert.deepEqual(defaults.body.availability, [], 'Missing windows default to an empty list');
  const windows = [
    {weekday: 0, start_minute: 540, end_minute: 720},
    {weekday: 6, start_minute: 1380, end_minute: 1440},
    {weekday: 0, start_minute: 0, end_minute: 60},
  ];
  await waitForSettingsReady();
  const themeBefore = await selectedTheme();
  assert.ok(themeBefore, 'Settings exposes a selected theme before discovery changes');
  const areaInput = page.getByLabel('Broad named area (not a street address)', {exact: true});
  await areaInput.fill(' Intramuros ');
  const availabilitySection = page.locator('section[aria-labelledby$="-availability"]');
  const addWindow = availabilitySection.getByRole('button', {name: 'Add availability window', exact: true});
  await addWindow.click();
  await addWindow.click();
  await addWindow.click();
  const windowRows = availabilitySection.locator('fieldset');
  assert.equal(await windowRows.count(), 3, 'Settings adds three weekly availability rows');
  await page.setViewportSize({width:390, height:844});
  await page.getByRole('region', {name:'Discovery preferences', exact:true})
    .screenshot({path:evidence('settings-discovery-preferences-390-section.png')});
  await page.setViewportSize({width:1440, height:900});
  await page.evaluate(() => window.scrollTo(0, 0));
  const mondayMorning = windowRows.nth(0);
  await mondayMorning.locator('select').selectOption('0');
  await mondayMorning.locator('input[type="time"]').nth(0).fill('09:00');
  await mondayMorning.locator('input[type="time"]').nth(1).fill('12:00');
  const sundayMidnight = windowRows.nth(1);
  await sundayMidnight.locator('select').selectOption('6');
  await sundayMidnight.locator('input[type="time"]').nth(0).fill('23:00');
  await sundayMidnight.getByLabel('Ends at midnight (24:00)', {exact: true}).check();
  const mondayAfterMidnight = windowRows.nth(2);
  await mondayAfterMidnight.locator('select').selectOption('0');
  await mondayAfterMidnight.locator('input[type="time"]').nth(0).fill('00:00');
  await mondayAfterMidnight.locator('input[type="time"]').nth(1).fill('01:00');
  const uiSaveWait = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith('/me/discovery-preferences')
      && response.request().method() === 'PATCH', {timeout: 15000});
  await page.getByRole('button', {name: 'Save discovery preferences', exact: true}).click();
  const uiSaveResponse = await uiSaveWait;
  assert.equal(uiSaveResponse.status(), 200, 'The Settings form saves discovery preferences');
  assert.deepEqual(uiSaveResponse.request().postDataJSON(), {
    coarse_area: 'Intramuros', availability: windows,
  }, 'The Settings form submits the selected area and Manila windows');
  const firstSave = await uiSaveResponse.json();
  assert.equal(firstSave.coarse_area, 'intramuros', 'Named area is normalized');
  assert.deepEqual(firstSave.availability, windows, 'Weekly windows preserve their fixed Manila minutes');
  const partialSave = await api('/me/discovery-preferences', {
    method: 'PATCH', token: studentToken, body: {coarse_area: 'INTRAMUROS'},
  });
  assertStatus(partialSave, 200, 'Partial discovery preference update');
  assert.deepEqual(partialSave.body.availability, windows, 'Omitted windows remain unchanged');

  await page.goto(`${appBase}/settings`, {waitUntil: 'networkidle'});
  await waitForSettingsReady();
  await page.reload({waitUntil: 'networkidle'});
  await waitForSettingsReady();
  assert.equal(await areaInput.inputValue(), 'intramuros', 'Settings rehydrates the saved area after reload');
  assert.deepEqual(await windowRows.evaluateAll(rows => rows.map(row => ({
    weekday: row.querySelector('select').value,
    start: row.querySelectorAll('input[type="time"]')[0].value,
    end: row.querySelectorAll('input[type="time"]')[1].value,
    endsAtMidnight: row.querySelector('input[type="checkbox"]').checked,
  }))), [
    {weekday: '0', start: '09:00', end: '12:00', endsAtMidnight: false},
    {weekday: '6', start: '23:00', end: '23:59', endsAtMidnight: true},
    {weekday: '0', start: '00:00', end: '01:00', endsAtMidnight: false},
  ], 'Settings rehydrates all saved weekday and time controls');
  const themeAfterSave = await selectedTheme();
  assert.equal(themeAfterSave, themeBefore, 'Discovery updates do not change the display theme');
  const persisted = await api('/me/discovery-preferences', {token: studentToken});
  assert.deepEqual(persisted.body.availability, windows, 'Windows persist across a settings reload');

  const waitForSavedFeed = waitForEventsResponse({sort: 'for_you'});
  await page.goto(`${appBase}/`, {waitUntil: 'networkidle'});
  await waitForSavedFeed;
  const waitForSavedSearch = waitForEventsResponse({sort: 'for_you', q: fixtures.titleSearch});
  await page.locator('#event-search').fill(fixtures.titleSearch);
  await waitForSavedSearch;
  const savedPreferenceFeed = await events({sort: 'for_you', q: fixtures.titleSearch}, studentToken);
  assert.deepEqual(eventIds(savedPreferenceFeed), fixtures.expectedForYou,
    'Saved area and whole-window availability change the live For You order');
  await waitForRenderedEventIds(fixtures.expectedForYou);
  for (const [key, expected] of Object.entries(fixtures.expectedReasons)) {
    const row = savedPreferenceFeed.find(event => event.id === fixtures.events[key].id);
    assert.ok(row, `The ${key} fixture remains in the saved-preference feed`);
    assert.deepEqual(row.recommendation_reasons, expected, `${key} returns its matched reason codes`);
  }
  await assertRenderedReasons(fixtures.expectedReasons, fixtures.events);
  await page.goto(`${appBase}/settings`, {waitUntil: 'networkidle'});
  await waitForSettingsReady();

  const uiClearWait = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith('/me/discovery-preferences')
      && response.request().method() === 'PATCH', {timeout: 15000});
  await page.getByRole('button', {name: 'Clear discovery preferences', exact: true}).click();
  const uiClearResponse = await uiClearWait;
  assert.equal(uiClearResponse.status(), 200, 'The Settings clear action succeeds');
  assert.deepEqual(uiClearResponse.request().postDataJSON(), {
    coarse_area: null, availability: [],
  }, 'The Settings clear action submits explicit area and window clears');
  const cleared = await uiClearResponse.json();
  assert.equal(cleared.coarse_area, null, 'Null clears the saved area');
  assert.deepEqual(cleared.availability, [], 'An empty list clears saved windows');
  await waitForDiscoveryPreferencesReady();
  assert.equal(await areaInput.inputValue(), '', 'Clearing removes the area from Settings');
  assert.equal(await windowRows.count(), 0, 'Clearing removes all availability rows');
  assert.equal(await selectedTheme(), themeBefore, 'Clearing discovery preferences leaves the theme unchanged');

  const waitForClearedFeed = waitForEventsResponse({sort: 'for_you'});
  await page.goto(`${appBase}/`, {waitUntil: 'networkidle'});
  await waitForClearedFeed;
  const waitForClearedSearch = waitForEventsResponse({sort: 'for_you', q: fixtures.titleSearch});
  await page.locator('#event-search').fill(fixtures.titleSearch);
  await waitForClearedSearch;
  const clearedFeed = await events({sort: 'for_you', q: fixtures.titleSearch}, studentToken);
  assert.deepEqual(eventIds(clearedFeed), fixtures.expectedForYouDefault,
    'Clearing preferences restores ranking without area or availability boosts');
  await waitForRenderedEventIds(fixtures.expectedForYouDefault);
  for (const [key, expected] of Object.entries(fixtures.expectedReasonsDefault)) {
    const row = clearedFeed.find(event => event.id === fixtures.events[key].id);
    assert.ok(row, `The ${key} fixture remains after clearing preferences`);
    assert.deepEqual(row.recommendation_reasons, expected, `${key} loses unmatched private-preference reasons`);
  }
  await assertRenderedReasons(fixtures.expectedReasonsDefault, fixtures.events);
  passed.push('Settings area/windows save, reload, clear, reset ranking, and preserve theme');

  stage = 'account preference isolation';
  await page.goto(`${appBase}/settings`, {waitUntil: 'networkidle'});
  const secondStudentToken = await useAccount('Fictional student 2');
  await waitForDiscoveryPreferencesReady();
  const secondAreaInput = page.getByLabel('Broad named area (not a street address)', {exact: true});
  const secondAvailabilitySection = page.locator('section[aria-labelledby$="-availability"]');
  assert.equal(await secondAreaInput.inputValue(), '', 'A second account starts with its own blank area');
  assert.equal(await secondAvailabilitySection.locator('fieldset').count(), 0,
    "A second account starts without another account's availability rows");
  const secondDefaults = await api('/me/discovery-preferences', {token: secondStudentToken});
  assertStatus(secondDefaults, 200, 'Second account discovery preferences');
  assert.equal(secondDefaults.body.coarse_area, null, 'A second account does not inherit the first area');
  assert.deepEqual(secondDefaults.body.availability, [], 'A second account does not inherit the first windows');
  await secondAreaInput.fill('Quiapo');
  const secondSaveWait = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith('/me/discovery-preferences')
      && response.request().method() === 'PATCH', {timeout: 15000});
  await page.getByRole('button', {name: 'Save discovery preferences', exact: true}).click();
  const secondSaveResponse = await secondSaveWait;
  assert.equal(secondSaveResponse.status(), 200, 'The second account saves its own Settings value');
  const secondSave = await secondSaveResponse.json();
  assert.equal(secondSave.coarse_area, 'quiapo', 'The second account can save its own area');
  const secondFeed = await events({sort: 'for_you', q: fixtures.titleSearch}, secondStudentToken);
  const areaEvent = secondFeed.find(event => event.id === fixtures.events.area.id);
  assert.ok(areaEvent, 'The area fixture remains visible to another account');
  assert.equal(areaEvent.recommendation_reasons.includes('area'), false,
    'A different account cannot receive the first account area-match reason');

  const restoredStudentToken = await useAccount('Fictional student 1');
  await waitForDiscoveryPreferencesReady();
  assert.equal(await secondAreaInput.inputValue(), '', 'The first account remains cleared after switching back');
  assert.equal(await secondAvailabilitySection.locator('fieldset').count(), 0,
    'The first account windows remain cleared after switching back');
  const firstAccountAfterSwitch = await api('/me/discovery-preferences', {token: restoredStudentToken});
  assert.equal(firstAccountAfterSwitch.body.coarse_area, null, 'The first account remains cleared after switching back');
  assert.deepEqual(firstAccountAfterSwitch.body.availability, [], 'The first account windows remain cleared');

  await useAccount('Fictional student 2');
  await waitForDiscoveryPreferencesReady();
  assert.equal(await secondAreaInput.inputValue(), 'quiapo', 'The second account retains only its own saved area');
  const secondClearWait = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith('/me/discovery-preferences')
      && response.request().method() === 'PATCH', {timeout: 15000});
  await page.getByRole('button', {name: 'Clear discovery preferences', exact: true}).click();
  const secondClearResponse = await secondClearWait;
  assert.equal(secondClearResponse.status(), 200, 'The second account can clear its isolated preference');
  const secondClear = await secondClearResponse.json();
  assert.equal(secondClear.coarse_area, null, 'The second account clear leaves no area behind');

  const restoredFirstToken = await useAccount('Fictional student 1');
  passed.push('Discovery preferences stay isolated between accounts');

  stage = 'explicit Upcoming and Newest override ranking';
  activeToken = restoredFirstToken;
  await page.goto(`${appBase}/`, {waitUntil: 'networkidle'});
  const upcoming = await events({sort: 'upcoming', q: fixtures.titleSearch}, activeToken);
  const newest = await events({sort: 'newest', q: fixtures.titleSearch}, activeToken);
  assert.deepEqual(eventIds(upcoming), fixtures.expectedUpcoming, 'Upcoming orders by event start');
  assert.deepEqual(eventIds(newest), fixtures.expectedNewest, 'Newest orders by publication time');
  assertNoReasons(upcoming, 'Upcoming chronology');
  assertNoReasons(newest, 'Newest chronology');
  assert.notEqual(fixtures.expectedForYou[0], fixtures.expectedUpcoming[0],
    'The fixture makes chronological order visibly differ from club-first rank');
  const sortSelect = page.getByLabel('Sort by', {exact: true});
  let wait = waitForEventsResponse({sort: 'upcoming'});
  await sortSelect.selectOption('upcoming');
  await wait;
  await waitForRenderedEventIds(fixtures.expectedUpcoming);
  assert.deepEqual(await renderedEventIds(), fixtures.expectedUpcoming, 'The Upcoming control renders chronology');
  wait = waitForEventsResponse({sort: 'newest'});
  await sortSelect.selectOption('newest');
  await wait;
  await waitForRenderedEventIds(fixtures.expectedNewest);
  assert.deepEqual(await renderedEventIds(), fixtures.expectedNewest, 'The Newest control renders publication order');
  passed.push('Upcoming and Newest override For You ranking and reasons');

  stage = 'My Clubs and organization search composition';
  wait = waitForEventsResponse({sort: 'for_you'});
  await sortSelect.selectOption('for_you');
  await wait;
  const otherSearchWait = waitForEventsResponse({q: fixtures.otherOrganizationName});
  await page.locator('#event-search').fill(fixtures.otherOrganizationName);
  await otherSearchWait;
  await waitForRenderedEventIds(fixtures.expectedOtherOrganization);
  assert.deepEqual(await renderedEventIds(), fixtures.expectedOtherOrganization,
    'Organization-name search returns matching public events');
  const clubs = page.locator('button[aria-controls="public-event-results"]');
  await visible(clubs);
  wait = waitForEventsResponse({q: fixtures.otherOrganizationName, my_clubs: 'true'});
  await clubs.click();
  await wait;
  await waitForRenderedEventIds([]);
  assert.deepEqual(await renderedEventIds(), [], 'My Clubs composes with a search for another organization');
  const ownSearchWait = waitForEventsResponse({q: fixtures.clubOrganizationName, my_clubs: 'true'});
  await page.locator('#event-search').fill(fixtures.clubOrganizationName);
  await ownSearchWait;
  await waitForRenderedEventIds([fixtures.events.club.id]);
  assert.deepEqual(await renderedEventIds(), [fixtures.events.club.id],
    'My Clubs and organization-name search retain the member club event');
  passed.push('My Clubs composes with organization-name search');

  stage = 'draft metadata save, owner access, publishing, and public privacy';
  const draftId = fixtures.draft.id;
  const ownerToken = await useAccount('Fictional organizer');
  const initialDraft = await api(`/events/${draftId}/draft`, {token: ownerToken});
  assertStatus(initialDraft, 200, 'Owner draft read');
  assert.ok(initialDraft.body.draft_version, 'Private draft includes its conditional-save version');
  const versionHeader = { 'If-Match': `"${initialDraft.body.draft_version}"` };
  const deniedSave = await api(`/events/${draftId}/draft`, {
    method: 'PATCH', token: restoredStudentToken, body: {tags: ['music'], coarse_area: 'intramuros'}, headers: versionHeader,
  });
  assertStatus(deniedSave, 403, 'A non-manager cannot save draft metadata');
  const deniedPublish = await api(`/events/${draftId}/publish`, {
    method: 'POST', token: restoredStudentToken, headers: versionHeader,
  });
  assertStatus(deniedPublish, 403, 'A non-manager cannot publish a draft');
  const staleSave = await api(`/events/${draftId}/draft`, {
    method: 'PATCH', token: ownerToken, body: {tags: ['stale'], coarse_area: 'stale'},
    headers: {'If-Match': '"stale"'},
  });
  assertStatus(staleSave, 409, 'A stale draft version is rejected');
  const unchangedDraft = await api(`/events/${draftId}/draft`, {token: ownerToken});
  assert.deepEqual(unchangedDraft.body.tags, [], 'A stale save does not change draft tags');
  assert.equal(unchangedDraft.body.coarse_area, null, 'A stale save does not change draft area');
  await page.goto(`${appBase}/draft?${new URLSearchParams({eventId: draftId})}`, {waitUntil: 'networkidle'});
  const tagsInput = page.getByLabel('Tags (optional)', {exact: true});
  const draftAreaInput = page.getByLabel('Broad area (optional)', {exact: true});
  await visible(tagsInput);
  await visible(draftAreaInput);
  const draftSaveWait = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith(`/events/${draftId}/draft`)
      && response.request().method() === 'PATCH'
      && response.request().postDataJSON()?.coarse_area === 'Intra  muros', {timeout: 15000});
  await tagsInput.fill(' Music ,MUSIC,Art ');
  await draftAreaInput.fill('  Intra  muros  ');
  const saveDraftButton = page.getByRole('button', {name: 'Save draft', exact: true});
  if (await saveDraftButton.isEnabled()) await saveDraftButton.click();
  const draftSaveResponse = await draftSaveWait;
  assert.equal(draftSaveResponse.status(), 200, 'The owner saves optional metadata through the draft editor');
  const draftSaveRequest = draftSaveResponse.request().postDataJSON();
  assert.deepEqual(draftSaveRequest.tags, ['Music', 'MUSIC', 'Art'], 'The draft editor submits the entered tags');
  assert.equal(draftSaveRequest.coarse_area, 'Intra  muros', 'The draft editor trims surrounding area whitespace');
  const savedFromEditor = await draftSaveResponse.json();
  assert.deepEqual(savedFromEditor.tags, ['music', 'art'], 'The editor response returns normalized tags');
  assert.equal(savedFromEditor.coarse_area, 'intra muros', 'The editor response returns normalized broad area');
  const savedDraft = await api(`/events/${draftId}/draft`, {token: ownerToken});
  assertStatus(savedDraft, 200, 'Owner draft after UI save');
  assert.notEqual(savedDraft.body.draft_version, unchangedDraft.body.draft_version,
    'Optional metadata participates in the draft content version');
  page.once('dialog', dialog => dialog.accept());
  const publishWait = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith(`/events/${draftId}/publish`)
      && response.request().method() === 'POST', {timeout: 15000});
  await page.getByRole('button', {name: 'Publish', exact: true}).click();
  const publish = await publishWait;
  assert.equal(publish.status(), 200, 'The owner publishes the saved optional metadata through the editor');
  assert.equal(publish.request().headers()['if-match'], `"${savedDraft.body.draft_version}"`,
    'The editor publishes only the saved draft version');
  const publishBody = await publish.json();
  assert.equal(publishBody.status, 'published', 'Saved optional metadata does not block publication');
  const publicEvent = await api(`/events/${draftId}`);
  assertStatus(publicEvent, 200, 'Public event detail');
  assert.deepEqual(publicEvent.body.tags, ['music', 'art'], 'Published event exposes its own tags');
  assert.equal(publicEvent.body.coarse_area, 'intra muros', 'Published event exposes its own coarse area');
  assert.deepEqual(publicEvent.body.recommendation_reasons, [], 'Public detail has no personalized reasons');
  assert.equal(Object.hasOwn(publicEvent.body, 'availability'), false, 'Public event detail omits private availability');
  assert.equal(Object.hasOwn(publicEvent.body, 'user_id'), false, 'Public event detail omits preference ownership');
  passed.push('Draft metadata saves and publishes owner-only without exposing private preferences');

  stage = 'mobile 320px and 390px layouts';
  await useAccount('Fictional student 1');
  await page.goto(`${appBase}/settings`, {waitUntil: 'networkidle'});
  await waitForSettingsReady();
  await assertMobile(320, 700);
  await capturePair('mobile-settings-320');
  await assertMobile(390, 844);
  await capturePair('mobile-settings-390');
  passed.push('Mobile Settings and discovery preferences at 320px and 390px');

  await page.goto(`${appBase}/`, {waitUntil: 'networkidle'});
  await assertMobile(320, 700);
  await capturePair('mobile-discover-320');
  await assertMobile(390, 844);
  await capturePair('mobile-discover-390');
  passed.push('Mobile discovery at 320px and 390px');

  stage = 'Filipino extra-large mobile';
  await page.goto(`${appBase}/settings`, {waitUntil: 'networkidle'});
  await waitForSettingsReady();
  const waitSizeSave = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith('/me/preferences') && response.request().method() === 'PATCH',
  {timeout: 15000});
  await page.locator('input[name="settings-text-size"][value="extra_large"]').check();
  await waitSizeSave;
  await page.waitForFunction(() => document.documentElement.dataset.textSize === 'extra_large', null,
    {timeout: 15000});
  const waitFilipino = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith('/me/preferences') && response.request().method() === 'PATCH',
  {timeout: 15000});
  await page.locator('#settings-language').selectOption('fil');
  await waitFilipino;
  await page.waitForFunction(() => document.documentElement.lang === 'fil', null, {timeout: 15000});
  await page.waitForFunction(() => document.documentElement.dataset.textSize === 'extra_large', null,
    {timeout: 15000});
  await assertMobile(390, 844);
  await capturePair('mobile-settings-filipino-xl-390');
  await page.goto(`${appBase}/`, {waitUntil: 'networkidle'});
  await assertMobile(390, 844);
  assert.equal(await page.locator('.mobile-nav a').count(), 4, 'Filipino keeps four mobile destinations');
  await capturePair('mobile-discover-filipino-xl-390');
  passed.push('Filipino extra-large discovery at 390px');

  stage = 'desktop 1440px';
  await page.goto(`${appBase}/settings`, {waitUntil: 'networkidle'});
  const waitStandard = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith('/me/preferences') && response.request().method() === 'PATCH',
  {timeout: 15000});
  await page.locator('input[name="settings-text-size"][value="standard"]').check();
  await waitStandard;
  await page.waitForFunction(() => document.documentElement.dataset.textSize === 'standard');
  const waitEnglish = page.waitForResponse(response =>
    new URL(response.url()).pathname.endsWith('/me/preferences') && response.request().method() === 'PATCH',
  {timeout: 15000});
  await page.locator('#settings-language').selectOption('en');
  await waitEnglish;
  await page.waitForFunction(() => document.documentElement.lang === 'en', null, {timeout: 15000});
  await page.goto(`${appBase}/`, {waitUntil: 'networkidle'});
  await page.setViewportSize({width: 1440, height: 900});
  const desktop = await page.evaluate(() => ({
    width: innerWidth,
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    desktopNav: document.querySelectorAll('.desktop-nav a').length,
  }));
  assert.ok(desktop.scrollWidth <= desktop.width + 1, 'The 1440px desktop feed has no horizontal overflow');
  assert.ok(desktop.desktopNav > 0, 'Desktop navigation is rendered');
  geometry.push({width: 1440, height: 900, ...desktop});
  await capturePair('desktop-discover-1440');
  passed.push('Desktop discovery at 1440px');

  assert.deepEqual(browserErrors, [], 'The browser reports no uncaught page errors');
} catch (error) {
  if (page) {
    try {
      await page.screenshot({path: evidence('failure-viewport.png'), fullPage: false});
      await page.screenshot({path: evidence('failure-fullpage.png'), fullPage: true});
      const failurePath = new URL(page.url()).pathname;
      await writeFile(evidence('failure.json'), JSON.stringify({
        stage,
        pathname: failurePath,
        browserErrorCount: browserErrors.length,
        message: sanitizedMessage(error),
      }, null, 2));
    } catch {
      // Failure evidence is best effort and excludes browser/network response bodies.
    }
  }
  throw new Error('Sprint 12 browser journey failed; inspect sanitized timestamped evidence.');
} finally {
  if (browser) await browser.close();
  await writeFile(evidence('results.json'), JSON.stringify({
    method: 'Isolated PostgreSQL with local Microsoft Edge; not participant or physical-device validation',
    passed,
    browserErrorCount: browserErrors.length,
    screenshots,
    geometry,
  }, null, 2));
}
