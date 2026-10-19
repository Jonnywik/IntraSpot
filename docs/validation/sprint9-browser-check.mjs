// Local persisted UI journey; developer evidence only, not participant validation.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.SPRINT9_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT9_FIXTURES);
const base = 'http://127.0.0.1:3000';
const output = path.resolve(
  'docs/validation/sprint9-browser-evidence',
  new Date().toISOString().replaceAll(':', '-').replaceAll('.', '-'),
);
await mkdir(output, {recursive: true});

const browser = await chromium.launch({channel: 'msedge', headless: true});
const context = await browser.newContext({
  viewport: {width: 1440, height: 900},
  colorScheme: 'light',
  reducedMotion: 'no-preference',
});
const page = await context.newPage();
page.setDefaultTimeout(15000);
const passed = [];
const pageErrors = [];
const privateSidebarRequests = [];
page.on('pageerror', error => pageErrors.push(error.message));
page.on('request', request => {
  const pathname = new URL(request.url()).pathname;
  if (request.method() === 'GET' && ['/api/v1/me/organizations', '/api/v1/me/registrations'].includes(pathname)) {
    privateSidebarRequests.push({pathname, authenticated: Boolean(request.headers().authorization)});
  }
});

const preferenceUrl = url => new URL(url).pathname === '/api/v1/me/preferences';
const methodAndPath = (request, method, pathname) =>
  request.method() === method && new URL(request.url()).pathname === pathname;
const waitForPatch = () => page.waitForResponse(response =>
  preferenceUrl(response.url()) && response.request().method() === 'PATCH',
);

async function openSettings() {
  await page.goto(`${base}/settings`, {waitUntil: 'networkidle'});
  await page.locator('main').getByRole('heading', {level: 1}).waitFor({state: 'visible'});
}

async function waitForSessionLabel(label) {
  await page.waitForFunction(value =>
    document.querySelector('.local-account-controls [role="status"]')?.textContent?.includes(value),
  label);
}

async function useAccount(label) {
  const controls = page.locator('.local-account-controls');
  await controls.locator('select').selectOption({value: label});
  await controls.locator('button').first().click();
  await waitForSessionLabel(label);
}

async function assertDiscoverySidebars(expected) {
  const requestStart = privateSidebarRequests.length;
  await page.goto(base, {waitUntil: 'networkidle'});
  const snapshot = await page.evaluate(() => {
    const sidebars = Array.from(document.querySelectorAll(
      '#main-content aside:not(.heritage-aside), #main-content [role="complementary"]:not(.heritage-aside)',
    )).filter(element => element.getClientRects().length).map(element => {
      const bounds = element.getBoundingClientRect();
      return {
        text: element.innerText,
        left: bounds.left,
        right: bounds.right,
        links: Array.from(element.querySelectorAll('a')).map(link => ({
          href: link.href,
          current: link.getAttribute('aria-current'),
        })),
      };
    }).sort((first, second) => first.left - second.left);
    const title = document.querySelector('#discovery-title');
    const feed = title?.closest('.discovery-stack');
    const feedBounds = feed?.getBoundingClientRect();
    return {
      language: document.documentElement.lang,
      sidebars,
      feed: feedBounds ? {left: feedBounds.left, right: feedBounds.right, width: feedBounds.width} : null,
    };
  });
  assert.equal(snapshot.sidebars.length, 2, 'Wide discovery view has left and right complementary sidebars');
  const [left, right] = snapshot.sidebars;
  if (expected !== 'guest') assert.equal(snapshot.language, 'en', 'Account sidebar content check runs in English');
  assert.ok(left.text.trim().length > 0, 'Left sidebar has visible content');
  assert.ok(right.text.trim().length > 0, 'Right sidebar has visible content');
  const shortcutPaths = new Set(left.links.map(link => new URL(link.href).pathname));
  for (const route of ['/my-events', '/chat', '/profile']) {
    assert.ok(shortcutPaths.has(route), `Left sidebar links to the existing ${route} route`);
  }
  assert.ok(snapshot.feed, 'Discovery feed is present as a single center column');
  assert.ok(snapshot.feed.width <= 681, `Discovery feed exceeds 680px (${snapshot.feed.width}px)`);
  assert.ok(left.right <= snapshot.feed.left + 1, 'Club shortcuts sit left of the feed');
  assert.ok(snapshot.feed.right <= right.left + 1, 'Registration summary sits right of the feed');

  if (expected === 'guest') {
    assert.ok(!right.text.includes(fixtures.privateEventTitle), 'Guest does not see private registration details');
    assert.equal(privateSidebarRequests.length, requestStart, 'Guest does not request account-private sidebar data');
  } else if (expected === 'accountA') {
    assert.ok(left.text.includes(fixtures.orgName), 'Account A sees its own club shortcut');
    assert.ok(!right.text.includes(fixtures.privateEventTitle), 'Account A cannot see account B registration details');
  } else {
    assert.ok(right.text.includes(fixtures.privateEventTitle), 'Account B sees its own upcoming registration');
    const registration = page.locator('.discovery-right .agenda-event').filter({hasText: fixtures.privateEventTitle});
    await registration.locator('.status-chip.confirmed').waitFor({state: 'visible'});
  }
  if (expected !== 'guest') {
    const requests = privateSidebarRequests.slice(requestStart);
    assert.ok(requests.some(request => request.pathname === '/api/v1/me/organizations' && request.authenticated),
      'Club sidebar loads the current account organization API');
    assert.ok(requests.some(request => request.pathname === '/api/v1/me/registrations' && request.authenticated),
      'Registration sidebar loads the current account registration API');
  }
  return snapshot;
}

async function assertFilipinoSidebarCopy() {
  await page.goto(base, {waitUntil: 'networkidle'});
  const snapshot = await page.evaluate(() => {
    const sidebars = Array.from(document.querySelectorAll(
      '#main-content aside:not(.heritage-aside), #main-content [role="complementary"]:not(.heritage-aside)',
    )).filter(element => element.getClientRects().length).map(element => ({
      text: element.innerText,
      left: element.getBoundingClientRect().left,
    })).sort((first, second) => first.left - second.left).map(element => element.text);
    return {language: document.documentElement.lang, sidebars};
  });
  assert.equal(snapshot.language, 'fil');
  assert.equal(snapshot.sidebars.length, 2);
  assert.ok(snapshot.sidebars.every(text => text.trim().length > 0), 'Both Filipino sidebars have visible content');
  assert.ok(snapshot.sidebars[0].includes(fixtures.orgName), 'Organization-authored name stays unchanged in Filipino');
  assert.ok(!snapshot.sidebars[1].includes(fixtures.privateEventTitle), 'Filipino sidebar does not reveal another account registration');
}

async function reloadAndVerifyAccountRestore({label, accountId, expectedRoot}) {
  await page.addInitScript(() => {
    const record = () => {
      const root = document.documentElement;
      if (!root) return;
      window.__sprint9RootHistory ??= [];
      window.__sprint9RootHistory.push({
        language: root.lang,
        theme: root.dataset.theme,
        textSize: root.dataset.textSize,
        highContrast: root.dataset.highContrast,
        reducedMotion: root.dataset.reducedMotion,
      });
    };
    new MutationObserver(record).observe(document, {
      attributes: true,
      childList: true,
      subtree: true,
      attributeFilter: ['lang', 'data-theme', 'data-text-size', 'data-high-contrast', 'data-reduced-motion'],
    });
    record();
  });

  let releaseMe;
  let resolveMeSeen;
  const meSeen = new Promise(resolve => { resolveMeSeen = resolve; });
  const meGate = new Promise(resolve => { releaseMe = resolve; });
  let released = false;
  const preferencePatches = [];
  const trackPatch = request => {
    if (methodAndPath(request, 'PATCH', '/api/v1/me/preferences')) preferencePatches.push(request);
  };
  page.on('request', trackPatch);
  await page.route('**/api/v1/me', async route => {
    if (route.request().method() === 'GET') {
      resolveMeSeen();
      await meGate;
    }
    await route.continue();
  });

  const catalogResponse = page.waitForResponse(response =>
    methodAndPath(response.request(), 'GET', '/api/v1/local-demo/accounts'),
  );
  const meResponse = page.waitForResponse(response =>
    methodAndPath(response.request(), 'GET', '/api/v1/me'),
  );
  const preferencesResponse = page.waitForResponse(response =>
    methodAndPath(response.request(), 'GET', '/api/v1/me/preferences'),
  );
  try {
    const reload = page.reload({waitUntil: 'domcontentloaded'});
    await meSeen;
    const catalog = await catalogResponse;
    assert.ok(catalog.ok(), `Fresh fictional account catalog returned HTTP ${catalog.status()}`);
    const accounts = await catalog.json();
    const restoredAccount = accounts.find(account => account.label === label);
    assert.ok(restoredAccount?.token, `Fresh account catalog contains ${label}`);

    const stored = await page.evaluate(() => Array.from({length: sessionStorage.length}, (_, index) => {
      const key = sessionStorage.key(index);
      return [key, key === null ? null : sessionStorage.getItem(key)];
    }));
    assert.ok(stored.some(([, value]) => value === label), 'Session storage keeps the selected label');
    assert.ok(!stored.some(([, value]) => value?.includes(restoredAccount.token)), 'Session storage does not persist the account token');
    assert.ok(!stored.some(([, value]) => typeof value === 'string' && /eyJ[\w-]+\.[\w-]+\.[\w-]+/.test(value)),
      'Session storage contains no JWT-like token');

    await page.locator('#settings-preferences-heading').waitFor({state: 'attached'});
    const controls = page.locator('section[aria-labelledby="settings-preferences-heading"] select, section[aria-labelledby="settings-preferences-heading"] input, section[aria-labelledby="settings-preferences-heading"] button');
    assert.ok(await controls.count() > 0, 'Preference controls render during account restoration');
    for (let index = 0; index < await controls.count(); index++) {
      assert.equal(await controls.nth(index).isEnabled(), false, 'Preference controls wait for account restoration');
    }
    await page.waitForTimeout(300);
    assert.equal(preferencePatches.length, 0, 'No account preference save is issued while /me verification is pending');
    const pendingRootHistory = await page.evaluate(() => window.__sprint9RootHistory ?? []);
    assert.ok(!pendingRootHistory.some(state => state.textSize === 'extra_large' || state.highContrast === 'true'),
      'Guest text-size and contrast settings are not applied while account restoration is pending');

    released = true;
    releaseMe();
    await reload;
    const verified = await meResponse;
    assert.ok(verified.ok(), `Restored /me check returned HTTP ${verified.status()}`);
    assert.equal((await verified.json()).id, accountId, 'Fresh /me verification restores the selected fictional account');
    const preferences = await preferencesResponse;
    assert.ok(preferences.ok(), `Restored account preferences returned HTTP ${preferences.status()}`);
    await waitForSessionLabel(label);
    await expectRoot(expectedRoot);
    const fullRootHistory = await page.evaluate(() => window.__sprint9RootHistory ?? []);
    assert.ok(!fullRootHistory.some(state => state.textSize === 'extra_large' || state.highContrast === 'true'),
      'Guest preferences never flash before restored account preferences');
  } finally {
    if (!released) releaseMe();
    page.off('request', trackPatch);
    await page.unroute('**/api/v1/me');
  }
}

async function continueAsGuest() {
  const controls = page.locator('.local-account-controls');
  await controls.locator('button.button-secondary').last().click();
  await controls.locator('select').waitFor({state: 'visible'});
}

const selectionControls = {
  language: {kind: 'select', selector: '#settings-language'},
  theme: {kind: 'radio', selector: 'input[type="radio"][name="settings-theme"]'},
  text_size: {kind: 'radio', selector: 'input[type="radio"][name="settings-text-size"]'},
};

async function choose(key, value) {
  const control = selectionControls[key];
  assert.ok(control, `Unknown preference control ${key}`);
  if (control.kind === 'select') {
    const select = page.locator(control.selector);
    assert.equal(await select.count(), 1, `Expected one stable settings control for ${key}`);
    await select.selectOption(value);
    return;
  }
  const radio = page.locator(`${control.selector}[value="${value}"]`);
  assert.equal(await radio.count(), 1, `Expected one stable settings control for ${key}=${value}`);
  await radio.check();
}

const checkboxControls = {
  high_contrast: {sectionId: 'settings-accessibility-heading', index: 0},
  reduced_motion: {sectionId: 'settings-accessibility-heading', index: 1},
  decoration_paused: {sectionId: 'settings-decoration-heading', index: 0},
};

async function toggle(key, checked) {
  const control = checkboxControls[key];
  assert.ok(control, `Unknown settings checkbox ${key}`);
  const checkboxes = page.locator(`section[aria-labelledby="${control.sectionId}"] input[type="checkbox"]`);
  assert.ok(await checkboxes.count() > control.index, `Missing stable settings checkbox for ${key}`);
  await checkboxes.nth(control.index).setChecked(checked);
}

async function chooseAndWait(key, value) {
  const response = waitForPatch();
  await choose(key, value);
  const result = await response;
  assert.ok(result.ok(), `Preference save returned HTTP ${result.status()}`);
}

async function toggleAndWait(key, checked) {
  const response = waitForPatch();
  await toggle(key, checked);
  const result = await response;
  assert.ok(result.ok(), `Preference save returned HTTP ${result.status()}`);
}

async function rootState() {
  return page.evaluate(() => ({
    language: document.documentElement.lang,
    theme: document.documentElement.dataset.theme,
    textSize: document.documentElement.dataset.textSize,
    highContrast: document.documentElement.dataset.highContrast,
    reducedMotion: document.documentElement.dataset.reducedMotion,
  }));
}

async function expectRoot(expected) {
  await page.waitForFunction(values => Object.entries(values).every(([key, value]) => {
    const actual = key === 'language'
      ? document.documentElement.lang
      : document.documentElement.dataset[{
        theme: 'theme', textSize: 'textSize', highContrast: 'highContrast', reducedMotion: 'reducedMotion',
      }[key]];
    return actual === value;
  }), expected);
  const current = await rootState();
  for (const [key, value] of Object.entries(expected)) {
    assert.equal(current[key], value, `Unexpected root preference ${key}`);
  }
}

async function expectGuestPreferences(expected) {
  await page.waitForFunction(values => {
    try {
      const record = JSON.parse(localStorage.getItem('intraspot.preferences.v1') ?? 'null');
      return record?.version === 1 && Object.entries(values).every(([key, value]) => record.preferences?.[key] === value);
    } catch {
      return false;
    }
  }, expected);
}

async function assertReducedMotionSearchLayout() {
  await page.goto(base, {waitUntil: 'networkidle'});
  const search = page.locator('#event-search');
  await search.fill('sprint-nine-layout-check');
  const clear = search.locator('xpath=..').locator('button');
  await clear.waitFor({state: 'visible'});
  const layout = await page.evaluate(() => {
    const input = document.querySelector('#event-search');
    const button = input?.parentElement?.querySelector('button');
    if (!input || !button) return null;
    const inputRect = input.getBoundingClientRect();
    const buttonRect = button.getBoundingClientRect();
    return {
      centerDelta: Math.abs((inputRect.top + inputRect.bottom) / 2 - (buttonRect.top + buttonRect.bottom) / 2),
      transform: getComputedStyle(button).transform,
    };
  });
  assert.ok(layout, 'Search clear control exists in reduced-motion mode');
  assert.ok(layout.centerDelta <= 1, `Search clear control stays vertically centered (${layout.centerDelta}px drift)`);
  assert.notEqual(layout.transform, 'none', 'Reduced motion preserves the clear control positional transform');
  await clear.click();
  assert.equal(await search.inputValue(), '', 'Search clear control remains usable in reduced-motion mode');
}

async function assertCorruptGuestPreferencesRecovery() {
  const recoveryContext = await browser.newContext({viewport: {width: 1440, height: 900}});
  const recoveryErrors = [];
  const recoveryPage = await recoveryContext.newPage();
  recoveryPage.on('pageerror',error=>recoveryErrors.push(error.message));
  try {
    await recoveryPage.goto(`${base}/settings`, {waitUntil: 'networkidle'});
    await recoveryPage.waitForFunction(() =>
      document.querySelector('section[aria-labelledby="settings-preferences-heading"]')?.getAttribute('aria-busy') === 'false',
    );
    await recoveryPage.evaluate(() => localStorage.setItem('intraspot.preferences.v1', '{corrupt-record'));
    await recoveryPage.reload({waitUntil: 'networkidle'});

    const section = recoveryPage.locator('section[aria-labelledby="settings-preferences-heading"]');
    await section.getByRole('alert').waitFor({state: 'visible'});
    await section.locator('button').last().click();
    await recoveryPage.waitForFunction(() => {
      try {
        const record = JSON.parse(localStorage.getItem('intraspot.preferences.v1') ?? 'null');
        return record?.version === 1 && record.preferences?.language === 'en' &&
          record.preferences?.theme === 'light' && record.preferences?.text_size === 'standard' &&
          record.preferences?.high_contrast === false && record.preferences?.reduced_motion === false &&
          record.preferences?.decoration_paused === false;
      } catch {
        return false;
      }
    });
    const recovered = await recoveryPage.evaluate(() => JSON.parse(localStorage.getItem('intraspot.preferences.v1')));
    assert.deepEqual(recovered, {
      version: 1,
      preferences: {
        language: 'en', theme: 'light', text_size: 'standard', high_contrast: false,
        reduced_motion: false, decoration_paused: false,
      },
    }, 'Reset replaces corrupt guest storage with a valid complete default record');

    await recoveryPage.reload({waitUntil: 'networkidle'});
    await recoveryPage.waitForFunction(() => {
      const root = document.documentElement;
      return root.lang === 'en' && root.dataset.theme === 'light' && root.dataset.textSize === 'standard' &&
        root.dataset.highContrast === 'false' && root.dataset.reducedMotion === 'false';
    });
    assert.equal(await section.getByRole('alert').count(), 0, 'A reload successfully reads the recovered guest record');
  } catch(error) {
    await recoveryPage.screenshot({path:path.join(output,'guest-recovery-failure.png')});
    console.error(JSON.stringify({recoveryErrors,heading:await recoveryPage.locator('h1').allTextContents(),status:await recoveryPage.getByRole('status').allTextContents()}));
    throw error;
  } finally {
    await recoveryContext.close();
  }
}

async function assertBodyContrast() {
  const ratios = await page.evaluate(() => {
    const channels = value => value.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
    const luminance = color => channels(color).map(channel => {
      const value = channel / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    }).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
    const ratio = (foreground, background) => {
      const first = luminance(foreground);
      const second = luminance(background);
      return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
    };
    const background = element => {
      for (let node = element; node; node = node.parentElement) {
        const color = getComputedStyle(node).backgroundColor;
        if (!color.includes(', 0)') && color !== 'rgba(0, 0, 0, 0)') return color;
      }
      return getComputedStyle(document.body).backgroundColor;
    };
    const body = getComputedStyle(document.body);
    return [ratio(body.color, body.backgroundColor), ...Array.from(document.querySelectorAll('main .muted'))
      .filter(element => element.getClientRects().length)
      .map(element => ratio(getComputedStyle(element).color, background(element)))];
  });
  assert.ok(ratios.length > 0);
  for (const ratio of ratios) assert.ok(ratio >= 4.5, `Text contrast is ${ratio.toFixed(2)}:1`);
}

async function assertResponsiveDiscoveryColumns(width, expectedSidebars) {
  await page.setViewportSize({width, height: 900});
  await page.goto(base, {waitUntil: 'networkidle'});
  const layout = await page.evaluate(() => {
    const main = document.querySelector('#main-content');
    const mainBounds = main?.getBoundingClientRect();
    const sidebars = Array.from(document.querySelectorAll(
      '#main-content aside:not(.heritage-aside), #main-content [role="complementary"]:not(.heritage-aside)',
    )).filter(element => element.getClientRects().length).map(element => {
      const bounds = element.getBoundingClientRect();
      return {left: bounds.left, right: bounds.right};
    }).sort((first, second) => first.left - second.left);
    const title = document.querySelector('#discovery-title');
    const feed = title?.closest('.discovery-stack')?.getBoundingClientRect();
    return {
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      mainWidth: mainBounds?.width ?? 0,
      sidebars,
      feed: feed ? {left: feed.left, right: feed.right, width: feed.width} : null,
    };
  });
  assert.equal(layout.sidebars.length, expectedSidebars, `${width}px breakpoint shows ${expectedSidebars} sidebars`);
  assert.ok(layout.documentWidth <= layout.viewportWidth + 1, `Horizontal overflow at ${width}px`);
  assert.ok(layout.mainWidth <= 1441, `Workspace exceeds 1440px at ${width}px`);
  assert.ok(layout.feed, `Discovery feed is present at ${width}px`);
  assert.ok(layout.feed.width <= 681, `Feed exceeds its 680px column at ${width}px`);
  if (expectedSidebars === 2) {
    assert.ok(layout.sidebars[0].right <= layout.feed.left + 1, `Left sidebar does not precede feed at ${width}px`);
    assert.ok(layout.feed.right <= layout.sidebars[1].left + 1, `Right sidebar does not follow feed at ${width}px`);
  } else if (expectedSidebars === 1) {
    const sidebar = layout.sidebars[0];
    assert.ok(sidebar.right <= layout.feed.left + 1 || layout.feed.right <= sidebar.left + 1,
      `The retained sidebar does not remain beside the feed at ${width}px`);
  }
}

async function setDecorationPaused(paused, persisted) {
  await page.goto(base, {waitUntil: 'networkidle'});
  const control = page.locator('.decoration-control');
  await control.waitFor({state: 'visible'});
  if ((await control.getAttribute('aria-pressed')) !== String(paused)) {
    const response = persisted ? waitForPatch() : null;
    await control.click();
    if (response) assert.ok((await response).ok());
  }
  assert.equal(await control.getAttribute('aria-pressed'), String(paused));
}

async function exerciseDesktopViewports() {
  const routes = [
    '/',
    `/events?eventId=${encodeURIComponent(fixtures.eventId)}`,
    '/my-events',
    '/chat',
    '/profile',
    '/settings',
  ];
  for (const viewport of [
    {width: 1440, height: 900},
    {width: 1280, height: 720},
    {width: 1366, height: 768},
    {width: 1920, height: 1080},
  ]) {
    await page.setViewportSize(viewport);
    for (const route of routes) {
      await page.goto(`${base}${route}`, {waitUntil: 'networkidle'});
      const layout = await page.evaluate(() => ({
        width: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
        mainRight: document.querySelector('main')?.getBoundingClientRect().right ?? 0,
        mainWidth: document.querySelector('#main-content')?.getBoundingClientRect().width ?? 0,
        sidebarCount: Array.from(document.querySelectorAll(
          '#main-content aside:not(.heritage-aside), #main-content [role="complementary"]:not(.heritage-aside)',
        )).filter(element => element.getClientRects().length).length,
        feedWidth: document.querySelector('#discovery-title')?.closest('.discovery-stack')?.getBoundingClientRect().width ?? 0,
      }));
      assert.ok(layout.width <= layout.viewport + 1, `Horizontal overflow at ${viewport.width} on ${route}`);
      assert.ok(layout.mainRight <= layout.viewport + 1, `Main content exceeds ${viewport.width} on ${route}`);
      if (route === '/') {
        assert.equal(layout.sidebarCount, 2, `Discovery uses three columns at ${viewport.width}px`);
        assert.ok(layout.mainWidth <= 1441, `Workspace exceeds 1440px at ${viewport.width}px`);
        assert.ok(layout.feedWidth <= 681, `Feed exceeds 680px at ${viewport.width}px`);
      }
    }
    await page.goto(base, {waitUntil: 'networkidle'});
    await page.screenshot({path: path.join(output, `discover-${viewport.width}x${viewport.height}.png`)});
  }
  await assertResponsiveDiscoveryColumns(1180, 2);
  await assertResponsiveDiscoveryColumns(1179, 1);
  await assertResponsiveDiscoveryColumns(1000, 1);
  await assertResponsiveDiscoveryColumns(999, 0);
  await page.setViewportSize({width: 1440, height: 900});
  await continueAsGuest();
  await assertDiscoverySidebars('guest');
  await assertResponsiveDiscoveryColumns(1180, 2);
  await assertResponsiveDiscoveryColumns(1179, 1);
  await assertResponsiveDiscoveryColumns(1000, 1);
  await assertResponsiveDiscoveryColumns(999, 0);
  await page.setViewportSize({width: 390, height: 844});
  await page.goto(base, {waitUntil: 'networkidle'});
  const mobileAsideCount = await page.locator('#main-content aside:not(.heritage-aside), #main-content [role="complementary"]:not(.heritage-aside)').evaluateAll(elements =>
    elements.filter(element => element.getClientRects().length).length,
  );
  assert.equal(mobileAsideCount, 0, 'Mobile discovery remains feed-only');
  assert.equal(await page.locator('.mobile-nav a').count(), 4, 'Mobile retains four navigation tabs');
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  passed.push('Sidebars and 680px feed meet 3/2/1-column breakpoints; required desktop routes fit; mobile keeps four tabs');
}

try {
  await assertCorruptGuestPreferencesRecovery();
  passed.push('Corrupt guest preferences reset to a valid default record and load successfully after reload in an isolated context');
  await assertDiscoverySidebars('guest');
  await openSettings();

  // Guest choices belong to this isolated browser context and must not seed accounts.
  await setDecorationPaused(true, false);
  await openSettings();
  await choose('theme', 'system');
  await choose('text_size', 'extra_large');
  await toggle('high_contrast', true);
  await choose('language', 'fil');
  await expectGuestPreferences({theme: 'system', text_size: 'extra_large', high_contrast: true, language: 'fil'});
  await page.reload({waitUntil: 'networkidle'});
  await expectRoot({language: 'fil', textSize: 'extra_large', highContrast: 'true'});
  await continueAsGuest();

  await useAccount(fixtures.accountALabel);
  await assertDiscoverySidebars('accountA');
  await openSettings();
  await expectRoot({language: 'en', theme: 'light', textSize: 'standard', highContrast: 'false', reducedMotion: 'false'});
  passed.push('Guest device preferences are not copied into the first signed-in account');

  await chooseAndWait('theme', 'dark');
  await chooseAndWait('text_size', 'large');
  await toggleAndWait('reduced_motion', true);
  await chooseAndWait('language', 'fil');
  await expectRoot({language: 'fil', theme: 'dark', textSize: 'large', reducedMotion: 'true'});
  await reloadAndVerifyAccountRestore({
    label: fixtures.accountALabel,
    accountId: fixtures.accountAId,
    expectedRoot: {language: 'fil', theme: 'dark', textSize: 'large', reducedMotion: 'true'},
  });
  await assertBodyContrast();
  await assertFilipinoSidebarCopy();
  await assertBodyContrast();
  passed.push('Account preferences persist across reload; Filipino updates the root language and sidebar privacy remains intact');

  await useAccount(fixtures.accountBLabel);
  await assertDiscoverySidebars('accountB');
  await openSettings();
  await expectRoot({language: 'en', theme: 'light', textSize: 'standard', highContrast: 'false', reducedMotion: 'false'});
  passed.push('A second account starts with its own defaults rather than the first account private settings');

  // Hold the first save while making a newer edit; both writes must serialize and persist.
  let releaseFirst;
  let firstRequestSeen;
  let secondRequestSeen;
  const firstSeen = new Promise(resolve => { firstRequestSeen = resolve; });
  const secondSeen = new Promise(resolve => { secondRequestSeen = resolve; });
  const firstGate = new Promise(resolve => { releaseFirst = resolve; });
  const saveBodies = [];
  await page.route('**/api/v1/me/preferences', async route => {
    if (route.request().method() === 'PATCH') {
      saveBodies.push(route.request().postDataJSON());
      if (saveBodies.length === 1) {
        firstRequestSeen();
        await firstGate;
      } else if (saveBodies.length === 2) {
        secondRequestSeen();
      }
    }
    await route.continue();
  });
  await choose('text_size', 'extra_large');
  await firstSeen;
  await toggle('high_contrast', true);
  await page.waitForTimeout(300);
  assert.equal(saveBodies.length, 1, 'Rapid preference edits should serialize while the first save is pending');
  const firstResponse = page.waitForResponse(response =>
    preferenceUrl(response.url()) && response.request().method() === 'PATCH' &&
    response.request().postDataJSON().text_size === 'extra_large',
  );
  const secondResponse = page.waitForResponse(response =>
    preferenceUrl(response.url()) && response.request().method() === 'PATCH' &&
    response.request().postDataJSON().high_contrast === true,
  );
  releaseFirst();
  await secondSeen;
  assert.ok((await firstResponse).ok(), 'First rapid preference save succeeds');
  assert.ok((await secondResponse).ok(), 'Queued rapid preference save succeeds');
  await page.unroute('**/api/v1/me/preferences');
  await page.reload({waitUntil: 'networkidle'});
  await expectRoot({language: 'en', theme: 'light', textSize: 'extra_large', highContrast: 'true'});

  // A response from the old account must not publish into a newly active account.
  let releaseLate;
  let resolveLateSeen;
  const lateSeen = new Promise(resolve => { resolveLateSeen = resolve; });
  const lateGate = new Promise(resolve => { releaseLate = resolve; });
  await page.route('**/api/v1/me/preferences', async route => {
    if (route.request().method() === 'PATCH' && route.request().postDataJSON().text_size === 'standard') {
      resolveLateSeen();
      await lateGate;
    }
    await route.continue();
  });
  const lateResponse = page.waitForResponse(response =>
    preferenceUrl(response.url()) && response.request().method() === 'PATCH' &&
    response.request().postDataJSON().text_size === 'standard',
  );
  await choose('text_size', 'standard');
  await lateSeen;
  await expectRoot({textSize: 'standard'});
  await useAccount(fixtures.accountALabel);
  // Stay in this document: a hard navigation cancels the held fetch rather than
  // exercising its stale-response guard.
  await expectRoot({language: 'fil', theme: 'dark', textSize: 'large', highContrast: 'false', reducedMotion: 'true'});
  releaseLate();
  assert.ok((await lateResponse).ok(), 'The delayed save for the previous account succeeds');
  await expectRoot({language: 'fil', theme: 'dark', textSize: 'large', highContrast: 'false', reducedMotion: 'true'});
  await page.unroute('**/api/v1/me/preferences');
  await useAccount(fixtures.accountBLabel);
  await openSettings();
  await expectRoot({language: 'en', theme: 'light', textSize: 'standard', highContrast: 'true', reducedMotion: 'false'});
  passed.push('Serialized rapid edits persist on their original account; delayed responses do not replace the active account settings');

  // Failed writes keep the chosen value and expose an explicit retry.
  let failedOnce = false;
  await page.route('**/api/v1/me/preferences', async route => {
    if (route.request().method() === 'PATCH' && !failedOnce) {
      failedOnce = true;
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({error: {code: 'temporary_failure', message: 'Retry this preference save.'}}),
      });
      return;
    }
    await route.continue();
  });
  await choose('text_size', 'large');
  const saveAlert = page.locator('main').getByRole('alert');
  await saveAlert.waitFor({state: 'visible'});
  await expectRoot({textSize: 'large'});
  const retryResponse = waitForPatch();
  await saveAlert.locator('xpath=..').locator('button').click();
  assert.ok((await retryResponse).ok(), 'Preference save retry succeeds');
  await page.unroute('**/api/v1/me/preferences');
  await page.reload({waitUntil: 'networkidle'});
  await expectRoot({textSize: 'large'});
  passed.push('A failed save retains the selected value and retry persists it');

  // System theme and OS motion preferences combine with the saved app choices.
  await chooseAndWait('theme', 'system');
  await page.emulateMedia({colorScheme: 'dark'});
  await expectRoot({theme: 'dark'});
  await page.emulateMedia({colorScheme: 'light'});
  await expectRoot({theme: 'light'});
  await chooseAndWait('theme', 'light');
  await page.emulateMedia({colorScheme: 'dark'});
  await expectRoot({theme: 'light'});
  await page.emulateMedia({reducedMotion: 'reduce'});
  await expectRoot({reducedMotion: 'true'});
  await assertReducedMotionSearchLayout();
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await expectRoot({reducedMotion: 'false'});
  await openSettings();
  await toggleAndWait('reduced_motion', true);
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await expectRoot({reducedMotion: 'true'});
  await assertReducedMotionSearchLayout();
  await openSettings();
  await toggleAndWait('reduced_motion', false);
  await expectRoot({reducedMotion: 'false'});
  passed.push('System theme follows OS changes; explicit theme wins; reduced motion honors both OS and app settings');

  await toggleAndWait('high_contrast', false);
  await assertBodyContrast();
  await toggleAndWait('high_contrast', true);
  await assertBodyContrast();
  await setDecorationPaused(true, true);
  await setDecorationPaused(false, true);
  await assertBodyContrast();
  passed.push('High-contrast and decoration-pause preferences remain operable and readable');

  // Open, keyboard-operate, and dismiss the existing registration sheet without submitting.
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto(`${base}/events?eventId=${encodeURIComponent(fixtures.eventId)}`, {waitUntil: 'networkidle'});
  const trigger = page.locator('button[aria-haspopup="dialog"][aria-controls^="registration-confirmation-"]');
  await trigger.click();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor({state: 'visible'});
  assert.equal(await dialog.evaluate(element => element.contains(document.activeElement)), true);
  const buttons = dialog.getByRole('button');
  const firstButton = buttons.first();
  const lastButton = buttons.last();
  await page.keyboard.press('Shift+Tab');
  assert.equal(await lastButton.evaluate(element => element === document.activeElement), true);
  await page.keyboard.press('Tab');
  assert.equal(await firstButton.evaluate(element => element === document.activeElement), true);
  await page.keyboard.press('Escape');
  await dialog.waitFor({state: 'hidden'});
  assert.equal(await trigger.evaluate(element => element === document.activeElement), true);
  passed.push('Registration sheet contains keyboard focus, closes on Escape, and returns focus without changing registration state');

  await exerciseDesktopViewports();
  assert.deepEqual(pageErrors, [], 'No uncaught browser errors');
} catch (error) {
  await page.screenshot({path: path.join(output, 'failure.png'), fullPage: true});
  console.error(JSON.stringify({
    path: new URL(page.url()).pathname,
    heading: await page.locator('main h1').allTextContents(),
    alerts: await page.getByRole('alert').allTextContents(),
  }));
  throw error;
} finally {
  await writeFile(path.join(output, 'results.json'), JSON.stringify({
    method: 'Local browser and isolated scratch PostgreSQL; not participant validation',
    passed,
    pageErrors,
  }, null, 2));
  await browser.close();
}

console.log(JSON.stringify({passed, output}));
