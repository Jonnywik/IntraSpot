// Isolated developer regression journey; this is not participant validation.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdtemp, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.SPRINT10_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT10_FIXTURES);
const base = 'http://127.0.0.1:3000';
const desktopSizes = [
  {width: 1280, height: 720},
  {width: 1366, height: 768},
  {width: 1440, height: 900},
  {width: 1920, height: 1080},
];
const evidenceDir = await mkdtemp(join(tmpdir(), 'intraspot-sprint10-browser-'));

const browser = await chromium.launch({channel: 'msedge', headless: true});
const context = await browser.newContext({
  viewport: {width: 1440, height: 900},
  colorScheme: 'light',
  reducedMotion: 'reduce',
});
const page = await context.newPage();
page.setDefaultTimeout(15000);
const passed = [];
const screenshots = [];
let navigationApiAvailable = false;
let failureName = null;
let pageErrorCount = 0;
page.on('pageerror', () => { pageErrorCount += 1; });

async function captureScreenshot(targetPage, name) {
  await targetPage.setViewportSize({width: 1440, height: 900});
  const filename = `${name}.png`;
  await targetPage.screenshot({path: join(evidenceDir, filename), fullPage: true, animations: 'disabled'});
  screenshots.push(filename);
}

async function assertDefaultLight(targetPage, surface) {
  const appearance = await targetPage.locator('html').evaluate(root => ({
    theme: root.dataset.theme,
    textSize: root.dataset.textSize,
    highContrast: root.dataset.highContrast,
  }));
  assert.deepEqual(appearance, {theme: 'light', textSize: 'standard', highContrast: 'false'},
    `${surface} screenshot uses the default light appearance`);
}

const apiPath = path => `/api/v1${path}`;
const requestIs = (request, method, pathname) =>
  request.method() === method && new URL(request.url()).pathname === pathname;
const waitForResponse = (targetPage, method, pathname) => {
  const pending = targetPage.waitForResponse(response => requestIs(response.request(), method, apiPath(pathname)));
  // Keep an early timeout handled until its paired UI action can report failure.
  pending.catch(() => {});
  return pending;
};
const quotedIfMatch = request => /^".+"$/.test(request.headers()['if-match'] ?? '');

async function useAccount(targetPage, label) {
  await targetPage.bringToFront();
  const selector = targetPage.getByRole('combobox', {name: 'Choose a fictional local account'});
  await selector.selectOption({label});
  await targetPage.getByRole('button', {name: 'Use fictional account', exact: true}).click();
  await targetPage.getByRole('status').filter({hasText: `Local session: ${label}`}).waitFor({state: 'visible'});
}

async function openDraft(targetPage, orgId, eventId) {
  const query = new URLSearchParams({orgId});
  if (eventId) query.set('eventId', eventId);
  await targetPage.goto(`${base}/draft?${query}`, {waitUntil: 'networkidle'});
  if (eventId) {
    await targetPage.getByRole('heading', {name: 'Edit event draft', exact: true}).waitFor({state: 'visible'});
    await targetPage.getByRole('button', {name: 'Save draft', exact: true}).waitFor({state: 'visible'});
  } else {
    await targetPage.getByRole('heading', {name: 'Create an event draft', level: 1, exact: true}).waitFor({state: 'visible'});
  }
}

async function waitForDraftSaved(targetPage) {
  await targetPage.getByRole('status').filter({hasText: 'Your draft is saved.'}).waitFor({state: 'visible'});
}

async function setAppearance(targetPage) {
  await targetPage.goto(`${base}/settings`, {waitUntil: 'networkidle'});
  await targetPage.getByRole('heading', {name: 'Settings', exact: true}).waitFor({state: 'visible'});

  const changes = [
    {control: targetPage.getByRole('radio', {name: 'Dark', exact: true}), key: 'theme', value: 'dark'},
    {control: targetPage.getByRole('radio', {name: 'Extra large', exact: true}), key: 'text_size', value: 'extra_large'},
    {control: targetPage.getByRole('checkbox', {name: /High contrast/}), key: 'high_contrast', value: true},
  ];
  for (const change of changes) {
    const saved = targetPage.waitForResponse(response => {
      const request = response.request();
      if (!requestIs(request, 'PATCH', apiPath('/me/preferences'))) return false;
      try { return request.postDataJSON()[change.key] === change.value; }
      catch { return false; }
    });
    await change.control.check();
    assert.ok((await saved).ok(), 'Appearance preference save succeeds');
  }

  const rootPreferences = await targetPage.locator('html').evaluate(root => ({
    theme: root.dataset.theme,
    textSize: root.dataset.textSize,
    highContrast: root.dataset.highContrast,
  }));
  assert.deepEqual(rootPreferences, {theme: 'dark', textSize: 'extra_large', highContrast: 'true'});
}

async function assertDesktopFit(targetPage, surface) {
  for (const size of desktopSizes) {
    await targetPage.setViewportSize(size);
    const geometry = await targetPage.evaluate(() => {
      const main = document.querySelector('main');
      return {
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        mainWidth: main?.clientWidth ?? 0,
        mainScrollWidth: main?.scrollWidth ?? 0,
        mainRight: main?.getBoundingClientRect().right ?? 0,
        overflowing: [...document.querySelectorAll('body *')].map(element => ({
          tag: element.tagName, className: typeof element.className === 'string' ? element.className : '',
          bounds: element.getBoundingClientRect(),
        })).filter(({bounds}) => bounds.width > 0 && (bounds.right > window.innerWidth + 1 || bounds.left < -1))
          .slice(0, 12).map(({tag, className, bounds}) => ({tag, className, left: bounds.left, right: bounds.right, width: bounds.width})),
      };
    });
    assert.ok(geometry.documentWidth <= geometry.viewportWidth + 1,
      `${surface} has horizontal page overflow at ${size.width}x${size.height}: ${JSON.stringify(geometry.overflowing)}`);
    assert.ok(geometry.mainScrollWidth <= geometry.mainWidth + 1,
      `${surface} content overflows its main region at ${size.width}x${size.height}`);
    assert.ok(geometry.mainRight <= geometry.viewportWidth + 1,
      `${surface} main region extends past the viewport at ${size.width}x${size.height}`);
  }
  await targetPage.setViewportSize({width: 1440, height: 900});
  passed.push(`${surface} fits all four desktop viewports`);
}

async function assertMobileManagementNotice(targetPage, surface, noticeText) {
  await targetPage.setViewportSize({width: 390, height: 844});
  await targetPage.getByRole('note').filter({hasText: noticeText}).waitFor({state: 'visible'});
  const management = targetPage.locator('.management-desktop');
  if (await management.count()) {
    assert.equal(await management.isVisible(), false, `${surface} management stays desktop-only`);
  }
}

try {
  // Pending owner: failed autosave, rejected account switch, retry, and reload.
  await page.goto(base, {waitUntil: 'networkidle'});
  await useAccount(page, fixtures.accounts.pendingOwner);
  await page.goto(`${base}/workspace?orgId=${fixtures.pendingOrgId}`, {waitUntil: 'networkidle'});
  await page.getByRole('heading', {name: 'Organization events', exact: true}).waitFor({state: 'visible'});
  await assertDefaultLight(page, 'Pending-owner management');
  await captureScreenshot(page, 'default-light-management-1440x900');
  await page.getByRole('link', {name: 'Open private draft', exact: true}).click();
  await page.getByRole('heading', {name: 'Edit event draft', exact: true}).waitFor({state: 'visible'});
  await waitForDraftSaved(page);
  await assertDefaultLight(page, 'Pending-owner draft');
  await captureScreenshot(page, 'default-light-draft-1440x900');
  await setAppearance(page);
  await openDraft(page, fixtures.pendingOrgId, fixtures.pendingDraftId);
  await waitForDraftSaved(page);
  await captureScreenshot(page, 'extreme-dark-xl-high-contrast-draft-1440x900');
  const publish = page.getByRole('button', {name: 'Publish', exact: true});
  assert.equal(await publish.isDisabled(), true, 'Pending organization cannot publish a complete draft');
  await assertDesktopFit(page, 'owner draft editor with dark theme, extra-large text, and high contrast');

  let failedOnce = false;
  let failedRequestUsedVersion = false;
  await page.route('**/api/v1/events/*/draft', async route => {
    if (route.request().method() === 'PATCH' && !failedOnce) {
      failedOnce = true;
      failedRequestUsedVersion = quotedIfMatch(route.request());
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({error: {code: 'temporary_failure', message: 'Retry this save.'}}),
      });
      return;
    }
    await route.continue();
  });
  const failedSave = waitForResponse(page, 'PATCH', `/events/${fixtures.pendingDraftId}/draft`);
  const pendingSummary = 'Fictional edits retained after an interrupted save.';
  await page.getByLabel('Short summary', {exact: true}).fill(pendingSummary);
  const failedResponse = await failedSave;
  assert.equal(failedResponse.status(), 503);
  assert.equal(failedRequestUsedVersion, true, 'Autosave sends the current draft version');
  await page.getByRole('alert').filter({hasText: /changes could not be saved/i}).waitFor({state: 'visible'});
  assert.equal(await page.getByLabel('Short summary', {exact: true}).inputValue(), pendingSummary);
  assert.equal(await page.getByRole('button', {name: 'Save draft', exact: true}).isEnabled(), true);

  const accountSelector = page.getByRole('combobox', {name: 'Choose a fictional local account'});
  await accountSelector.selectOption({label: fixtures.accounts.approvedOwner});
  let accountChangeDismissed = false;
  page.once('dialog', async dialog => {
    assert.equal(dialog.type(), 'confirm');
    accountChangeDismissed = true;
    await dialog.dismiss();
  });
  await page.getByRole('button', {name: 'Use fictional account', exact: true}).click();
  assert.equal(accountChangeDismissed, true, 'Unsaved account-change confirmation was shown');
  await page.getByRole('status').filter({hasText: `Local session: ${fixtures.accounts.pendingOwner}`}).waitFor({state: 'visible'});
  assert.equal(await page.getByLabel('Short summary', {exact: true}).inputValue(), pendingSummary,
    'Declining account discard retains the current editor input');

  await page.unroute('**/api/v1/events/*/draft');
  const retrySave = waitForResponse(page, 'PATCH', `/events/${fixtures.pendingDraftId}/draft`);
  const retryButton = page.getByRole('button', {name: 'Save draft', exact: true});
  await retryButton.click();
  const retryResponse = await retrySave;
  assert.ok(retryResponse.ok(), 'Explicit autosave retry succeeds');
  assert.equal(quotedIfMatch(retryResponse.request()), true, 'Retry keeps draft version preconditions');
  await waitForDraftSaved(page);
  await page.reload({waitUntil: 'networkidle'});
  await waitForDraftSaved(page);
  assert.equal(await page.getByLabel('Short summary', {exact: true}).inputValue(), pendingSummary,
    'Recovered draft persists after reload');
  assert.equal(await page.getByRole('button', {name: 'Publish', exact: true}).isDisabled(), true);

  let releaseHeldSave;
  let announceHeldSave;
  let heldSaveSeen = false;
  const heldSave = new Promise(resolve => { releaseHeldSave = resolve; });
  const heldSaveStarted = new Promise(resolve => { announceHeldSave = resolve; });
  await page.route('**/api/v1/events/*/draft', async route => {
    if (route.request().method() === 'PATCH' && !heldSaveSeen) {
      heldSaveSeen = true;
      announceHeldSave();
      await heldSave;
    }
    await route.continue();
  });
  await page.getByLabel('Event title', {exact: true}).fill('Fictional first queued title');
  await heldSaveStarted;
  const newestTitle = 'Fictional newest title entered while saving';
  const newestSave = page.waitForResponse(response => {
    if (!requestIs(response.request(), 'PATCH', apiPath(`/events/${fixtures.pendingDraftId}/draft`))) return false;
    return response.request().postDataJSON()?.title === newestTitle;
  });
  assert.equal(await page.getByLabel('Event title', {exact: true}).isEditable(), true);
  await page.getByLabel('Event title', {exact: true}).fill(newestTitle);
  releaseHeldSave();
  assert.ok((await newestSave).ok(), 'Edits typed during a save receive their own acknowledgement');
  await waitForDraftSaved(page);
  await page.unroute('**/api/v1/events/*/draft');
  await page.reload({waitUntil: 'networkidle'});
  await waitForDraftSaved(page);
  assert.equal(await page.getByLabel('Event title', {exact: true}).inputValue(), newestTitle);
  passed.push('Typing during a held save remains editable and the newest title persists after reload');

  // Browser back starts from a real workspace link so the draft route has a prior history entry.
  navigationApiAvailable = await page.evaluate(() =>
    typeof window.navigation?.addEventListener === 'function',
  );
  assert.equal(navigationApiAvailable, true,
    'The Edge regression baseline must support Navigation API traversal interception');
  await page.goto(`${base}/workspace?orgId=${fixtures.pendingOrgId}`, {waitUntil: 'networkidle'});
  const openPrivateDraft = page.getByRole('link', {name: 'Open private draft', exact: true});
  await openPrivateDraft.waitFor({state: 'visible'});
  await openPrivateDraft.click();
  await page.getByRole('heading', {name: 'Edit event draft', exact: true}).waitFor({state: 'visible'});
  await waitForDraftSaved(page);
  const backRetainedTitle = 'Fictional title retained after dismissing browser back.';
  const backTitleSave = waitForResponse(page, 'PATCH', `/events/${fixtures.pendingDraftId}/draft`);
  await page.getByLabel('Event title', {exact: true}).fill(backRetainedTitle);
  const backDialogPromise = page.waitForEvent('dialog');
  const backNavigation = page.goBack({waitUntil: 'domcontentloaded', timeout: 5000}).catch(() => null);
  const backDialog = await backDialogPromise;
  assert.equal(backDialog.type(), 'confirm', 'Unsaved browser-back traversal presents a confirmation');
  assert.ok(backDialog.message(), 'Browser-back confirmation is not blank');
  await backDialog.dismiss();
  await backNavigation;
  await page.getByRole('heading', {name: 'Edit event draft', exact: true}).waitFor({state: 'visible'});
  assert.equal(new URL(page.url()).pathname, '/draft', 'Dismissing browser back keeps the draft route active');
  assert.equal(new URL(page.url()).searchParams.get('eventId'), fixtures.pendingDraftId);
  assert.equal(await page.getByLabel('Event title', {exact: true}).inputValue(), backRetainedTitle,
    'Dismissing browser back retains the unsaved title');
  await page.getByRole('status').filter({hasText: `Local session: ${fixtures.accounts.pendingOwner}`}).waitFor({state: 'visible'});
  assert.ok((await backTitleSave).ok(), 'Retained browser-back title is autosaved');
  await waitForDraftSaved(page);
  passed.push('Pending-owner edits survive a failed autosave, a declined account switch, retry, and reload; publish stays gated');
  passed.push('Dismissing browser back from a workspace-linked draft retains the pending owner and unsaved title');

  // Platform admin records an approval through the confirmed decision flow.
  await useAccount(page, fixtures.accounts.platformAdmin);
  await page.goto(`${base}/admin`, {waitUntil: 'networkidle'});
  await page.getByRole('heading', {name: 'Organization applications', exact: true}).waitFor({state: 'visible'});
  await assertDefaultLight(page, 'Platform accreditation review');
  await captureScreenshot(page, 'default-light-admin-1440x900');
  const pendingApplication = page.getByRole('article').filter({hasText: fixtures.pendingOrgName});

  const canceledApprovalRequests = [];
  const recordApprovalRequest = request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname ===
      apiPath(`/platform-admin/organizations/${fixtures.pendingOrgId}/accreditation-decision`)) {
      canceledApprovalRequests.push(true);
    }
  };
  page.on('request', recordApprovalRequest);
  await pendingApplication.getByRole('button', {name: /Approve after offline assessment/}).click();
  const canceledDialog = page.getByRole('dialog');
  await canceledDialog.getByRole('heading', {name: 'Confirm approval', exact: true}).waitFor({state: 'visible'});
  await canceledDialog.getByRole('button', {name: 'Go back', exact: true}).click();
  await canceledDialog.waitFor({state: 'hidden'});
  page.off('request', recordApprovalRequest);
  assert.equal(canceledApprovalRequests.length, 0, 'Canceling accreditation confirmation sends no decision request');
  await pendingApplication.getByRole('button', {name: /Approve after offline assessment/}).waitFor({state: 'visible'});

  await setAppearance(page);
  await page.goto(`${base}/admin`, {waitUntil: 'networkidle'});
  await page.getByRole('heading', {name: 'Organization applications', exact: true}).waitFor({state: 'visible'});
  await captureScreenshot(page, 'extreme-dark-xl-high-contrast-admin-1440x900');
  await assertDesktopFit(page, 'platform accreditation review with dark theme, extra-large text, and high contrast');
  await pendingApplication.getByRole('button', {name: /Approve after offline assessment/}).click();
  const approvalDialog = page.getByRole('dialog');
  await approvalDialog.getByRole('heading', {name: 'Confirm approval', exact: true}).waitFor({state: 'visible'});
  const approvalResponseWait = waitForResponse(
    page,
    'POST',
    `/platform-admin/organizations/${fixtures.pendingOrgId}/accreditation-decision`,
  );
  await approvalDialog.getByRole('button', {name: 'Confirm approval', exact: true}).click();
  const approvalResponse = await approvalResponseWait;
  assert.ok(approvalResponse.ok(), 'Platform admin approval is recorded');
  assert.equal((await approvalResponse.json()).accreditation_status, 'approved');
  await page.getByRole('status').filter({hasText: 'Decision recorded'}).waitFor({state: 'visible'});
  passed.push('Platform admin approval is confirmed and appears in the decision result');

  await page.goto(`${base}/settings`, {waitUntil: 'networkidle'});
  const filipinoSave = waitForResponse(page, 'PATCH', '/me/preferences');
  await page.locator('#settings-language').selectOption('fil');
  assert.ok((await filipinoSave).ok());
  await page.goto(`${base}/admin`, {waitUntil: 'networkidle'});
  await page.getByRole('heading', {name: 'Mga aplikasyon ng organisasyon', exact: true}).waitFor({state: 'visible'});
  assert.equal(await page.locator('html').getAttribute('lang'), 'fil');
  await assertDesktopFit(page, 'Filipino platform review with dark theme and extra-large text');
  await captureScreenshot(page, 'filipino-dark-xl-admin-1440x900');
  await page.goto(`${base}/settings`, {waitUntil: 'networkidle'});
  const englishSave = waitForResponse(page, 'PATCH', '/me/preferences');
  await page.locator('#settings-language').selectOption('en');
  assert.ok((await englishSave).ok());
  passed.push('Filipino management copy stays readable at all desktop sizes and language changes independently');

  // The formerly pending owner's complete draft is now publishable.
  await useAccount(page, fixtures.accounts.pendingOwner);
  await openDraft(page, fixtures.pendingOrgId, fixtures.pendingDraftId);
  await waitForDraftSaved(page);
  const nowApprovedPublish = page.getByRole('button', {name: 'Publish', exact: true});
  assert.equal(await nowApprovedPublish.isEnabled(), true, 'Approved organization with a saved complete draft may publish');
  let publishConfirmationSeen = false;
  page.once('dialog', async dialog => {
    assert.equal(dialog.type(), 'confirm');
    publishConfirmationSeen = true;
    await dialog.accept();
  });
  const publishResponseWait = waitForResponse(page, 'POST', `/events/${fixtures.pendingDraftId}/publish`);
  await nowApprovedPublish.click();
  const publishResponse = await publishResponseWait;
  assert.equal(publishConfirmationSeen, true);
  assert.ok(publishResponse.ok(), 'Saved approved draft publishes successfully');
  assert.equal(quotedIfMatch(publishResponse.request()), true, 'Publish sends the saved draft version');
  const publicEvent = await publishResponse.json();
  assert.equal(Object.hasOwn(publicEvent, 'draft_version'), false, 'Public publish response omits the private draft version');
  await page.getByRole('status').filter({hasText: 'This event is now published.'}).waitFor({state: 'visible'});
  passed.push('Approved publish succeeds with If-Match and does not expose the private draft version');

  // Two tabs exercise stale publish and stale autosave independently.
  await useAccount(page, fixtures.accounts.approvedOwner);
  await setAppearance(page);
  await openDraft(page, fixtures.approvedOrgId, fixtures.approvedDraftId);
  await waitForDraftSaved(page);
  await captureScreenshot(page, 'extreme-dark-xl-high-contrast-approved-draft-1440x900');
  await assertDesktopFit(page, 'approved-owner draft editor with dark theme, extra-large text, and high contrast');
  const secondTab = await context.newPage();
  secondTab.setDefaultTimeout(15000);
  secondTab.on('pageerror', () => { pageErrorCount += 1; });
  await secondTab.goto(base, {waitUntil: 'networkidle'});
  await useAccount(secondTab, fixtures.accounts.approvedOwner);
  await openDraft(secondTab, fixtures.approvedOrgId, fixtures.approvedDraftId);
  await waitForDraftSaved(secondTab);

  const firstTabTitle = 'Fictional title saved from the first tab.';
  await page.bringToFront();
  const firstTabTitleSave = waitForResponse(page, 'PATCH', `/events/${fixtures.approvedDraftId}/draft`);
  await page.getByLabel('Event title', {exact: true}).fill(firstTabTitle);
  assert.equal(await page.getByRole('button', {name: 'Publish', exact: true}).isDisabled(), true,
    'Publish is gated while edits are unsaved');
  const firstTabTitleResponse = await firstTabTitleSave;
  assert.ok(firstTabTitleResponse.ok());
  assert.equal(quotedIfMatch(firstTabTitleResponse.request()), true);
  await waitForDraftSaved(page);

  let stalePublishConfirmationSeen = false;
  await secondTab.bringToFront();
  secondTab.once('dialog', async dialog => {
    stalePublishConfirmationSeen = true;
    await dialog.accept();
  });
  const stalePublishWait = waitForResponse(secondTab, 'POST', `/events/${fixtures.approvedDraftId}/publish`);
  await secondTab.getByRole('button', {name: 'Publish', exact: true}).click();
  const stalePublish = await stalePublishWait;
  assert.equal(stalePublishConfirmationSeen, true);
  assert.equal(stalePublish.status(), 409, 'Stale tab cannot publish over a newer draft');
  assert.equal(quotedIfMatch(stalePublish.request()), true);
  assert.equal((await stalePublish.json()).error.code, 'draft_conflict');
  await secondTab.getByRole('button', {name: 'Reload saved draft', exact: true}).waitFor({state: 'visible'});

  let reloadConfirmationSeen = false;
  secondTab.once('dialog', async dialog => {
    reloadConfirmationSeen = true;
    await dialog.accept();
  });
  const firstReload = waitForResponse(secondTab, 'GET', `/events/${fixtures.approvedDraftId}/draft`);
  await secondTab.getByRole('button', {name: 'Reload saved draft', exact: true}).click();
  await firstReload;
  await waitForDraftSaved(secondTab);
  assert.equal(reloadConfirmationSeen, true);
  await secondTab.getByLabel('Event title', {exact: true}).waitFor({state: 'visible'});
  assert.equal(await secondTab.getByLabel('Event title', {exact: true}).inputValue(), firstTabTitle);
  await waitForDraftSaved(secondTab);

  const firstTabDescription = 'A newer description saved before the second-tab retry.';
  await page.bringToFront();
  const firstTabDescriptionSave = waitForResponse(page, 'PATCH', `/events/${fixtures.approvedDraftId}/draft`);
  await page.getByLabel('Description', {exact: true}).fill(firstTabDescription);
  assert.ok((await firstTabDescriptionSave).ok());
  await waitForDraftSaved(page);

  const staleSummary = 'Second-tab text that must not overwrite the current draft.';
  await secondTab.bringToFront();
  const stalePatchWait = waitForResponse(secondTab, 'PATCH', `/events/${fixtures.approvedDraftId}/draft`);
  await secondTab.getByLabel('Short summary', {exact: true}).fill(staleSummary);
  const stalePatch = await stalePatchWait;
  assert.equal(stalePatch.status(), 409, 'Stale tab autosave cannot overwrite a newer draft');
  assert.equal(quotedIfMatch(stalePatch.request()), true);
  assert.equal((await stalePatch.json()).error.code, 'draft_conflict');
  assert.equal(await secondTab.getByLabel('Short summary', {exact: true}).inputValue(), staleSummary,
    'Conflicting tab keeps its unsaved input until the user chooses reload');
  await secondTab.getByRole('button', {name: 'Reload saved draft', exact: true}).waitFor({state: 'visible'});

  secondTab.once('dialog', async dialog => { await dialog.accept(); });
  const reloadLatestWait = waitForResponse(secondTab, 'GET', `/events/${fixtures.approvedDraftId}/draft`);
  await secondTab.getByRole('button', {name: 'Reload saved draft', exact: true}).click();
  await reloadLatestWait;
  await waitForDraftSaved(secondTab);
  assert.equal(await secondTab.getByLabel('Event title', {exact: true}).inputValue(), firstTabTitle);
  assert.equal(await secondTab.getByLabel('Description', {exact: true}).inputValue(), firstTabDescription);
  assert.notEqual(await secondTab.getByLabel('Short summary', {exact: true}).inputValue(), staleSummary);
  await secondTab.close();
  passed.push('Two-tab stale publish and autosave return draft_conflict, preserve edits, and offer an explicit reload');

  // Inbox: composable filters, optimistic read state, and context-aware routes.
  await useAccount(page, fixtures.accounts.member);
  await page.goto(`${base}/notifications`, {waitUntil: 'networkidle'});
  await page.getByRole('heading', {name: 'Notifications', exact: true}).waitFor({state: 'visible'});
  await assertDefaultLight(page, 'Member notification inbox');
  await captureScreenshot(page, 'default-light-inbox-1440x900');
  await setAppearance(page);
  await page.goto(`${base}/notifications`, {waitUntil: 'networkidle'});
  await page.getByRole('heading', {name: 'Notifications', exact: true}).waitFor({state: 'visible'});
  await captureScreenshot(page, 'extreme-dark-xl-high-contrast-inbox-1440x900');
  await assertDesktopFit(page, 'notification inbox with dark theme, extra-large text, and high contrast');
  const notificationList = page.getByRole('list', {name: 'Notifications'});
  await notificationList.waitFor({state: 'visible'});
  assert.equal(await notificationList.getByRole('listitem').count(), 3);

  const stateFilters = page.getByRole('group', {name: 'Notification status filter'});
  const categoryFilters = page.getByRole('group', {name: 'Notification category filter'});
  await stateFilters.getByRole('button', {name: /^Unread,/}).click();
  assert.equal(await notificationList.getByRole('listitem').count(), 2, 'Unread filter excludes a previously read notice');
  await categoryFilters.getByRole('button', {name: /^Clubs,/}).click();
  assert.equal(await notificationList.getByRole('listitem').count(), 1, 'Unread and category filters compose');
  const clubHref = `/organizations?orgId=${fixtures.approvedOrgId}`;
  assert.equal(await notificationList.locator(`a[href="${clubHref}"]`).count(), 1);
  const markRead = notificationList.getByRole('button', {name: 'Mark as read', exact: true});
  const markReadResponse = waitForResponse(page, 'POST', `/me/notifications/${fixtures.memberClubNoticeId}/read`);
  await markRead.click();
  assert.ok((await markReadResponse).ok(), 'Notification read state is saved');
  await page.getByRole('status').filter({hasText: 'Notification marked as read.'}).waitFor({state: 'visible'});
  assert.equal(await notificationList.getByRole('listitem').count(), 0,
    'Read notice leaves the active unread filter without a reload');

  await stateFilters.getByRole('button', {name: /^All,/}).click();
  await categoryFilters.getByRole('button', {name: /^All categories,/}).click();
  const eventHref = `/events?eventId=${fixtures.reviewEventId}`;
  const chatHref = `/chat?eventId=${fixtures.reviewEventId}`;
  assert.equal(await notificationList.locator(`a[href="${eventHref}"]`).count(), 1,
    'Event notification returns to the referenced event');
  assert.equal(await notificationList.locator(`a[href="${clubHref}"]`).count(), 1,
    'Club notification returns to the referenced organization');
  assert.equal(await notificationList.locator(`a[href="${chatHref}"]`).count(), 1,
    'Chat notification returns to the referenced event conversation');
  await page.setViewportSize({width: 390, height: 844});
  const inboxGeometry = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    mainScrollWidth: document.querySelector('main')?.scrollWidth ?? 0,
    mainWidth: document.querySelector('main')?.clientWidth ?? 0,
  }));
  assert.ok(inboxGeometry.documentWidth <= inboxGeometry.viewportWidth + 1);
  assert.ok(inboxGeometry.mainScrollWidth <= inboxGeometry.mainWidth + 1);
  await page.setViewportSize({width: 1440, height: 900});
  passed.push('Inbox filters, read feedback, event/club/chat destinations, and mobile fit are verified');

  // A moderator follows a scoped notification into only the granted workspace.
  await useAccount(page, fixtures.accounts.moderator);
  await setAppearance(page);
  await page.goto(`${base}/notifications`, {waitUntil: 'networkidle'});
  const moderatorDestination = page.getByRole('link', {name: 'Open registration review', exact: true});
  assert.equal(await moderatorDestination.getAttribute('href'),
    `/workspace?orgId=${fixtures.approvedOrgId}&eventId=${fixtures.reviewEventId}`);
  const scopedReviewEvents = page.waitForResponse(response => {
    const request = response.request();
    const pathname = new URL(response.url()).pathname;
    return request.method() === 'GET' &&
      pathname.startsWith(apiPath(`/organizations/${fixtures.approvedOrgId}/`)) &&
      pathname.includes('review-events');
  });
  await page.evaluate(() => {
    const original = Element.prototype.scrollIntoView;
    window.__sprint10ScrollBehaviors = [];
    Element.prototype.scrollIntoView = function(options) {
      window.__sprint10ScrollBehaviors.push(typeof options === 'object' ? options.behavior : 'auto');
      return original.call(this, options);
    };
  });
  const reviewQueueResponse = waitForResponse(page, 'GET', `/events/${fixtures.reviewEventId}/registration-review`);
  await moderatorDestination.click();
  const scopedReviewResponse = await scopedReviewEvents;
  assert.ok(scopedReviewResponse.ok(), 'Moderator event discovery uses the organization-scoped review summary');
  await page.getByRole('heading', {name: fixtures.approvedOrgName, exact: true}).waitFor({state: 'visible'});
  await page.getByRole('heading', {name: fixtures.reviewEventTitle, exact: true}).waitFor({state: 'visible'});
  const scrollBehaviors = await page.evaluate(() => window.__sprint10ScrollBehaviors);
  assert.equal(scrollBehaviors.includes('smooth'), false, 'Reduced-motion workspace links avoid smooth scrolling');
  await captureScreenshot(page, 'extreme-dark-xl-high-contrast-moderator-workspace-1440x900');
  await assertDesktopFit(page, 'moderator review workspace');
  assert.equal(await page.getByRole('link', {name: /Create event draft|Create private draft/}).count(), 0,
    'Moderator workspace does not expose owner/admin event creation');
  const reviewSummary = page.getByText('Review registrations', {exact: true});
  if (!await reviewSummary.evaluate(element => element.closest('details')?.open)) await reviewSummary.click();
  await page.getByRole('button', {name: 'Approve', exact: true}).waitFor({state: 'visible'});
  assert.ok((await reviewQueueResponse).ok(), 'Scoped staff review loads its registration queue');
  await page.getByRole('button', {name: 'Approve', exact: true}).click();
  const confirmDecision = page.getByRole('button', {name: 'Confirm decision', exact: true});
  const registrationDecision = page.waitForResponse(response => {
    const request = response.request();
    const pathname = new URL(response.url()).pathname;
    return request.method() === 'POST' &&
      pathname.startsWith(apiPath(`/events/${fixtures.reviewEventId}/registrations/`)) &&
      pathname.endsWith('/decision');
  });
  await confirmDecision.click();
  assert.ok((await registrationDecision).ok(), 'Moderator can complete the assigned registration review');
  await page.getByRole('status').filter({hasText: 'Registration approved.'}).waitFor({state: 'visible'});
  await assertMobileManagementNotice(
    page,
    'moderator workspace',
    'Organization management is available on desktop.',
  );
  await page.setViewportSize({width: 1440, height: 900});
  passed.push('Moderator notification opens a scoped review workspace and an authorized registration decision completes');

  // Member context stays out of the staff-only workspace; platform safety goes to admin review.
  await useAccount(page, fixtures.accounts.member);
  const forbiddenWorkspaceRequests = [];
  const forbiddenWorkspacePath = apiPath(`/organizations/${fixtures.approvedOrgId}/workspace`);
  const recordWorkspaceRequest = request => {
    if (request.method() === 'GET' && new URL(request.url()).pathname === forbiddenWorkspacePath) {
      forbiddenWorkspaceRequests.push(true);
    }
  };
  page.on('request', recordWorkspaceRequest);
  await page.goto(`${base}/workspace?orgId=${fixtures.approvedOrgId}`, {waitUntil: 'networkidle'});
  page.off('request', recordWorkspaceRequest);
  await page.getByRole('status').filter({hasText: 'This workspace is unavailable to this account.'}).waitFor({state: 'visible'});
  assert.equal(forbiddenWorkspaceRequests.length, 0, 'Member client does not request a staff workspace resource');

  await useAccount(page, fixtures.accounts.platformAdmin);
  await page.goto(`${base}/notifications`, {waitUntil: 'networkidle'});
  const safetyDestination = page.getByRole('link', {name: 'Open safety review', exact: true});
  assert.equal(await safetyDestination.getAttribute('href'), '/admin');
  await safetyDestination.click();
  await page.getByRole('heading', {name: 'Organization applications', exact: true}).waitFor({state: 'visible'});
  await assertDesktopFit(page, 'platform safety review workspace');
  await assertMobileManagementNotice(
    page,
    'platform administration',
    'Accreditation review is available on desktop.',
  );
  passed.push('Member cannot open staff workspace data; platform safety notification routes to admin review');

  // Management creation should not be actionable on the mobile-only notice view.
  await page.setViewportSize({width: 1440, height: 900});
  await useAccount(page, fixtures.accounts.pendingOwner);
  await openDraft(page, fixtures.pendingOrgId, '');
  await page.setViewportSize({width: 390, height: 844});
  await page.getByRole('note').filter({hasText: 'Event draft management is available on desktop.'}).waitFor({state: 'visible'});
  const mobileCreateDraft = page.getByRole('button', {name: 'Create draft', exact: true});
  assert.ok(!(await mobileCreateDraft.isVisible()) || !(await mobileCreateDraft.isEnabled()),
    'Mobile-only draft notice must not leave a usable management create action');
  passed.push('Draft creation stays unavailable on mobile');

  assert.equal(pageErrorCount, 0, 'No uncaught browser errors');
} catch (error) {
  failureName = error instanceof Error ? error.name : 'Error';
  const context = await page.evaluate(() => ({
    width: innerWidth, height: innerHeight, route: location.pathname,
    notes: [...document.querySelectorAll('[role="note"]')].map(element => ({
      text: element.textContent, className: element.className,
      display: getComputedStyle(element).display,
      bounds: {width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height},
    })),
  })).catch(() => null);
  console.error('Sanitized failure context:', JSON.stringify(context));
  await page.screenshot({path: join(evidenceDir, 'failure.png'), fullPage: true, animations: 'disabled'}).catch(() => {});
  screenshots.push('failure.png');
  throw error;
} finally {
  await browser.close();
  await writeFile(join(evidenceDir, 'results.json'), `${JSON.stringify({
    suite: 'Sprint 10 browser regression',
    classification: 'developer-only; not participant validation',
    browserBaseline: 'Microsoft Edge (Chromium) via Playwright',
    status: failureName ? 'failed' : 'passed',
    failureName,
    navigationApiAvailable,
    passed,
    screenshots,
    screenshotViewport: {width: 1440, height: 900},
    desktopViewports: desktopSizes,
    fallbackLimitation: 'Only the Edge Navigation API traversal path is exercised. Browsers without Navigation API support are not validated for preserving the in-app draft view; they rely on the native beforeunload fallback.',
    participantValidation: false,
  }, null, 2)}\n`, 'utf8');
}

console.log(JSON.stringify({
  classification: 'developer-only; not participant validation',
  passed,
  evidenceDir,
  screenshots,
  resultsFile: join(evidenceDir, 'results.json'),
}));
