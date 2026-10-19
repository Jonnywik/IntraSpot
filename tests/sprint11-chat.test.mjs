import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';

const workspace = readFileSync(new URL('../Code/Frontend/features/communication/ChatWorkspace.tsx', import.meta.url), 'utf8');
const mobileStyles = readFileSync(new URL('../Code/Frontend/features/communication/mobile-chat.module.css', import.meta.url), 'utf8');

test('mobile chat focuses the selected thread and returns to the inbox route', () => {
  assert.match(workspace, /data-has-selection=\{Boolean\(eventId\)\}/);
  assert.equal((workspace.match(/href="\/chat"/g) ?? []).length, 4);
  assert.doesNotMatch(workspace, /href="#chat-inbox"/);
  assert.match(mobileStyles, /data-has-selection='true'\] \.mobileInbox/);
  assert.match(mobileStyles, /:not\(\[data-has-selection='true'\]\) \.mobileThread/);
  assert.match(workspace, /aria-labelledby="chat-thread-heading"/);
});

test('mobile thread overrides compact chat resets and clears the measured navigation', () => {
  assert.match(mobileStyles, /@media \(max-width: 767px\)/);
  assert.match(mobileStyles, /\.mobileChatPage \.mobileChatLayout\[data-has-selection\]/);
  assert.match(mobileStyles, /height: auto;[\s\S]*?min-height: 0;[\s\S]*?max-height: none;/);
  assert.match(mobileStyles, /bottom: calc\(var\(--mobile-nav-height, 96px\) \+ 0\.5rem\)/);
  assert.match(mobileStyles, /max-height: max\(7rem, calc\(100dvh - var\(--mobile-nav-height, 96px\) - 18rem\)\)/);
});

test('chat polling cleanup, archive cutoff, and unchanged-key retry stay intact', () => {
  assert.match(workspace, /item\.status === 'archived'/);
  assert.match(workspace, /!ended && !expired/);
  assert.match(workspace, /if \(pollTimer !== null\) window\.clearInterval\(pollTimer\)/);
  assert.match(workspace, /const request = payload \?\? \(draft\.trim\(\) \? \{ body: draft\.trim\(\), clientKey: crypto\.randomUUID\(\) \} : null\)/);
  assert.match(workspace, /sendMessage\(pendingMessage\)/);
  assert.match(workspace, /countdown\(item\.deletes_at, now, t\)/);
});
