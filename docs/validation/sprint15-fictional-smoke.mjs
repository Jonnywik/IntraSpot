import assert from 'node:assert/strict';
import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
const {chromium} = require(process.env.SPRINT15_PLAYWRIGHT);
assert.equal((await fetch('http://127.0.0.1:8001/ready')).status, 200);
const browser = await chromium.launch({channel:'msedge', headless:true});
try {
  const context = await browser.newContext({viewport:{width:1440, height:900}});
  const page = await context.newPage();
  let pageErrors = 0;
  let failedRequests = 0;
  page.on('pageerror', () => {pageErrors++;});
  page.on('requestfailed', request => {
    if (request.failure()?.errorText !== 'net::ERR_ABORTED') failedRequests++;
  });
  await page.goto('http://127.0.0.1:3000/', {waitUntil:'networkidle'});
  await page.getByText('LOCAL MVP · FICTIONAL ACCOUNTS ONLY', {exact:true}).waitFor();
  assert.equal(await page.getByRole('button', {name:'Continue with Google', exact:true}).count(), 0);
  const choose = page.getByRole('combobox', {name:'Choose a fictional local account', exact:true});
  await choose.selectOption({label:'Fictional student 1'});
  await page.getByRole('button', {name:'Use fictional account', exact:true}).click();
  await page.getByText('Local session: Fictional student 1', {exact:true}).waitFor();
  assert.ok(!new URL(page.url()).searchParams.has('code'));
  await page.getByRole('button', {name:'Continue as guest', exact:true}).click();
  await page.getByText('Local session: Fictional student 1', {exact:true}).waitFor({state:'detached'});
  await page.setViewportSize({width:390, height:844});
  const mobile = page.getByRole('navigation', {name:'Mobile navigation', exact:true});
  assert.deepEqual(await mobile.getByRole('link').allTextContents(), ['Discover','My Events','Chat','Settings']);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  const persisted = await page.evaluate(() => JSON.stringify({local:{...localStorage}, session:{...sessionStorage}}));
  assert.ok(!/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/.test(persisted));
  assert.equal(pageErrors, 0, 'Fictional smoke produced a JavaScript error');
  assert.equal(failedRequests, 0, 'Fictional smoke had an unexpected failed request');
  console.log('Fictional default smoke passed: guest discovery, fictional sign-in/sign-out, four mobile tabs, fit and no persisted bearer credentials.');
  await context.close();
} finally {
  await browser.close();
}
