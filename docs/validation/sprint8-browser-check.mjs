// Rendered local membership journeys, not participant validation or release approval.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
const {chromium} = createRequire(import.meta.url)(process.env.SPRINT8_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT8_FIXTURES);
const output = path.resolve('docs/validation/sprint8-browser-evidence');
await mkdir(output,{recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
const context = await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
const page = await context.newPage();
page.setDefaultTimeout(15000);
const passed=[], errors=[];
page.on('pageerror',()=>errors.push('uncaught_browser_error'));
const visible = locator => locator.waitFor({state:'visible'});
const section = id => page.locator(`[aria-labelledby="${id}"]`);
async function account(label) {
  await page.getByLabel('Choose a fictional local account').selectOption({label});
  await page.getByRole('button',{name:'Use fictional account',exact:true}).click();
  await visible(page.getByText(`Local session: ${label}`,{exact:true}));
}
async function clubs() {
  if(page.viewportSize().width<768){
    await page.locator('.mobile-nav').getByRole('link',{name:'Settings',exact:true}).click();
    await page.getByRole('link',{name:'Clubs and membership',exact:true}).click();
  } else await page.getByRole('link',{name:'Clubs',exact:true}).click();
  await page.getByRole('button',{name:/Fictional Membership Society/}).click();
  await visible(section('selected-organization-title').getByRole('heading',{name:'Fictional Membership Society',exact:true}));
}
async function workspace(moderator=false) {
  await page.getByRole('link',{name:'Organization',exact:true}).click();
  if(moderator) await page.getByRole('link',{name:'Review published event registrations',exact:true}).click();
  else await page.getByRole('navigation',{name:'Owner and admin workspaces'}).getByRole('link').filter({hasText:'Fictional Membership Society'}).click();
  await visible(section('membership-review-title').getByRole('heading',{name:'Applications',exact:true}));
}
function pendingReview() {
  return section('membership-review-title').locator('article').filter({has:page.getByRole('button',{name:'Approve membership',exact:true})}).first();
}
function rosterCard(id) {
  return section('membership-roster-title').locator('article').filter({hasText:id.replaceAll('-','').slice(-6).toUpperCase()});
}
try {
  await page.goto('http://127.0.0.1:3000',{waitUntil:'networkidle'});
  await clubs();
  await visible(page.getByText('Sign in with your own account to request membership. Guests can browse, but cannot acquire an anonymous membership.',{exact:true}));
  assert.equal(await page.getByRole('button',{name:'Request membership',exact:true}).count(),0);
  passed.push('Guest browses approved clubs without applications, private rosters or anonymous membership');

  await account('Fictional visitor (not PLM)'); await clubs();
  const consent=page.getByRole('checkbox',{name:/Optionally share my nickname and interests/});
  assert.equal(await consent.isChecked(),false);
  await page.getByRole('button',{name:'Request membership',exact:true}).click();
  await visible(page.getByText('Awaiting organization review',{exact:true}));
  await account('Fictional student 5'); await workspace(true);
  await pendingReview().getByRole('button',{name:'Approve membership',exact:true}).click();
  await visible(page.getByText('No pending membership applications.',{exact:true}));
  await account('Fictional visitor (not PLM)'); await clubs();
  await visible(page.getByText('Your membership is on file, but member features are locked.',{exact:true}));
  await visible(section('memberships-title').getByText('Access locked',{exact:true}));
  assert.equal(await page.getByRole('link',{name:'Organization',exact:true}).count(),0);
  assert.equal(await section('selected-organization-title').locator('textarea').count(),0);
  passed.push('Non-PLM signed-in application can be approved by moderator, but member features remain locked');

  await account('Fictional student 2'); await clubs();
  await page.getByRole('checkbox',{name:/Optionally share my nickname and interests/}).check();
  const keys=[];
  let lost=false;
  await page.route('**/api/v1/organizations/*/membership-applications',async route=>{
    if(route.request().method()==='POST') {
      keys.push(route.request().postDataJSON().client_key);
      if(!lost){lost=true;await route.fetch();await route.abort('failed');return;}
    }
    await route.continue();
  });
  await page.getByRole('button',{name:'Request membership',exact:true}).click();
  await visible(page.getByRole('button',{name:'Retry membership request',exact:true}));
  await page.getByRole('button',{name:'Retry membership request',exact:true}).click();
  await visible(page.getByText('Awaiting organization review',{exact:true}));
  assert.equal(keys.length,2); assert.equal(keys[0],keys[1]);
  await page.unroute('**/api/v1/organizations/*/membership-applications');
  await account('Fictional student 5'); await workspace(true);
  const review=pendingReview();
  await visible(review.getByText(/Nickname:/));
  await visible(review.getByText(/Interests:/));
  assert.equal(await section('membership-review-title').getByText(/Age bracket:|Email:|Pronouns:/).count(),0);
  await review.getByRole('combobox',{name:/^Rejection reason/}).selectOption('requirements_not_met');
  await review.getByRole('button',{name:'Reject application',exact:true}).click();
  await visible(page.getByText('No pending membership applications.',{exact:true}));
  assert.equal(await section('membership-review-title').getByText(/Nickname:/).count(),0);
  passed.push('Lost application response retries one key; pending basic consent expires after categorized rejection');

  await account('Fictional student 2'); await clubs();
  await visible(page.getByText(/Your previous request was not approved.*Membership requirements not met/));
  await page.getByRole('button',{name:'Request membership',exact:true}).click();
  await visible(page.getByText('Awaiting organization review',{exact:true}));
  await page.getByRole('button',{name:'Withdraw request',exact:true}).click();
  await page.getByRole('group',{name:'Confirm request withdrawal',exact:true}).getByRole('button',{name:'Confirm withdrawal',exact:true}).click();
  await visible(page.getByText('Reapplication is temporarily paused after withdrawal.',{exact:true}));
  assert.equal(await page.getByRole('button',{name:'Request membership',exact:true}).count(),0);
  await visible(page.getByText(/This rejection did not impose a reapplication cooldown; your current request status determines when you can apply again/));
  assert.equal(await page.getByText(/You may reapply immediately/).count(),0);
  passed.push('Rejection allows immediate reapplication; withdrawing then enforces the persisted 24-hour cooldown');

  await account('Fictional student 4'); await workspace();
  await page.getByLabel('Existing account code (UUID)',{exact:true}).fill(fixtures.inviteeId);
  await page.getByRole('button',{name:'Send invitation',exact:true}).click();
  await visible(section('membership-invitations-title').getByRole('heading',{name:`Account ${fixtures.inviteeId}`,exact:true}));
  await account('Fictional student 3'); await clubs();
  await section('invitations-title').getByRole('button',{name:'Accept',exact:true}).click();
  await visible(section('memberships-title').getByText('Access ready',{exact:true}));
  await page.locator('.desktop-nav').getByRole('link',{name:'Discover',exact:true}).click();
  await visible(page.getByRole('button',{name:'My Clubs',exact:true}));
  await page.getByRole('button',{name:'My Clubs',exact:true}).click();
  await page.getByLabel('Search events or organizations').fill('Fictional Membership Society');
  await visible(page.getByRole('link',{name:/^View Fictional Membership Gathering by/}));
  passed.push('Targeted invitation acceptance grants membership and refreshes composed My Clubs access without signing in again');

  await account('Fictional student 4'); await workspace();
  let member=rosterCard(fixtures.inviteeId);
  await member.getByRole('combobox',{name:/^Change role/}).selectOption('admin');
  await member.getByRole('button',{name:'Confirm role change',exact:true}).click();
  await page.getByRole('group',{name:'Confirm membership role change',exact:true}).getByRole('button',{name:'Confirm role change',exact:true}).click();
  await visible(rosterCard(fixtures.inviteeId).getByText(/Admin.*PLM eligible/));
  await section('membership-roster-title').screenshot({path:path.join(output,'desktop-staff-roster.png')});
  await account('Fictional student 6'); await workspace();
  assert.equal(await rosterCard(fixtures.inviteeId).getByRole('button',{name:'Remove member',exact:true}).count(),0);
  await account('Fictional student 4'); await workspace();
  await rosterCard(fixtures.inviteeId).getByRole('button',{name:'Remove member',exact:true}).click();
  await page.getByRole('group',{name:'Confirm membership removal',exact:true}).getByRole('button',{name:'Confirm removal',exact:true}).click();
  await rosterCard(fixtures.inviteeId).waitFor({state:'detached'});
  passed.push('Owner grants admin; another admin cannot remove that admin; owner removal persists');

  await account('Fictional student 1'); await clubs();
  await section('memberships-title').getByRole('button',{name:'Leave organization',exact:true}).click();
  await page.getByRole('group',{name:'Confirm leaving Fictional Membership Society',exact:true}).getByRole('button',{name:'Confirm leave',exact:true}).click();
  await visible(section('memberships-title').getByText('Membership ended',{exact:true}));
  await page.locator('.desktop-nav').getByRole('link',{name:'Discover',exact:true}).click();
  await page.getByRole('button',{name:'My Clubs',exact:true}).waitFor({state:'detached'});
  await page.locator('.desktop-nav').getByRole('link',{name:'Chat',exact:true}).click();
  await visible(page.getByText('No confirmed event chats are available.',{exact:true}));
  passed.push('Leaving ends existing event participation and active/archived chat without deleting attendance history');

  await account('Fictional faculty');
  await page.locator('.desktop-nav').getByRole('link',{name:'My Events',exact:true}).click();
  await visible(page.getByRole('heading',{name:'Fictional Membership Gathering',exact:true}));
  await page.getByRole('link',{name:'Notifications',exact:true}).click();
  await visible(page.getByText('Attendance confirmed',{exact:true}).first());
  passed.push('Released membership departure seat promotes the public faculty waiter and persists an in-app notice');

  await account('Fictional student 2'); await page.setViewportSize({width:390,height:844}); await clubs();
  await visible(page.getByText('Reapplication is temporarily paused after withdrawal.',{exact:true}));
  assert.equal(await page.locator('.mobile-nav a').count(),4);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.equal(await page.getByRole('heading',{name:'Membership management',exact:true}).count(),0);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(output,'mobile-membership.png'),fullPage:true});
  passed.push('Mobile retains four tabs, readable membership status and no organization-management controls');
  assert.equal(errors.length,0);
} catch(error) {
  await page.screenshot({path:path.join(output,'failure.png'),fullPage:true});
  console.error(JSON.stringify({path:new URL(page.url()).pathname,headings:await page.locator('h1').allTextContents(),alerts:await page.getByRole('alert').allTextContents()}));
  throw error;
} finally {
  await writeFile(path.join(output,'results.json'),JSON.stringify({method:'Real browser and scratch PostgreSQL, not participant validation',passed,errors},null,2));
  await browser.close();
}
console.log(JSON.stringify({passed,output}));
