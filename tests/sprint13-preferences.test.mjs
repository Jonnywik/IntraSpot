import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const source = await readFile(new URL('../Code/Frontend/lib/preferences.tsx', import.meta.url), 'utf8');
const ts = createRequire(new URL('../Code/Frontend/package.json', import.meta.url))('typescript');
const parsed = ts.createSourceFile('preferences.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
assert.equal(parsed.parseDiagnostics.length, 0, 'preferences.tsx parses without syntax errors');

function variable(name) {
  let found;
  const visit = node => {
    if (ts.isVariableDeclaration(node) && node.name.getText(parsed) === name) found = node;
    if (!found) ts.forEachChild(node, visit);
  };
  visit(parsed);
  assert.ok(found, `${name} exists`);
  return found;
}

function declaration(name) {
  let found;
  const visit = node => {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) found = node;
    if (!found) ts.forEachChild(node, visit);
  };
  visit(parsed);
  assert.ok(found, `${name} exists`);
  return found.getText(parsed);
}

const helpers = ts.transpileModule([
  declaration('isRecord'),
  declaration('decodePreferences'),
  declaration('decodeResponse'),
  declaration('decodeGuestRecord'),
].join('\n'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;
const { decodePreferences, decodeResponse, decodeGuestRecord } = new Function(
  helpers + '; return { decodePreferences, decodeResponse, decodeGuestRecord };',
)();
const defaults = new Function(`return (${variable('DEFAULT_PREFERENCES').initializer.getText(parsed)});`)();
const setterNode = variable('setPreference').initializer.arguments[0];
const setter = ts.transpileModule(setterNode.getText(parsed), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;

const legacyPreferences = {
  language: 'en',
  theme: 'light',
  text_size: 'standard',
  high_contrast: false,
  reduced_motion: false,
  decoration_paused: false,
};

test('show_flash defaults on in frontend preferences', () => {
  assert.equal(defaults.show_flash, true);
});

test('legacy API and version 1 guest preferences decode with show_flash enabled', () => {
  assert.equal(decodePreferences(legacyPreferences).show_flash, true);
  assert.equal(decodeResponse({
    ...legacyPreferences,
    initialized: true,
    updated_at: null,
  }).show_flash, true);
  assert.equal(decodeGuestRecord({ version: 1, preferences: legacyPreferences }).show_flash, true);
});

test('explicit show_flash choices survive decoding', () => {
  assert.equal(decodePreferences({ ...legacyPreferences, show_flash: false }).show_flash, false);
  assert.equal(decodeGuestRecord({
    version: 1,
    preferences: { ...legacyPreferences, show_flash: false },
  }).show_flash, false);
});

test('a present malformed show_flash value is rejected by API and guest decoders', () => {
  for (const value of [undefined, null, 0, 1, 'false']) {
    const malformed = { ...legacyPreferences, show_flash: value };
    assert.throws(() => decodePreferences(malformed));
    assert.throws(() => decodeResponse({ ...malformed, initialized: true, updated_at: null }));
    assert.throws(() => decodeGuestRecord({ version: 1, preferences: malformed }));
  }
});

test('setting another preference keeps the existing show_flash choice', () => {
  const scopeRef = { current: { activationKey: 'account:test' } };
  const runtime = {
    activationKey: 'account:test',
    ready: true,
    kind: 'account',
    preferences: { ...defaults, show_flash: false },
    dirty: {},
  };
  const setPreference = new Function(
    'scopeRef', 'activeRuntime', 'publish', 'startSave',
    `return ${setter};`,
  )(scopeRef, { current: runtime }, () => {}, () => {});

  setPreference('theme', 'dark');

  assert.equal(runtime.preferences.show_flash, false);
  assert.deepEqual(runtime.dirty, { theme: 'dark' });
});
