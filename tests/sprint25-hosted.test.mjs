import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {mkdtemp, readFile, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {api, localDemoEnabled} from '../Code/Frontend/lib/api.ts';
import {getFrontendDeployment, resolveHostedConfig, resolveRealAuthConfig} from '../Code/Frontend/lib/auth-storage.ts';
import {assertNoHostedCredentialArtifacts, validateHostedBuildEnvironment} from '../Code/Frontend/scripts/build-hosted.mjs';
import {mediaApiPath} from '../Code/Frontend/features/media/media-url.ts';

const environmentNames = [
  'NEXT_PUBLIC_DEPLOYMENT',
  'NEXT_PUBLIC_AUTH_MODE',
  'NEXT_PUBLIC_LOCAL_DEMO',
  'NEXT_PUBLIC_API_URL',
  'NEXT_PUBLIC_FRONTEND_ORIGIN',
  'NEXT_PUBLIC_SUPABASE_URL',
  'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY',
];
const originalEnvironment = Object.fromEntries(environmentNames.map(name => [name, process.env[name]]));
const originalFetch = globalThis.fetch;
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');

afterEach(() => {
  for (const name of environmentNames) {
    if (originalEnvironment[name] === undefined) delete process.env[name];
    else process.env[name] = originalEnvironment[name];
  }
  globalThis.fetch = originalFetch;
  if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow);
  else Reflect.deleteProperty(globalThis, 'window');
});

const hostedEnvironment = {
  deployment: 'hosted',
  authMode: 'supabase',
  localDemo: 'false',
  apiUrl: 'https://api.intraspot.example.com',
  frontendOrigin: 'https://intraspot.example.com',
  supabaseUrl: 'https://sprint25-test.supabase.co',
  supabasePublishableKey: 'sb_publishable_test-only-public-config',
};

function hostedProcessEnvironment() {
  process.env.NEXT_PUBLIC_DEPLOYMENT = hostedEnvironment.deployment;
  process.env.NEXT_PUBLIC_AUTH_MODE = hostedEnvironment.authMode;
  process.env.NEXT_PUBLIC_LOCAL_DEMO = hostedEnvironment.localDemo;
  process.env.NEXT_PUBLIC_API_URL = hostedEnvironment.apiUrl;
  process.env.NEXT_PUBLIC_FRONTEND_ORIGIN = hostedEnvironment.frontendOrigin;
  process.env.NEXT_PUBLIC_SUPABASE_URL = hostedEnvironment.supabaseUrl;
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = hostedEnvironment.supabasePublishableKey;
}

test('deployment selection defaults to local and hosted URLs must be exact HTTPS roots', () => {
  assert.equal(getFrontendDeployment(undefined), 'local');
  assert.equal(getFrontendDeployment('hosted'), 'hosted');
  assert.equal(getFrontendDeployment('typo'), null);

  const config = resolveHostedConfig(hostedEnvironment, 'https://intraspot.example.com');
  assert.deepEqual(config, {
    apiUrl: 'https://api.intraspot.example.com',
    frontendOrigin: 'https://intraspot.example.com',
    callbackUrl: 'https://intraspot.example.com/auth/callback',
    projectRef: 'sprint25-test',
    supabaseUrl: 'https://sprint25-test.supabase.co',
    supabasePublishableKey: hostedEnvironment.supabasePublishableKey,
  });

  for (const invalid of [
    {apiUrl: 'https://*.example.com'},
    {apiUrl: 'http://api.intraspot.example.com'},
    {apiUrl: 'https://api.intraspot.example.com/v1'},
    {apiUrl: 'https://user@api.intraspot.example.com'},
    {apiUrl: 'https://api.intraspot.example.com?next=/v1'},
    {apiUrl: 'https://api.intraspot.example.com:443'},
    {apiUrl: 'https://localhost'},
    {apiUrl: 'https://intraspot.local'},
    {apiUrl: 'https://api.intraspot.localhost'},
    {apiUrl: 'https://api.intraspot.test'},
    {apiUrl: 'https://127.0.0.1'},
    {apiUrl: 'https://8.8.8.8'},
    {apiUrl: 'https://[::1]'},
    {apiUrl: 'https://[2606:4700:4700::1111]'},
    {frontendOrigin: 'https://intraspot.example.com/path'},
    {frontendOrigin: 'https://intraspot.local'},
    {authMode: 'fixture'},
    {localDemo: 'true'},
    {supabaseUrl: 'https://sprint25-test.supabase.co/auth/v1'},
    {supabasePublishableKey: 'sb_secret_test-only-sentinel'},
  ]) {
    assert.equal(resolveHostedConfig({...hostedEnvironment, ...invalid}), null);
  }
  assert.equal(resolveHostedConfig(hostedEnvironment, 'https://other.example.com'), null);
});

test('hosted OAuth uses the configured frontend callback and rejects an origin or protocol mismatch', () => {
  const authEnvironment = {...hostedEnvironment};
  const location = {
    protocol: 'https:',
    hostname: 'intraspot.example.com',
    port: '',
    origin: hostedEnvironment.frontendOrigin,
  };
  const config = resolveRealAuthConfig(authEnvironment, location);
  assert.equal(config?.apiUrl, hostedEnvironment.apiUrl);
  assert.equal(config?.callbackUrl, 'https://intraspot.example.com/auth/callback');
  assert.equal(resolveRealAuthConfig(authEnvironment, {...location, origin: 'https://other.example.com'}), null);
  assert.equal(resolveRealAuthConfig(authEnvironment, {...location, protocol: 'http:'}), null);
  assert.equal(resolveRealAuthConfig({...authEnvironment, localDemo: 'true'}, location), null);
});

test('hosted API calls use the exact API origin and refuse wrong frontend origins before fetch', async () => {
  hostedProcessEnvironment();
  Object.defineProperty(globalThis, 'window', {configurable: true, value: {
    location: {hostname: 'intraspot.example.com', origin: hostedEnvironment.frontendOrigin},
  }});
  let request;
  let calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++;
    request = {url: String(url), options};
    return new Response('{}');
  };

  const id = '550e8400-e29b-41d4-a716-446655440000';
  const path = mediaApiPath(`/api/v1/media/${id}`);
  assert.equal(path, `/media/${id}`);
  await api(path, {token: 'test-token-sentinel'});
  assert.equal(request.url, `https://api.intraspot.example.com/api/v1/media/${id}`);
  assert.equal(request.options.credentials, 'omit');
  assert.equal(request.options.headers.Authorization, 'Bearer test-token-sentinel');
  assert.equal(localDemoEnabled(), false);

  window.location.origin = 'https://other.example.com';
  await assert.rejects(api('/me'), error => error.code === 'hosted_config_invalid');
  window.location.origin = hostedEnvironment.frontendOrigin;
  for (const value of [
    'https://localhost',
    'https://api.intraspot.local',
    'https://api.intraspot.localhost',
    'https://127.0.0.1',
    'https://[2606:4700:4700::1111]',
  ]) {
    process.env.NEXT_PUBLIC_API_URL = value;
    await assert.rejects(api('/me'), error => error.code === 'hosted_config_invalid');
  }
  process.env.NEXT_PUBLIC_API_URL = hostedEnvironment.apiUrl;
  for (const value of ['https://intraspot.local', 'https://192.0.2.1']) {
    process.env.NEXT_PUBLIC_FRONTEND_ORIGIN = value;
    await assert.rejects(api('/me'), error => error.code === 'hosted_config_invalid');
  }
  assert.equal(calls, 1, 'invalid origins must fail before a network request');
});

test('hosted build requires explicit settings and blocks files Next would auto-load', () => {
  const processEnvironment = Object.fromEntries([
    ['NEXT_PUBLIC_DEPLOYMENT', hostedEnvironment.deployment],
    ['NEXT_PUBLIC_AUTH_MODE', hostedEnvironment.authMode],
    ['NEXT_PUBLIC_LOCAL_DEMO', hostedEnvironment.localDemo],
    ['NEXT_PUBLIC_API_URL', hostedEnvironment.apiUrl],
    ['NEXT_PUBLIC_FRONTEND_ORIGIN', hostedEnvironment.frontendOrigin],
    ['NEXT_PUBLIC_SUPABASE_URL', hostedEnvironment.supabaseUrl],
    ['NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY', hostedEnvironment.supabasePublishableKey],
  ]);
  assert.equal(validateHostedBuildEnvironment(processEnvironment, ['package.json']).callbackUrl,
    'https://intraspot.example.com/auth/callback');
  assert.throws(() => validateHostedBuildEnvironment(processEnvironment, ['.env.local']),
    /clean build directory/);

  const marker = 'private-test-config-sentinel';
  assert.throws(() => validateHostedBuildEnvironment({
    ...processEnvironment,
    NEXT_PUBLIC_API_URL: `https://api.intraspot.example/${marker}`,
  }, []), error => !error.message.includes(marker));
});

test('hosted export scan rejects credential-shaped artifacts without printing them', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'intraspot-sprint25-hosted-'));
  const sentinel = 'sb_secret_only_a_fictional_sentinel';
  try {
    await writeFile(join(directory, 'bundle.js'), JSON.stringify(sentinel));
    await assert.rejects(assertNoHostedCredentialArtifacts(directory), error => {
      assert.equal(error.message, 'Hosted export contains a credential artifact.');
      assert.equal(error.message.includes(sentinel), false);
      return true;
    });
    await writeFile(join(directory, 'bundle.js'), '"sb_publishable_test-only-public-config"');
    await assert.doesNotReject(assertNoHostedCredentialArtifacts(directory));
  } finally {
    await rm(directory, {recursive: true, force: true});
  }
});

test('hosted build output is isolated and new coverage is part of npm test', async () => {
  const frontend = new URL('../Code/Frontend/', import.meta.url);
  const config = await readFile(new URL('next.config.ts', frontend), 'utf8');
  const build = await readFile(new URL('scripts/build-hosted.mjs', frontend), 'utf8');
  const packageJson = JSON.parse(await readFile(new URL('package.json', frontend), 'utf8'));
  const shell = await readFile(new URL('components/application-shell.tsx', frontend), 'utf8');
  const media = await readFile(new URL('features/media/MediaImage.tsx', frontend), 'utf8');
  const ignore = await readFile(new URL('../../.gitignore', frontend), 'utf8');
  const eslint = await readFile(new URL('eslint.config.mjs', frontend), 'utf8');

  assert.match(config, /distDir:\s*'out-hosted'/);
  assert.match(config, /INTRASPOT_HOSTED_BUILD_GUARD/);
  assert.match(build, /assertNoHostedCredentialArtifacts\(resolve\('out-hosted'\)\)/);
  assert.equal(packageJson.scripts['build:hosted'], 'node scripts/build-hosted.mjs');
  assert.match(packageJson.scripts.test, /sprint25-hosted\.test\.mjs/);
  assert.match(ignore, /\*\*\/out-hosted\//);
  assert.match(eslint, /out-hosted\/\*\*/);
  assert.match(shell, /NEXT_PUBLIC_DEPLOYMENT === 'hosted'[\s\S]*Hosted configuration/);
  assert.match(media, /api<Blob>\(path,/);
  assert.doesNotMatch(media, /\bfetch\(/);
});
