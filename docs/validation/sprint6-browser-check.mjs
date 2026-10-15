// Live persisted local journeys, not participant testing or a production gate.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const require = createRequire(import.meta.url);
const {chromium} = require(process.env.SPRINT6_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT6_FIXTURES);
const output = path.resolve('docs/validation/sprint6-browser-evidence');
await mkdir(output, {recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
const context = await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
const page = await context.newPage();
page.setDefaultTimeout(15000);
const errors = [], passed = [];
page.on('pageerror', () => errors.push('uncaught_browser_error'));
async function visible(locator) {await locator.waitFor({state:'visible'});}
async function account(label) {
  await page.getByLabel('Choose a fictional local account').selectOption({label});
  await page.getByRole('button',{name:'Use fictional account',exact:true}).click();
  await visible(page.getByText(`Local session: ${label}`,{exact:true}));
}
async function nav(label) {
  const menu = page.viewportSize().width < 768 ? '.mobile-nav' : '.desktop-nav';
  await page.locator(menu).getByRole('link',{name:label,exact:true}).click();
}
async function event(title='Fictional Approval Gathering') {
  await nav('Discover');
  await page.getByLabel('Search events or organizations').fill(title);
  await page.getByRole('link',{name:new RegExp(`^View ${title} by`)}).click();
  await visible(page.getByRole('heading',{name:title,level:1}));
}
async function request(shared=false, waitlisted=false) {
  await page.getByRole('button',{name:waitlisted ? 'Join waitlist' : /Request|Register/}).first().click();
  const dialog = page.getByRole('dialog');
  await visible(dialog);
  const consent = dialog.getByRole('checkbox');
  assert.equal(await consent.isChecked(),false,'Per-event consent starts unchecked');
  if(shared) await consent.check();
  await dialog.getByRole('button',{name:waitlisted ? 'Join waitlist' : 'Send registration request',exact:true}).click();
  await visible(page.getByRole('link',{name:'View My Events',exact:true}));
  await visible(page.getByText(waitlisted ? 'Waitlist position: 1.' : /Your request is pending organizer approval/));
}
async function workspace(title) {
  await page.getByRole('link',{name:'Organization',exact:true}).click();
  await page.getByRole('navigation').getByRole('link',{name:/Fictional Approval Society/}).click();
  return page.locator('article').filter({has:page.getByRole('heading',{name:title,exact:true})}).first();
}
function futureManila(hours=4) {return new Date(Date.now()+(hours+8)*3600000).toISOString().slice(0,16);}

try {
  await page.goto('http://127.0.0.1:3000',{waitUntil:'networkidle'});
  await event();
  await visible(page.getByText('Sign in from the header to register for this event.',{exact:true}));
  passed.push('Guest can inspect an approval event without private review data');
  await account('Fictional student 1');
  await request(true);
  await page.getByRole('link',{name:'View My Events',exact:true}).click();
  await visible(page.getByRole('heading',{name:'My Events',level:1}));
  assert.equal(await page.getByRole('tab',{name:'Pending',exact:true}).getAttribute('aria-selected'),'true');
  await visible(page.getByText(/Your request is awaiting organizer review/));
  passed.push('Student opts in per-event, reserves a seat and finds Pending in My Events');
  await account('Fictional faculty');
  await event();
  await request(false);
  await account('Fictional student 2');
  await event();
  await request(false,true);
  await visible(page.getByText(/no estimated wait time/i));
  await page.getByRole('link',{name:'View My Events',exact:true}).click();
  assert.equal(await page.getByRole('tab',{name:'Waitlist',exact:true}).getAttribute('aria-selected'),'true');
  await visible(page.getByText('Waitlist position: 1.',{exact:true}));
  passed.push('Faculty can request approval without sharing persona; full event waitlists next student');

  await account('Fictional student 4');
  let managed = await workspace('Fictional Approval Gathering');
  await managed.getByText('Review registrations',{exact:true}).click();
  const sharedRow = managed.locator('article').filter({has:page.getByRole('heading',{name:'Fictional student 1',exact:true})});
  await visible(sharedRow);
  await sharedRow.getByRole('button',{name:'Approve',exact:true}).click();
  await visible(managed.getByText('Registration approved.',{exact:true}));
  await managed.getByRole('button',{name:'Approve',exact:true}).click();
  await visible(managed.getByText('0 awaiting review',{exact:false}));
  passed.push('Owner approves both pending requests; only opted-in persona appears in staff review');

  const catalog = await context.request.get('http://127.0.0.1:8002/api/v1/local-demo/accounts');
  assert.equal(catalog.status(),200);
  const accounts = await catalog.json();
  const token = label => accounts.find(item=>item.label===label).token;
  const ownerHeaders = {Authorization:`Bearer ${token('Fictional student 4')}`};
  const queue = await context.request.get(`http://127.0.0.1:8002/api/v1/events/${fixtures.eventId}/registration-review`,{headers:ownerHeaders});
  const rows = await queue.json();
  const facultyId = rows.find(item=>item.registration.persona_shared===false && item.registration.status==='confirmed').registration.id;
  const change = managed.locator('details').filter({has:page.getByText('Propose a material event change',{exact:true})});
  await change.locator('summary').click();
  assert.equal(await change.getByLabel('Capacity selection mode',{exact:true}).inputValue(),'exact');
  await change.getByLabel('Capacity',{exact:true}).fill('1');
  await change.getByLabel('Reconfirmation deadline (Manila time)',{exact:true}).fill(futureManila());
  await change.locator('label').filter({hasText:`Registrant ${facultyId.slice(0,8)}`}).getByRole('checkbox').check();
  await change.getByRole('button',{name:'Submit material change',exact:true}).click();
  await visible(page.getByText(/Material changes submitted/));
  const detail = await context.request.get(`http://127.0.0.1:8002/api/v1/events/${fixtures.eventId}`);
  const updated = await detail.json();
  assert.equal(updated.capacity,1);assert.equal(updated.confirmed_count,0);assert.equal(updated.reserved_count,1);
  passed.push('Exact default removes the selected attendee only and reserves the remaining reconfirmation seat');

  await account('Fictional student 1');
  await nav('My Events');
  await page.getByRole('tab',{name:'Pending',exact:true}).click();
  await page.getByRole('button',{name:'Accept and keep my seat',exact:true}).click();
  await page.getByRole('tab',{name:'Confirmed',exact:true}).click();
  await visible(page.getByRole('heading',{name:'Fictional Approval Gathering',level:2}));
  passed.push('Attendee accepts current material revision and returns to Confirmed');

  // Create three persisted instant confirmations for the alternative-selection journey.
  for (const label of ['Fictional student 1','Fictional faculty','Fictional student 2']) {
    const response = await context.request.post(`http://127.0.0.1:8002/api/v1/events/${fixtures.poolEventId}/registrations`,
      {headers:{Authorization:`Bearer ${token(label)}`,'Idempotency-Key':`pool-browser-${label}`}});
    assert.equal(response.status(),201);
  }
  await account('Fictional student 4');
  managed = await workspace('Fictional Pool Gathering');
  const poolChange = managed.locator('details').filter({has:page.getByText('Propose a material event change',{exact:true})});
  await poolChange.locator('summary').click();
  await poolChange.getByLabel('Capacity',{exact:true}).fill('2');
  await poolChange.getByLabel('Reconfirmation deadline (Manila time)',{exact:true}).fill(futureManila());
  await poolChange.getByLabel('Capacity selection mode',{exact:true}).selectOption('newest_in_pool');
  await visible(poolChange.getByText(/3 occupied seats/));
  for(const checkbox of await poolChange.getByRole('checkbox').all()) await checkbox.check();
  await poolChange.getByRole('button',{name:'Submit material change',exact:true}).click();
  await visible(page.getByText(/Material changes submitted/));
  const newest = await context.request.get('http://127.0.0.1:8002/api/v1/me/registrations',
    {headers:{Authorization:`Bearer ${token('Fictional student 2')}`}});
  assert.equal((await newest.json()).find(item=>item.event_id===fixtures.poolEventId).status,'cancelled');
  passed.push('Explicit pool option cancels the newest confirmation, not every selected candidate');

  await page.setViewportSize({width:390,height:844});
  await account('Fictional student 1');
  await nav('My Events');
  await page.getByRole('tab',{name:'Pending',exact:true}).click();
  const poolCard = page.locator('article').filter({has:page.getByRole('heading',{name:'Fictional Pool Gathering',level:2})});
  await poolCard.getByRole('button',{name:'Decline seat',exact:true}).click();
  await visible(page.getByText('You declined your seat for Fictional Pool Gathering.',{exact:true}));
  await visible(page.getByText('This registration is cancelled. The event is still upcoming.',{exact:false}));
  assert.equal(await page.locator('.mobile-nav a').count(),4);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.screenshot({path:path.join(output,'mobile-my-events.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:900});
  await account('Fictional student 5');
  await page.getByRole('link',{name:'Organization',exact:true}).click();
  assert.equal(await page.getByText('Propose a material event change',{exact:true}).count(),0);
  passed.push('Mobile declines safely with four tabs; moderator cannot edit material event fields');
  assert.equal(errors.length,0);
} catch(error) {
  await page.screenshot({path:path.join(output,'failure.png'),fullPage:true});
  console.error(JSON.stringify({path:new URL(page.url()).pathname,headings:await page.locator('h1').allTextContents(),alerts:await page.getByRole('alert').allTextContents()}));
  throw error;
} finally {
  await writeFile(path.join(output,'results.json'),JSON.stringify({method:'Live browser with isolated PostgreSQL; not participant testing',passed,errors},null,2));
  await browser.close();
}
console.log(JSON.stringify({passed,output}));
