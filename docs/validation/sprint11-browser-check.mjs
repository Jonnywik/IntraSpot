// Bounded rendered Sprint 11 journeys; evidence is local and not participant validation.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.SPRINT11_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT11_FIXTURES);
const output = path.resolve(process.env.SPRINT11_EVIDENCE_DIR);
await mkdir(output, {recursive: true});

let browser;
let page;
let stage = 'launch';
let contrastRatio = null;
let sheetChecked = false;
const passed = [];
const browserErrors = [];
const geometry = [];
const evidence = name => path.join(output, name);
const visible = locator => locator.waitFor({state: 'visible'});

async function capture(name, fullPage = true) {
  if (fullPage) await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({path: evidence(name), fullPage});
}

function setStage(value) {
  stage = value;
}

async function account(label) {
  // Keep the original account-picker accessible-name locator intact.
  await page.getByLabel('Choose a fictional local account').selectOption({label});
  await page.getByRole('button', {name: 'Use fictional account', exact: true}).click();
  await visible(page.getByText(`Local session: ${label}`, {exact: true}));
}

async function nav(label) {
  const selector = page.viewportSize().width < 768 ? '.mobile-nav' : '.desktop-nav';
  await page.locator(selector).getByRole('link', {name: label, exact: true}).click();
}

async function openEvent(eventId, title) {
  await page.goto(`http://127.0.0.1:3000/events?eventId=${encodeURIComponent(eventId)}`, {
    waitUntil: 'networkidle',
  });
  await visible(page.getByRole('heading', {name: title, level: 1}));
}

async function registerInstant() {
  const previousSize = page.viewportSize();
  if (!sheetChecked) await page.setViewportSize({width: 320, height: 568});
  await page.getByRole('button', {name: 'Register', exact: true}).click();
  const dialog = page.getByRole('dialog');
  await visible(dialog);
  if (!sheetChecked) {
    const bounds = await dialog.boundingBox();
    assert.ok(bounds && bounds.x >= 0 && bounds.y >= 0 && bounds.x + bounds.width <= 321 && bounds.y + bounds.height <= 569,
      'The confirmation sheet stays inside the narrow short viewport');
    await page.keyboard.press('Shift+Tab');
    assert.equal(await dialog.evaluate(element => element.contains(document.activeElement)), true,
      'Confirmation keyboard focus stays inside the dialog');
    await page.keyboard.press('Escape');
    await dialog.waitFor({state: 'hidden'});
    assert.equal(await page.getByRole('button', {name: 'Register', exact: true}).evaluate(element => element === document.activeElement), true,
      'Cancel restores focus to the registration trigger');
    await page.getByRole('button', {name: 'Register', exact: true}).click();
    await visible(dialog);
    await capture('registration-sheet-320-short.png', false);
    sheetChecked = true;
  }
  await dialog.getByRole('button', {name: 'Confirm your registration', exact: true}).click();
  await visible(page.getByText('Your registration is confirmed.', {exact: true}));
  await page.setViewportSize(previousSize);
}

async function waitForPreferenceSave() {
  await visible(page.getByRole('status').filter({hasText: 'Preferences saved.'}));
}

function accessibilityCheckbox(index) {
  return page.locator('#settings-accessibility-heading')
    .locator('xpath=..')
    .getByRole('checkbox')
    .nth(index);
}

async function assertMobileGeometry(width, height, {localized = false} = {}) {
  await page.setViewportSize({width, height});
  await page.waitForFunction(() => {
    const nav = document.querySelector('.mobile-nav');
    const measured = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--mobile-nav-height'));
    return nav && Math.abs(nav.getBoundingClientRect().height - measured) <= 1;
  });
  const metrics = await page.evaluate(() => {
    const nav = document.querySelector('.mobile-nav');
    const navRect = nav?.getBoundingClientRect();
    const root = document.documentElement;
    const parsedHeight = Number.parseFloat(getComputedStyle(root).getPropertyValue('--mobile-nav-height'));
    return {
      innerWidth,
      innerHeight,
      scrollWidth: Math.max(root.scrollWidth, document.body.scrollWidth),
      navCount: document.querySelectorAll('.mobile-nav a').length,
      navHeight: navRect?.height ?? 0,
      navBottom: navRect?.bottom ?? 0,
      measuredHeight: parsedHeight,
      navTargets: [...document.querySelectorAll('.mobile-nav a')].map(link => ({
        href: new URL(link.href).pathname,
        height: link.getBoundingClientRect().height,
      })),
      utilityTargets: [...document.querySelectorAll('.utilities .utility-icon, .utilities .avatar')]
        .map(link => ({label: link.getAttribute('aria-label'), height: link.getBoundingClientRect().height})),
      demoSelectHeight: document.querySelector('.local-account-controls select')?.getBoundingClientRect().height ?? 0,
      demoButtonHeight: document.querySelector('.local-account-controls button')?.getBoundingClientRect().height ?? 0,
      bodyBottomPadding: Number.parseFloat(getComputedStyle(document.body).paddingBottom),
    };
  });
  assert.equal(metrics.navCount, 4, 'The mobile shell retains its four destinations');
  assert.ok(metrics.scrollWidth <= metrics.innerWidth + 1, `No horizontal overflow at ${width}x${height}`);
  assert.ok(Math.abs(metrics.navHeight - metrics.measuredHeight) <= 1.5,
    'The shared shell height follows the measured mobile navigation');
  assert.ok(Math.abs(metrics.navBottom - metrics.innerHeight) <= 1.5, 'The fixed navigation stays at the viewport edge');
  assert.ok(metrics.bodyBottomPadding >= metrics.measuredHeight - 1, 'Page content clears the fixed navigation');
  assert.ok(metrics.navTargets.every(target => target.height >= 44), 'Mobile destination targets are at least 44px');
  assert.equal(metrics.utilityTargets.length, 2, 'Profile and Notifications utilities remain present');
  assert.ok(metrics.utilityTargets.every(target => target.height >= 44), 'Header utilities are at least 44px');
  if (!localized) {
    assert.ok(metrics.demoSelectHeight >= 44, 'The account picker remains a 44px touch target');
    assert.ok(metrics.demoButtonHeight >= 44, 'The local account action remains a 44px touch target');
  }
  return metrics;
}

async function checkFocusAndShell() {
  await visible(page.locator('.mobile-nav'));
  const links = await page.locator('.mobile-nav a').evaluateAll(nodes => nodes.map(node => ({
    path: new URL(node.href).pathname,
    label: node.textContent.trim(),
  })));
  assert.deepEqual(links.map(link => link.path), ['/', '/my-events', '/chat', '/settings']);
  assert.deepEqual(links.map(link => link.label), ['Discover', 'My Events', 'Chat', 'Settings']);
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('skip-link')), true,
    'Keyboard focus first reaches the skip link');
  const skipRect = await page.locator('.skip-link').boundingBox();
  assert.ok(skipRect && skipRect.width > 0 && skipRect.height > 0, 'The focused skip link is visible');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => location.hash === '#main-content');
  await visible(page.getByRole('link', {name: 'Profile'}));
  await visible(page.getByRole('link', {name: 'Notifications'}));
}

try {
  browser = await chromium.launch({channel: 'msedge', headless: true});
  const context = await browser.newContext({
    viewport: {width: 390, height: 844},
    reducedMotion: 'reduce',
    isMobile: true,
    hasTouch: true,
  });
  page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on('pageerror', () => browserErrors.push('uncaught_browser_error'));

  setStage('guest search and mobile shell');
  await page.goto('http://127.0.0.1:3000/', {waitUntil: 'networkidle'});
  await checkFocusAndShell();
  await page.getByRole('button', {name: 'Continue as guest', exact: true}).click();
  await page.getByLabel('Search events or organizations', {exact: true}).fill('Fictional Sprint 11');
  await visible(page.getByText(fixtures.searchEventTitle, {exact: true}));
  await visible(page.getByText(fixtures.otherEventTitle, {exact: true}));
  assert.equal(await page.getByRole('button', {name: 'My Clubs', exact: true}).count(), 0,
    'Guests do not receive the member-only My Clubs filter');
  await capture('guest-search-mobile.png');
  passed.push('Guest global search, four mobile destinations, keyboard skip link, and header utilities');

  setStage('guest preference persistence');
  await nav('Settings');
  await waitForPreferenceSave();
  await page.getByLabel('Dark', {exact: true}).check();
  await page.getByLabel('Extra large', {exact: true}).check();
  await page.getByLabel('High contrast', {exact: false}).check();
  await page.getByLabel('Reduce motion', {exact: false}).check();
  await page.locator('#settings-language').selectOption('fil');
  await page.waitForFunction(() => document.documentElement.lang === 'fil');
  await capture('guest-filipino-dark-accessibility.png');
  await page.reload({waitUntil: 'networkidle'});
  await page.waitForFunction(() => document.documentElement.lang === 'fil' &&
    document.documentElement.dataset.theme === 'dark' &&
    document.documentElement.dataset.textSize === 'extra_large' &&
    document.documentElement.dataset.highContrast === 'true');
  assert.equal(await page.locator('#settings-language').inputValue(), 'fil');
  assert.equal(await accessibilityCheckbox(1).isChecked(), true);
  await page.locator('#settings-language').selectOption('en');
  await page.waitForFunction(() => document.documentElement.lang === 'en');
  await capture('guest-preferences-reloaded.png');
  passed.push('Guest device preferences persist through reload in Filipino, dark, XL, high contrast, and reduced motion');

  setStage('account preference isolation and My Clubs');
  await account('Fictional student 1');
  await nav('Settings');
  await waitForPreferenceSave();
  assert.equal(await page.locator('#settings-language').inputValue(), 'en', 'Guest language does not leak to an account');
  assert.equal(await page.getByLabel('Light', {exact: true}).isChecked(), true, 'Guest theme does not leak to an account');
  assert.equal(await page.getByLabel('Standard', {exact: true}).isChecked(), true, 'Guest text size does not leak to an account');
  assert.equal(await page.getByLabel('High contrast', {exact: false}).isChecked(), false);
  await nav('Discover');
  await page.getByLabel('Search events or organizations', {exact: true}).fill('Fictional Sprint 11');
  await visible(page.getByText(fixtures.otherEventTitle, {exact: true}));
  await page.getByRole('button', {name: 'My Clubs', exact: true}).click();
  await visible(page.getByText(fixtures.searchEventTitle, {exact: true}));
  await page.getByText(fixtures.otherEventTitle, {exact: true}).waitFor({state: 'hidden'});
  await capture('member-my-clubs-mobile.png');
  passed.push('Account preferences stay separate from guest storage; My Clubs narrows member search');

  setStage('registration eligibility and profile completion');
  await account('Fictional visitor (not PLM)');
  await openEvent(fixtures.searchEventId, fixtures.searchEventTitle);
  await visible(page.getByText(/^Registration requires an eligible PLM account\./));
  assert.equal(await page.getByRole('button', {name: 'Register', exact: true}).count(), 0);

  await account('Fictional incomplete profile');
  await openEvent(fixtures.searchEventId, fixtures.searchEventTitle);
  await visible(page.getByText(/^Complete your profile before registering\./));
  await page.getByRole('link', {name: 'Update your profile', exact: true}).click();
  await page.getByRole('button', {name: 'Save profile', exact: true}).click();
  await visible(page.getByRole('alert').filter({hasText: 'Enter a nickname.'}));
  assert.equal(await page.getByLabel('Nickname', {exact: true}).evaluate(element => element === document.activeElement), true);
  await page.getByLabel('Nickname', {exact: true}).fill('Fictional Profile Complete');
  await page.getByLabel('Age bracket', {exact: true}).fill('18-24');
  await page.getByLabel('Interest or vibe tags', {exact: true}).fill('arts, community');
  let failProfileOnce = true;
  await page.route('**/api/v1/me/profile', async route => {
    if (route.request().method() !== 'PATCH' || !failProfileOnce) return route.continue();
    failProfileOnce = false;
    await route.fulfill({status: 503, contentType: 'application/json',
      headers: {'access-control-allow-origin': 'http://127.0.0.1:3000'},
      body: JSON.stringify({error: {code: 'request_failed', message: 'Please retry.'}})});
  });
  await page.getByRole('button', {name: 'Save profile', exact: true}).click();
  await visible(page.locator('main').getByRole('alert').filter({hasText: 'Please retry.'}));
  assert.equal(await page.getByLabel('Nickname', {exact: true}).inputValue(), 'Fictional Profile Complete');
  assert.equal(await page.getByLabel('Interest or vibe tags', {exact: true}).inputValue(), 'arts, community');
  await page.getByRole('button', {name: 'Retry', exact: true}).click();
  await visible(page.getByRole('status').filter({hasText: 'Profile saved.'}));
  await page.unroute('**/api/v1/me/profile');
  await openEvent(fixtures.searchEventId, fixtures.searchEventTitle);
  await registerInstant();
  await page.reload({waitUntil: 'networkidle'});
  await visible(page.getByText('Your registration is confirmed.', {exact: true}));
  assert.equal(await page.getByRole('button', {name: 'Register', exact: true}).count(), 0,
    'Reload uses the account saved registration instead of offering a duplicate request');
  passed.push('Ineligible identity is denied; profile validates, preserves failed-save input and retries; a bounded focus-safe confirmation unlocks registration');

  setStage('faculty registration and My Events states');
  await account('Fictional faculty');
  await openEvent(fixtures.searchEventId, fixtures.searchEventTitle);
  await registerInstant();
  await openEvent(fixtures.approvalEventId, fixtures.approvalEventTitle);
  await page.getByRole('button', {name: 'Request to register', exact: true}).click();
  const approvalDialog = page.getByRole('dialog');
  await visible(approvalDialog);
  await approvalDialog.getByRole('button', {name: 'Send registration request', exact: true}).click();
  await visible(page.getByText(/Your request is pending organizer approval\./));
  await openEvent(fixtures.withdrawalEventId, fixtures.withdrawalEventTitle);
  await registerInstant();

  await page.goto('http://127.0.0.1:3000/my-events?tab=pending', {waitUntil: 'networkidle'});
  await visible(page.getByRole('heading', {name: 'My Events', exact: true}));
  const pendingTab = page.getByRole('tab', {name: /Pending/});
  await visible(pendingTab);
  assert.equal(await pendingTab.getAttribute('aria-selected'), 'true');
  const pendingCard = page.locator('article').filter({hasText: fixtures.approvalEventTitle});
  await visible(pendingCard);
  assert.equal(await pendingCard.getByRole('link', {name: 'Open event chat', exact: true}).count(), 0,
    'A pending approval does not expose chat');
  await page.getByRole('tab', {name: /Confirmed/}).click();
  const confirmedCard = page.locator('article').filter({hasText: fixtures.searchEventTitle});
  await visible(confirmedCard);
  await visible(confirmedCard.getByRole('link', {name: 'Open event chat', exact: true}));
  const withdrawalCard = page.locator('article').filter({hasText: fixtures.withdrawalEventTitle});
  await visible(withdrawalCard);
  await withdrawalCard.getByRole('button', {name: 'Withdraw registration', exact: true}).click();
  await visible(page.getByRole('status').filter({
    hasText: `Registration withdrawn for ${fixtures.withdrawalEventTitle}.`,
  }));
  passed.push('Faculty approval is pending, confirmed registration unlocks chat, and My Events withdrawal reports success');

  setStage('waitlist position and attendee actions');
  await account('Fictional student 3');
  await openEvent(fixtures.fullEventId, fixtures.fullEventTitle);
  await page.getByRole('button', {name: 'Join waitlist', exact: true}).click();
  const waitlistDialog = page.getByRole('dialog');
  await visible(waitlistDialog);
  await waitlistDialog.getByRole('button', {name: 'Join waitlist', exact: true}).click();
  await visible(page.getByText('Waitlist position: 1.', {exact: true}));
  await visible(page.getByText('You are on the waitlist. No estimated wait time is available.', {exact: true}));
  await page.reload({waitUntil: 'networkidle'});
  await visible(page.getByText('Waitlist position: 1.', {exact: true}));
  assert.equal(await page.getByRole('button', {name: 'Join waitlist', exact: true}).count(), 0);
  await page.goto('http://127.0.0.1:3000/my-events?tab=waitlist', {waitUntil: 'networkidle'});
  await visible(page.locator('article').filter({hasText: fixtures.fullEventTitle}));
  await nav('Chat');
  await visible(page.getByText('No confirmed event chats are available.', {exact: true}));
  passed.push('Full event shows durable waitlist position/no-ETA copy in registration and My Events; waitlist grants no chat access');

  setStage('active chat send, retry, and archived read-only');
  await account('Fictional faculty');
  await page.goto('http://127.0.0.1:3000/my-events', {waitUntil: 'networkidle'});
  await page.getByRole('tab', {name: /Confirmed/}).waitFor({state: 'visible'});
  const activeCard = page.locator('article').filter({hasText: fixtures.searchEventTitle});
  await visible(activeCard.getByRole('link', {name: 'Open event chat', exact: true}));
  await activeCard.getByRole('link', {name: 'Open event chat', exact: true}).click();
  await visible(page.getByRole('heading', {name: fixtures.searchEventTitle, level: 2}));
  await page.setViewportSize({width: 390, height: 568});
  const composer = page.getByLabel('Write a message', {exact: true});
  await visible(composer);
  await composer.scrollIntoViewIfNeeded();
  const composerGeometry = await composer.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const bottomNav = document.querySelector('.mobile-nav')?.getBoundingClientRect().top ?? innerHeight;
    return {bottom: rect.bottom, navTop: bottomNav, height: rect.height};
  });
  assert.ok(composerGeometry.height > 0 && composerGeometry.bottom <= composerGeometry.navTop,
    'The message composer is reachable above the fixed navigation in a short viewport');

  const retryKeys = [];
  let responseLost = false;
  await page.route('**/api/v1/events/*/chat/messages', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    const body = route.request().postDataJSON();
    retryKeys.push(body.client_key);
    if (!responseLost) {
      responseLost = true;
      const upstream = await route.fetch();
      assert.ok(upstream.ok(), 'The first chat post reached the isolated API');
      await route.abort('failed');
      return;
    }
    await route.continue();
  });
  await composer.fill('Fictional Sprint 11 chat retry');
  await page.getByRole('button', {name: 'Send message', exact: true}).click();
  await visible(page.getByRole('alert'));
  await page.getByRole('button', {name: 'Retry unchanged message', exact: true}).click();
  await visible(page.getByRole('log').getByText('Fictional Sprint 11 chat retry', {exact: true}));
  assert.equal(retryKeys.length, 2);
  assert.ok(retryKeys[0] && retryKeys[0] === retryKeys[1], 'Retry reuses the original idempotency key');
  assert.equal(await page.getByRole('log').getByText('Fictional Sprint 11 chat retry', {exact: true}).count(), 1,
    'The lost-response retry persists only one message');
  await page.unroute('**/api/v1/events/*/chat/messages');
  await capture('short-mobile-chat-retry.png', false);
  await page.getByRole('link', {name: 'All event chats', exact: true}).click();
  const chatList = page.getByRole('navigation', {name: 'Event chat list', exact: true});
  await visible(chatList);
  await visible(chatList.getByRole('link').filter({hasText: fixtures.searchEventTitle}));
  await page.goto(`http://127.0.0.1:3000/my-events?tab=past`, {waitUntil: 'networkidle'});
  const pastTab = page.getByRole('tab', {name: /Past/});
  await visible(pastTab);
  await pastTab.click();
  const pastCard = page.locator('article').filter({hasText: fixtures.archiveEventTitle});
  await visible(pastCard);
  await pastCard.getByRole('link', {name: 'Open event chat', exact: true}).click();
  await visible(page.getByText('This chat is archived and read-only after its scheduled end.', {exact: true}));
  assert.equal(await page.getByLabel('Write a message', {exact: true}).count(), 0);
  await visible(page.getByText('Fictional archived discussion', {exact: true}));
  await visible(page.getByRole('status').filter({hasText: /Deletes in/}));
  await capture('archived-chat-retention-mobile.png');
  await page.getByRole('link', {name: 'All event chats', exact: true}).click();
  await visible(page.getByRole('navigation', {name: 'Event chat list', exact: true})
    .getByRole('link').filter({hasText: fixtures.archiveEventTitle}));
  passed.push('Real chat send survives a lost response and same-key retry; archived chat is read-only with retention countdown');

  setStage('notifications and account preferences');
  await page.goto('http://127.0.0.1:3000/notifications', {waitUntil: 'networkidle'});
  const notifications = page.getByRole('list', {name: 'Notifications', exact: true});
  await visible(notifications);
  const notice = notifications.getByRole('listitem').filter({
    hasText: 'A fictional registration update is ready to review.',
  });
  await visible(notice);
  await notice.getByRole('button', {name: 'Mark as read', exact: true}).click();
  await visible(page.getByRole('status').filter({hasText: 'Notification marked as read.'}));
  await page.goto('http://127.0.0.1:3000/settings', {waitUntil: 'networkidle'});
  await waitForPreferenceSave();
  assert.equal(await page.getByRole('status').filter({hasText: 'These preferences are saved for this account.'}).count(), 1);
  await page.getByLabel('Dark', {exact: true}).check();
  await page.getByLabel('Extra large', {exact: true}).check();
  await page.getByLabel('High contrast', {exact: false}).check();
  await page.getByLabel('Reduce motion', {exact: false}).check();
  await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark' &&
    document.documentElement.dataset.textSize === 'extra_large' &&
    document.documentElement.dataset.highContrast === 'true' &&
    document.documentElement.dataset.reducedMotion === 'true');
  await waitForPreferenceSave();
  contrastRatio = await page.evaluate(() => {
    const parse = color => color.match(/[\d.]+/g).slice(0, 3).map(Number);
    const luminance = color => {
      const channel = parse(color).map(value => {
        const normalized = value / 255;
        return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
      });
      return channel[0] * 0.2126 + channel[1] * 0.7152 + channel[2] * 0.0722;
    };
    const foreground = luminance(getComputedStyle(document.body).color);
    const background = luminance(getComputedStyle(document.body).backgroundColor);
    return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
  });
  assert.ok(contrastRatio >= 7, `Dark high-contrast body text ratio is ${contrastRatio.toFixed(2)}:1`);
  const reducedTransition = await page.locator('button').first().evaluate(element => getComputedStyle(element).transitionDuration);
  assert.ok(reducedTransition.split(',').every(value => Number.parseFloat(value) === 0),
    'Reduced motion disables button transitions');

  setStage('mobile viewport geometry sweep');
  for (const [width, height] of [[320, 844], [360, 844], [390, 844], [430, 844], [390, 568], [667, 375]]) {
    const metrics = await assertMobileGeometry(width, height);
    geometry.push({width, height, navHeight: metrics.navHeight, measuredHeight: metrics.measuredHeight});
    if (height === 844) await capture(`settings-mobile-${width}.png`);
  }
  passed.push('320/360/390/430 widths, short-height, and landscape geometry retain measured shell, 44px targets, and no overflow');

  setStage('Filipino XL dark contrast and preference persistence');
  await page.setViewportSize({width: 390, height: 844});
  const filipinoPreferenceSave = page.waitForResponse(response =>
    response.request().method() === 'PATCH' && new URL(response.url()).pathname.endsWith('/me/preferences'));
  await page.locator('#settings-language').selectOption('fil');
  await filipinoPreferenceSave;
  await page.waitForFunction(() => document.documentElement.lang === 'fil');
  await capture('account-filipino-dark-xl-contrast-motion.png');
  await page.reload({waitUntil: 'networkidle'});
  await page.waitForFunction(() => document.documentElement.lang === 'fil' &&
    document.documentElement.dataset.theme === 'dark' &&
    document.documentElement.dataset.textSize === 'extra_large' &&
    document.documentElement.dataset.highContrast === 'true' &&
    document.documentElement.dataset.reducedMotion === 'true');
  assert.equal(await page.locator('#settings-language').inputValue(), 'fil');
  assert.equal(await accessibilityCheckbox(0).isChecked(), true);
  assert.equal(await accessibilityCheckbox(1).isChecked(), true);
  const localizedGeometry = await assertMobileGeometry(390, 844, {localized: true});
  geometry.push({width: 390, height: 844, localized: true, navHeight: localizedGeometry.navHeight});
  passed.push(`Account preferences persist on the account; Filipino dark high-contrast body text is ${contrastRatio.toFixed(2)}:1`);

  setStage('all mobile attendee surfaces in Filipino extra-large text');
  const surfaces = [
    ['discover', '/'], ['detail', `/events?eventId=${fixtures.searchEventId}`],
    ['my-events', '/my-events'], ['chat', `/chat?eventId=${fixtures.searchEventId}`],
    ['profile', '/profile'], ['inbox', '/notifications'],
  ];
  for (const [surface, route] of surfaces) {
    await page.goto(`http://127.0.0.1:3000${route}`, {waitUntil: 'networkidle'});
    await page.waitForFunction(() => document.documentElement.lang === 'fil');
    for (const width of [320, 360, 390, 430]) {
      const metrics = await assertMobileGeometry(width, 844, {localized: true});
      geometry.push({surface, width, height: 844, localized: true, navHeight: metrics.navHeight});
      if (width === 390) await capture(`filipino-xl-${surface}-390.png`);
    }
  }
  passed.push('Discovery, details, My Events, chat, profile and inbox fit all four widths with Filipino extra-large text');

  setStage('mobile staff denial and desktop smoke');
  await page.goto('http://127.0.0.1:3000/settings', {waitUntil: 'networkidle'});
  await page.locator('#settings-language').selectOption('en');
  await page.waitForFunction(() => document.documentElement.lang === 'en');
  await account('Fictional organizer');
  await page.goto(`http://127.0.0.1:3000/workspace?orgId=${encodeURIComponent(fixtures.orgId)}`, {
    waitUntil: 'networkidle',
  });
  await visible(page.getByRole('note').filter({hasText: 'Organization management is available on desktop.'}));
  assert.equal(await page.getByRole('heading', {name: 'Workspace', exact: true}).isVisible().catch(() => false), false,
    'Mobile does not expose workspace management controls');
  await capture('mobile-workspace-denial.png');
  await page.setViewportSize({width: 1440, height: 900});
  await visible(page.getByRole('heading', {name: 'Workspace', exact: true}));
  await visible(page.getByRole('navigation', {name: 'Owner and admin workspaces'})
    .getByRole('link').filter({hasText: fixtures.orgName}));
  await capture('desktop-workspace-smoke.png');
  passed.push('Workspace management is withheld on mobile and owner workspace smoke-checks on desktop');

  assert.equal(browserErrors.length, 0, 'No uncaught browser errors');
} catch (error) {
  if (page) {
    try {
      await page.screenshot({path: evidence('failure.png'), fullPage: true});
      const errorName = error && typeof error.name === 'string' ? error.name.slice(0, 100) : 'Error';
      const errorMessage = error && typeof error.message === 'string'
        ? error.message.split(/\r?\n/, 1)[0]
          .replace(/\bBearer\s+[^\s,;]+/gi, 'Bearer [redacted]')
          .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '[redacted-email]')
          .replace(/\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, '[redacted-token]')
          .slice(0, 500)
        : 'Browser check failed without a message';
      await writeFile(evidence('failure.json'), JSON.stringify({
        stage,
        pathname: new URL(page.url()).pathname,
        browserErrors,
        errorName,
        errorMessage,
      }, null, 2));
    } catch {
      // Keep failure evidence best-effort and avoid serializing browser/network details.
    }
  }
  throw new Error('Sprint 11 browser journey failed; inspect sanitized timestamped evidence.');
} finally {
  await writeFile(evidence('results.json'), JSON.stringify({
    method: 'Isolated test PostgreSQL with local Edge; not participant/device validation',
    passed,
    browserErrors,
    contrastRatio,
  }, null, 2));
  if (browser) await browser.close();
}

await writeFile(evidence('geometry.json'), JSON.stringify({geometry}, null, 2));
