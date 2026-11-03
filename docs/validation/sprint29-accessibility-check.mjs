// Rendered registration journeys on fictional test data; not participant testing.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.SPRINT29_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT29_FIXTURES ?? '{}');
for (const name of ['confirmation', 'waitlist', 'retry']) {
  assert.ok(fixtures[name]?.id && fixtures[name]?.title, `Missing ${name} test event`);
}

const outputRoot = path.resolve(process.env.SPRINT29_EVIDENCE_DIR);
const runId = `${new Date().toISOString().replace(/[:.]/g, '-')}-${process.pid}`;
const output = path.join(outputRoot, `run-${runId}`);
await mkdir(output, {recursive: true});

const browser = await chromium.launch({channel: 'msedge', headless: true});
const context = await browser.newContext({viewport: {width: 1440, height: 900}, reducedMotion: 'no-preference'});
const page = await context.newPage();
page.setDefaultTimeout(15000);

const report = {
  method: 'Microsoft Edge rendered checks against isolated fictional test API data',
  participantValidation: false,
  passed: [],
  failures: [],
  viewports: [],
  screenshots: [],
  retry: {attempts: 0, keyPresent: false, sameKey: false, samePayload: false},
  browserErrors: 0,
};
page.on('pageerror', () => { report.browserErrors += 1; });

async function check(name, action) {
  try {
    await action();
    report.passed.push(name);
    return true;
  } catch (error) {
    report.failures.push({name, errorType: error?.name ?? 'Error', message: String(error?.message ?? '').split('\n')[0].slice(0, 180)});
    return false;
  }
}

async function capture(name) {
  const file = `${name}.png`;
  await page.screenshot({path: path.join(output, file), fullPage: true});
  report.screenshots.push(file);
}

async function visitEvent(event) {
  await page.goto(`http://127.0.0.1:3000/events?eventId=${encodeURIComponent(event.id)}`, {waitUntil: 'domcontentloaded'});
  await page.getByRole('heading', {level: 1, name: event.title, exact: true}).waitFor({state: 'visible'});
  await page.locator('button[aria-haspopup="dialog"]').waitFor({state: 'visible'});
}

async function openConfirmation() {
  const trigger = page.locator('button[aria-haspopup="dialog"]');
  await trigger.focus();
  await page.keyboard.press('Enter');
  const dialog = page.locator('[role="dialog"]');
  await dialog.waitFor({state: 'visible'});
  await page.waitForFunction(() => {
    const action = document.querySelector('[role="dialog"] .actions button[aria-live="polite"]');
    return !!action && !action.disabled;
  });
  return {trigger, dialog, action: dialog.locator('.actions button[aria-live="polite"]')};
}

async function activateWithKeyboard(action, scope) {
  const focusables = scope.locator('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
  const count = await focusables.count();
  for (let index = 0; index <= count; index += 1) {
    if (await action.evaluate(element => document.activeElement === element)) break;
    await page.keyboard.press('Tab');
  }
  assert.equal(await action.evaluate(element => document.activeElement === element), true);
  await page.keyboard.press('Enter');
}

async function proveConfirmationDialog(size) {
  let dialog;
  try {
    const controls = await openConfirmation();
    dialog = controls.dialog;
    const semantics = await dialog.evaluate(element => {
      const labelledBy = element.getAttribute('aria-labelledby');
      return {
        modal: element.getAttribute('aria-modal'),
        labelledBy,
        title: labelledBy ? document.getElementById(labelledBy)?.textContent?.trim() ?? '' : '',
        initialFocus: document.activeElement === element,
      };
    });
    await check(`Confirmation dialog has rendered modal semantics at ${size.width}x${size.height}`, async () => {
      assert.equal(semantics.modal, 'true');
      assert.ok(semantics.labelledBy && semantics.title.length > 0);
      assert.equal(semantics.initialFocus, true);
      assert.equal(await controls.trigger.getAttribute('aria-expanded'), 'true');
      assert.equal(await controls.trigger.getAttribute('aria-controls'), await dialog.getAttribute('id'));
      assert.ok((await controls.action.innerText()).trim().length > 0);
    });

    const focusables = dialog.locator('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
    const focusableCount = await focusables.count();
    const submit = dialog.locator('.actions button[aria-live="polite"]');
    const cancel = dialog.locator('.actions button.button-secondary');
    await check(`Keyboard can reach and cycle through dialog actions at ${size.width}x${size.height}`, async () => {
      assert.ok(focusableCount >= 2);
      const actionBox = await submit.boundingBox();
      const cancelBox = await cancel.boundingBox();
      assert.ok(actionBox && actionBox.width >= 44 && actionBox.height >= 44);
      assert.ok(cancelBox && cancelBox.width >= 44 && cancelBox.height >= 44);

      await page.keyboard.press('Shift+Tab');
      assert.equal(await cancel.evaluate(element => document.activeElement === element), true);
      await page.keyboard.press('Tab');
      assert.equal(await dialog.evaluate(element => element.contains(document.activeElement)), true);
      let reachedSubmit = false;
      let reachedCancel = await cancel.evaluate(element => document.activeElement === element);
      for (let index = 0; index < focusableCount + 1; index += 1) {
        await page.keyboard.press('Tab');
        const focusState = await dialog.evaluate(element => ({
          inside: element.contains(document.activeElement),
          action: document.activeElement === element.querySelector('.actions button[aria-live="polite"]'),
          cancel: document.activeElement === element.querySelector('.actions button.button-secondary'),
        }));
        assert.equal(focusState.inside, true);
        reachedSubmit ||= focusState.action;
        reachedCancel ||= focusState.cancel;
      }
      assert.equal(reachedSubmit && reachedCancel, true);
    });

    if ([1280, 320].includes(size.width)) await capture(`confirmation-dialog-${size.width}x${size.height}`);
    await page.keyboard.press('Escape');
    await check(`Escape closes the dialog and returns focus at ${size.width}x${size.height}`, async () => {
      await dialog.waitFor({state: 'detached'});
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-haspopup') === 'dialog');
      assert.equal(await controls.trigger.evaluate(element => document.activeElement === element), true);
    });
  } catch (error) {
    report.failures.push({name: `Confirmation dialog journey at ${size.width}x${size.height}`, errorType: error?.name ?? 'Error', message: String(error?.message ?? '').split('\n')[0].slice(0, 180)});
  } finally {
    if (dialog && await dialog.count()) {
      await page.keyboard.press('Escape').catch(() => {});
      await dialog.waitFor({state: 'detached', timeout: 3000}).catch(() => {});
    }
  }
}

async function outcomeRegion() {
  const outcome = page.locator('[role="status"][aria-live="polite"][tabindex="-1"]');
  await outcome.waitFor({state: 'visible'});
  await page.waitForFunction(() => {
    const status = document.querySelector('[role="status"][aria-live="polite"][tabindex="-1"]');
    return !!status && document.activeElement === status;
  });
  const state = await outcome.evaluate(element => ({
    role: element.getAttribute('role'),
    live: element.getAttribute('aria-live'),
    text: element.innerText.trim(),
  }));
  assert.equal(state.role, 'status');
  assert.equal(state.live, 'polite');
  assert.ok(state.text.length > 0);
  return outcome;
}

async function openMyEventsFrom(outcome, title) {
  const link = outcome.locator('a[href^="/my-events"]');
  await link.waitFor({state: 'visible'});
  const box = await link.boundingBox();
  assert.ok(box && box.width >= 44 && box.height >= 44);
  await link.click();
  await page.waitForURL(url => url.pathname === '/my-events');
  await page.getByText(title, {exact: true}).waitFor({state: 'visible'});
  assert.equal(await page.getByText(title, {exact: true}).count(), 1);
}

try {
  await page.goto('http://127.0.0.1:3000/profile', {waitUntil: 'domcontentloaded'});
  const accountPicker = page.getByRole('combobox', {name: 'Choose a fictional local account'});
  await accountPicker.waitFor({state: 'visible'});
  await accountPicker.selectOption('Fictional student 1');
  await page.getByRole('button', {name: 'Use fictional account', exact: true}).click();
  await page.getByRole('status').filter({hasText: 'Fictional student 1'}).waitFor({state: 'visible'});
  report.passed.push('Signed in through the rendered fictional local account flow');

  await page.goto('http://127.0.0.1:3000/settings', {waitUntil: 'domcontentloaded'});
  await page.getByRole('radio', {name: 'Extra large', exact: true}).check();
  await page.getByRole('radio', {name: 'Dark', exact: true}).check();
  await page.getByRole('checkbox', {name: /^High contrast/}).check();
  await page.getByRole('checkbox', {name: /^Reduce motion/}).check();
  await page.getByRole('combobox', {name: /^Language/}).selectOption('fil');
  await page.waitForFunction(() => document.documentElement.lang === 'fil' &&
    document.documentElement.dataset.theme === 'dark' &&
    document.documentElement.dataset.textSize === 'extra_large' &&
    document.documentElement.dataset.highContrast === 'true' &&
    document.documentElement.dataset.reducedMotion === 'true');
  report.passed.push('Filipino, extra large text, dark theme, high contrast, and reduced motion rendered');

  const viewports = [
    {width: 1280, height: 720}, {width: 1366, height: 768}, {width: 1440, height: 900},
    {width: 1920, height: 1080}, {width: 390, height: 844}, {width: 320, height: 740},
  ];
  for (const size of viewports) {
    await page.setViewportSize(size);
    await visitEvent(fixtures.confirmation);
    const action = page.locator('button[aria-haspopup="dialog"]');
    const geometry = await page.evaluate(() => ({
      width: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      language: document.documentElement.lang,
      theme: document.documentElement.dataset.theme,
      textSize: document.documentElement.dataset.textSize,
      highContrast: document.documentElement.dataset.highContrast,
      reducedMotion: document.documentElement.dataset.reducedMotion,
      mobileNavHeight: document.querySelector('.mobile-nav')?.getBoundingClientRect().height ?? 0,
      bottomClearance: parseFloat(getComputedStyle(document.body).paddingBottom) || 0,
    }));
    const actionName = (await action.innerText()).trim();
    const actionBox = await action.boundingBox();
    report.viewports.push({
      route: 'event-details', ...size, ...geometry,
      actionName, actionWidth: actionBox?.width ?? 0, actionHeight: actionBox?.height ?? 0,
    });
    await check(`Rendered event details and registration action are reachable at ${size.width}x${size.height}`, async () => {
      assert.equal(geometry.documentWidth <= geometry.width + 1, true);
      assert.equal(geometry.language, 'fil');
      assert.equal(geometry.theme, 'dark');
      assert.equal(geometry.textSize, 'extra_large');
      assert.equal(geometry.highContrast, 'true');
      assert.equal(geometry.reducedMotion, 'true');
      assert.ok(actionName.length > 0);
      assert.ok(actionBox && actionBox.width >= 44 && actionBox.height >= 44);
    });
    if (size.width <= 390) {
      await check(`Four mobile navigation actions meet touch size and clearance at ${size.width}px`, async () => {
        const links = page.locator('.mobile-nav').getByRole('link');
        assert.equal(await links.count(), 4);
        for (const link of await links.all()) {
          assert.equal(await link.isVisible(), true);
          const box = await link.boundingBox();
          assert.ok(box && box.width >= 44 && box.height >= 44);
        }
        assert.ok(geometry.bottomClearance >= geometry.mobileNavHeight);
      });
    }
    await capture(`details-${size.width}x${size.height}`);
    await proveConfirmationDialog(size);
  }

  await check('Reduced motion suppresses rendered animations', async () => {
    const moving = await page.evaluate(() => [...document.querySelectorAll('*')].filter(element => {
      const style = getComputedStyle(element);
      return style.animationName !== 'none' && style.animationDuration.split(',').some(value => parseFloat(value) > 0.01);
    }).length);
    assert.equal(moving, 0);
  });

  let detailFailure = 429;
  const detailMatcher = url => url.origin === 'http://127.0.0.1:8002' &&
    url.pathname === `/api/v1/events/${fixtures.retry.id}`;
  await context.route(detailMatcher, async route => {
    if (route.request().method() !== 'GET' || detailFailure === null) {
      await route.continue();
      return;
    }
    await route.fulfill({status: detailFailure, contentType: 'application/json',
      headers: {'Retry-After': '2', 'Access-Control-Allow-Origin': 'http://127.0.0.1:3000',
        'Access-Control-Expose-Headers': 'Retry-After'}, body: JSON.stringify({error: {
        code: detailFailure === 429 ? 'rate_limited' : 'database_unavailable',
        message: 'Synthetic recovery fault',
      }})});
  });
  await page.goto(`http://127.0.0.1:3000/events?eventId=${fixtures.retry.id}`);
  const recoveryAlert = page.locator('.panel.error[role="alert"]');
  await recoveryAlert.waitFor({state: 'visible'});
  await check('Throttling announces Retry-After in the rendered Filipino alert', async () => {
    assert.equal(await recoveryAlert.getAttribute('aria-live'), 'assertive');
    assert.match(await recoveryAlert.innerText(), /2/);
    assert.doesNotMatch(await recoveryAlert.innerText(), /Synthetic recovery fault/);
  });
  detailFailure = 503;
  await recoveryAlert.getByRole('button', {name: 'Subukan muli', exact: true}).click();
  await check('Cold-start recovery announces and focuses the rendered error after explicit retry', async () => {
    await page.waitForFunction(() => {
      const alert = document.querySelector('.panel.error[role="alert"]');
      return alert && document.activeElement === alert && !alert.textContent.includes('2');
    });
    assert.doesNotMatch(await recoveryAlert.innerText(), /Synthetic recovery fault/);
  });
  detailFailure = null;
  await recoveryAlert.getByRole('button', {name: 'Subukan muli', exact: true}).click();
  await check('Event-detail recovery returns focus to the real loaded heading', async () => {
    const heading = page.getByRole('heading', {level: 1, name: fixtures.retry.title, exact: true});
    await heading.waitFor();
    await page.waitForFunction(title => document.activeElement?.textContent === title, fixtures.retry.title);
  });
  await context.unroute(detailMatcher);

  await page.setViewportSize({width: 1280, height: 720});
  await visitEvent(fixtures.confirmation);
  const confirmation = await openConfirmation();
  await activateWithKeyboard(confirmation.action, confirmation.dialog);
  const confirmed = await outcomeRegion();
  await check('Successful registration is announced in the rendered polite live region', async () => {
    const text = await confirmed.innerText();
    assert.match(text, /kumpirm/i);
  });
  await capture('registration-confirmed');
  await openMyEventsFrom(confirmed, fixtures.confirmation.title);

  await page.setViewportSize({width: 390, height: 844});
  await visitEvent(fixtures.waitlist);
  const waitlistAction = page.locator('button[aria-haspopup="dialog"]');
  await check('Full event exposes a rendered waitlist action in Filipino', async () => {
    assert.match((await waitlistAction.innerText()).trim(), /waitlist/i);
  });
  const waitlistDialog = await openConfirmation();
  await check('Waitlist confirmation dialog explains the waitlist action', async () => {
    assert.match((await waitlistDialog.dialog.getByRole('heading').innerText()).trim(), /waitlist/i);
    assert.match((await waitlistDialog.action.innerText()).trim(), /waitlist/i);
  });
  await activateWithKeyboard(waitlistDialog.action, waitlistDialog.dialog);
  const waitlisted = await outcomeRegion();
  await check('Real API waitlist outcome announces position one', async () => {
    const text = await waitlisted.innerText();
    assert.match(text, /waitlist/i);
    assert.match(text, /1/);
    assert.match(text, /Walang (?:matantiyang oras|available na tinatayang oras)/i);
  });
  await capture('waitlist-confirmed');
  await openMyEventsFrom(waitlisted, fixtures.waitlist.title);
  await check('My Events repeats waitlist position and the no-estimated-wait explanation', async () => {
    const card = page.locator('article.event-card').filter({
      has: page.getByRole('heading', {name: fixtures.waitlist.title, exact: true}),
    });
    const text = await card.innerText();
    assert.match(text, /Puwesto sa waitlist:\s*1/i);
    assert.match(text, /Walang (?:matantiyang oras|available na tinatayang oras)/i);
  });

  const retryKeys = [];
  const retryBodies = [];
  await context.route(url => url.origin === 'http://127.0.0.1:8002' &&
    url.pathname.endsWith(`/events/${fixtures.retry.id}/registrations`), async route => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    retryKeys.push((await route.request().headerValue('Idempotency-Key')) ?? '');
    retryBodies.push(route.request().postDataJSON());
    if (retryKeys.length === 1) await route.abort('failed');
    else await route.continue();
  });

  await page.setViewportSize({width: 320, height: 740});
  await visitEvent(fixtures.retry);
  const retryDialog = await openConfirmation();
  await activateWithKeyboard(retryDialog.action, retryDialog.dialog);
  const retryAlert = retryDialog.dialog.getByRole('alert');
  await retryAlert.waitFor({state: 'visible'});
  await check('Transport failure renders an assertive error and reachable retry action', async () => {
    assert.equal(await retryAlert.getAttribute('aria-live'), 'assertive');
    assert.ok((await retryAlert.innerText()).trim().length > 0);
    assert.match((await retryDialog.action.innerText()).trim(), /muli/i);
    assert.equal(await retryDialog.action.isEnabled(), true);
  });
  await capture('registration-retry-error');
  await retryDialog.action.click();
  const recovered = await outcomeRegion();
  report.retry = {
    attempts: retryKeys.length,
    keyPresent: retryKeys.length === 2 && retryKeys.every(key => key.length >= 8),
    sameKey: retryKeys.length === 2 && retryKeys[0] === retryKeys[1],
    samePayload: retryBodies.length === 2 && JSON.stringify(retryBodies[0]) === JSON.stringify(retryBodies[1]),
  };
  await check('Retry reuses the original idempotency key and recovers through the real API', async () => {
    assert.equal(report.retry.attempts, 2);
    assert.equal(report.retry.keyPresent, true);
    assert.equal(report.retry.sameKey, true);
    assert.equal(report.retry.samePayload, true);
    assert.deepEqual(retryBodies[0], retryBodies[1]);
    assert.match(await recovered.innerText(), /kumpirm/i);
  });
  await capture('registration-retry-recovered');
  await openMyEventsFrom(recovered, fixtures.retry.title);

  const retryCard = page.locator('article.event-card').filter({
    has: page.getByRole('heading', {name: fixtures.retry.title, exact: true}),
  });
  await retryCard.getByRole('button', {name: 'Bawiin ang pagpaparehistro', exact: true}).click();
  await check('My Events withdrawal preserves keyboard focus on its named success status', async () => {
    await page.waitForFunction(title => {
      const status = document.querySelector('.panel.success[role="status"][tabindex="0"]');
      return status?.textContent.includes(title) && document.activeElement === status &&
        !!status.getAttribute('aria-label');
    }, fixtures.retry.title);
  });

  await check('No uncaught browser errors during the rendered registration journeys', async () => {
    assert.equal(report.browserErrors, 0);
  });
} catch (error) {
  report.failures.push({name: 'Registration journey setup or continuation', errorType: error?.name ?? 'Error', message: String(error?.message ?? '').split('\n')[0].slice(0, 180)});
} finally {
  await writeFile(path.join(output, 'results.json'), `${JSON.stringify(report)}\n`);
  await browser.close();
}

console.log(JSON.stringify({run: runId, passed: report.passed.length, failures: report.failures.length, evidence: output}));
assert.equal(report.failures.length, 0, `Rendered registration checks failed; inspect ${path.join(output, 'results.json')}`);
