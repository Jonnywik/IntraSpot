import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const frontendRequire = createRequire(new URL('../Code/Frontend/package.json', import.meta.url));
const React = frontendRequire('react');
const { renderToStaticMarkup } = frontendRequire('react-dom/server');
const ts = frontendRequire('typescript');

function read(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8');
}

function dataUrl(source) {
  return 'data:text/javascript;base64,' + Buffer.from(source, 'utf8').toString('base64');
}

function transpile(source, relativePath, jsx = ts.JsxEmit.Preserve) {
  const result = ts.transpileModule(source, {
    compilerOptions: {
      jsx,
      jsxFactory: 'React.createElement',
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
    reportDiagnostics: true,
  });
  const errors = (result.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error);
  assert.deepEqual(errors, [], relativePath + ' must parse and transpile');
  return result.outputText;
}

const sessionUrl = dataUrl('export function useSession() { return globalThis.__sprint24Session; }');
const i18nUrl = dataUrl("export function useT() { return message => message; }");
const authConfigUrl = dataUrl('export function getRealAuthConfig() { return null; }');
const stylesUrl = dataUrl('export default { controls: "controls", sessionStatus: "session-status", details: "details", explanation: "explanation" };');
const reactUrl = pathToFileURL(frontendRequire.resolve('react')).href;
let componentSource = transpile(
  read('../Code/Frontend/features/identity/GoogleSignIn.tsx'),
  'GoogleSignIn.tsx',
  ts.JsxEmit.React,
).replace(
  "import { useState, useSyncExternalStore } from 'react';",
  `import React from '${reactUrl}';\nconst { useState, useSyncExternalStore } = React;`,
);
for (const [specifier, url] of [
  ["'@/lib/session'", sessionUrl],
  ["'@/lib/i18n'", i18nUrl],
  ["'@/lib/supabase-auth'", authConfigUrl],
  ["'./google-sign-in.module.css'", stylesUrl],
]) {
  componentSource = componentSource.replaceAll(`from ${specifier}`, `from '${url}'`);
}
const { GoogleSignIn } = await import(dataUrl(componentSource));

function renderSession(session) {
  globalThis.__sprint24Session = session;
  try {
    return renderToStaticMarkup(React.createElement(GoogleSignIn));
  } finally {
    delete globalThis.__sprint24Session;
  }
}

test('renders pending and failed local verification without claiming a verified session', () => {
  const pending = renderSession({
    actor: null,
    token: 'synthetic-access-token',
    authLoading: true,
    error: null,
    signInWithGoogle() {},
    signOut() {},
    refreshActor() {},
  });
  assert.match(pending, /Verifying account with the local IntraSpot API…/);
  assert.doesNotMatch(pending, /IntraSpot session verified\.|PLM email eligibility confirmed\./);
  assert.match(pending, /Sign out/);

  const staleActorWhileLoading = renderSession({
    actor: { id: 'synthetic-user', eligible: true, profile_complete: true },
    token: 'synthetic-access-token',
    authLoading: true,
    error: null,
    signInWithGoogle() {},
    signOut() {},
    refreshActor() {},
  });
  assert.match(staleActorWhileLoading, /Verifying account with the local IntraSpot API…/);
  assert.doesNotMatch(staleActorWhileLoading, /IntraSpot session verified\.|PLM email eligibility confirmed\./);

  const failed = renderSession({
    actor: null,
    token: 'synthetic-access-token',
    authLoading: false,
    error: {
      status: 503,
      code: 'real_auth_verification_failed',
      message: 'The local IntraSpot API could not verify this account. Check that it is running and retry.',
    },
    signInWithGoogle() {},
    signOut() {},
    refreshActor() {},
  });
  assert.match(failed, /Local account verification failed\./);
  assert.match(failed, /Retry local verification/);
  assert.match(failed, /Sign out/);
  assert.doesNotMatch(failed, /IntraSpot session verified\.|PLM email eligibility confirmed\./);
  assert.doesNotMatch(failed, /synthetic-access-token/);

  const staleActorWithError = renderSession({
    actor: { id: 'synthetic-user', eligible: true, profile_complete: true },
    token: 'synthetic-access-token',
    authLoading: false,
    error: {
      status: 503,
      code: 'real_auth_verification_failed',
      message: 'The local IntraSpot API could not verify this account. Check that it is running and retry.',
    },
    signInWithGoogle() {},
    signOut() {},
    refreshActor() {},
  });
  assert.match(staleActorWithError, /Local account verification failed\./);
  assert.doesNotMatch(staleActorWithError, /IntraSpot session verified\.|PLM email eligibility confirmed\./);

  const rejected = renderSession({
    actor: null,
    token: null,
    authLoading: false,
    error: { status: 401, code: 'real_auth_verification_failed', message: 'The signed-in account could not be verified. Sign in again.' },
    signInWithGoogle() {},
    signOut() {},
    refreshActor() {},
  });
  assert.match(rejected, /Local account verification failed\./);
  assert.match(rejected, /Continue with Google/);
  assert.doesNotMatch(rejected, /Sign out|Retry local verification|IntraSpot session verified\./);
});

test('renders server-derived PLM eligibility only after verification, without exposing email', () => {
  const eligible = renderSession({
    actor: { id: 'synthetic-user', email: 'private-sentinel@example.invalid', eligible: true, profile_complete: false },
    token: 'synthetic-access-token',
    authLoading: false,
    error: null,
    signInWithGoogle() {},
    signOut() {},
    refreshActor() {},
  });
  assert.match(eligible, /IntraSpot session verified\./);
  assert.match(eligible, /PLM email eligibility confirmed\./);
  assert.match(eligible, /Complete your profile before registering\./);
  assert.match(eligible, /Sign out/);
  assert.ok(eligible.indexOf('PLM email eligibility confirmed.') < eligible.indexOf('<details'));
  assert.doesNotMatch(eligible, /private-sentinel@example\.invalid|synthetic-access-token/);

  const ineligible = renderSession({
    actor: { id: 'synthetic-user', email: 'private-sentinel@example.invalid', eligible: false, profile_complete: true },
    token: 'synthetic-access-token',
    authLoading: false,
    error: null,
    signInWithGoogle() {},
    signOut() {},
    refreshActor() {},
  });
  assert.match(ineligible, /IntraSpot session verified\./);
  assert.match(ineligible, /Not eligible for PLM-only actions\./);
  assert.match(ineligible, /Your Google account can browse public events/);
  assert.ok(ineligible.indexOf('Not eligible for PLM-only actions.') < ineligible.indexOf('<details'));
  assert.doesNotMatch(ineligible, /PLM email eligibility confirmed\.|private-sentinel@example\.invalid/);
});

test('provides Filipino translations for each new auth-feedback state', async () => {
  const translated = transpile(read('../Code/Frontend/lib/auth-messages.ts'), 'auth-messages.ts');
  const { authMessages } = await import(dataUrl(translated));
  for (const message of [
    'IntraSpot session verified.',
    'Verifying account with the local IntraSpot API…',
    'Local account verification failed. Sign in again or retry local verification.',
    'PLM email eligibility confirmed.',
    'Not eligible for PLM-only actions.',
  ]) {
    assert.ok(authMessages[message], 'missing Filipino translation: ' + message);
  }
});
