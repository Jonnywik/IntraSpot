import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import os from 'node:os';
const require = createRequire(import.meta.url);
const {chromium} = require(path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const directory = path.dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch({channel:'msedge', headless:true});
try {
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  for (const variant of ['a','b']) {
    const url = new URL('./sprint9-desktop-options.html', import.meta.url);
    url.searchParams.set('variant',variant);
    await page.goto(url.href, {waitUntil:'networkidle'});
    await page.screenshot({path:path.join(directory,`sprint9-option-${variant}.png`)});
  }
  console.log('Rendered both desktop visual directions.');
} finally { await browser.close(); }
