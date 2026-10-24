// Rendered developer checks on fictional scratch data; not participant testing.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.SPRINT24_PLAYWRIGHT);
const output = path.resolve(process.env.SPRINT24_EVIDENCE_DIR);
await mkdir(output, {recursive:true});
const browser = await chromium.launch({channel:'msedge', headless:true});
const context = await browser.newContext({viewport:{width:1440,height:900}, reducedMotion:'no-preference'});
const page = await context.newPage();
page.setDefaultTimeout(15000);
const passed = [], failures = [], metrics = [], focusProof = [];
let browserErrors = 0;
page.on('pageerror', () => browserErrors++);

async function check(name, action) {
  try {await action(); passed.push(name);}
  catch (error) {failures.push({name, errorType:error?.name ?? 'Error'});}
}
const base = 'http://127.0.0.1:3000';
try {
  await page.goto(base, {waitUntil:'networkidle'});
  await check('Skip link transfers real keyboard focus to the main landmark', async () => {
    await page.keyboard.press('Tab');
    focusProof.push(await page.evaluate(()=>({phase:'tab',tag:document.activeElement?.tagName,id:document.activeElement?.id,className:document.activeElement?.className})));
    assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('skip-link')), true);
    await page.keyboard.press('Enter');
    focusProof.push(await page.evaluate(()=>({phase:'enter',tag:document.activeElement?.tagName,id:document.activeElement?.id})));
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'main-content');
  });

  await page.goto(`${base}/settings`, {waitUntil:'networkidle'});
  await page.getByRole('radio', {name:'Extra large',exact:true}).check();
  await page.getByRole('radio', {name:'Dark',exact:true}).check();
  await page.getByRole('checkbox', {name:/^High contrast/}).check();
  await page.getByRole('checkbox', {name:/^Reduce motion/}).check();
  await page.getByRole('combobox', {name:/^Language/}).selectOption('fil');
  await page.waitForFunction(() => document.documentElement.lang === 'fil' &&
    document.documentElement.dataset.textSize === 'extra_large' &&
    document.documentElement.dataset.highContrast === 'true' &&
    document.documentElement.dataset.reducedMotion === 'true');

  await check('Filipino Discover navigation has its translated accessible name', async () => {
    assert.equal(await page.locator('.desktop-nav').getByRole('link', {name:'Tuklasin',exact:true}).count(), 1);
  });

  for (const size of [{width:1280,height:720},{width:1366,height:768},{width:1440,height:900},
      {width:1920,height:1080},{width:390,height:844},{width:320,height:740}]) {
    await page.setViewportSize(size);
    for (const route of ['/', '/settings', '/my-events', '/chat', '/profile', '/notifications']) {
      await page.goto(`${base}${route}`, {waitUntil:'networkidle'});
      const geometry = await page.evaluate(() => ({width:innerWidth,
        documentWidth:document.documentElement.scrollWidth,
        language:document.documentElement.lang,
        textSize:document.documentElement.dataset.textSize,
        bottomNavHeight:document.querySelector('.mobile-nav')?.getBoundingClientRect().height,
        bottomClearance:parseFloat(getComputedStyle(document.body).paddingBottom),
      }));
      metrics.push({route, ...size, ...geometry});
      await check(`${route} has no horizontal overflow at ${size.width}px with Filipino/extra-large/dark/high-contrast`, async () => {
        assert.ok(geometry.documentWidth <= geometry.width + 1);
        assert.equal(geometry.language, 'fil');
        assert.equal(geometry.textSize, 'extra_large');
      });
      if (size.width <= 390) {
        await check(`${route} retains four usable mobile tabs at ${size.width}px`, async () => {
          const links = page.locator('.mobile-nav').getByRole('link');
          assert.equal(await links.count(), 4);
          for (const link of await links.all()) {
            assert.equal(await link.isVisible(), true);
            const box = await link.boundingBox();
            assert.ok(box && box.width >= 44 && box.height >= 44);
          }
          assert.ok(geometry.bottomClearance >= geometry.bottomNavHeight);
        });
      }
      if (route === '/' && [1440,390].includes(size.width)) {
        await page.screenshot({path:path.join(output, `filipino-xl-contrast-${size.width}.png`), fullPage:true});
      }
    }
  }
  await check('Reduced motion suppresses ambient and interactive motion', async () => {
    const moving = await page.evaluate(() => [...document.querySelectorAll('*')].filter(element => {
      const style=getComputedStyle(element);
      return style.animationName !== 'none' && style.animationDuration.split(',').some(value=>parseFloat(value)>0.01);
    }).length);
    assert.equal(moving,0);
  });
  await check('No uncaught browser errors during the accessibility matrix', async () => assert.equal(browserErrors,0));
} finally {
  await page.screenshot({path:path.join(output,'final-view.png'),fullPage:true}).catch(()=>{});
  await writeFile(path.join(output,'results.json'), JSON.stringify({
    method:'Microsoft Edge rendered developer checks on isolated fictional scratch data',
    participantValidation:false, physicalDeviceValidation:false, passed, failures, metrics, focusProof, browserErrors,
  },null,2));
  await browser.close();
}
console.log(JSON.stringify({passed:passed.length,failures,output}));
assert.equal(failures.length,0,'Accessibility checks failed; inspect sanitized results.json');
