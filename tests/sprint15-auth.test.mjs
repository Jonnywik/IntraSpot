import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from '../Code/Frontend/node_modules/typescript/lib/typescript.js';

function read(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8');
}

function transpile(relativePath) {
  const result = ts.transpileModule(read(relativePath), {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
    reportDiagnostics: true,
  });
  const errors = (result.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error);
  assert.deepEqual(errors, [], relativePath + ' must parse and transpile');
  return result.outputText;
}

async function importTypeScript(relativePath) {
  const output = transpile(relativePath);
  return import(dataUrl(output));
}

function dataUrl(source) {
  const encoded = Buffer.from(source, 'utf8').toString('base64');
  return 'data:text/javascript;base64,' + encoded;
}

async function importAuthCallback() {
  const storageUrl = dataUrl(transpile('../Code/Frontend/lib/auth-storage.ts'));
  const output = transpile('../Code/Frontend/lib/auth-callback.ts')
    .replace("from './auth-storage'", `from '${storageUrl}'`);
  return import(dataUrl(output));
}

function fakeSessionStorage() {
  const values = new Map();
  return {
    values,
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

test('real auth config is limited to the explicit local profile and public project key', async () => {
  const { resolveRealAuthConfig } = await importTypeScript('../Code/Frontend/lib/auth-storage.ts');
  const environment = {
    authMode: 'supabase',
    localDemo: 'false',
    apiUrl: 'http://127.0.0.1:8011',
    supabaseUrl: 'https://intraspotdev123.supabase.co',
    supabasePublishableKey: 'sb_publishable_public-test-key',
  };
  const location = {
    protocol: 'http:',
    hostname: '127.0.0.1',
    port: '3001',
    origin: 'http://127.0.0.1:3001',
  };

  const config = resolveRealAuthConfig(environment, location);
  assert.equal(config?.projectRef, 'intraspotdev123');
  assert.equal(config?.callbackUrl, 'http://127.0.0.1:3001/auth/callback');
  assert.equal(config?.apiUrl, 'http://127.0.0.1:8011');

  assert.equal(resolveRealAuthConfig({ ...environment, authMode: 'fixture' }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, localDemo: 'true' }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, apiUrl: 'http://127.0.0.1:8001' }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, supabaseUrl: 'http://intraspotdev123.supabase.co' }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, supabaseUrl: 'https://example.com' }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, supabasePublishableKey: 'sb_secret_not-public' }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, supabasePublishableKey: 'eyJhbGciOiJIUzI1NiJ9' }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, supabaseUrl: 'https://short.supabase.co' }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, supabasePublishableKey: 'sb_publishable_123456789' }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, supabaseUrl: `https://${'a'.repeat(65)}.supabase.co` }, location), null);
  assert.equal(resolveRealAuthConfig({ ...environment, supabasePublishableKey: `sb_publishable_${'a'.repeat(257)}` }, location), null);
  assert.equal(resolveRealAuthConfig(environment, { ...location, port: '3000' }), null);
  assert.equal(resolveRealAuthConfig(environment, { ...location, hostname: 'example.com' }), null);
});

test('SDK session values stay in the per-instance memory map while verifier suffixes share one project slot', async () => {
  const { createAuthStorage } = await importTypeScript('../Code/Frontend/lib/auth-storage.ts');
  const sessionStorage = fakeSessionStorage();
  let now = 1000;
  const first = createAuthStorage('intraspotdev123', { sessionStorage, now: () => now });

  const session = JSON.stringify({ access_token: 'memory-only-access', refresh_token: 'memory-only-refresh' });
  await first.adapter.setItem('random-client-one', session);
  assert.equal(await first.adapter.getItem('random-client-one'), session);
  assert.equal(sessionStorage.values.size, 0);

  await first.adapter.setItem('random-client-one-flow-0123456789abcdef-code-verifier', JSON.stringify('pkce-verifier'));
  await first.adapter.setItem('random-client-one-flows-code-verifier', JSON.stringify(['0123456789abcdef']));
  await first.adapter.setItem('random-client-one-code-verifier', JSON.stringify('pkce-verifier'));
  assert.equal(sessionStorage.values.size, 1);
  const storedSlot = [...sessionStorage.values.values()][0];
  assert.equal(storedSlot.includes('memory-only-access'), false);
  assert.equal(storedSlot.includes('memory-only-refresh'), false);

  const afterRedirect = createAuthStorage('intraspotdev123', { sessionStorage, now: () => now });
  assert.equal(await afterRedirect.adapter.getItem('random-client-two'), null);
  assert.equal(
    await afterRedirect.adapter.getItem('random-client-two-flow-0123456789abcdef-code-verifier'),
    JSON.stringify('pkce-verifier'),
  );
  assert.equal(
    await afterRedirect.adapter.getItem('random-client-two-flows-code-verifier'),
    JSON.stringify(['0123456789abcdef']),
  );
  assert.equal(await afterRedirect.adapter.getItem('random-client-two-code-verifier'), JSON.stringify('pkce-verifier'));

  now += 10 * 60 * 1000 + 1;
  assert.equal(await afterRedirect.adapter.getItem('random-client-two-code-verifier'), null);
  assert.equal(sessionStorage.values.size, 0);
});

test('SDK PKCE cleanup clears verifier state and memory cleanup removes in-tab sessions', async () => {
  const { createAuthStorage } = await importTypeScript('../Code/Frontend/lib/auth-storage.ts');
  const sessionStorage = fakeSessionStorage();
  const storage = createAuthStorage('intraspotdev123', { sessionStorage });
  await storage.adapter.setItem('random-client-code-verifier', JSON.stringify('one-use'));
  await storage.adapter.setItem('random-client', JSON.stringify({ access_token: 'never-persist' }));
  storage.clearVerifier();
  storage.clearMemory();
  assert.equal(sessionStorage.values.size, 0);
  assert.equal(await storage.adapter.getItem('random-client'), null);
});

test('logout fences late SDK session events and verification tickets bind to the latest token', async () => {
  const { createRealSessionGuard } = await importTypeScript('../Code/Frontend/lib/real-session-guard.ts');
  const guard = createRealSessionGuard();
  const first = { access_token: 'access-a', user: { id: 'google-user' } };
  const refreshed = { access_token: 'access-b', user: { id: 'google-user' } };

  assert.equal(guard.receive('SIGNED_IN', first).accepted, true);
  const inFlight = guard.captureVerification();
  assert.equal(inFlight?.accessToken, 'access-a');
  assert.equal(guard.receive('TOKEN_REFRESHED', refreshed).accepted, true);
  assert.equal(guard.isCurrent(inFlight), false, 'an older /me response cannot win after refresh');

  const staleRenderCallback = () => guard.captureVerification();
  const newest = { access_token: 'access-c', user: { id: 'google-user' } };
  guard.receive('TOKEN_REFRESHED', newest);
  const retryTicket = staleRenderCallback();
  assert.equal(retryTicket?.accessToken, 'access-c', 'refreshActor reads the guard live rather than a render closure');

  const logout = guard.beginLogout();
  assert.equal(logout.hadAccount, true);
  const generationAfterLogout = guard.generation;
  assert.equal(guard.receive('TOKEN_REFRESHED', refreshed).accepted, false);
  assert.equal(guard.receive('SIGNED_IN', refreshed).accepted, false);
  assert.equal(guard.generation, generationAfterLogout, 'ignored late events cannot advance or restore the session');
  assert.equal(guard.userId, null);
  assert.equal(guard.accessToken, null);
  assert.equal(guard.isCurrent(retryTicket), false);
  assert.equal(guard.captureVerification(), null);

  const freshCallbackDocument = createRealSessionGuard();
  assert.equal(freshCallbackDocument.receive('SIGNED_IN', first).accepted, true);

  const expired = createRealSessionGuard();
  expired.receive('SIGNED_IN', first);
  assert.equal(expired.receive('TOKEN_REFRESHED', null).accepted, true);
  assert.equal(expired.receive('SIGNED_IN', first).accepted, false, 'a lost session cannot be restored by a late event');
});

test('callback URL is scrubbed before configuration, SDK construction, or code exchange', async () => {
  const { exchangeAuthCallback, getAuthCallbackExchange, scrubAuthCallbackUrl } = await importAuthCallback();
  const order = [];
  let replacedWith = null;
  const capture = scrubAuthCallbackUrl(
    'http://127.0.0.1:3001/auth/callback?code=one-use-code&sb_flow_id=0123456789abcdef#ignored',
    {
      state: { retained: true },
      replaceState(state, _unused, url) {
        assert.deepEqual(state, { retained: true });
        order.push('scrub');
        replacedWith = url;
      },
    },
  );
  assert.equal(replacedWith, '/auth/callback');
  assert.equal(capture.code, 'one-use-code');
  assert.equal(capture.flowId, '0123456789abcdef');

  const dependencies = {
    isConfigured() {
      order.push('config');
      return true;
    },
    getClient() {
      order.push('client');
      return {
        async exchangeCodeForSession(code, options) {
          order.push('exchange');
          assert.equal(code, 'one-use-code');
          assert.deepEqual(options, { flowId: '0123456789abcdef' });
          return { error: null };
        },
      };
    },
    clearVerifier() {
      order.push('clear');
    },
  };
  const exchangeCell = { current: null };
  const firstAttempt = getAuthCallbackExchange(exchangeCell, capture, dependencies);
  const strictModeAttempt = getAuthCallbackExchange(exchangeCell, capture, dependencies);
  assert.equal(firstAttempt, strictModeAttempt, 'StrictMode remounts reuse one in-flight callback exchange');
  const result = await firstAttempt;
  assert.equal(result, 'verifying');
  assert.deepEqual(order, ['scrub', 'config', 'client', 'exchange', 'clear']);

  const providerErrorCapture = scrubAuthCallbackUrl(
    'http://127.0.0.1:3001/auth/callback?error=access_denied&error_description=private-provider-text',
    { state: null, replaceState(_state, _unused, url) { replacedWith = url; } },
  );
  assert.equal(replacedWith, '/auth/callback');
  assert.equal(providerErrorCapture.hasProviderError, true);
  assert.equal(Object.hasOwn(providerErrorCapture, 'error_description'), false);
  let contactedSdk = false;
  assert.equal(await exchangeAuthCallback(providerErrorCapture, {
    isConfigured() { contactedSdk = true; return true; },
    getClient() { contactedSdk = true; throw new Error('must not be called'); },
    clearVerifier() {},
  }), 'failed');
  assert.equal(contactedSdk, false);
});

test('callback diagnostics use only predefined reasons and never expose private provider text', async () => {
  const { classifyAuthExchangeFailure, exchangeAuthCallback, scrubAuthCallbackUrl } = await importAuthCallback();
  const privateText = 'private-code-token-email-secret-sentinel';
  for (const [error, reason] of [
    [{ name: 'AuthPKCECodeVerifierMissingError' }, 'verifier_missing'],
    [{ code: 'bad_code_verifier' }, 'verifier_mismatch'],
    [{ code: 'flow_state_expired' }, 'exchange_expired'],
    [{ code: 'flow_state_not_found' }, 'exchange_expired'],
    [{ name: 'AuthRetryableFetchError' }, 'exchange_network_failed'],
    [{ name: 'TypeError' }, 'exchange_network_failed'],
    [{ code: privateText, name: privateText }, 'exchange_rejected'],
  ]) {
    assert.equal(classifyAuthExchangeFailure({ ...error, message: privateText }), reason);
  }
  for (const suffix of [
    '?error=access_denied&error_description=' + privateText,
    '#error=server_error&error_description=' + privateText,
  ]) {
    const capture = scrubAuthCallbackUrl('http://127.0.0.1:3001/auth/callback' + suffix,
      { state: null, replaceState(_state, _unused, url) { assert.equal(url, '/auth/callback'); } });
    const reasons = [];
    let cleared = 0;
    assert.equal(await exchangeAuthCallback(capture, {
      isConfigured: () => true,
      getClient() { throw new Error('provider errors must not contact SDK'); },
      clearVerifier() { cleared++; },
      reportFailure(reason) { reasons.push(reason); },
    }), 'failed');
    assert.deepEqual(reasons, ['provider_rejected']);
    assert.equal(cleared, 1);
    assert.equal(JSON.stringify(capture).includes(privateText), false);
  }
  for (const thrown of [false, true]) {
    const reasons = [];
    let cleared = 0;
    assert.equal(await exchangeAuthCallback({ code: privateText, flowId: null, hasProviderError: false }, {
      isConfigured: () => true,
      getClient: () => ({ async exchangeCodeForSession() {
        const error = { name: 'AuthPKCECodeVerifierMissingError', message: privateText };
        if (thrown) throw error;
        return { error };
      } }),
      clearVerifier() { cleared++; },
      reportFailure(reason) { reasons.push(reason); },
    }), 'failed');
    assert.deepEqual(reasons, ['verifier_missing']);
    assert.equal(cleared, 1);
  }
  for (const [capture, configured, status, reason] of [
    [{ code: null, flowId: null, hasProviderError: false }, true, 'failed', 'callback_code_missing'],
    [{ code: privateText, flowId: 'invalid', hasProviderError: false }, true, 'failed', 'callback_invalid'],
    [{ code: privateText, flowId: null, hasProviderError: false }, false, 'unavailable', 'configuration_unavailable'],
  ]) {
    const reasons = [];
    assert.equal(await exchangeAuthCallback(capture, {
      isConfigured: () => configured,
      getClient() { throw new Error('must not contact SDK'); },
      clearVerifier() {},
      reportFailure(reason) { reasons.push(reason); },
    }), status);
    assert.deepEqual(reasons, [reason]);
  }
});

test('the pinned SDK requires persistSession for custom storage and scopes BroadcastChannel by storageKey', () => {
  const sdkPackage = JSON.parse(read('../Code/Frontend/node_modules/@supabase/auth-js/package.json'));
  const sdkSource = read('../Code/Frontend/node_modules/@supabase/auth-js/src/GoTrueClient.ts');
  const clientSource = read('../Code/Frontend/lib/supabase-auth.ts');

  assert.equal(sdkPackage.version, '2.118.0');
  assert.match(
    sdkSource,
    /if\s*\(this\.persistSession\)\s*\{\s*if\s*\(settings\.storage\)\s*\{\s*this\.storage\s*=\s*settings\.storage/s,
  );
  assert.match(
    sdkSource,
    /globalThis\.BroadcastChannel\s*&&\s*this\.persistSession\s*&&\s*this\.storageKey/,
  );
  assert.match(clientSource, /storageKey:\s*createClientStorageKey\(\)/);
  assert.match(clientSource, /storage:\s*storage\.adapter/);
  assert.match(clientSource, /persistSession:\s*true/);
});

test('every literal auth translation in the new UI is exported by authMessages', async () => {
  const { authMessages } = await importTypeScript('../Code/Frontend/lib/auth-messages.ts');
  const ui = [
    read('../Code/Frontend/features/identity/GoogleSignIn.tsx'),
    read('../Code/Frontend/app/auth/callback/page.tsx'),
  ].join('\n');
  const literals = [...ui.matchAll(/\bt\('([^']+)'\)/g)].map(match => match[1]);
  const developmentLabel = ['ISOLATED', 'DEVELOPMENT', String.fromCodePoint(0xb7), 'GOOGLE', 'SIGN-IN'].join(' ');
  assert.ok(read('../Code/Frontend/app/site-header.tsx').includes(developmentLabel));
  assert.ok(Object.hasOwn(authMessages, developmentLabel));
  assert.ok(literals.includes('Google sign-in'));
  for (const literal of literals) {
    assert.ok(Object.hasOwn(authMessages, literal), 'missing auth translation: ' + literal);
  }
});

test('all new frontend auth files pass isolated TypeScript syntax transpilation', () => {
  for (const file of [
    '../Code/Frontend/lib/auth-storage.ts',
    '../Code/Frontend/lib/auth-callback.ts',
    '../Code/Frontend/lib/real-session-guard.ts',
    '../Code/Frontend/lib/supabase-auth.ts',
    '../Code/Frontend/lib/real-session.tsx',
    '../Code/Frontend/lib/auth-messages.ts',
    '../Code/Frontend/features/identity/GoogleSignIn.tsx',
    '../Code/Frontend/app/auth/callback/page.tsx',
  ]) {
    transpile(file);
  }
});
