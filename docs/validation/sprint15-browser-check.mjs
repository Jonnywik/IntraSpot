import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { access, mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createStaticServer } from '../../Code/Frontend/scripts/serve-static.mjs';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const frontendRoot = resolve(projectRoot, 'Code/Frontend');
const outputRoot = resolve(frontendRoot, 'out-real');
const webOrigin = 'http://127.0.0.1:3001';
const apiOrigin = 'http://127.0.0.1:8011';
const supabaseOrigin = 'https://sprint15-test.supabase.co';
const authSlot = 'intraspot.auth.pkce.v1.sprint15-test';
const unrelatedSessionKey = 'sprint15-qa-unrelated-session-value';
const unrelatedSessionValue = 'preserve-outside-auth-cleanup';
const accessToken = 'sprint15-mock-supabase-access-token';
const refreshToken = 'sprint15-mock-supabase-refresh-token';
const providerToken = 'sprint15-mock-google-provider-token';
const providerRefreshToken = 'sprint15-mock-google-provider-refresh-token';
const privateEmail = 'sprint15-private-user@example.invalid';
const privateProviderMessage = 'S15_PRIVATE_PROVIDER_ERROR_SENTINEL';
const privateApiMessage = 'S15_PRIVATE_API_ERROR_SENTINEL';
const mockUserId = '15151515-1515-4515-8515-151515151515';

const callbackFailure = 'The Google sign-in response could not be completed. Start again.';
const callbackSuccess = 'Your development session is ready. Continue to IntraSpot.';
const output = [];
const viewportChecks = [];
const evidenceRoot = resolve(projectRoot, 'docs/validation/sprint15-browser-evidence');
let stage = 'preflight';
let staticServer = null;
let browser = null;
let unexpectedExternalRequests = 0;
let unexpectedAuthRequests = 0;

function insist(condition, label) {
  if (!condition) throw new Error(label);
}

function jsonHeaders(origin, requestHeaders = '') {
  return {
    'access-control-allow-origin': origin,
    'access-control-allow-methods': 'GET, POST, PATCH, DELETE, OPTIONS',
    'access-control-allow-headers': requestHeaders || 'authorization, apikey, content-type, x-client-info',
    'access-control-max-age': '600',
    'content-type': 'application/json; charset=utf-8',
    vary: 'Origin',
  };
}

function payloadResponse(origin, status, payload, requestHeaders = '') {
  return {
    status,
    headers: jsonHeaders(origin, requestHeaders),
    body: payload === undefined ? undefined : JSON.stringify(payload),
  };
}

function accessActor() {
  return {
    id: mockUserId,
    nickname: null,
    eligible: false,
    profile_complete: false,
    platform_admin: false,
    grants: [],
    communication_restricted: false,
  };
}

function sessionResponse() {
  return {
    access_token: accessToken,
    token_type: 'bearer',
    expires_in: 3600,
    refresh_token: refreshToken,
    provider_token: providerToken,
    provider_refresh_token: providerRefreshToken,
    user: {
      id: mockUserId,
      aud: 'authenticated',
      role: 'authenticated',
      email: privateEmail,
      email_confirmed_at: '2026-10-19T00:00:00Z',
      created_at: '2026-10-19T00:00:00Z',
      app_metadata: { provider: 'google', providers: ['google'], role: 'service_role' },
      user_metadata: { email: privateEmail, platform_admin: true },
      identities: [{ provider: 'google', identity_data: { email: privateEmail } }],
      is_anonymous: false,
    },
  };
}

function makeDeferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

function containsPrivateValue(value) {
  const text = String(value ?? '');
  return [accessToken, refreshToken, providerToken, providerRefreshToken, privateEmail,
    privateProviderMessage, privateApiMessage].some(marker => text.includes(marker));
}

async function readBrowserState(page) {
  return page.evaluate(() => ({
    url: `${location.origin}${location.pathname}${location.search}${location.hash}`,
    origin: location.origin,
    pathname: location.pathname,
    search: location.search,
    hash: location.hash,
    cookie: document.cookie,
    session: Array.from({ length: sessionStorage.length }, (_, index) => {
      const key = sessionStorage.key(index);
      return key === null ? null : [key, sessionStorage.getItem(key)];
    }).filter(Boolean),
    local: Array.from({ length: localStorage.length }, (_, index) => {
      const key = localStorage.key(index);
      return key === null ? null : [key, localStorage.getItem(key)];
    }).filter(Boolean),
  }));
}

function makeProtocol(page, scenario) {
  const delayedStarted = makeDeferred();
  const delayedRelease = makeDeferred();
  const protocol = {
    scenario,
    failure: null,
    authorizeCount: 0,
    exchangeCount: 0,
    apiMeCount: 0,
    apiAccessTokenCount: 0,
    apiMeAccessTokenCount: 0,
    apiMeOtherBearer: false,
    unexpectedNetwork: [],
    unexpectedAuth: [],
    apiOtherBearer: false,
    providerTokenSentToApi: false,
    emailSentToApi: false,
    leakedDiagnostics: false,
    callbackPolicy: null,
    challenge: null,
    callbackFlowId: null,
    delayedStarted,
    delayedRelease,
    deferNextMe: false,
    armDelayedMe() { this.deferNextMe = true; },
    releaseDelayedMe() { delayedRelease.resolve(); },
  };

  page.on('response', response => {
    let url;
    try { url = new URL(response.url()); } catch { return; }
    if (url.origin === webOrigin && url.pathname === '/auth/callback') {
      protocol.callbackPolicy = response.headers()['referrer-policy'] ?? null;
    }
  });
  page.on('pageerror', error => {
    if (containsPrivateValue(error?.message)) protocol.leakedDiagnostics = true;
  });
  page.on('console', message => {
    if (containsPrivateValue(message.text())) protocol.leakedDiagnostics = true;
  });

  async function fulfillApi(route, status, payload) {
    await route.fulfill(payloadResponse(webOrigin, status, payload));
  }

  async function handleApi(route, url) {
    const request = route.request();
    const headers = request.headers();
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: jsonHeaders(webOrigin, headers['access-control-request-headers']),
      });
      return;
    }

    const authorization = headers.authorization ?? '';
    const body = request.postData() ?? '';
    if (authorization === `Bearer ${accessToken}`) protocol.apiAccessTokenCount += 1;
    else if (authorization) protocol.apiOtherBearer = true;
    if (authorization.includes(providerToken) || body.includes(providerToken) ||
        JSON.stringify(headers).includes(providerToken) || url.href.includes(providerToken)) {
      protocol.providerTokenSentToApi = true;
    }
    if (body.includes(privateEmail) || JSON.stringify(headers).includes(privateEmail) ||
        url.href.includes(privateEmail)) protocol.emailSentToApi = true;

    if (url.pathname === '/api/v1/me' && request.method() === 'GET') {
      protocol.apiMeCount += 1;
      if (authorization === `Bearer ${accessToken}`) protocol.apiMeAccessTokenCount += 1;
      else if (authorization) protocol.apiMeOtherBearer = true;
      if (protocol.deferNextMe) {
        protocol.deferNextMe = false;
        protocol.delayedStarted.resolve();
        await protocol.delayedRelease.promise;
        await fulfillApi(route, 200, accessActor());
        return;
      }
      if (scenario === 'backend-denial') {
        await fulfillApi(route, 401, {
          error: { code: 'auth_failure', message: privateApiMessage },
          request_id: 'sprint15-mock-request',
        });
        return;
      }
      if (scenario === 'logout-race' || scenario === 'api-unavailable') {
        await fulfillApi(route, 503, {
          error: { code: 'identity_provider_unavailable', message: privateApiMessage },
          request_id: 'sprint15-mock-request',
        });
        return;
      }
      await fulfillApi(route, 200, accessActor());
      return;
    }

    if (url.pathname === '/api/v1/events' && request.method() === 'GET') {
      await fulfillApi(route, 200, []);
      return;
    }
    if (url.pathname === '/api/v1/me/preferences' && request.method() === 'GET') {
      await fulfillApi(route, 200, {
        language: 'en', text_size: 'normal', theme: 'dark', show_flash: true,
      });
      return;
    }
    await fulfillApi(route, 200, []);
  }

  async function verifyStoredVerifier(requestBody) {
    const state = await readBrowserState(page);
    insist(state.origin === webOrigin && state.pathname === '/auth/callback', 'Callback did not remain same-origin.');
    insist(state.search === '' && state.hash === '', 'Callback URL was not scrubbed before token exchange.');
    insist(state.cookie === '', 'Auth cookies were written by the mocked browser flow.');

    const slot = state.session.find(([key]) => key === authSlot);
    insist(Boolean(slot), 'The PKCE verifier was not persisted in the project-scoped sessionStorage slot.');
    const envelope = JSON.parse(slot[1]);
    const now = Date.now();
    insist(envelope.version === 1, 'The PKCE storage envelope version is unexpected.');
    insist(Number.isFinite(envelope.expiresAt) && envelope.expiresAt > now &&
      envelope.expiresAt <= now + 10 * 60 * 1000 + 2000, 'The PKCE verifier expiry is missing or unbounded.');
    insist(envelope.values && typeof envelope.values === 'object' && !Array.isArray(envelope.values),
      'The PKCE storage slot has an invalid envelope.');

    const values = envelope.values;
    const flowEntries = Object.entries(values).filter(([key]) => key.startsWith('flow:'));
    insist(flowEntries.length === 1, 'The current callback did not resolve to exactly one SDK flow verifier.');
    const [flowKey, flowValue] = flowEntries[0];
    const flowId = flowKey.slice('flow:'.length);
    insist(/^[A-Za-z0-9_-]{8,64}$/.test(flowId), 'The persisted SDK flow id is malformed.');
    insist(Array.isArray(JSON.parse(values.index)) && JSON.parse(values.index).includes(flowId),
      'The SDK flow index does not identify the persisted verifier.');
    insist(JSON.parse(flowValue) === requestBody.code_verifier, 'The SDK exchanged a verifier other than the persisted flow verifier.');
    insist(JSON.parse(values.legacy) === requestBody.code_verifier, 'The SDK legacy verifier slot did not match this PKCE exchange.');
    if (protocol.callbackFlowId) {
      insist(protocol.callbackFlowId === flowId, 'Callback flow id did not select its scoped PKCE verifier.');
    }

    const expectedChallenge = createHash('sha256').update(requestBody.code_verifier)
      .digest().toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
    insist(protocol.challenge === expectedChallenge, 'The authorize challenge did not match the stored PKCE verifier.');
    insist(state.session.some(([key, value]) => key === unrelatedSessionKey && value === unrelatedSessionValue),
      'The test-owned unrelated sessionStorage value was not preserved.');
    insist(state.session.length === 2, 'Unexpected browser storage appeared alongside the PKCE verifier.');
    insist(!state.session.some(([key, value]) => key !== unrelatedSessionKey && containsPrivateValue(`${key} ${value}`)),
      'A session token, provider token, or email was persisted with the verifier.');
  }

  async function handleSupabase(route, url) {
    const request = route.request();
    const headers = request.headers();
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: jsonHeaders(webOrigin, headers['access-control-request-headers']),
      });
      return;
    }

    if (url.pathname === '/auth/v1/authorize' && request.method() === 'GET') {
      protocol.authorizeCount += 1;
      insist(url.searchParams.get('provider') === 'google', 'The SDK did not request the Google provider.');
      const requestedScopes = (url.searchParams.get('scopes') ?? url.searchParams.get('scope') ?? '')
        .trim().split(/\s+/).filter(Boolean).sort();
      insist(requestedScopes.join(' ') === 'email openid profile', 'The SDK OAuth scope set changed from the reviewed identity scopes.');
      const redirect = url.searchParams.get('redirect_to');
      insist(Boolean(redirect), 'The SDK authorize request omitted its callback URL.');
      const callback = new URL(redirect);
      insist(callback.origin === webOrigin && callback.pathname === '/auth/callback',
        'The SDK callback escaped the fixed same-origin callback path.');
      insist([...callback.searchParams.keys()].every(key => key === 'sb_flow_id'),
        'The callback contains an arbitrary return destination or unexpected query parameter.');
      insist(url.searchParams.has('code_challenge') &&
        url.searchParams.get('code_challenge_method')?.toLowerCase() === 's256',
      'The SDK did not start an S256 PKCE authorization flow.');
      protocol.challenge = url.searchParams.get('code_challenge');
      protocol.callbackFlowId = callback.searchParams.get('sb_flow_id');

      if (scenario === 'cancel') {
        callback.searchParams.set('error', 'access_denied');
        callback.searchParams.set('error_description', privateProviderMessage);
      } else {
        callback.searchParams.set('code', 'sprint15-mock-authorization-code');
      }
      await route.fulfill({
        status: 302,
        headers: { location: callback.href, 'cache-control': 'no-store' },
      });
      return;
    }

    if (url.pathname === '/auth/v1/token' && request.method() === 'POST') {
      protocol.exchangeCount += 1;
      insist(url.searchParams.get('grant_type') === 'pkce', 'The pinned SDK did not use the PKCE token exchange.');
      insist(headers.apikey?.startsWith('sb_publishable_'), 'The SDK request did not use a publishable test key.');
      let requestBody;
      try { requestBody = request.postDataJSON(); } catch { requestBody = null; }
      insist(requestBody?.auth_code === 'sprint15-mock-authorization-code', 'The SDK token request omitted the mocked authorization code.');
      insist(typeof requestBody?.code_verifier === 'string' && requestBody.code_verifier.length >= 43,
        'The SDK token request omitted its PKCE verifier.');
      await verifyStoredVerifier(requestBody);

      if (scenario === 'exchange-failure') {
        await route.fulfill(payloadResponse(webOrigin, 400, {
          code: 'mock_oauth_failure',
          msg: privateProviderMessage,
        }, headers['access-control-request-headers']));
        return;
      }
      await route.fulfill(payloadResponse(webOrigin, 200, sessionResponse()));
      return;
    }

    if (url.pathname === '/auth/v1/logout' && request.method() === 'POST') {
      await route.fulfill({ status: 204, headers: jsonHeaders(webOrigin) });
      return;
    }

    protocol.unexpectedAuth.push({ method: request.method(), path: url.pathname });
    await route.abort();
  }

  protocol.install = async context => {
    await context.route('**/*', async route => {
      try {
        const url = new URL(route.request().url());
        if (url.origin === webOrigin) {
          await route.continue();
          return;
        }
        if (url.origin === apiOrigin) {
          await handleApi(route, url);
          return;
        }
        if (url.origin === supabaseOrigin) {
          await handleSupabase(route, url);
          return;
        }
        protocol.unexpectedNetwork.push({
          method: route.request().method(),
          origin: url.origin,
          path: url.pathname,
        });
        await route.abort();
      } catch (error) {
        protocol.failure = error instanceof Error ? error.message : 'Mock route failed.';
        await route.abort().catch(() => undefined);
      }
    });
  };

  return protocol;
}

function checkNoPrivateValues(protocol, state, visibleText) {
  insist(!containsPrivateValue(visibleText), 'Private auth or API content appeared in the visible page.');
  insist(!containsPrivateValue(JSON.stringify(state.session)), 'Private auth content appeared in sessionStorage.');
  insist(!containsPrivateValue(JSON.stringify(state.local)), 'Private auth content appeared in localStorage.');
  insist(!containsPrivateValue(state.cookie), 'Private auth content appeared in cookies.');
  insist(!protocol.leakedDiagnostics, 'Private auth or API content appeared in browser diagnostics.');
  insist(!protocol.providerTokenSentToApi, 'The Google provider token was sent to the local API.');
  insist(!protocol.emailSentToApi, 'The Auth user email was sent to the local API.');
  insist(!protocol.apiOtherBearer, 'An unrecognized bearer token was sent to the local API.');
  insist(protocol.unexpectedNetwork.length === 0, 'The browser attempted an unmocked external network request.');
  insist(protocol.unexpectedAuth.length === 0, 'The SDK attempted an unmocked Auth endpoint.');
  insist(protocol.failure === null, 'A mocked protocol assertion failed.');
}

async function makeContext(browser, scenario) {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const protocol = makeProtocol(page, scenario);
  await context.addInitScript(`(() => {
    if (location.origin === ${JSON.stringify(webOrigin)} &&
        sessionStorage.getItem(${JSON.stringify(unrelatedSessionKey)}) === null) {
      sessionStorage.setItem(${JSON.stringify(unrelatedSessionKey)}, ${JSON.stringify(unrelatedSessionValue)});
    }
  })();`);
  await protocol.install(context);
  return { context, page, protocol };
}

async function beginSignIn(page) {
  await page.goto(webOrigin, { waitUntil: 'domcontentloaded' });
  const button = page.getByRole('button', { name: 'Continue with Google', exact: true });
  await button.waitFor({ state: 'visible', timeout: 20000 });
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll('button')]
      .find(item => item.textContent?.trim() === 'Continue with Google');
    return Boolean(button && !button.disabled);
  }, null, { timeout: 20000 });
  const callbackNavigation = page.waitForURL(url =>
    url.origin === webOrigin && url.pathname === '/auth/callback', { timeout: 20000 });
  await button.click();
  await callbackNavigation;
}

async function waitForCallbackFailure(page) {
  await page.getByText(callbackFailure, { exact: true }).waitFor({ state: 'visible', timeout: 20000 });
}

async function assertCleanedProjectSlot(page, protocol) {
  const state = await readBrowserState(page);
  insist(!state.session.some(([key]) => key === authSlot), 'Project-scoped PKCE slot survived callback cleanup.');
  insist(state.session.some(([key, value]) => key === unrelatedSessionKey && value === unrelatedSessionValue),
    'Auth cleanup removed unrelated same-tab sessionStorage.');
  insist(state.session.length === 1, 'Auth cleanup left an unexpected sessionStorage entry.');
  checkNoPrivateValues(protocol, state, await page.locator('body').innerText());
  return state;
}

async function runProtocolCase(browser, scenario) {
  stage = scenario;
  const { context, page, protocol } = await makeContext(browser, scenario);
  try {
    await beginSignIn(page);
    insist(protocol.authorizeCount === 1, 'The SDK authorize endpoint was not called exactly once.');
    insist(protocol.callbackPolicy === 'no-referrer', 'The static callback response omitted its no-referrer policy.');

    if (scenario === 'cancel') {
      await waitForCallbackFailure(page);
      insist(protocol.exchangeCount === 0, 'Cancelled OAuth unexpectedly exchanged an authorization code.');
      const state = await assertCleanedProjectSlot(page, protocol);
      insist(state.search === '' && state.hash === '', 'Provider error details remained in the callback URL.');
      output.push('provider cancellation is generic; callback URL and only the project PKCE slot are cleared');
      return;
    }

    if (scenario === 'exchange-failure') {
      await waitForCallbackFailure(page);
      insist(protocol.exchangeCount === 1, 'The SDK did not make exactly one mocked PKCE exchange.');
      insist(protocol.apiMeCount === 0, 'An Auth exchange error reached the local API.');
      await assertCleanedProjectSlot(page, protocol);
      output.push('SDK PKCE exchange error is recoverable and does not disclose provider response content');
      return;
    }

    if (scenario === 'backend-denial') {
      await waitForCallbackFailure(page);
      insist(protocol.exchangeCount === 1 && protocol.apiMeCount === 1,
        'The mocked backend denial did not follow one successful SDK exchange and one /me request.');
      insist(protocol.apiMeAccessTokenCount === 1 && !protocol.apiMeOtherBearer,
        'The API did not receive only the Supabase access token for /me.');
      const state = await assertCleanedProjectSlot(page, protocol);
      insist(!state.session.some(([key]) => key === authSlot), 'Backend denial did not clear project PKCE state.');
      insist(await page.getByRole('button', { name: 'Sign out', exact: true }).count() === 0,
        'Backend-denied session remained visible as signed in.');
      output.push('backend 401 clears the in-memory session; no Auth user or error body is shown');
      return;
    }

    if (scenario === 'logout-race') {
      await waitForCallbackFailure(page);
      insist(protocol.apiMeCount === 1 && protocol.apiMeAccessTokenCount === 1 && !protocol.apiMeOtherBearer,
        'API-unavailable setup did not use the expected access-token request.');
      insist((await page.getByRole('alert').allTextContents()).join(' ')
        .includes('The local IntraSpot API could not verify this account.'),
      'The API-unavailable state was not described with generic recoverable feedback.');
      protocol.armDelayedMe();
      const retry = page.getByRole('button', { name: 'Retry local verification', exact: true }).first();
      await retry.waitFor({ state: 'visible' });
      await retry.click();
      await protocol.delayedStarted.promise;
      await page.getByRole('button', { name: 'Sign out', exact: true }).click();
      await page.getByRole('button', { name: 'Continue with Google', exact: true })
        .waitFor({ state: 'visible', timeout: 10000 });
      const delayedResponse = page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.origin === apiOrigin && url.pathname === '/api/v1/me' &&
          response.request().method() === 'GET' && response.status() === 200;
      }, { timeout: 10000 });
      protocol.releaseDelayedMe();
      await delayedResponse;
      await page.evaluate(() => new Promise(resolveFrame =>
        requestAnimationFrame(() => requestAnimationFrame(resolveFrame))));
      const state = await assertCleanedProjectSlot(page, protocol);
      insist(protocol.apiMeCount === 2 && protocol.apiMeAccessTokenCount === 2 && !protocol.apiMeOtherBearer,
        'The delayed refresh did not perform exactly one access-token retry.');
      insist(await page.getByRole('button', { name: 'Sign out', exact: true }).count() === 0,
        'The delayed /me response restored a signed-out session.');
      // count() includes DOM text inside collapsed <details>; closed state cannot hide stale actor UI.
      insist(await page.getByText(
        'Your Google account can browse public events. PLM-only actions require an eligible PLM account.',
        { exact: true },
      ).count() === 0, 'The delayed /me response restored private actor UI after logout.');
      insist(state.session.some(([key, value]) => key === unrelatedSessionKey && value === unrelatedSessionValue),
        'Logout cleanup removed unrelated sessionStorage.');
      output.push('API-unavailable retry delayed across logout is discarded; scoped PKCE cleanup preserves unrelated storage');
      return;
    }

    await page.getByText(callbackSuccess, { exact: true }).waitFor({ state: 'visible', timeout: 20000 });
    insist(protocol.exchangeCount === 1 && protocol.apiMeCount === 1,
      'Success did not exercise exactly one SDK exchange followed by API /me.');
    insist(protocol.apiMeAccessTokenCount === 1 && !protocol.apiMeOtherBearer,
      'The local API did not receive only the access token for /me.');
    const disclosureSummary = page.getByText('About development sign-in', { exact: true });
    const disclosure = page.locator('details').filter({ has: disclosureSummary });
    const personalEligibilityNotice = page.getByText(
      'Your Google account can browse public events. PLM-only actions require an eligible PLM account.',
      { exact: true },
    );
    const incompleteProfileNotice = page.getByText(
      'Complete your profile before registering.', { exact: true },
    );
    const noAutomaticGrantsNotice = page.getByText(
      'No admin access or organization memberships are granted automatically.', { exact: true },
    );
    insist(await disclosure.count() === 1 && !await disclosure.evaluate(node => node.open),
      'The development-sign-in disclosure was not present and collapsed after sign-in.');
    for (const notice of [personalEligibilityNotice, incompleteProfileNotice, noAutomaticGrantsNotice]) {
      insist(await notice.count() === 1, 'A mock actor notice was missing or duplicated in the collapsed disclosure.');
      insist(!await notice.isVisible(), 'A disclosure notice was visible before opening the disclosure.');
    }
    await disclosureSummary.click();
    for (const notice of [personalEligibilityNotice, incompleteProfileNotice, noAutomaticGrantsNotice]) {
      insist(await notice.isVisible(), 'A development-sign-in notice did not become visible when its disclosure opened.');
    }
    let state = await assertCleanedProjectSlot(page, protocol);
    insist(state.session.length === 1, 'Successful callback left auth data beyond the test-owned session value.');

    await mkdir(evidenceRoot, {recursive: true});
    for (const width of [1280, 390]) {
      await page.setViewportSize({width, height: 900});
      const metrics = await page.evaluate(() => ({
        width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        mainRegions: document.querySelectorAll('main').length,
        mobileDestinations: document.querySelectorAll('nav[aria-label="Mobile navigation"] a').length,
      }));
      insist(metrics.scrollWidth <= width + 1, 'Isolated sign-in UI overflows the viewport horizontally.');
      insist(metrics.mainRegions === 1, 'Callback introduced nested or duplicate main regions.');
      insist(metrics.mobileDestinations === 4, 'Isolated sign-in changed the four mobile destinations.');
      viewportChecks.push(metrics);
      await page.screenshot({path: resolve(evidenceRoot, `synthetic-callback-${width}.png`)});
    }
    await page.setViewportSize({width: 1280, height: 900});
    await disclosureSummary.click();

    await page.getByRole('link', { name: 'Continue to IntraSpot', exact: true }).click();
    await page.waitForURL(`${webOrigin}/`, { timeout: 10000 });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Continue with Google', exact: true })
      .waitFor({ state: 'visible', timeout: 20000 });
    state = await assertCleanedProjectSlot(page, protocol);
    insist(protocol.apiMeCount === 1 && protocol.apiMeAccessTokenCount === 1,
      'A full reload restored the in-memory session to the API.');
    insist(!await page.getByRole('button', { name: 'Sign out', exact: true }).count(),
      'A full reload restored the in-memory signed-in state.');
    output.push('actual SDK PKCE success uses persisted verifier once; session/provider/user data stay memory-only and reload requires sign-in');
  } finally {
    unexpectedExternalRequests += protocol.unexpectedNetwork.length;
    unexpectedAuthRequests += protocol.unexpectedAuth.length;
    protocol.releaseDelayedMe();
    await context.close();
  }
}

function sanitizedFailure(error) {
  let message = error instanceof Error ? error.message : 'Unknown harness error.';
  for (const marker of [accessToken, refreshToken, providerToken, providerRefreshToken,
    privateEmail, privateProviderMessage, privateApiMessage, 'sprint15-mock-authorization-code']) {
    message = message.split(marker).join('[redacted]');
  }
  return message
    .replace(/([?&](?:code|error|error_code|error_description|sb_flow_id)=)[^&\s]*/gi, '$1[redacted]')
    .replace(/Bearer\s+\S+/gi, 'Bearer [redacted]')
    .slice(0, 800);
}

try {
  insist(Boolean(process.env.SPRINT15_PLAYWRIGHT), 'Set SPRINT15_PLAYWRIGHT to the coordinator-provided Playwright module path.');
  await access(resolve(outputRoot, 'index.html'));
  await access(resolve(outputRoot, 'auth/callback.html'));
  const require = createRequire(import.meta.url);
  const { chromium } = require(process.env.SPRINT15_PLAYWRIGHT);
  staticServer = createStaticServer(outputRoot);
  await new Promise((resolveListen, rejectListen) => {
    staticServer.once('error', rejectListen);
    staticServer.listen(3001, '127.0.0.1', resolveListen);
  });
  browser = await chromium.launch({ channel: 'msedge', headless: true });

  await runProtocolCase(browser, 'success');
  await runProtocolCase(browser, 'cancel');
  await runProtocolCase(browser, 'exchange-failure');
  await runProtocolCase(browser, 'backend-denial');
  await runProtocolCase(browser, 'logout-race');

  const result = {
    status: 'passed',
    method: 'Mocked browser protocol using the pinned Supabase Auth JS SDK and coordinator-built out-real static export.',
    authOrigin: 'https://sprint15-test.supabase.co (intercepted; fictional only)',
    apiOrigin: 'http://127.0.0.1:8011 (intercepted; no API server contact)',
    liveGoogleOrSupabase: false,
    unexpectedExternalRequests,
    unexpectedAuthRequests,
    cases: output,
    viewportChecks,
  };
  await mkdir(evidenceRoot, {recursive: true});
  await writeFile(resolve(evidenceRoot, 'summary.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  process.exitCode = 1;
  console.error(JSON.stringify({
    status: 'failed',
    stage,
    message: sanitizedFailure(error),
    note: 'No live Google, Supabase, or API request is enabled by this harness.',
  }, null, 2));
} finally {
  if (browser) await browser.close().catch(() => undefined);
  if (staticServer?.listening) {
    await new Promise(resolveClose => staticServer.close(resolveClose));
  }
}
