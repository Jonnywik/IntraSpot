// Real persisted local journeys; not participant testing or a deployment gate.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
const {chromium} = createRequire(import.meta.url)(process.env.SPRINT7_PLAYWRIGHT);
const fixtures = JSON.parse(process.env.SPRINT7_FIXTURES);
const output = path.resolve(process.env.SPRINT7_EVIDENCE_DIR || 'docs/validation/sprint7-browser-evidence');
await mkdir(output,{recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
const context = await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
const page = await context.newPage();
page.setDefaultTimeout(15000);
const passed = [], errors = [];
page.on('pageerror',()=>errors.push('uncaught_browser_error'));
const visible = locator => locator.waitFor({state:'visible'});
async function account(label) {
  await page.getByLabel('Choose a fictional local account').selectOption({label});
  await page.getByRole('button',{name:'Use fictional account',exact:true}).click();
  await visible(page.getByText(`Local session: ${label}`,{exact:true}));
}
async function nav(label) {
  const menu = page.viewportSize().width < 768 ? '.mobile-nav' : '.desktop-nav';
  await page.locator(menu).getByRole('link',{name:label,exact:true}).click();
}
async function event() {
  await nav('Discover');
  await page.getByLabel('Search events or organizations').fill('Fictional Community Gathering');
  await page.getByRole('link',{name:/^View Fictional Community Gathering by/}).click();
  await visible(page.getByRole('heading',{name:'Fictional Community Gathering',level:1}));
}
async function register() {
  await page.getByRole('button',{name:'Register',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Confirm your registration',exact:true}).click();
  await visible(page.getByText('Your registration is confirmed.',{exact:true}));
}
const commentCard = body => page.locator('article').filter({has:page.getByText(body,{exact:true})}).last();
async function reportCard(card,person=false) {
  await card.locator('summary').filter({hasText:'Report'}).click();
  if(person) await card.getByRole('radio',{name:'This member',exact:true}).check();
  await card.getByRole('button',{name:'Submit report',exact:true}).click();
  await visible(card.getByText(person ? 'Person report sent for review.' : 'Content report sent. The item remains visible while it is reviewed.',{exact:true}));
}
async function chat(title) {
  await nav('Chat');
  await page.getByRole('navigation',{name:'Event chat list'}).getByRole('link').filter({hasText:title}).click();
  await visible(page.getByRole('heading',{name:title,level:2}));
}
try {
  await page.goto('http://127.0.0.1:3000',{waitUntil:'networkidle'});
  await event();
  await visible(page.getByText('Public fictional welcome',{exact:true}));
  assert.equal(await page.getByLabel('Add a comment',{exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:/Choose Interested reaction/}).isDisabled(),true);
  passed.push('Guests read real public comments but cannot comment or react');

  await account('Fictional student 1');
  await register();
  for(const label of ['Interested','Excited','Support','Kudos','Wow','Relate']) {
    await page.getByRole('button',{name:new RegExp(`Choose ${label} reaction`)}).click();
    await visible(page.getByRole('button',{name:new RegExp(`Remove ${label} reaction`)}));
  }
  await page.getByRole('button',{name:/Remove Relate reaction/}).click();
  await visible(page.getByRole('button',{name:/Choose Relate reaction/}));
  passed.push('All six reactions replace or clear without registering again');

  let lost = false;
  await page.route('**/api/v1/events/*/comments',async route=>{
    if(route.request().method()==='POST'&&!lost){lost=true;await route.fetch();await route.abort('failed');}
    else await route.continue();
  });
  await page.getByLabel('Add a comment',{exact:true}).fill('A persisted fictional comment');
  await page.getByRole('button',{name:'Post comment',exact:true}).click();
  await visible(page.getByRole('alert').filter({hasText:'Comment could not be completed'}));
  await page.getByRole('button',{name:'Retry unchanged comment',exact:true}).click();
  await visible(page.getByText('A persisted fictional comment',{exact:true}));
  await page.unroute('**/api/v1/events/*/comments');
  passed.push('Lost comment response retries the same key and persisted text');

  await account('Fictional faculty'); await event(); await register();
  await chat('Fictional Community Gathering');
  await page.getByLabel('Write a message',{exact:true}).fill('Meet at the fictional courtyard');
  await page.getByRole('button',{name:'Send message',exact:true}).click();
  await visible(page.getByText('Meet at the fictional courtyard',{exact:true}));
  await account('Fictional student 1');
  await chat('Fictional Community Gathering');
  let message = commentCard('Meet at the fictional courtyard');
  await message.getByRole('button',{name:'Hide for me',exact:true}).click();
  await visible(page.getByText('This message is hidden for you.',{exact:true}));
  await page.getByRole('button',{name:'Restore for me',exact:true}).click();
  await visible(page.getByText('Meet at the fictional courtyard',{exact:true}));
  passed.push('Confirmed attendees send/poll real chat; personal hide/restore is reversible');

  await account('Fictional student 2'); await event();
  await page.getByRole('button',{name:'Join waitlist',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Join waitlist',exact:true}).click();
  await visible(page.getByText('Waitlist position: 1.',{exact:true}));
  await nav('Chat');
  assert.equal(await page.getByRole('navigation',{name:'Event chat list'}).count(),0);
  await visible(page.getByText('No confirmed event chats are available.',{exact:true}));
  passed.push('Waitlisted attendee cannot read private event chat');

  await account('Fictional faculty'); await event();
  await reportCard(commentCard('A persisted fictional comment'));
  await visible(page.getByText('A persisted fictional comment',{exact:true}));
  await account('Fictional student 5');
  await page.getByRole('link',{name:'Organization',exact:true}).click();
  await page.getByRole('navigation',{name:'Moderator review workspaces',exact:true})
    .getByRole('link').filter({hasText:'Fictional Community Society'}).click();
  await page.getByRole('button',{name:/Comment.*Harassment/}).click();
  await visible(page.getByText('A persisted fictional comment',{exact:true}));
  page.once('dialog',dialog=>{
    assert.equal(dialog.message(),'Remove this reported content for everyone?');
    void dialog.accept();
  });
  await page.getByRole('button',{name:'Remove globally',exact:true}).click();
  await visible(page.getByRole('status').filter({hasText:/recorded|removed/i}).first());
  await page.getByRole('button',{name:/Comment.*Harassment/}).click();
  assert.equal(await page.getByText('A persisted fictional comment',{exact:true}).count(),0);
  passed.push('Organization moderator removes content with a server-recorded decision and cleared evidence');

  await account('Fictional faculty'); await event();
  await reportCard(commentCard('Public fictional welcome'),true);
  await account('Fictional student 1');
  await chat('Fictional Community Gathering');
  await visible(page.getByText(/Sending is temporarily paused|Sending is currently unavailable/));
  assert.equal(await page.getByLabel('Write a message',{exact:true}).count(),0);
  await visible(page.getByText('Meet at the fictional courtyard',{exact:true}));
  await account('Fictional platform admin');
  await page.getByRole('link',{name:'Platform admin',exact:true}).click();
  await page.getByRole('button',{name:/Person.*Harassment/}).click();
  await page.getByRole('button',{name:'Warn user',exact:true}).click();
  await account('Fictional student 1');
  await chat('Fictional Community Gathering');
  await visible(page.getByLabel('Write a message',{exact:true}));
  passed.push('Personal review pauses sending but keeps reads and seats; platform warning restores access');

  await page.setViewportSize({width:390,height:844});
  await chat('Fictional Archived Gathering');
  await visible(page.getByText('This chat is archived and read-only after its scheduled end.',{exact:true}));
  assert.equal(await page.getByLabel('Write a message',{exact:true}).count(),0);
  await visible(page.getByText('Historical fictional discussion',{exact:true}));
  assert.equal(await page.getByRole('navigation',{name:'Event chat list'}).getByRole('link').filter({hasText:'Fictional Expired Gathering'}).count(),0);
  assert.equal(await page.locator('.mobile-nav a').count(),4);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(output,'mobile-archived-chat.png'),fullPage:true});
  passed.push('Mobile keeps four tabs and archived chat in the same list with countdown; expired chat is absent');

  await page.setViewportSize({width:1440,height:900});
  await page.getByRole('link',{name:'Notifications',exact:true}).click();
  await visible(page.getByText('Safety review',{exact:true}).first());
  await page.getByRole('button',{name:'Mark as read',exact:true}).first().click();
  await visible(page.getByText('Read',{exact:true}).first());
  passed.push('Sanitized durable in-app notifications have persisted read feedback');
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
