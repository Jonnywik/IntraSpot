// Independent headless-browser presentation checks; never participant testing.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const require = createRequire(import.meta.url);
const argv = process.argv.slice(2);
const base = argv.find(a => a.startsWith('--base='))?.slice(7) || 'http://127.0.0.1:3000';
const output = path.resolve('docs/validation/local-mvp-browser-evidence');
const routes = argv.filter(a => a.startsWith('--route=')).map(a => a.slice(8));
if (!routes.length) routes.push('/');
const viewports = [
  { width: 1280, height: 720 }, { width: 1366, height: 768 },
  { width: 1440, height: 900 }, { width: 1920, height: 1080 },
  { width: 390, height: 844 },
];
assert.equal(new URL(base).protocol, 'http:');
assert.ok(['localhost', '127.0.0.1'].includes(new URL(base).hostname), 'Local QA only');
assert.ok(routes.every(r => r.startsWith('/') && !r.startsWith('//')), 'Relative local routes only');
if (argv.includes('--self-test')) {
  assert.equal(viewports.length, 5);
  assert.ok(output.includes(path.join('docs', 'validation')));
  console.log('Browser QA argument and viewport self-checks passed');
  process.exit(0);
}
let playwright;
for (const bin of process.env.PATH.split(path.delimiter)) {
  try { playwright = require(path.resolve(bin, '../playwright-core')); break; } catch {}
}
if (!playwright) throw new Error('Run with npm exec --package=playwright-core so the driver is available');
await mkdir(output, { recursive: true });
const browser = await playwright.chromium.launch({ channel: 'msedge', headless: true });
const results = [];
try {
  for (const viewport of viewports) {
    for (const [index, route] of routes.entries()) {
      const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', () => errors.push('uncaught_browser_error'));
      const response = await page.goto(new URL(route, base).href, { waitUntil: 'networkidle', timeout: 30000 });
      await page.evaluate(() => document.fonts.ready);
      const checks = await page.evaluate(() => {
        const visible = el => Boolean(el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
        const buttons = [...document.querySelectorAll('button')].filter(visible);
        const textOnly = buttons.filter(el => !el.querySelector('svg,img') && el.textContent.trim());
        const miscentered = textOnly.filter(el => {
          const style = getComputedStyle(el);
          return style.textAlign !== 'center' && !['center', 'space-between'].includes(style.justifyContent);
        }).length;
        return {
          title: document.title,
          horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
          headings: document.querySelectorAll('h1').length,
          buttonCount: buttons.length,
          unnamedButtons: buttons.filter(el => !el.textContent.trim() && !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby')).length,
          miscenteredTextButtons: miscentered,
          mobileManagementLinks: innerWidth < 768 ? [...document.querySelectorAll('nav a')].filter(visible).filter(el => /organizer|platform.admin|manage organization/i.test(el.textContent)).length : 0,
        };
      });
      const screenshot = `viewport-${viewport.width}-${viewport.height}-route-${index}.png`;
      await page.screenshot({ path: path.join(output, screenshot), fullPage: true });
      results.push({ viewport, route, status: response?.status(), ...checks, errors, screenshot });
      await context.close();
    }
  }
} finally { await browser.close(); }
const failures = results.filter(r => r.status !== 200 || r.horizontalOverflow || r.unnamedButtons || r.miscenteredTextButtons || r.mobileManagementLinks || r.errors.length);
await writeFile(path.join(output, 'presentation-results.json'), JSON.stringify({ method: 'Headless browser rendered-layout checks; not participant testing', results, failures }, null, 2));
console.log(JSON.stringify({ checked: results.length, failures: failures.length, output }));
assert.equal(failures.length, 0, 'Presentation failures recorded in presentation-results.json');
