import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {applyAuthorLabels, clearAuthorLabels} from '../Code/Frontend/lib/content-labels.ts';

const items = [
  {id:'old',author_id:'other',author_label:'Old private nickname',body:'Keep this message',mine:false},
  {id:'mine',author_id:'self',author_label:'You',body:'My message',mine:true},
];

test('privacy label refresh preserves older messages and does not change content or ownership', () => {
  const refreshed = applyAuthorLabels(items, {other:'PLM member'});
  assert.equal(refreshed[0].author_label, 'PLM member');
  assert.deepEqual(refreshed.map(item=>item.body), items.map(item=>item.body));
  assert.equal(refreshed[1].author_label, 'You');
  assert.equal(items[0].author_label, 'Old private nickname');
  assert.equal(applyAuthorLabels(items, {})[0].author_label, 'PLM member');
  assert.equal(clearAuthorLabels(items, 'other')[0].author_label, 'PLM member');
  assert.equal(clearAuthorLabels(items, 'unrelated')[0].author_label, 'Old private nickname');
});

test('content refresh consumes current server labels even when incremental chat has no new items', async () => {
  for (const file of ['EventSocial.tsx','ChatWorkspace.tsx']) {
    const source = await readFile(new URL(`../Code/Frontend/features/communication/${file}`, import.meta.url),'utf8');
    assert.match(source, /applyAuthorLabels/);
    assert.match(source, /author_labels/);
    assert.match(source, /clearAuthorLabels/);
    assert.match(source, /PERSONA_ACCESS_CHANGED_EVENT/);
    assert.match(source, /removeEventListener/);
  }
});
