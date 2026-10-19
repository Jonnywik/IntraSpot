import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.SPRINT13_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT13_FIXTURES);
const apiBase = process.env.SPRINT13_API_BASE_URL.replace(/\/+$/, '');
const appBase = 'http://127.0.0.1:3000';
const output = path.resolve(process.env.SPRINT13_EVIDENCE_DIR);
await mkdir(output, {recursive: true});

let browser;
let context;
let page;
let stage = 'launch';
let activeToken = null;
const passed = [];
const screenshots = [];
const geometry = [];
let browserErrorCount = 0;
const browserErrors = new Set();
const failedRequests = new Set();
const sanitize = value => String(value).replace(/eyJ[A-Za-z0-9._-]+/g, '[redacted]')
  .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[redacted]').slice(0, 2400);
const evidence = name => path.join(output, name);

function eventPath(id) {
  return `/events/${encodeURIComponent(id)}`;
}

async function api(pathname, {token, method = 'GET', body, headers = {}} = {}) {
  const response = await fetch(`${apiBase}${pathname}`, {
    method,
    headers: {
      ...(body === undefined ? {} : {'Content-Type': 'application/json'}),
      ...(token ? {Authorization: `Bearer ${token}`} : {}),
      ...headers,
    },
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  return {status: response.status, body: payload};
}

function eventQuery(filters) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null) query.set(key, String(value));
  }
  return query.toString();
}

function waitForEventsResponse(filters) {
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    if (!url.pathname.endsWith('/api/v1/events')) return false;
    const params = url.searchParams;
    return Object.entries(filters).every(([key, value]) => params.get(key) === String(value));
  }, {timeout: 20000});
}

function waitForPreferencePatch() {
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname.endsWith('/api/v1/me/preferences') &&
      response.request().method() === 'PATCH';
  }, {timeout: 20000});
}

function waitForRegistration(id) {
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname.endsWith(`/api/v1/events/${id}/registrations`) &&
      response.request().method() === 'POST';
  }, {timeout: 20000});
}

async function waitForSettled() {
  await page.waitForFunction(() => {
    const busy = [...document.querySelectorAll('[aria-busy="true"]')]
      .some(element => element.getClientRects().length > 0);
    const loading = [...document.querySelectorAll('.loading-indicator, p[role="status"]')]
      .some(element => element.getClientRects().length > 0 &&
        (element.matches('.loading-indicator') || /loading|nilo-load/i.test(element.textContent)));
    return !busy && !loading;
  }, null, {timeout: 20000});
}

async function waitForFlashSwitchReady() {
  const control = page.getByRole('switch', {name: 'Show Flash events', exact: true});
  await control.waitFor({state: 'visible'});
  await page.waitForFunction(() => {
    const input = document.querySelector('input[type="checkbox"][role="switch"]');
    return input !== null && !input.disabled;
  }, null, {timeout: 20000});
  return control;
}

async function renderedEventIds() {
  return page.locator('#public-event-results a[href*="eventId="]').evaluateAll(links =>
    links.map(link => new URL(link.href).searchParams.get('eventId'))
      .filter((id, index, all) => id && all.indexOf(id) === index));
}

async function waitForRenderedEventIds(expected) {
  await page.waitForFunction(expectedIds => {
    const ids = [...document.querySelectorAll('#public-event-results a[href*="eventId="]')]
      .map(link => new URL(link.href).searchParams.get('eventId'))
      .filter((id, index, all) => id && all.indexOf(id) === index);
    return JSON.stringify(ids) === JSON.stringify(expectedIds);
  }, expected, {timeout: 20000});
}

async function readEvents(filters, token) {
  const query = eventQuery(filters);
  const result = await api(`/events${query ? `?${query}` : ''}`, {token});
  assert.equal(result.status, 200, 'Public discovery API responds successfully');
  return result.body;
}

async function useAccount(label) {
  // The app persists only this fictional label; the returned bearer token stays in memory.
  await page.getByLabel('Choose a fictional local account', {exact: true}).selectOption({label});
  await page.getByRole('button', {name: 'Use fictional account', exact: true}).click();
  await page.getByText(`Local session: ${label}`, {exact: true}).waitFor({state: 'visible'});
  const catalog = await api('/local-demo/accounts');
  assert.equal(catalog.status, 200, 'Fictional local accounts are available');
  const account = catalog.body.find(item => item.label === label);
  assert.ok(account, 'The requested fictional local account exists');
  const actor = await api('/me', {token: account.token});
  assert.equal(actor.status, 200, 'The selected fictional account can read its session');
  return {token: account.token};
}

async function assertApiOrder(filters, expectedIds, token) {
  const rows = await readEvents(filters, token);
  assert.deepEqual(rows.map(row => row.id), expectedIds, 'The public API order matches the fixture contract');
  return rows;
}

async function assertCleanViewport(width, height) {
  await page.setViewportSize({width, height});
  await waitForSettled();
  const metrics = await page.evaluate(() => ({
    innerWidth,
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    navCount: document.querySelectorAll('.mobile-nav a').length,
    scrollHeight: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight),
  }));
  assert.ok(metrics.scrollWidth <= width + 1, `The ${width}px viewport has no horizontal overflow`);
  assert.equal(metrics.navCount, 4, 'The four attendee destinations remain present');
  geometry.push({width, height, scrollWidth: metrics.scrollWidth, navCount: metrics.navCount});
  return metrics;
}

async function captureSettledViewport(name) {
  await waitForSettled();
  const metrics = await page.evaluate(() => ({
    width: innerWidth,
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    height: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight),
  }));
  assert.ok(metrics.scrollWidth <= metrics.width + 1, 'The screenshot viewport is clean');
  await page.evaluate(() => window.scrollTo(0, 0));
  const viewportFile = `${name}-viewport.png`;
  await page.screenshot({path: evidence(viewportFile), fullPage: false});
  screenshots.push(viewportFile);
  if (metrics.height <= 6500) {
    const fullPageFile = `${name}-fullpage.png`;
    await page.screenshot({path: evidence(fullPageFile), fullPage: true});
    screenshots.push(fullPageFile);
  }
}

async function feedWithSearch(filters) {
  const response = waitForEventsResponse(filters);
  await page.locator('#event-search').fill(filters.q);
  await response;
  await waitForSettled();
}

async function navigateToFixtureEvent(event) {
  const response = waitForEventsResponse({sort: 'for_you'});
  await page.goto(`${appBase}/`, {waitUntil: 'domcontentloaded'});
  await response;
  await waitForSettled();
  await feedWithSearch({sort: 'for_you', q: fixtures.titleSearch});
  const link = page.locator(`#public-event-results a[href*="eventId=${event.id}"]`).first();
  await link.waitFor({state: 'visible'});
  await link.click();
  await page.getByRole('heading', {name: event.title, level: 1, exact: true}).waitFor({state: 'visible'});
  await waitForSettled();
}

async function registerFromDetail(event, expectedStatus) {
  const actionName = expectedStatus === 'waitlisted' ? 'Join waitlist' : 'Register';
  await page.getByRole('button', {name: actionName, exact: true}).click();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor({state: 'visible'});
  const submitName = expectedStatus === 'waitlisted' ? 'Join waitlist' : 'Confirm your registration';
  const responseWait = waitForRegistration(event.id);
  await dialog.getByRole('button', {name: submitName, exact: true}).click();
  const response = await responseWait;
  assert.equal(response.status(), 201, 'The registration API accepts the UI submission');
  const result = await response.json();
  assert.equal(result.status, expectedStatus, 'The UI receives the expected registration state');
  await waitForSettled();
}

async function assertMyEventStatus(tabName, eventTitle, status) {
  await page.getByRole('tab', {name: new RegExp(`^${tabName}`)}).click();
  const eventHeading = page.locator('#registration-panel')
    .getByRole('heading', {name: eventTitle, exact: true});
  await eventHeading.waitFor({state: 'visible'});
  assert.equal(await eventHeading.count(), 1, 'My Events retains the registration by event title');
  const card = eventHeading.locator('xpath=ancestor::article[1]');
  assert.equal(await card.locator(`.status-chip.${status}`).count(), 1,
    'My Events retains the actual registration status');
}

try {
  browser = await chromium.launch({channel: 'msedge', headless: true});
  context = await browser.newContext({viewport: {width: 1440, height: 900}});
  page = await context.newPage();
  page.on('pageerror', error => { browserErrorCount += 1; browserErrors.add(sanitize(error.message)); });
  page.on('console', message => {
    if (message.type() === 'error') {
      browserErrorCount += 1;
      browserErrors.add(sanitize(`${message.text()} ${message.location().url ?? ''}`));
    }
  });
  page.on('response', response => {
    if (response.status() >= 400) {
      const url = new URL(response.url());
      failedRequests.add(`${response.status()} ${url.origin}${url.pathname} (${response.request().resourceType()})`);
    }
  });

  stage = 'guest defaults, Upcoming fallback, search, and local persistence';
  let eventsWait = waitForEventsResponse({sort: 'upcoming'});
  await page.goto(`${appBase}/`, {waitUntil: 'domcontentloaded'});
  await eventsWait;
  await waitForSettled();
  const flashSwitch = () => page.getByRole('switch', {name: 'Show Flash events', exact: true});
  await waitForFlashSwitchReady();
  assert.equal(await flashSwitch().isChecked(), true, 'A guest starts with Show Flash enabled');
  await feedWithSearch({sort: 'upcoming', q: fixtures.titleSearch});
  await assertApiOrder({sort: 'upcoming', q: fixtures.titleSearch}, fixtures.expectedUpcoming);
  await waitForRenderedEventIds(fixtures.expectedUpcoming);
  assert.equal(
    await page.locator('#public-event-results ul[aria-label="Why this event appears"]').count(),
    0,
    'Guest discovery does not show personal recommendation reasons',
  );
  passed.push('Guest default, Upcoming fallback, search, and public API parity');

  stage = 'guest hide persistence and feed-only filtering';
  const guestFilteredResponse = waitForEventsResponse({
    sort: 'upcoming', q: fixtures.titleSearch, include_flash: 'false',
  });
  await flashSwitch().uncheck();
  await guestFilteredResponse;
  await waitForSettled();
  assert.equal(await flashSwitch().isChecked(), false, 'The guest can hide Flash from discovery');
  assert.deepEqual(await renderedEventIds(), fixtures.expectedHiddenFeed);
  await assertApiOrder(
    {sort: 'upcoming', q: fixtures.titleSearch, include_flash: false},
    fixtures.expectedHiddenFeed,
  );
  eventsWait = waitForEventsResponse({sort: 'upcoming', include_flash: 'false'});
  await page.reload({waitUntil: 'domcontentloaded'});
  await eventsWait;
  await waitForSettled();
  await waitForFlashSwitchReady();
  assert.equal(await flashSwitch().isChecked(), false, 'The guest discovery choice survives reload');
  await feedWithSearch({sort: 'upcoming', q: fixtures.titleSearch, include_flash: 'false'});
  await waitForRenderedEventIds(fixtures.expectedHiddenFeed);
  await captureSettledViewport('guest-flash-hidden');
  passed.push('Guest Show Flash choice persists locally and changes discovery only');

  stage = 'signed-in default and For You ranking';
  const student = await useAccount('Fictional student 1');
  activeToken = student.token;
  eventsWait = waitForEventsResponse({sort: 'for_you'});
  await page.goto(`${appBase}/`, {waitUntil: 'domcontentloaded'});
  await eventsWait;
  await waitForSettled();
  await waitForFlashSwitchReady();
  assert.equal(await flashSwitch().isChecked(), true, 'The first account starts with Show Flash enabled');
  const firstPreferences = await api('/me/preferences', {token: activeToken});
  assert.equal(firstPreferences.status, 200);
  assert.equal(firstPreferences.body.show_flash, true, 'The first account has an independent default');
  await feedWithSearch({sort: 'for_you', q: fixtures.titleSearch});
  const forYou = await assertApiOrder(
    {sort: 'for_you', q: fixtures.titleSearch}, fixtures.expectedForYou, activeToken,
  );
  await waitForRenderedEventIds(fixtures.expectedForYou);
  for (const row of forYou) {
    assert.deepEqual(row.recommendation_reasons, fixtures.expectedReasons[row.id]);
  }
  for (const [id, reasons] of Object.entries(fixtures.expectedReasons)) {
    const card = page.locator(`#public-event-results a[href*="eventId=${id}"]`)
      .locator('xpath=ancestor::article[1]');
    const chips = card.locator('ul[aria-label="Why this event appears"] li');
    assert.equal(await chips.count(), reasons.length, 'The card shows only its controlled reason chips');
  }
  passed.push('Signed-in For You order, transient Flash boost, and controlled reason chips');
  await assertCleanViewport(1440, 900);
  await captureSettledViewport('desktop-flash-discover-1440');
  await assertCleanViewport(320, 700);
  await assertCleanViewport(390, 844);
  await captureSettledViewport('english-flash-discover-390');
  await page.setViewportSize({width: 1440, height: 900});

  stage = 'explicit Upcoming, Newest, search, and My Clubs composition';
  const sort = page.getByRole('combobox', {name: 'Sort by', exact: true});
  const upcomingWait = waitForEventsResponse({sort: 'upcoming', q: fixtures.titleSearch});
  await sort.selectOption('upcoming');
  await upcomingWait;
  await waitForSettled();
  await assertApiOrder(
    {sort: 'upcoming', q: fixtures.titleSearch}, fixtures.expectedUpcoming, activeToken,
  );
  await waitForRenderedEventIds(fixtures.expectedUpcoming);
  const newestWait = waitForEventsResponse({sort: 'newest', q: fixtures.titleSearch});
  await sort.selectOption('newest');
  await newestWait;
  await waitForSettled();
  await assertApiOrder(
    {sort: 'newest', q: fixtures.titleSearch}, fixtures.expectedNewest, activeToken,
  );
  await waitForRenderedEventIds(fixtures.expectedNewest);

  const myClubs = page.locator('button[aria-controls="public-event-results"]');
  await myClubs.waitFor({state: 'visible'});
  const clubFilters = {
    sort: 'newest',
    q: fixtures.clubOrganizationName,
    my_clubs: 'true',
  };
  const clubsWait = waitForEventsResponse(clubFilters);
  await page.locator('#event-search').fill(fixtures.clubOrganizationName);
  await myClubs.click();
  await clubsWait;
  await waitForSettled();
  const clubRows = await assertApiOrder(
    {sort: 'newest', q: fixtures.clubOrganizationName, my_clubs: true},
    [fixtures.events.club_scheduled.id],
    activeToken,
  );
  assert.equal(clubRows[0].event_type, 'scheduled');
  await waitForRenderedEventIds([fixtures.events.club_scheduled.id]);
  passed.push('Upcoming/Newest overrides and My Clubs compose with organization search');

  stage = 'Flash registration and waitlist before hiding discovery';
  await navigateToFixtureEvent(fixtures.events.active_flash);
  await registerFromDetail(fixtures.events.active_flash, 'confirmed');
  await navigateToFixtureEvent(fixtures.events.expired_area_flash);
  await registerFromDetail(fixtures.events.expired_area_flash, 'waitlisted');
  const myRegistrations = await api('/me/registrations', {token: activeToken});
  assert.equal(myRegistrations.status, 200);
  const activeRegistration = myRegistrations.body.find(item => item.event_id === fixtures.events.active_flash.id);
  const waitlistRegistration = myRegistrations.body.find(item => item.event_id === fixtures.events.expired_area_flash.id);
  assert.equal(activeRegistration?.status, 'confirmed');
  assert.equal(waitlistRegistration?.status, 'waitlisted');
  passed.push('Flash UI registration and capacity waitlist use existing participation routes');

  stage = 'theme independence, signed-in preference save, and hidden My Events';
  await page.goto(`${appBase}/settings`, {waitUntil: 'domcontentloaded'});
  await waitForSettled();
  const darkTheme = page.locator('input[name="settings-theme"][value="dark"]');
  const themeWait = waitForPreferencePatch();
  await darkTheme.check();
  const themeResponse = await themeWait;
  await waitForSettled();
  assert.equal(themeResponse.status(), 200, 'The theme preference save completes');
  assert.equal((await themeResponse.json()).theme, 'dark');

  eventsWait = waitForEventsResponse({sort: 'for_you'});
  await page.goto(`${appBase}/`, {waitUntil: 'domcontentloaded'});
  await eventsWait;
  await waitForSettled();
  await feedWithSearch({sort: 'for_you', q: fixtures.titleSearch});
  const flashHiddenWait = waitForEventsResponse({
    sort: 'for_you', q: fixtures.titleSearch, include_flash: 'false',
  });
  const flashPreferenceWait = waitForPreferencePatch();
  await flashSwitch().uncheck();
  const savedFlashPreference = await flashPreferenceWait;
  await flashHiddenWait;
  await waitForSettled();
  assert.equal(savedFlashPreference.status(), 200, 'The saved Show Flash preference returns successfully');
  const savedPreferences = await savedFlashPreference.json();
  assert.equal(savedPreferences.show_flash, false);
  assert.equal(savedPreferences.theme, 'dark', 'A partial Show Flash save preserves the theme');
  await waitForRenderedEventIds(fixtures.expectedHiddenFeed);
  assert.equal(await flashSwitch().isChecked(), false);
  const hiddenDefault = await assertApiOrder(
    {sort: 'for_you', q: fixtures.titleSearch, include_flash: false},
    fixtures.expectedHiddenFeed,
    activeToken,
  );
  assert.ok(hiddenDefault.every(row => row.event_type === 'scheduled'));
  const stillPublic = await api(eventPath(fixtures.events.active_flash.id), {token: activeToken});
  assert.equal(stillPublic.status, 200, 'Hiding discovery does not hide the public detail route');

  eventsWait = waitForEventsResponse({sort: 'for_you', include_flash: 'false'});
  await page.reload({waitUntil: 'domcontentloaded'});
  await eventsWait;
  await waitForSettled();
  await waitForFlashSwitchReady();
  await feedWithSearch({sort: 'for_you', q: fixtures.titleSearch, include_flash: 'false'});
  assert.equal(await flashSwitch().isChecked(), false, 'The account preference survives reload');
  const myEventsResponse = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname.endsWith('/api/v1/me/registrations');
  }, {timeout: 20000});
  await page.goto(`${appBase}/my-events`, {waitUntil: 'domcontentloaded'});
  await myEventsResponse;
  await waitForSettled();
  await assertMyEventStatus('Confirmed', fixtures.events.active_flash.title, 'confirmed');
  await assertMyEventStatus('Waitlist', fixtures.events.expired_area_flash.title, 'waitlisted');
  passed.push('Hidden Flash stays in My Events by title with confirmed/waitlist states and detail access');

  stage = 'account preference isolation';
  const secondStudent = await useAccount('Fictional student 2');
  activeToken = secondStudent.token;
  eventsWait = waitForEventsResponse({sort: 'for_you'});
  await page.goto(`${appBase}/`, {waitUntil: 'domcontentloaded'});
  await eventsWait;
  await waitForSettled();
  await waitForFlashSwitchReady();
  assert.equal(await flashSwitch().isChecked(), true, 'A second account does not inherit the first account choice');
  let secondPreferences = await api('/me/preferences', {token: activeToken});
  assert.equal(secondPreferences.body.show_flash, true);
  assert.equal(secondPreferences.body.theme, 'light');

  const restoredStudent = await useAccount('Fictional student 1');
  activeToken = restoredStudent.token;
  eventsWait = waitForEventsResponse({sort: 'for_you'});
  await page.goto(`${appBase}/`, {waitUntil: 'domcontentloaded'});
  await eventsWait;
  await waitForSettled();
  await waitForFlashSwitchReady();
  assert.equal(await flashSwitch().isChecked(), false, 'Switching back restores the first account choice');
  const restoredPreferences = await api('/me/preferences', {token: activeToken});
  assert.equal(restoredPreferences.body.show_flash, false);
  assert.equal(restoredPreferences.body.theme, 'dark');
  passed.push('Show Flash and theme remain isolated when switching fictional accounts');

  stage = 'Flash authoring transition, non-manager denial, and publish';
  const organizer = await useAccount('Fictional organizer');
  activeToken = organizer.token;
  await page.goto(`${appBase}/draft?eventId=${encodeURIComponent(fixtures.draft.id)}`, {
    waitUntil: 'domcontentloaded',
  });
  const eventType = page.getByRole('combobox', {name: 'Event type', exact: true});
  await eventType.waitFor({state: 'visible'});
  assert.equal(await eventType.inputValue(), 'scheduled');
  const registrationMode = page.getByRole('combobox', {name: 'Registration mode', exact: true});
  assert.equal(await registrationMode.inputValue(), 'approval');
  const reviewWindow = page.getByRole('spinbutton', {name: 'Review window (15–2,880 minutes)', exact: true});
  assert.equal(await reviewWindow.inputValue(), '15');
  await eventType.selectOption('flash');
  assert.equal(await registrationMode.inputValue(), 'instant');
  assert.equal(await reviewWindow.count(), 0, 'Flash removes the approval review-window control');
  const saveDraftWait = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname.endsWith(`/api/v1/events/${fixtures.draft.id}/draft`) &&
      response.request().method() === 'PATCH';
  }, {timeout: 20000});
  await page.getByRole('button', {name: 'Save draft', exact: true}).click();
  const saveDraftResponse = await saveDraftWait;
  await waitForSettled();
  assert.equal(saveDraftResponse.status(), 200, 'The Flash draft save succeeds');
  const savedDraftRequest = JSON.parse(saveDraftResponse.request().postData() ?? '{}');
  assert.equal(savedDraftRequest.event_type, 'flash');
  assert.equal(savedDraftRequest.registration_mode, 'instant');
  assert.equal(savedDraftRequest.review_window_minutes, null);
  const savedDraft = await saveDraftResponse.json();
  assert.equal(savedDraft.event_type, 'flash');
  assert.equal(savedDraft.registration_mode, 'instant');
  assert.equal(savedDraft.review_window_minutes, null);

  const nonManager = await api(`/events/${fixtures.draft.id}/publish`, {
    token: restoredStudent.token,
    method: 'POST',
    headers: {'If-Match': `"${savedDraft.draft_version}"`},
  });
  assert.equal(nonManager.status, 403, 'A non-manager cannot publish the Flash draft');
  const publishWait = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname.endsWith(`/api/v1/events/${fixtures.draft.id}/publish`) &&
      response.request().method() === 'POST';
  }, {timeout: 20000});
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Publish', exact: true}).click();
  const publishResponse = await publishWait;
  await waitForSettled();
  assert.equal(publishResponse.status(), 200, 'The manager can publish the saved Flash draft');
  const published = await publishResponse.json();
  assert.equal(published.event_type, 'flash');
  assert.equal(published.registration_mode, 'instant');
  assert.equal(published.review_window_minutes, null);
  passed.push('Scheduled approval draft converts to Flash instant/null before publish; non-manager denied');

  stage = 'mobile 320px/390px and Filipino extra-large geometry';
  // Leave the owner-only route before switching accounts: a denial there is expected.
  await page.goto(`${appBase}/settings`, {waitUntil: 'domcontentloaded'});
  await waitForSettled();
  const mobileAccount = await useAccount('Fictional student 2');
  activeToken = mobileAccount.token;
  await page.goto(`${appBase}/settings`, {waitUntil: 'domcontentloaded'});
  await waitForSettled();
  let preferenceWait = waitForPreferencePatch();
  await page.locator('#settings-language').selectOption('fil');
  let preferenceResponse = await preferenceWait;
  await waitForSettled();
  assert.equal(preferenceResponse.status(), 200, 'The Filipino language preference save completes');
  preferenceWait = waitForPreferencePatch();
  await page.locator('input[name="settings-text-size"][value="extra_large"]').check();
  preferenceResponse = await preferenceWait;
  await waitForSettled();
  assert.equal(preferenceResponse.status(), 200, 'The extra-large text preference save completes');
  await waitForSettled();

  eventsWait = waitForEventsResponse({sort: 'for_you'});
  await page.goto(`${appBase}/`, {waitUntil: 'domcontentloaded'});
  await eventsWait;
  await feedWithSearch({sort: 'for_you', q: fixtures.titleSearch});
  await assertCleanViewport(320, 700);
  await assertCleanViewport(390, 844);
  await captureSettledViewport('filipino-xl-discover-390');
  const mobileEventsResponse = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname.endsWith('/api/v1/me/registrations');
  }, {timeout: 20000});
  await page.goto(`${appBase}/my-events`, {waitUntil: 'domcontentloaded'});
  await mobileEventsResponse;
  await assertCleanViewport(390, 844);
  passed.push('320px/390px mobile and Filipino extra-large layouts retain four attendee tabs');

  assert.equal(browserErrorCount, 0, 'Edge reports no uncaught browser or console errors');
} catch (error) {
  if (page) {
    const pathname = new URL(page.url()).pathname;
    await writeFile(evidence('failure.json'), JSON.stringify({
      stage,
      pathname,
      errorType: error?.constructor?.name ?? 'Error',
      message: String(error?.message ?? '').replace(/eyJ[A-Za-z0-9._-]+/g, '[redacted]').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[redacted]').slice(0, 2400),
      browserErrorCount,
      browserErrors: [...browserErrors],
      failedRequests: [...failedRequests],
      passedCount: passed.length,
    }, null, 2));
    await page.screenshot({path: evidence('failure-viewport.png'), fullPage: false}).catch(() => {});
  }
  throw error;
} finally {
  if (context) await context.close();
  if (browser) await browser.close();
  await writeFile(evidence('results.json'), JSON.stringify({
    method: 'Isolated PostgreSQL, local static frontend, and Microsoft Edge; not participant or physical-device validation',
    passed,
    browserErrorCount,
    browserErrors: [...browserErrors],
    failedRequests: [...failedRequests],
    screenshots,
    geometry,
  }, null, 2));
}
