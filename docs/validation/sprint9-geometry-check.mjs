// Focused developer geometry/interaction checks, not participant validation.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.SPRINT9_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT9_FIXTURES);
const output = path.resolve('docs/validation/sprint9-browser-evidence', `${new Date().toISOString().replaceAll(':','-').replaceAll('.','-')}-geometry`);
await mkdir(output,{recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
const context = await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'no-preference'});
const page = await context.newPage();
const passed = [];
const problems = [];
const check = (condition,message) => { if (!condition) problems.push(message); };
try {
  // Reset only the isolated fixture account, never the development database.
  const catalog = await context.request.get('http://127.0.0.1:8002/api/v1/local-demo/accounts', {headers:{Origin:'http://127.0.0.1:3000'}});
  assert.ok(catalog.ok());
  const account = (await catalog.json()).find(row=>row.label === fixtures.accountBLabel);
  assert.ok(account);
  const reset = await context.request.patch('http://127.0.0.1:8002/api/v1/me/preferences', {
    headers:{Authorization:`Bearer ${account.token}`},
    data:{language:'en',theme:'light',text_size:'standard',high_contrast:false,reduced_motion:false,decoration_paused:false},
  });
  assert.ok(reset.ok());
  await page.goto('http://127.0.0.1:3000',{waitUntil:'networkidle'});
  const local = page.locator('.local-account-controls');
  await local.locator('select').selectOption(fixtures.accountBLabel);
  await local.locator('button').first().click();
  await page.waitForFunction(label=>document.querySelector('.local-account-controls [role="status"]')?.textContent.includes(label),fixtures.accountBLabel);
  await page.locator('.event-card').first().waitFor();
  await page.evaluate(()=>document.fonts.ready);
  const card = page.locator('.event-card').first();
  const target = card.locator('.event-card-link');
  const resting = await card.boundingBox();
  console.log(JSON.stringify({geometry:await page.evaluate(() => {
    const selectors=['.site-header','.local-demo-bar','.discovery-heading','.filters','.event-card'];
    return selectors.map(selector=>{const element=document.querySelector(selector);const box=element.getBoundingClientRect();
      return {selector,top:box.top,height:box.height,children:[...element.children].map(child=>({tag:child.tagName,height:child.getBoundingClientRect().height}))};});
  })}));
  check(resting.y + resting.height <= 900, `First complete card ends at ${resting.y+resting.height}px`);
  await target.hover();
  await page.waitForTimeout(300);
  const hover = await card.boundingBox();
  assert.ok(Math.abs(resting.y-hover.y)<1,'Hover keeps the interactive card hitbox stable');
  const feedback = await card.evaluate(element=>({
    surface:getComputedStyle(element,'::before').transform,
    image:getComputedStyle(element.querySelector('img, .event-art svg')).transform,
  }));
  assert.notEqual(feedback.surface,'none');
  assert.notEqual(feedback.image,'none');
  await target.focus();
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Tab');
  assert.ok(await target.evaluate(element=>element===document.activeElement));
  assert.notEqual(await target.evaluate(element=>getComputedStyle(element).outlineStyle),'none');
  await page.mouse.move(0,0);
  await page.screenshot({path:path.join(output,'discover-standard-1440x900.png')});
  if (!problems.length) passed.push('Complete representative card fits 1440x900; hover animates surface/art without moving target; keyboard focus visible');

  for (const viewport of [{width:1280,height:720},{width:1440,height:900}]) {
    await page.setViewportSize(viewport);
    await page.goto(`http://127.0.0.1:3000/chat?eventId=${encodeURIComponent(fixtures.eventId)}`,{waitUntil:'networkidle'});
    const composer = page.locator('form').filter({has:page.getByLabel('Write a message',{exact:true})});
    await composer.waitFor();
    const geometry = await composer.evaluate(element=>{
      const textarea = element.querySelector('textarea').getBoundingClientRect();
      const submit = element.querySelector('button').getBoundingClientRect();
      const thread = element.closest('section').getBoundingClientRect();
      const heading = element.closest('section').querySelector('h2').getBoundingClientRect();
      const log = element.closest('section').querySelector('[role="log"]').getBoundingClientRect();
      return {textarea:textarea.toJSON(),submit:submit.toJSON(),thread:thread.toJSON(),heading:heading.toJSON(),log:log.toJSON(),height:innerHeight,scrollY};
    });
    await page.screenshot({path:path.join(output,`chat-${viewport.width}x${viewport.height}.png`)});
    for(const [name,bounds] of Object.entries({textarea:geometry.textarea,submit:geometry.submit})) {
      check(bounds.top >= geometry.thread.top && bounds.bottom <= Math.min(geometry.thread.bottom,geometry.height)+1,
        `${name} is obscured at ${viewport.width}x${viewport.height}: ${JSON.stringify(geometry)}`);
    }
    check(geometry.heading.bottom <= geometry.log.top && geometry.log.bottom <= geometry.textarea.top,
      `Header, messages and composer overlap: ${JSON.stringify(geometry)}`);
    check(geometry.heading.top >= geometry.thread.top && geometry.log.height >= 48,
      `Conversation heading and message area remain visible: ${JSON.stringify(geometry)}`);
    assert.equal(geometry.scrollY,0,'Composer reachable without scrolling the page');
  }
  if (!problems.length) passed.push('Confirmed attendee chat header, messages, composer and send action visible without overlap at 1280x720 and 1440x900');
  assert.deepEqual(problems,[],'Card/chat geometry checks failed');
} catch(error) {
  await page.screenshot({path:path.join(output,'failure.png')});
  throw error;
} finally {
  await writeFile(path.join(output,'results.json'),JSON.stringify({method:'Isolated PostgreSQL/browser developer check, not participant validation',passed,problems},null,2));
  await browser.close();
}
console.log(JSON.stringify({passed,output}));
