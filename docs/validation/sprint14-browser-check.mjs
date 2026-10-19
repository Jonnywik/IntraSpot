import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.SPRINT14_PLAYWRIGHT);
const apiBase = process.env.SPRINT14_API_BASE_URL;
const webBase = process.env.SPRINT14_WEB_BASE_URL;
const evidenceDirectory = process.env.SPRINT14_EVIDENCE_DIR;
const fixtures = JSON.parse(process.env.SPRINT14_FIXTURES ?? '{}');

for (const [key, value] of Object.entries({ apiBase, webBase, evidenceDirectory })) {
  if (!value) throw new Error(`Missing Sprint 14 browser configuration: ${key}`);
}
const apiPrefix = new URL(apiBase).pathname.replace(/\/$/, '');
for (const key of ['orgId', 'orgName', 'organizerId', 'studentId', 'platformAdminId']) {
  if (typeof fixtures[key] !== 'string' || fixtures[key].length === 0) {
    throw new Error(`Missing Sprint 14 fixture field: ${key}`);
  }
}

await mkdir(evidenceDirectory, { recursive: true });

function sanitize(value) {
  return String(value ?? '')
    .replace(/Bearer\s+\S+/gi, 'Bearer [redacted]')
    .replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '[redacted-token]')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[redacted-email]')
    .slice(0, 1800);
}

function evidencePath(name) {
  return join(evidenceDirectory, name);
}

const passed = [];
const screenshots = [];
const viewportMetrics = [];
const preflightChecks = [];
const intentionalNegativeApiChecks = [];
const unexpectedHttpFailures = [];
const expectedAuthResponses = [];
const consoleNetworkMessages = [];
const javascriptErrors = [];
const failedRequests = [];
const networkFailures = [];
let stage = 'preflight';
let activePersona = 'preflight';
let browser = null;
let context = null;
let page = null;
let failure = null;

const apiOrigin = new URL(apiBase).origin;

function expectedEndpointPath(path) {
  return `${apiPrefix}${path}`;
}

async function apiRequest(path, { token, method = 'GET', body, headers = {} } = {}) {
  const requestHeaders = new Headers(headers);
  if (token) requestHeaders.set('Authorization', `Bearer ${token}`);
  if (body !== undefined) requestHeaders.set('Content-Type', 'application/json');
  const response = await fetch(`${apiBase}${path}`, {
    method,
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const raw = await response.text();
  let parsed = null;
  if (raw) {
    try { parsed = JSON.parse(raw); } catch { /* Keep non-JSON response content out of evidence. */ }
  }
  return { status: response.status, body: parsed };
}

function requireStatus(result, expected, label) {
  if (result.status !== expected) {
    throw new Error(`${label}: expected HTTP ${expected}, received HTTP ${result.status}.`);
  }
}

async function requireNegativeApi(method, path, expectedStatus, token, label) {
  const result = await apiRequest(path, { token, method });
  intentionalNegativeApiChecks.push({
    label,
    method,
    path: expectedEndpointPath(path),
    expectedStatus,
    actualStatus: result.status,
  });
  requireStatus(result, expectedStatus, label);
  return result;
}

function pageResponse(path, method = 'GET') {
  const expectedPath = expectedEndpointPath(path);
  return page.waitForResponse((response) => {
    const request = response.request();
    let pathname = '';
    try { pathname = new URL(response.url()).pathname; } catch { return false; }
    return pathname === expectedPath && request.method() === method;
  }, { timeout: 25000 });
}

async function requirePageStatus(responsePromise, expectedStatus, label) {
  const response = await responsePromise;
  requireStatus({ status: response.status() }, expectedStatus, label);
  return response;
}

async function navigateAndWait(path, expectedRequests = []) {
  const requestWaits = expectedRequests.map(({ path: apiPath, method = 'GET' }) =>
    pageResponse(apiPath, method));
  const navigation = page.goto(`${webBase}${path}`, { waitUntil: 'domcontentloaded' });
  const results = await Promise.all([navigation, ...requestWaits]);
  for (let index = 1; index < results.length; index += 1) {
    const spec = expectedRequests[index - 1];
    requireStatus(
      { status: results[index].status() },
      spec.status ?? 200,
      `UI ${spec.method ?? 'GET'} ${expectedEndpointPath(spec.path)}`,
    );
  }
}

async function selectUiAccount(label) {
  activePersona = label;
  const preferencesResponse = pageResponse('/me/preferences', 'GET');
  await page.getByRole('combobox', { name: 'Choose a fictional local account' })
    .selectOption({ label });
  const sessionReady = page.getByRole('status')
    .filter({ hasText: label })
    .waitFor({ state: 'visible' });
  await page.getByRole('button', { name: 'Use fictional account', exact: true }).click();
  const [preferences] = await Promise.all([preferencesResponse, sessionReady]);
  requireStatus({ status: preferences.status() }, 200, 'Account preferences load');

  const tokenStored = await page.evaluate(() => {
    const values = [sessionStorage, localStorage].flatMap((storage) =>
      Array.from({ length: storage.length }, (_, index) => {
        const key = storage.key(index);
        return key === null ? '' : storage.getItem(key) ?? '';
      }));
    return values.some((value) =>
      /eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/.test(value));
  });
  assert.equal(tokenStored, false, 'Fictional catalog tokens stay out of browser storage');
}

async function saveUiPreferences(language, textSize) {
  await page.goto(`${webBase}/settings`, { waitUntil: 'domcontentloaded' });
  const preferencesPanel = page.locator('section[aria-labelledby="settings-preferences-heading"]');
  await preferencesPanel.waitFor({ state: 'visible' });
  await page.waitForFunction(() =>
    document.querySelector('section[aria-labelledby="settings-preferences-heading"]')
      ?.getAttribute('aria-busy') === 'false');

  const languageControl = page.locator('#settings-language');
  if (await languageControl.inputValue() !== language) {
    const languageSave = pageResponse('/me/preferences', 'PATCH');
    await languageControl.selectOption(language);
    const languageResponse = await languageSave;
    requireStatus({ status: languageResponse.status() }, 200, 'Language preference save');
  }
  await page.waitForFunction((expected) =>
    document.documentElement.lang === expected, language);

  const sizeControl = page.locator(`input[name="settings-text-size"][value="${textSize}"]`);
  if (!await sizeControl.isChecked()) {
    const sizeSave = pageResponse('/me/preferences', 'PATCH');
    await sizeControl.check();
    const sizeResponse = await sizeSave;
    requireStatus({ status: sizeResponse.status() }, 200, 'Text-size preference save');
  }
  await page.waitForFunction((expected) =>
    document.documentElement.dataset.textSize === expected, textSize);
}

async function capture(name, anchor = null) {
  await page.waitForFunction(() => ![...document.querySelectorAll('p[role="status"]')]
    .some(element => element.getClientRects().length > 0 &&
      /loading|kinukuha|nilo-load/i.test(element.textContent ?? '')));
  if (anchor) {
    await anchor.evaluate(element => element.scrollIntoView({block: 'start', behavior: 'instant'}));
  } else {
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  await page.screenshot({ path: evidencePath(name), fullPage: false });
  screenshots.push(name);
}

async function announcementCard(title) {
  const heading = page.getByRole('heading', { name: title, exact: true });
  await heading.waitFor({ state: 'visible' });
  const card = heading.locator('xpath=ancestor::article[1]');
  assert.equal(await card.count(), 1, 'Announcement heading is scoped to one article');
  return card;
}

async function recordMobileViewport(width, name) {
  await page.setViewportSize({ width, height: 844 });
  await navigateAndWait(
    `/organizations?orgId=${encodeURIComponent(fixtures.orgId)}`,
    [{ path: `/organizations/${fixtures.orgId}/announcements` }],
  );
  await page.getByRole('heading', { name: 'Mga anunsyo', exact: true })
    .waitFor({ state: 'visible' });
  await page.waitForFunction(() =>
    document.documentElement.lang === 'fil' &&
    document.documentElement.dataset.textSize === 'extra_large');

  const metrics = await page.evaluate(() => ({
    viewportWidth: innerWidth,
    documentWidth: Math.max(
      document.documentElement.scrollWidth,
      document.body.scrollWidth,
    ),
    mobileTabs: document.querySelectorAll('.mobile-nav a').length,
    language: document.documentElement.lang,
    textSize: document.documentElement.dataset.textSize,
  }));
  assert.equal(metrics.mobileTabs, 4, 'The four attendee destinations remain present');
  assert.ok(metrics.documentWidth <= width + 1, `No horizontal overflow at ${width}px`);
  assert.equal(metrics.language, 'fil');
  assert.equal(metrics.textSize, 'extra_large');
  assert.equal(
    await page.getByRole('heading', { name: 'Announcement management', exact: true }).count(),
    0,
    'The reader view does not expose owner management on mobile',
  );
  assert.equal(
    await page.getByRole('button', { name: /^(Create announcement|Edit announcement|Remove announcement|View history)$/ }).count(),
    0,
    'Management actions are absent from the mobile reader',
  );
  viewportMetrics.push(metrics);
  await capture(name, page.getByRole('heading', {name: 'Mga anunsyo', exact: true}));
}

async function selectReviewCase(queue, postId, reportId) {
  const reportButton = queue.getByRole('button').filter({ hasText: postId });
  await reportButton.waitFor({ state: 'visible' });
  assert.equal(await reportButton.count(), 1, 'The intended report case is uniquely selectable');
  const isSelected = await reportButton.getAttribute('aria-pressed') === 'true';
  if (!isSelected) {
    const detailWait = pageResponse(`/moderation/announcement-reports/${reportId}`, 'GET');
    await reportButton.click();
    const response = await detailWait;
    requireStatus({ status: response.status() }, 200, 'Platform report detail');
  }
  const details = queue.locator('[aria-label="Selected report details"]');
  await details.waitFor({ state: 'visible' });
  await details.getByText(reportId, { exact: true }).waitFor({ state: 'visible' });
  return details;
}

async function decideInQueue(queue, details, action, reportId, expectedStatus, expectedPostState) {
  const decisionWait = pageResponse(
    `/moderation/announcement-reports/${reportId}/decision`, 'POST');
  await queue.getByRole('group', { name: 'Report decisions' })
    .getByRole('button', { name: action, exact: true }).click();
  const response = await decisionWait;
  let body = null;
  try { body = await response.json(); } catch { /* Status check below remains actionable. */ }
  requireStatus({ status: response.status() }, 200, `Platform ${action} decision`);
  assert.equal(body?.status, expectedStatus, `The report records the ${expectedStatus} decision`);
  assert.equal(body?.post_state, expectedPostState, `The post is ${expectedPostState}`);
  await details.locator('header').getByText(
    expectedStatus[0].toUpperCase() + expectedStatus.slice(1),
    { exact: true },
  ).waitFor({ state: 'visible' });
}

try {
  // The catalog is fetched only into this process. Tokens are never placed in
  // environment variables, fixtures, screenshots, logs, or evidence files.
  const catalogResult = await apiRequest('/local-demo/accounts');
  requireStatus(catalogResult, 200, 'Fictional account catalog readiness');
  assert.ok(Array.isArray(catalogResult.body), 'The account catalog is a list');
  const requiredLabels = [
    'Fictional organizer',
    'Fictional student 1',
    'Fictional platform admin',
  ];
  const accounts = new Map(catalogResult.body.map((account) => [account.label, account]));
  const tokens = new Map();
  for (const label of requiredLabels) {
    const token = accounts.get(label)?.token;
    assert.equal(typeof token, 'string', `The renewed catalog includes ${label}`);
    assert.ok(token.length > 40, `The renewed ${label} token is present`);
    tokens.set(label, token);
    const identity = await apiRequest('/me', { token });
    requireStatus(identity, 200, `Renewed fictional identity ${label}`);
    const expectedId = label === 'Fictional organizer'
      ? fixtures.organizerId
      : label === 'Fictional student 1'
        ? fixtures.studentId
        : fixtures.platformAdminId;
    assert.equal(identity.body?.id, expectedId, `The catalog resolves ${label} to this run's fixture`);
    if (label === 'Fictional platform admin') {
      assert.equal(identity.body?.platform_admin, true, 'The admin account has platform review access');
    } else {
      assert.equal(identity.body?.eligible, true, `${label} is an eligible fictional PLM account`);
    }
  }
  preflightChecks.push({
    check: 'renewed fictional account catalog',
    ready: true,
    labels: requiredLabels,
  });

  const organizations = await apiRequest('/organizations');
  requireStatus(organizations, 200, 'Organization fixture preflight');
  assert.ok(
    organizations.body.some((organization) => organization.id === fixtures.orgId),
    'The isolated API contains this run\'s approved organization',
  );
  preflightChecks.push({ check: 'fixture API preflight', ready: true });

  const organizerToken = tokens.get('Fictional organizer');
  const studentToken = tokens.get('Fictional student 1');
  const adminToken = tokens.get('Fictional platform admin');
  const runTag = randomUUID().slice(0, 8);
  const publicTitle = `S14 QA public notice ${runTag}`;
  const publicBody = `Fictional public announcement content ${runTag}.`;
  const privateTitle = `S14 QA members notice ${runTag}`;
  const privateBody = `PRIVATE FICTIONAL MARKER ${runTag}`;
  const removalTitle = `S14 QA removal case ${runTag}`;
  const removalBody = `Fictional removal-case evidence ${runTag}.`;

  async function createAnnouncement(title, body, audience) {
    const result = await apiRequest(
      `/organizations/${fixtures.orgId}/announcements`,
      {
        token: organizerToken,
        method: 'POST',
        body: { title, body, audience, client_key: randomUUID() },
      },
    );
    requireStatus(result, 201, 'Fictional announcement setup');
    return result.body;
  }

  const publicPost = await createAnnouncement(publicTitle, publicBody, 'public');
  const privatePost = await createAnnouncement(privateTitle, privateBody, 'members');
  const removalPost = await createAnnouncement(removalTitle, removalBody, 'public');
  assert.ok(publicPost?.id && privatePost?.id && removalPost?.id);

  const memberCanRead = await apiRequest(`/announcements/${privatePost.id}`, {
    token: studentToken,
  });
  requireStatus(memberCanRead, 200, 'Active member private-read preflight');
  assert.equal(memberCanRead.body?.body, privateBody);

  const privateDirect = await requireNegativeApi(
    'GET', `/announcements/${privatePost.id}`, 404, null, 'Guest private direct detail',
  );
  assert.ok(!JSON.stringify(privateDirect.body).includes(privateBody));
  const privateReactions = await requireNegativeApi(
    'GET', `/announcements/${privatePost.id}/reactions`, 404, null,
    'Guest private reaction summary',
  );
  assert.ok(!JSON.stringify(privateReactions.body).includes('counts'));
  await requireNegativeApi(
    'GET', `/announcements/${privatePost.id}/history`, 401, null,
    'Guest private history',
  );

  const removalReceipt = await apiRequest(
    `/announcements/${removalPost.id}/reports`,
    { token: studentToken, method: 'POST', body: { reason: 'spam' } },
  );
  requireStatus(removalReceipt, 201, 'Fictional platform removal-case report setup');
  const removalReportId = removalReceipt.body?.id;
  assert.equal(typeof removalReportId, 'string');
  preflightChecks.push({ check: 'public/private fixture access', ready: true });

  browser = await chromium.launch({ channel: 'msedge', headless: true });
  context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  page = await context.newPage();
  page.setDefaultTimeout(20000);
  page.on('pageerror', (error) => javascriptErrors.push(sanitize(error.message)));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (/failed to load resource|responded with a status of \d{3}/i.test(text)) {
      const location = message.location().url ?? '';
      let path = '[unknown path]';
      try { path = new URL(location).pathname; } catch { /* Keep only a safe path. */ }
      const status = Number(text.match(/\b(401|403|404|408|429|5\d\d)\b/)?.[1] ?? 0);
      consoleNetworkMessages.push({ path, status, message: sanitize(text) });
      return;
    }
    javascriptErrors.push(sanitize(text));
  });
  page.on('response', (response) => {
    if (response.status() < 400) return;
    let url;
    try { url = new URL(response.url()); } catch { return; }
    if (url.origin !== apiOrigin && url.origin !== new URL(webBase).origin) return;
    const entry = {
      method: response.request().method(),
      path: url.pathname,
      status: response.status(),
    };
    if (
      activePersona === 'guest' &&
      entry.method === 'GET' &&
      entry.path === `${apiPrefix}/me` &&
      entry.status === 401
    ) {
      expectedAuthResponses.push(entry);
    } else {
      unexpectedHttpFailures.push(entry);
    }
  });
  page.on('requestfailed', (request) => {
    let url;
    try { url = new URL(request.url()); } catch { return; }
    if (url.origin !== apiOrigin && url.origin !== new URL(webBase).origin) return;
    const entry = {
      method: request.method(),
      path: url.pathname,
      failure: sanitize(request.failure()?.errorText),
    };
    failedRequests.push(entry);
    if (!/ERR_ABORTED|aborted/i.test(entry.failure)) networkFailures.push(entry);
  });

  stage = 'guest public-only read';
  activePersona = 'guest';
  await navigateAndWait(
    `/organizations?orgId=${encodeURIComponent(fixtures.orgId)}`,
    [
      { path: '/local-demo/accounts' },
      { path: `/organizations/${fixtures.orgId}/announcements` },
    ],
  );
  await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
  await page.getByRole('heading', { name: 'Announcements', exact: true })
    .waitFor({ state: 'visible' });
  await page.getByRole('heading', { name: publicTitle, exact: true })
    .waitFor({ state: 'visible' });
  assert.equal(
    await page.getByRole('heading', { name: privateTitle, exact: true }).count(),
    0,
    'A guest sees the public item but not the members-only item',
  );
  await capture('guest-public-only.png', page.getByRole('heading', {name: 'Announcements', exact: true}));
  passed.push('Guest UI shows the public announcement and omits members-only content.');

  stage = 'member read, reaction, and report';
  await selectUiAccount('Fictional student 1');
  await saveUiPreferences('en', 'standard');
  await navigateAndWait(
    `/organizations?orgId=${encodeURIComponent(fixtures.orgId)}`,
    [{ path: `/organizations/${fixtures.orgId}/announcements` }],
  );
  const privateCard = await announcementCard(privateTitle);
  const support = privateCard.getByRole('button', { name: /Choose Support reaction/ });
  const reactionWait = pageResponse(`/announcements/${privatePost.id}/reactions`, 'POST');
  await support.click();
  const reactionResponse = await reactionWait;
  requireStatus({ status: reactionResponse.status() }, 200, 'Member reaction');
  await page.waitForFunction((title) => {
    const article = [...document.querySelectorAll('article')]
      .find((element) => element.textContent?.includes(title));
    return Boolean(article?.querySelector('button[aria-pressed="true"]'));
  }, privateTitle);

  const publicCard = await announcementCard(publicTitle);
  await publicCard.locator('summary').filter({ hasText: 'Report announcement' }).click();
  await publicCard.getByLabel('Reason').selectOption('spam');
  const memberReportWait = pageResponse(`/announcements/${publicPost.id}/reports`, 'POST');
  await publicCard.getByRole('button', { name: 'Submit report', exact: true }).click();
  const memberReportResponse = await memberReportWait;
  requireStatus({ status: memberReportResponse.status() }, 201, 'Member report submission');
  const memberReport = await memberReportResponse.json();
  assert.equal(typeof memberReport?.id, 'string');
  await publicCard.getByText('Your report receipt', { exact: true })
    .waitFor({ state: 'visible' });
  await capture('member-reacted-and-reported.png', privateCard);
  passed.push('An eligible member reads members-only content, reacts, and receives a report receipt.');

  stage = 'owner desktop create, edit, history, and removal';
  await navigateAndWait(
    `/organizations?orgId=${encodeURIComponent(fixtures.orgId)}`,
    [{ path: `/organizations/${fixtures.orgId}/announcements` }],
  );
  await selectUiAccount('Fictional organizer');
  await page.setViewportSize({ width: 1440, height: 900 });
  await navigateAndWait(
    `/workspace?orgId=${encodeURIComponent(fixtures.orgId)}`,
    [
      { path: '/me/organizations' },
      { path: `/organizations/${fixtures.orgId}/announcements/manage` },
    ],
  );
  const managerHeading = page.getByRole('heading', {
    name: 'Announcement management', exact: true,
  });
  await managerHeading.waitFor({ state: 'visible' });
  const manager = managerHeading.locator('xpath=ancestor::section[1]');
  const ownerTitle = `S14 QA owner-created notice ${runTag}`;
  const ownerBody = `Initial fictional owner text ${runTag}.`;
  const editedBody = `Edited fictional owner text ${runTag}.`;
  await manager.getByRole('button', { name: 'Create announcement', exact: true }).click();
  await manager.getByLabel('Title').fill(ownerTitle);
  await manager.getByLabel('Body').fill(ownerBody);
  await manager.getByLabel('Audience').selectOption('public');
  const ownerCreateWait = pageResponse(
    `/organizations/${fixtures.orgId}/announcements`, 'POST');
  await manager.getByRole('button', { name: 'Create', exact: true }).click();
  const ownerCreateResponse = await ownerCreateWait;
  requireStatus({ status: ownerCreateResponse.status() }, 201, 'Owner UI announcement create');
  const ownerCreated = await ownerCreateResponse.json();
  assert.equal(typeof ownerCreated?.id, 'string');
  let ownerCard = await announcementCard(ownerTitle);

  await ownerCard.getByRole('button', { name: 'Edit announcement', exact: true }).click();
  const editor = manager.getByRole('heading', { name: 'Edit announcement', exact: true })
    .locator('xpath=ancestor::form[1]');
  await editor.getByLabel('Body').fill(editedBody);
  const editWait = pageResponse(`/announcements/${ownerCreated.id}`, 'PATCH');
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  const editResponse = await editWait;
  requireStatus({ status: editResponse.status() }, 200, 'Owner UI announcement edit');
  ownerCard = await announcementCard(ownerTitle);
  await ownerCard.getByText('Edited', { exact: true }).waitFor({ state: 'visible' });
  assert.ok((await ownerCard.innerText()).includes(editedBody));

  const historyWait = pageResponse(`/announcements/${ownerCreated.id}/history`, 'GET');
  await ownerCard.getByRole('button', { name: 'View history', exact: true }).click();
  const historyResponse = await historyWait;
  requireStatus({ status: historyResponse.status() }, 200, 'Owner UI announcement history');
  const historyHeading = ownerCard.getByRole('heading', {
    name: 'Announcement history', exact: true,
  });
  await historyHeading.waitFor({ state: 'visible' });
  assert.ok((await ownerCard.innerText()).includes(fixtures.organizerId));
  await capture('owner-desktop-edited-history.png', ownerCard);

  await ownerCard.getByRole('button', { name: 'Remove announcement', exact: true }).click();
  const confirmGroup = ownerCard.getByRole('group', { name: 'Remove announcement' });
  const ownerRemoveWait = pageResponse(`/announcements/${ownerCreated.id}`, 'DELETE');
  await confirmGroup.getByRole('button', { name: 'Confirm removal', exact: true }).click();
  const ownerRemoveResponse = await ownerRemoveWait;
  requireStatus({ status: ownerRemoveResponse.status() }, 204, 'Owner UI removal');
  const removedAsManager = await requireNegativeApi(
    'GET', `/announcements/${ownerCreated.id}`, 404, organizerToken,
    'Owner public detail after removal',
  );
  assert.ok(!JSON.stringify(removedAsManager.body).includes(editedBody));
  await capture('owner-desktop-edited-history-removed.png', ownerCard);
  passed.push('Owner desktop UI creates, edits, marks Edited, reads history, and removes an announcement.');

  stage = 'owner mobile management visibility';
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByText(
    'Organization management is available on desktop. Open this page on a wider screen to apply or manage a workspace.',
    { exact: true },
  ).waitFor({ state: 'visible' });
  assert.equal(
    await page.getByRole('heading', { name: 'Announcement management', exact: true }).count(),
    0,
    'Owner management is hidden from the mobile accessibility tree',
  );
  const ownerMobileMetrics = await page.evaluate(() => ({
    viewportWidth: innerWidth,
    documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    mobileTabs: document.querySelectorAll('.mobile-nav a').length,
  }));
  assert.equal(ownerMobileMetrics.mobileTabs, 4);
  assert.ok(ownerMobileMetrics.documentWidth <= 391);
  viewportMetrics.push(ownerMobileMetrics);
  await capture('owner-mobile-management-hidden.png');
  passed.push('Owner management remains desktop-only at a 390px viewport.');

  stage = 'platform queue hide, restore, and remove';
  await navigateAndWait(
    `/organizations?orgId=${encodeURIComponent(fixtures.orgId)}`,
    [{ path: `/organizations/${fixtures.orgId}/announcements` }],
  );
  await selectUiAccount('Fictional platform admin');
  await page.setViewportSize({ width: 1440, height: 900 });
  await navigateAndWait('/admin', [{ path: '/moderation/announcement-reports' }]);
  const queueHeading = page.getByRole('heading', {
    name: 'Announcement safety report queue', exact: true,
  });
  await queueHeading.waitFor({ state: 'visible' });
  const queue = queueHeading.locator('xpath=ancestor::section[1]');

  const publicCase = await selectReviewCase(queue, publicPost.id, memberReport.id);
  await decideInQueue(queue, publicCase, 'Hide announcement', memberReport.id, 'hidden', 'hidden');
  await requireNegativeApi(
    'GET', `/announcements/${publicPost.id}`, 404, organizerToken,
    'Owner public detail after platform hide',
  );
  const restoreWait = pageResponse(
    `/moderation/announcement-reports/${memberReport.id}/decision`, 'POST');
  await queue.getByRole('group', { name: 'Report decisions' })
    .getByRole('button', { name: 'Restore announcement', exact: true }).click();
  const restoreResponse = await restoreWait;
  let restoreBody = null;
  try { restoreBody = await restoreResponse.json(); } catch { /* Omit response content from evidence. */ }
  requireStatus({ status: restoreResponse.status() }, 200, 'Platform restore decision');
  assert.equal(restoreBody?.status, 'restored');
  assert.equal(restoreBody?.post_state, 'visible');
  await publicCase.locator('header').getByText('Restored', { exact: true }).waitFor({ state: 'visible' });
  const visibleAfterRestore = await apiRequest(`/announcements/${publicPost.id}`, {
    token: organizerToken,
  });
  requireStatus(visibleAfterRestore, 200, 'Owner detail after platform restore');

  const removalCase = await selectReviewCase(queue, removalPost.id, removalReportId);
  await decideInQueue(queue, removalCase, 'Hide announcement', removalReportId, 'hidden', 'hidden');
  const decisionWait = pageResponse(
    `/moderation/announcement-reports/${removalReportId}/decision`, 'POST');
  const confirmation = page.waitForEvent('dialog').then((dialog) => dialog.accept());
  await queue.getByRole('group', { name: 'Report decisions' })
    .getByRole('button', { name: 'Remove announcement', exact: true }).click();
  const [removeResponse] = await Promise.all([decisionWait, confirmation]);
  let removeBody = null;
  try { removeBody = await removeResponse.json(); } catch { /* Omit response content from evidence. */ }
  requireStatus({ status: removeResponse.status() }, 200, 'Platform remove decision');
  assert.equal(removeBody?.status, 'removed');
  assert.equal(removeBody?.post_state, 'removed');
  await removalCase.locator('header').getByText('Removed', { exact: true }).waitFor({ state: 'visible' });
  await requireNegativeApi(
    'GET', `/announcements/${removalPost.id}`, 404, organizerToken,
    'Owner public detail after platform removal',
  );
  await capture('platform-queue-hide-restore-remove.png', queueHeading);
  passed.push('Platform UI hides and restores one report case, and hides then removes another.');

  stage = 'member Filipino XL mobile';
  await navigateAndWait(
    `/organizations?orgId=${encodeURIComponent(fixtures.orgId)}`,
    [{ path: `/organizations/${fixtures.orgId}/announcements` }],
  );
  await selectUiAccount('Fictional student 1');
  await saveUiPreferences('fil', 'extra_large');

  await recordMobileViewport(320, 'member-filipino-xl-320.png');
  await recordMobileViewport(390, 'member-filipino-xl-390.png');
  assert.equal(await (await announcementCard(privateTitle))
    .getByRole('button', {name: /Suporta/}).getAttribute('aria-pressed'), 'true',
  'The saved member reaction survives a mobile page reload');
  passed.push('Filipino extra-large preferences render at 320px and 390px without overflow or management controls.');

  stage = 'announcement dark contrast and reduced-motion preferences';
  await saveUiPreferences('fil', 'extra_large');
  const darkSave = pageResponse('/me/preferences', 'PATCH');
  await page.locator('input[name="settings-theme"][value="dark"]').check();
  await requirePageStatus(darkSave, 200, 'Dark theme preference save');
  const accessibility = page.locator('section[aria-labelledby="settings-accessibility-heading"]');
  for (const index of [0, 1]) {
    const control = accessibility.locator('input[type="checkbox"]').nth(index);
    const preferenceSave = pageResponse('/me/preferences', 'PATCH');
    await control.check();
    await requirePageStatus(preferenceSave, 200, 'Accessibility preference save');
  }
  await recordMobileViewport(390, 'member-dark-contrast-xl-390.png');
  const appearance = await page.getByRole('heading', {name: privateTitle, exact: true})
    .evaluate(heading => ({
      color: getComputedStyle(heading).color,
      bodyColor: getComputedStyle(document.body).color,
      size: parseFloat(getComputedStyle(heading).fontSize),
      theme: document.documentElement.dataset.theme,
      contrast: document.documentElement.dataset.highContrast,
      reducedMotion: document.documentElement.dataset.reducedMotion,
    }));
  assert.equal(appearance.theme, 'dark');
  assert.equal(appearance.contrast, 'true');
  assert.equal(appearance.reducedMotion, 'true');
  assert.equal(appearance.color, appearance.bodyColor, 'Announcement titles use theme-aware text color');
  assert.ok(appearance.size >= 25, 'Announcement titles scale with extra-large text');
  passed.push('Announcement headings honor dark contrast, extra-large text and reduced-motion preferences.');

  assert.equal(javascriptErrors.length, 0, 'No unexpected browser JavaScript or console errors');
  assert.equal(unexpectedHttpFailures.length, 0, 'No unexpected failed browser HTTP responses');
  assert.equal(networkFailures.length, 0, 'No unexpected same-origin browser network failures');
  stage = 'complete';
} catch (error) {
  failure = sanitize(error?.stack ?? error?.message ?? error);
  if (page) {
    try {
      await page.screenshot({ path: evidencePath('failure-viewport.png'), fullPage: false });
      screenshots.push('failure-viewport.png');
    } catch { /* Keep the primary failure and write the remaining evidence. */ }
  }
  throw error;
} finally {
  if (context) await context.close();
  if (browser) await browser.close();
  const result = {
    method: 'Isolated PostgreSQL test database, local static frontend, and Microsoft Edge; not participant or physical-device validation',
    stage,
    passed,
    preflightChecks,
    intentionalNegativeApiChecks,
    expectedAuthResponses,
    javascriptErrors,
    unexpectedHttpFailures,
    consoleNetworkMessages,
    failedRequests,
    networkFailures,
    viewportMetrics,
    screenshots,
    failure,
  };
  await writeFile(evidencePath('results.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
}
