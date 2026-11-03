import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import test from 'node:test';
import ts from '../Code/Frontend/node_modules/typescript/lib/typescript.js';

const frontend = new URL('../Code/Frontend/', import.meta.url);
const require = createRequire(new URL('../Code/Frontend/package.json', import.meta.url));
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const read = path => readFile(new URL(path, frontend), 'utf8');

function dataUrl(source) {
  return 'data:text/javascript;base64,' + Buffer.from(source, 'utf8').toString('base64');
}

function transpile(source) {
  const result = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
    reportDiagnostics: true,
  });
  const errors = (result.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error);
  assert.deepEqual(errors, [], 'Sprint 28 erasure UI TypeScript must parse and transpile');
  return result.outputText;
}

const reactModuleUrl = dataUrl(`
  import React from ${JSON.stringify(pathToFileURL(require.resolve('react')).href)};
  export const useEffect = React.useEffect;
  export const useId = React.useId;
  export const useMemo = React.useMemo;
  export const useRef = React.useRef;
  export const useState = React.useState;
`);
const jsxRuntimeModuleUrl = dataUrl(`
  import runtime from ${JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href)};
  export const jsx = runtime.jsx;
  export const jsxs = runtime.jsxs;
  export const Fragment = runtime.Fragment;
`);
const apiModuleUrl = dataUrl(`
  export async function api() { throw new Error('Static render must not call the API.'); }
`);
const i18nModuleUrl = dataUrl('export function useT() { return message => message; }');
const preferencesModuleUrl = dataUrl('export function usePreferences() { return {preferences: {language: "en"}}; }');
const sessionModuleUrl = dataUrl(`
  export function useSession() {
    return {actor: {id: 'account-sentinel'}, token: 'test-token', authLoading: false, version: 1};
  }
`);

async function importErasureRequest(source) {
  let output = transpile(source);
  for (const [specifier, url] of [
    ['react/jsx-runtime', jsxRuntimeModuleUrl],
    ['react', reactModuleUrl],
    ['@/lib/api', apiModuleUrl],
    ['@/lib/i18n', i18nModuleUrl],
    ['@/lib/preferences', preferencesModuleUrl],
    ['@/lib/session', sessionModuleUrl],
  ]) {
    output = output.replace(new RegExp(`from (["'])${specifier}\\1`, 'g'), `from ${JSON.stringify(url)}`);
  }
  return import(dataUrl(output));
}

test('settings erasure section explains review, timing, blockers, and request-only behavior accessibly', async () => {
  const source = await read('features/privacy/ErasureRequest.tsx');
  const {ErasureRequest} = await importErasureRequest(source);
  const html = renderToStaticMarkup(React.createElement(ErasureRequest));

  assert.match(html, /Account erasure/);
  assert.match(html, /30 calendar days/);
  assert.match(html, /does not delete the account immediately/);
  assert.match(html, /ownership or appoint a platform administrator automatically/);
  assert.match(html, /do not ask for or collect your email address/);
  assert.match(html, /role="status"/);
  assert.doesNotMatch(source, /<input\b[^>]*(?:type=["']email|name=["']email)/i);
  assert.doesNotMatch(source, /method:\s*["']DELETE["']/i);
});

test('receipt reads and confirmed requests use only the signed-in account endpoint with no POST body', async () => {
  const source = await read('features/privacy/ErasureRequest.tsx');
  assert.match(source, /api<ErasureReceipt \| null>\('\/me\/erasure-request', \{token, signal: controller\.signal\}\)/);
  assert.match(source, /api<ErasureReceipt>\('\/me\/erasure-request', \{token, method: 'POST'\}\)/);
  assert.match(source, /current\.phase !== 'ready'.*current\.receipt.*!confirming/);
  assert.match(source, /aria-expanded=\{confirming\}/);
  assert.match(source, /t\('Confirm erasure request'\)/);
  assert.equal([...source.matchAll(/api<ErasureReceipt/g)].length, 2, 'the component has one read and one explicit request call');
  assert.doesNotMatch(source, /setTimeout|setInterval|method:\s*["']DELETE["']/i);
});

test('receipt data and feedback are scoped to the current account without browser persistence', async () => {
  const source = await read('features/privacy/ErasureRequest.tsx');
  for (const field of ['id', 'requested_at', 'due_at', 'completed_at', 'status', 'blocker_code', 'counts']) {
    assert.match(source, new RegExp(`receipt\\.${field}`));
  }
  assert.match(source, /const accountContext = useMemo\(\(\) => \(\{actorId, sessionVersion\}\), \[actorId, sessionVersion\]\)/);
  assert.match(source, /resource\?\.context === resourceContext/);
  assert.match(source, /return \(\) => controller\.abort\(\)/);
  assert.match(source, /previous\?\.context === resourceContext/);
  assert.match(source, /The request result could not be confirmed/);
  assert.match(source, /Retry status check/);
  assert.match(source, /Refresh request status/);
  assert.doesNotMatch(source, /localStorage|sessionStorage|navigator\.sendBeacon/i);
});

test('ownership and last-platform-admin blockers have distinct user guidance', async () => {
  const source = await read('features/privacy/ErasureRequest.tsx');
  assert.match(source, /code === 'owner_transfer_required'/);
  assert.match(source, /code === 'platform_admin_replacement_required'/);
  assert.match(source, /Transfer each organization you own to another eligible owner/);
  assert.match(source, /An operator must appoint another platform administrator/);
  assert.match(source, /No organization ownership or platform administrator role will be changed automatically/);
});

test('every erasure interface message has Filipino copy and the component stays in the Settings layout', async () => {
  const source = await read('features/privacy/ErasureRequest.tsx');
  const settings = await read('app/settings/page.tsx');
  const translations = transpile(await read('lib/auth-messages.ts'), ts.JsxEmit.Preserve);
  const {authMessages} = await import(dataUrl(translations));
  const uiCalls = [...source.matchAll(/\bt\(([^)]*)\)/gs)];
  const nonMessageValues = new Set(['load', 'submit', 'pending', 'blocked', 'processing', 'completed']);
  const messages = new Set(uiCalls.flatMap(([, body]) =>
    [...body.matchAll(/'([^']*)'/g)].map(([, value]) => value).filter(value => !nonMessageValues.has(value))));

  assert.ok(messages.size > 20, 'translation check must cover the full erasure interface');
  for (const message of messages) {
    assert.ok(Object.hasOwn(authMessages, message), `Missing Filipino translation for: ${message}`);
    assert.notEqual(authMessages[message], message, `Translation must not fall back to English: ${message}`);
  }
  assert.match(settings, /<DiscoveryPreferences \/>[\s\S]*<ErasureRequest \/>/);
});
