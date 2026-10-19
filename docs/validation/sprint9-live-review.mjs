// Developer visual checks against the running local app. No participant testing.
import {createRequire} from 'node:module';
import os from 'node:os';
import path from 'node:path';
import {mkdir} from 'node:fs/promises';
const require = createRequire(import.meta.url);
const {chromium} = require(path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const output = path.resolve('docs/validation/sprint9-browser-evidence');
await mkdir(output, {recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
try {
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:3000', {waitUntil:'networkidle',timeout:120000});
  await page.screenshot({path:path.join(output,'desktop-guest.png'),fullPage:true});
  await page.screenshot({path:path.join(output,'desktop-guest-viewport.png')});
  console.log(JSON.stringify({title:await page.title(), h1:await page.locator('h1').allTextContents(), geometry:await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth, firstCard:document.querySelector('.event-card')?.getBoundingClientRect().toJSON(), heading:document.querySelector('.discovery-heading')?.getBoundingClientRect().toJSON(), controls:document.querySelector('.filters')?.getBoundingClientRect().toJSON()})), errors}));
} finally {await browser.close();}
