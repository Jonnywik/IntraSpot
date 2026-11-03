// Local developer rehearsal only; this does not promote or deploy a hosted artifact.
import {createRequire} from 'node:module';

const summary = {
  discoveryResponseCount: 0,
  discoverySuccessCount: 0,
  visibleTitleCount: 0,
  privateMarkerMatchCount: 0,
  authenticatedDiscoveryRequestCount: 0,
  fixtureAccountPickerCount: 0,
  profileRequestCount: 0,
  browserErrorCount: 0,
  failureCount: 0,
};

let browser;
try {
  let inputText = '';
  for await (const chunk of process.stdin) inputText += chunk;
  const input = JSON.parse(inputText);
  const title = typeof input.title === 'string' ? input.title : '';
  const privateMarkers = Array.isArray(input.privateMarkers)
    ? input.privateMarkers.filter(marker => typeof marker === 'string' && marker.length > 0)
    : [];
  const playwrightPath = process.env.SPRINT30_PLAYWRIGHT;
  if (!title || !playwrightPath) throw new Error('missing smoke input');

  const {chromium} = createRequire(import.meta.url)(playwrightPath);
  browser = await chromium.launch({channel: 'msedge', headless: true});
  const context = await browser.newContext({viewport: {width: 1440, height: 900}});
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on('pageerror', () => { summary.browserErrorCount += 1; });
  page.on('request', request => {
    let url;
    try { url = new URL(request.url()); } catch { return; }
    if (url.origin !== 'http://127.0.0.1:8002') return;
    if (request.method() === 'GET' && url.pathname === '/api/v1/events') {
      if (request.headers().authorization) summary.authenticatedDiscoveryRequestCount += 1;
    }
    if (url.pathname === '/api/v1/me/profile') summary.profileRequestCount += 1;
  });

  const discoveryResponse = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.origin === 'http://127.0.0.1:8002' &&
      url.pathname === '/api/v1/events' && response.request().method() === 'GET';
  }).catch(() => null);
  await page.goto('http://127.0.0.1:3000/', {waitUntil: 'domcontentloaded'});
  const response = await discoveryResponse;
  if (!response) throw new Error('missing guest discovery response');
  summary.discoveryResponseCount = 1;
  if (response.status() === 200) summary.discoverySuccessCount = 1;
  const responseBody = await response.text();
  const bodyLower = responseBody.toLocaleLowerCase();
  summary.privateMarkerMatchCount += privateMarkers.filter(
    marker => bodyLower.includes(marker.toLocaleLowerCase()),
  ).length;

  const titleHeading = page.locator('#public-event-results')
    .getByRole('heading', {level: 2, name: title, exact: true});
  await titleHeading.waitFor({state: 'visible'});
  summary.visibleTitleCount = await titleHeading.count();
  summary.fixtureAccountPickerCount = await page.getByRole(
    'combobox', {name: 'Choose a fictional local account', exact: true},
  ).count();
  const visibleText = (await page.locator('body').innerText()).toLocaleLowerCase();
  summary.privateMarkerMatchCount += privateMarkers.filter(
    marker => visibleText.includes(marker.toLocaleLowerCase()),
  ).length;
} catch {
  summary.failureCount += 1;
} finally {
  if (browser) {
    try { await browser.close(); } catch { summary.failureCount += 1; }
  }
  if (
    summary.discoveryResponseCount !== 1 ||
    summary.discoverySuccessCount !== 1 ||
    summary.visibleTitleCount !== 1 ||
    summary.privateMarkerMatchCount !== 0 ||
    summary.authenticatedDiscoveryRequestCount !== 0 ||
    summary.fixtureAccountPickerCount !== 0 ||
    summary.profileRequestCount !== 0 ||
    summary.browserErrorCount !== 0
  ) summary.failureCount += 1;
  process.stdout.write(`${JSON.stringify(summary)}\n`);
  if (summary.failureCount > 0) process.exitCode = 1;
}
