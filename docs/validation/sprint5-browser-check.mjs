// Local heuristic browser checks: not participant testing or a production release.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const require = createRequire(import.meta.url);
const {chromium} = require(process.env.SPRINT5_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT5_FIXTURES);
const base = 'http://127.0.0.1:3000';
const output = path.resolve('docs/validation/sprint5-browser-evidence');
await mkdir(output, {recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
const context = await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
const page = await context.newPage();
const browserErrors = [];
const passed = [];
page.on('pageerror', () => browserErrors.push('uncaught_browser_error'));
page.setDefaultTimeout(15000);
async function visible(locator) {await locator.waitFor({state:'visible'});}
async function account(label) {
  await page.getByLabel('Choose a fictional local account').selectOption({label});
  await page.getByRole('button',{name:'Use fictional account',exact:true}).click();
  await visible(page.getByText(`Local session: ${label}`,{exact:true}));
}
async function nav(label) {await page.locator('.desktop-nav').getByRole('link',{name:label,exact:true}).click();}
async function event(title='Fictional Heritage Gathering') {
  await nav('Discover');
  await page.getByLabel('Search events or organizations').fill(title);
  await page.getByRole('link',{name:new RegExp(`^View ${title} by`)}).click();
  await visible(page.getByRole('heading',{name:title,level:1}));
}
async function register(expected) {
  await page.getByRole('button',{name:/^(Register|Join waitlist)$/}).click();
  const dialog=page.getByRole('dialog');
  await visible(dialog);
  // Initial reverse tab must stay within the confirmation sheet.
  await page.keyboard.press('Shift+Tab');
  assert.equal(await dialog.evaluate(el=>el.contains(document.activeElement)),true);
  await dialog.getByRole('button',{name: /^(Confirm your registration|Join waitlist)$/}).click();
  await visible(page.getByText(expected,{exact:true}));
}
try {
  await page.goto(base,{waitUntil:'networkidle'});
  await event();
  await visible(page.getByText('Sign in from the header to register for this event.',{exact:true}));
  assert.equal(await page.locator('dl[aria-label="Event counts"]').count(),1);
  passed.push('Guest discovery and public detail, distinct attendance counts');

  await account('Fictional incomplete profile');
  await page.getByRole('link',{name:'Update your profile',exact:true}).click();
  await page.getByLabel('Nickname',{exact:true}).fill('Fictional New Member');
  await page.getByLabel('Age bracket',{exact:true}).fill('18-24');
  await page.getByLabel('Interest or vibe tags',{exact:true}).fill('arts, community');
  await page.getByRole('button',{name:'Save profile',exact:true}).click();
  await visible(page.getByText('Profile saved.',{exact:true}));
  await event();
  await register('Your registration is confirmed.');
  const confirmedCount = page.locator('dl[aria-label="Event counts"] > div').filter({has:page.locator('dt').getByText('Confirmed',{exact:true})}).locator('dd');
  await page.waitForFunction(() => [...document.querySelectorAll('dl[aria-label="Event counts"] > div')]
    .some(element => element.querySelector('dt')?.textContent === 'Confirmed' && element.querySelector('dd')?.textContent === '1'));
  assert.equal(await confirmedCount.textContent(),'1');
  await page.getByRole('link',{name:'View My Events',exact:true}).click();
  await visible(page.getByRole('heading',{name:'My Events',level:1}));
  await visible(page.getByRole('heading',{name:'Fictional Heritage Gathering',level:2}));
  passed.push('Incomplete student completes persisted profile, registers, finds My Events');

  await account('Fictional faculty');
  await event();
  await register('Waitlist position: 1.');
  await visible(page.getByText(/no estimated wait time/i));
  await page.getByRole('link',{name:'View My Events',exact:true}).click();
  await visible(page.getByRole('heading',{name:'My Events',level:1}));
  await page.getByRole('tab',{name:/^Waitlist(?:\s|$)/}).click();
  await visible(page.getByText('Waitlist position: 1.',{exact:true}));
  await visible(page.getByText(/no estimated wait time/i));
  passed.push('Faculty eligibility and immediate/persisted waitlist position');

  await account('Fictional incomplete profile');
  await nav('My Events');
  await page.getByRole('button',{name:'Withdraw registration',exact:true}).click();
  await visible(page.getByText('This registration is cancelled. The event is still upcoming.',{exact:false}));
  await account('Fictional faculty');
  await visible(page.getByRole('heading',{name:'Fictional Heritage Gathering',level:2}));
  await page.getByRole('link',{name:'Notifications',exact:true}).click();
  await visible(page.getByText(/promoted|confirmed/i).filter({hasNot:page.locator('button')}).first());
  passed.push('Withdrawal promotes faculty waiter and persists an in-app notification');

  await account('Fictional student 4');
  await nav('Discover');
  const clubs=page.getByRole('button',{name:'My Clubs',exact:true});
  await visible(clubs);
  await clubs.click();
  await page.getByLabel('Search events or organizations').fill('Arts Society');
  await visible(page.getByRole('link',{name:/^View Fictional Heritage Gathering by/}));
  assert.equal(await clubs.getAttribute('aria-pressed'),'true');
  await page.getByLabel('Search events or organizations').fill('PLM courtyard');
  await visible(page.getByRole('heading',{name:'No events found',exact:true}));
  passed.push('Owner membership supports My Clubs composed with organization search, not venue');

  await account('Fictional student 2');
  await event('Fictional Retry Gathering');
  let attempts=0;
  const keys=[];
  await page.route('**/api/v1/events/*/registrations',async route=>{
    if(route.request().method()!=='POST') return route.continue();
    attempts++;
    keys.push(route.request().headers()['idempotency-key']);
    const response=await route.fetch(); // First attempt commits in PostgreSQL.
    if(attempts===1) await route.abort('failed');
    else await route.fulfill({response});
  });
  await page.getByRole('button',{name:'Register',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Confirm your registration',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Retry registration',exact:true}).click();
  await visible(page.getByText('Your registration is confirmed.',{exact:true}));
  assert.equal(attempts,2);assert.ok(keys[0]);assert.equal(keys[0],keys[1]);
  await page.unroute('**/api/v1/events/*/registrations');
  await page.getByRole('link',{name:'View My Events',exact:true}).click();
  await visible(page.getByRole('heading',{name:'My Events',level:1}));
  await visible(page.getByRole('heading',{name:'Fictional Retry Gathering',level:2}));
  assert.equal(await page.getByRole('heading',{name:'Fictional Retry Gathering',level:2}).count(),1);
  passed.push('Lost-response retry preserves idempotency key and one persisted registration');

  await account('Fictional organizer');
  await page.getByRole('link',{name:'Organization',exact:true}).click();
  await page.getByLabel('Organization name',{exact:true}).fill('Fictional Sprint Five Club');
  await page.getByRole('button',{name:'Submit organization',exact:true}).click();
  await page.getByRole('link',{name:'Start a private draft',exact:true}).click();
  await page.getByRole('button',{name:'Create draft',exact:true}).click();
  await page.getByLabel('Event title',{exact:true}).fill('Fictional Newly Published Event');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await visible(page.getByText('Draft saved.',{exact:true}));
  assert.equal(await page.getByRole('button',{name:'Publish',exact:true}).isDisabled(),true);
  const draftUrl=page.url();
  const draftId=new URL(draftUrl).searchParams.get('eventId');
  const orgId=new URL(draftUrl).searchParams.get('orgId');
  assert.ok(draftId&&orgId);
  const guestDraft=await context.request.get(`http://127.0.0.1:8002/api/v1/events/${draftId}`);
  assert.equal(guestDraft.status(),404);
  passed.push('Pending organization saves incomplete private draft and cannot publish');

  await account('Fictional platform admin');
  await page.getByRole('link',{name:'Platform admin',exact:true}).click();
  const application=page.locator('article').filter({has:page.getByRole('heading',{name:'Fictional Sprint Five Club',exact:true})});
  await application.getByRole('button',{name:'Approve after offline assessment',exact:true}).click();
  const approvalDialog = page.getByRole('dialog', {name:'Confirm approval',exact:true});
  await visible(approvalDialog);
  await approvalDialog.getByRole('button', {name:'Confirm approval',exact:true}).click();
  await visible(page.getByRole('status').filter({hasText:'Decision recorded for Fictional Sprint Five Club.'}));
  passed.push('Platform admin records authoritative offline accreditation decision');

  await account('Fictional organizer');
  await page.getByRole('link',{name:'Organization',exact:true}).click();
  await page.getByRole('navigation',{name:'Owner and admin workspaces'}).getByRole('link',{name:/Fictional Sprint Five Club/}).click();
  await page.getByRole('link',{name:'Open private draft',exact:true}).click();
  const future = new Date(Date.now()+4*86400000+8*3600000).toISOString().slice(0,16);
  const end = new Date(Date.now()+4*86400000+10*3600000).toISOString().slice(0,16);
  await page.getByLabel('Starts at (Manila time)',{exact:true}).fill(future);
  await page.getByLabel('Ends at (Manila time)',{exact:true}).fill(end);
  await page.getByLabel('Venue name',{exact:true}).fill('Fictional PLM Courtyard');
  await page.getByLabel('Venue address',{exact:true}).fill('Intramuros, Manila');
  await page.getByLabel('Capacity',{exact:true}).fill('5');
  await page.getByRole('combobox',{name:/^Artwork theme/}).selectOption('heritage');
  await page.getByLabel('Description',{exact:true}).fill('Fictional event for local Sprint 5 acceptance only.');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await visible(page.getByText('Draft saved.',{exact:true}));
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button',{name:'Publish',exact:true}).click();
  await visible(page.getByRole('status').filter({hasText:'This event is now published.'}));
  await page.getByRole('button',{name:'Continue as guest',exact:true}).click();
  await page.goto(`${base}/events?eventId=${draftId}`,{waitUntil:'networkidle'});
  await visible(page.getByRole('heading',{name:'Fictional Newly Published Event',level:1}));
  passed.push('Approved organization publishes; newly created query route loads without rebuild');

  const viewports=[{width:1280,height:720},{width:1366,height:768},{width:1440,height:900},
    {width:1920,height:1080},{width:390,height:844}];
  for(const viewport of viewports){
    await page.setViewportSize(viewport);
    await page.goto(base,{waitUntil:'networkidle'});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,
      `Horizontal overflow at ${viewport.width}`);
    assert.equal(await page.evaluate(()=>[...document.querySelectorAll('button')].filter(el=>el.getClientRects().length)
      .some(el=>!el.textContent.trim()&&!el.getAttribute('aria-label'))),false);
    const crop=await page.locator('.artwork-crop').first().boundingBox();
    assert.ok(crop && Math.abs(crop.width/crop.height-2.88)<.02,'Approved image aspect ratio');
    if(viewport.width===1440){
      const card=await page.locator('.event-card').first().boundingBox();
      assert.ok(card && card.y+card.height<=viewport.height,`Representative first card fits 1440×900: ${JSON.stringify(card)}`);
    }
    await page.screenshot({path:path.join(output,`discover-${viewport.width}.png`),fullPage:true});
  }
  await account('Fictional organizer');
  await page.goto(draftUrl,{waitUntil:'networkidle'}); // Restored local account is reverified after hard navigation.
  await account('Fictional organizer');
  await visible(page.locator('.desktop-required'));
  assert.equal(await page.getByLabel('Event title',{exact:true}).isVisible(),false);
  assert.equal(await page.locator('.mobile-nav a').count(),4);
  passed.push('Five viewport fit checks; four mobile tabs; direct mobile manager editor unavailable');
  assert.equal(browserErrors.length,0,'Uncaught browser errors');
}catch(error){
  await page.screenshot({path:path.join(output,'failure.png'),fullPage:true});
  console.error(JSON.stringify({path:new URL(page.url()).pathname,heading:await page.locator('h1').allTextContents(),
    guestProfile:await page.getByRole('heading',{name:'Profile unavailable as a guest'}).count(),
    signedIn:await page.getByText(/^Local session:/).count(),alertCount:await page.getByRole('alert').count()}));
  throw error;
}finally{
  await writeFile(path.join(output,'results.json'),JSON.stringify({method:'Live browser against real PostgreSQL scratch database; not participant testing',passed,browserErrors},null,2));
  await browser.close();
}
console.log(JSON.stringify({journeyChecks:passed.length,passed,output}));
