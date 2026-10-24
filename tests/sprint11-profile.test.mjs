import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const source = await readFile(new URL('../Code/Frontend/app/profile/page.tsx', import.meta.url), 'utf8');
const ts = createRequire(new URL('../Code/Frontend/package.json', import.meta.url))('typescript');
const parsed = ts.createSourceFile('profile/page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

function declaration(name, kind) {
  let found;
  const visit = node => {
    if (kind === 'function' && ts.isFunctionDeclaration(node) && node.name?.text === name) found = node;
    if (kind === 'variable' && ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === name) found = node;
    if (!found) ts.forEachChild(node, visit);
  };
  visit(parsed);
  assert.ok(found, `${name} exists`);
  return found;
}

function evaluateTypeScript(text, returnName) {
  const javascript = ts.transpileModule(text, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return new Function(`${javascript}; return ${returnName};`)();
}

const profileCompletion = evaluateTypeScript(declaration('profileCompletion', 'function').getText(parsed), 'profileCompletion');

test('profile completion counts only fields that meet the save limits', () => {
  assert.equal(profileCompletion({ nickname: '', ageBracket: '', tags: '' }), 0);
  assert.equal(profileCompletion({ nickname: ' Mika ', ageBracket: '', tags: ' ' }), 1);
  assert.equal(profileCompletion({ nickname: 'Mika', ageBracket: '18-24', tags: 'music, art' }), 3);
  assert.equal(profileCompletion({ nickname: 'Mika', ageBracket: 'x'.repeat(33), tags: 'music' }), 2);
  assert.equal(profileCompletion({ nickname: 'Mika', ageBracket: '18-24', tags: 'x'.repeat(65) }), 2);
  assert.equal(profileCompletion({ nickname: 'Mika', ageBracket: '18-24', tags: Array(33).fill('tag').join(',') }), 2);
});

test('profile form keeps editable values and associates validation accessibly', () => {
  assert.match(source, /noValidate/);
  assert.match(source, /aria-invalid=\{clientError\?\.field === 'nickname'/);
  assert.match(source, /aria-describedby=\{clientError\?\.field === 'nickname' \? 'profile-validation-error'/);
  assert.match(source, /role="alert"/);
  assert.match(source, /value=\{fields\.nickname\}/);
  for (const field of ['nickname', 'ageBracket', 'tags']) {
    const input = source.match(new RegExp(`<input(?=[^>]*id="profile-${field}")[^>]*>`))?.[0];
    assert.ok(input?.includes('disabled={saving || refreshingActor}'), `${field} is locked during save/refresh`);
  }
  assert.match(source, /method: 'PATCH'/);
  assert.match(source, /body: \{\s*nickname,\s*age_bracket: ageBracket,\s*tags,/);
  assert.match(source, /pronouns: fields\.pronouns\.trim\(\) \|\| null/);
  assert.match(source, /icebreaker: fields\.icebreaker\.trim\(\) \|\| null/);
});

test('Settings only labels a preference scope as saved after persistence succeeds', async () => {
  const settings = await readFile(new URL('../Code/Frontend/app/settings/page.tsx', import.meta.url), 'utf8');
  assert.match(settings, /ready && status === 'saved' && !error/);
  assert.match(settings, /onClick=\{retry\}/);
  const styles = await readFile(new URL('../Code/Frontend/features/preferences/preferences.module.css', import.meta.url), 'utf8');
  assert.match(styles, /min-width: 0/);
  assert.match(styles, /overflow-wrap: anywhere/);
});
