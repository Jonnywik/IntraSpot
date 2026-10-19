import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {readFile, mkdtemp, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {api, localDemoEnabled} from '../Code/Frontend/lib/api.ts';
import {createStaticServer} from '../Code/Frontend/scripts/serve-static.mjs';

const names = ['NEXT_PUBLIC_AUTH_MODE', 'NEXT_PUBLIC_LOCAL_DEMO', 'NEXT_PUBLIC_API_URL'];
const original = Object.fromEntries(names.map(name => [name, process.env[name]]));
const originalFetch = globalThis.fetch;
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
afterEach(() => {
  for (const name of names) {
    if (original[name] === undefined) delete process.env[name];
    else process.env[name] = original[name];
  }
  globalThis.fetch = originalFetch;
  if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow);
  else Reflect.deleteProperty(globalThis, 'window');
});

test('real auth cannot use fictional selection or send credentials to the demo API', async () => {
  process.env.NEXT_PUBLIC_AUTH_MODE = 'supabase';
  process.env.NEXT_PUBLIC_LOCAL_DEMO = 'true';
  Object.defineProperty(globalThis, 'window', {configurable: true,
    value: {location: {hostname: '127.0.0.1'}}});
  assert.equal(localDemoEnabled(), false);
  let calls = 0;
  globalThis.fetch = async () => {calls++; return new Response('{}');};
  for (const address of ['http://127.0.0.1:8001', 'http://localhost:8011', 'http://127.0.0.1:8011/other']) {
    process.env.NEXT_PUBLIC_API_URL = address;
    await assert.rejects(api('/me', {token: 'non-secret-test-sentinel'}),
      error => error.code === 'isolated_api_required');
  }
  assert.equal(calls, 0);
  process.env.NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8011';
  await api('/me', {token: 'non-secret-test-sentinel'});
  assert.equal(calls, 1);
});

test('unknown auth profiles never enable the local account catalog', () => {
  process.env.NEXT_PUBLIC_AUTH_MODE = 'typo';
  process.env.NEXT_PUBLIC_LOCAL_DEMO = 'true';
  Object.defineProperty(globalThis, 'window', {configurable: true,
    value: {location: {hostname: 'localhost'}}});
  assert.equal(localDemoEnabled(), false);
});

test('real development discovery does not ask for a fictional sample account', async () => {
  const source = await readFile(new URL('../Code/Frontend/components/discovery-layout.tsx', import.meta.url), 'utf8');
  assert.match(source, /realDevelopment = process\.env\.NEXT_PUBLIC_AUTH_MODE === 'supabase'/);
  assert.match(source, /realDevelopment \? t\('Sign in with an eligible PLM Google account\.'\) : t\('Choose an eligible sample PLM account\.'\)/);
});

test('static callback responses prevent referrer leakage and cache persistence', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'intraspot-sprint15-'));
  const server = createStaticServer(directory);
  try {
    await writeFile(join(directory, 'index.html'), '<p>Development callback fixture</p>');
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const response = await originalFetch(`http://127.0.0.1:${server.address().port}/?code=non-secret-fixture`);
    assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
    assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
    assert.equal(response.headers.get('cache-control'), 'no-store');
  } finally {
    await new Promise(resolve => server.close(resolve));
    // Exact owned temporary test directory, never a workspace or user directory.
    await rm(directory, {recursive: true, force: true});
  }
});

test('real exports use a separate output directory and never replace the fictional export', async () => {
  const config = await readFile(new URL('../Code/Frontend/next.config.ts', import.meta.url), 'utf8');
  const build = await readFile(new URL('../Code/Frontend/scripts/build-real.mjs', import.meta.url), 'utf8');
  const serve = await readFile(new URL('../Code/Frontend/scripts/serve-real.mjs', import.meta.url), 'utf8');
  assert.match(config, /INTRASPOT_FRONTEND_PROFILE.*real/);
  assert.match(config, /distDir: 'out-real'/);
  assert.match(build, /check-public-assets\.mjs.*out-real/);
  assert.match(serve, /listen\(3001, '127\.0\.0\.1'/);
});

test('export guard rejects Supabase and Google secrets but permits public publishable keys', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'intraspot-sprint15-assets-'));
  const script = fileURLToPath(new URL('../Code/Frontend/scripts/check-public-assets.mjs', import.meta.url));
  try {
    for (const value of ['sb_secret_only_a_fictional_sentinel', 'GOCSPX-only_a_fictional_sentinel']) {
      await writeFile(join(directory, 'bundle.js'), JSON.stringify(value));
      const result = spawnSync(process.execPath, [script, directory], {encoding: 'utf8'});
      assert.notEqual(result.status, 0);
      assert.ok(!result.stderr.includes(value), 'guard must not echo the rejected value');
    }
    await writeFile(join(directory, 'bundle.js'), '"sb_publishable_fictional_public_configuration"');
    assert.equal(spawnSync(process.execPath, [script, directory]).status, 0);
  } finally {
    await rm(directory, {recursive: true, force: true});
  }
});
