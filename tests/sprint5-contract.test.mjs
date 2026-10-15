import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { api, ApiError, localDemoEnabled } from '../Code/Frontend/lib/api.ts';
import { formatDate, formatTime, fromUtcToManila, toUtcFromManila } from '../Code/Frontend/lib/date.ts';

const originalFetch = globalThis.fetch;
const originalApiUrl = process.env.NEXT_PUBLIC_API_URL;
const originalLocalDemo = process.env.NEXT_PUBLIC_LOCAL_DEMO;
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');

function restoreEnv(name, value) {
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  restoreEnv('NEXT_PUBLIC_API_URL', originalApiUrl);
  restoreEnv('NEXT_PUBLIC_LOCAL_DEMO', originalLocalDemo);
  if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow);
  else Reflect.deleteProperty(globalThis, 'window');
});

test('API sends bearer and retry keys only to the configured local API without ambient credentials', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8001';
  let sent;
  globalThis.fetch = async (input, init) => {
    sent = { url: new URL(String(input)), init };
    return new Response('{"id":"event-1"}', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await api('/events', {
    token: 'fictional-test-token',
    method: 'POST',
    body: { title: 'Test event' },
    idempotencyKey: 'attempt-1',
  });

  assert.deepEqual(result, { id: 'event-1' });
  assert.equal(sent.url.origin, 'http://localhost:8001');
  assert.equal(sent.url.pathname, '/api/v1/events');
  assert.equal(sent.url.search, '');
  assert.equal(sent.init.credentials, 'omit');
  assert.equal(sent.init.cache, 'no-store');
  assert.equal(sent.init.headers.Authorization, 'Bearer fictional-test-token');
  assert.equal(sent.init.headers['Idempotency-Key'], 'attempt-1');
  assert.equal(sent.init.body, JSON.stringify({ title: 'Test event' }));
});

test('API paths cannot escape the frozen /api/v1 prefix', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8001';
  let requests = 0;
  globalThis.fetch = async () => {
    requests++;
    return new Response('{}', { status: 200 });
  };

  for (const path of ['/../me', '/%2e%2e/me', '/%2E%2E/me', '//other-host/path']) {
    await assert.rejects(api(path), error =>
      error instanceof ApiError && error.code === 'invalid_api_path');
  }
  assert.equal(requests, 0);
});

test('non-loopback API configuration is rejected before a token can be sent', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'https://api.example.test';
  let requests = 0;
  globalThis.fetch = async () => {
    requests++;
    return new Response('{}', { status: 200 });
  };

  await assert.rejects(api('/me', { token: 'fictional-test-token' }), error => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.code, 'local_api_required');
    assert.equal(error.message.includes('fictional-test-token'), false);
    return true;
  });
  assert.equal(requests, 0);
});

test('fictional account access requires the explicit flag and a loopback page hostname', () => {
  process.env.NEXT_PUBLIC_LOCAL_DEMO = 'true';
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { location: { hostname: 'localhost' } },
  });
  assert.equal(localDemoEnabled(), true);

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { location: { hostname: 'intraspot.example' } },
  });
  assert.equal(localDemoEnabled(), false);

  process.env.NEXT_PUBLIC_LOCAL_DEMO = 'false';
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { location: { hostname: '127.0.0.1' } },
  });
  assert.equal(localDemoEnabled(), false);
});

test('Manila midnight wall time round-trips to the corresponding UTC instant', () => {
  const utc = toUtcFromManila('2026-10-13T00:00');
  assert.equal(utc, '2026-10-12T16:00:00.000Z');
  assert.equal(fromUtcToManila(utc), '2026-10-13T00:00');

  const beforeMidnight = '2026-10-12T15:59:00.000Z';
  assert.notEqual(formatDate(beforeMidnight), formatDate(utc));
  assert.match(formatDate(utc), /\b13\b/);
  assert.notEqual(formatTime(beforeMidnight), formatTime(utc));
});

test('Manila date-time input rejects impossible calendar days instead of normalizing them', () => {
  for (const value of ['2026-02-30T12:00', '2026-04-31T12:00', '2026-02-29T12:00']) {
    assert.throws(() => toUtcFromManila(value), /valid Manila date and time/, value);
  }
  assert.equal(toUtcFromManila('2024-02-29T12:00'), '2024-02-29T04:00:00.000Z');
});

test('private resource snapshots are token-keyed, hidden on key changes, and aborted on cleanup', async () => {
  const source = await readFile(new URL('../Code/Frontend/lib/use-api-resource.ts', import.meta.url), 'utf8');
  assert.match(source, /const key = .*token/);
  assert.match(source, /const current = state\.key === key/);
  assert.match(source, /data: current \? state\.data : null/);
  assert.match(source, /return \(\) => \{ controller\.abort\(\);/);
  assert.match(source, /window\.clearInterval\(timer\)/);
  assert.match(source, /document\.visibilityState === 'visible'/);
});

test('session version remounts page state only for account changes, not actor refreshes', async () => {
  const [session, shell] = await Promise.all([
    readFile(new URL('../Code/Frontend/lib/session.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../Code/Frontend/components/application-shell.tsx', import.meta.url), 'utf8'),
  ]);
  const refreshActor = session.match(/async function refreshActor\(\) \{([\s\S]*?)\n  \}/)?.[1];
  assert.ok(refreshActor, 'refreshActor implementation is present');
  assert.doesNotMatch(refreshActor, /version:\s*previous\.version\s*\+\s*1/);
  assert.match(shell, /<div key=\{version\}>\{children\}<\/div>/);
});

test('generated OpenAPI paths and named schema aliases still match the reviewed backend contract', async () => {
  const [specText, generated, aliases] = await Promise.all([
    readFile(new URL('../docs/backend/openapi.json', import.meta.url), 'utf8'),
    readFile(new URL('../Code/Frontend/lib/api.generated.ts', import.meta.url), 'utf8'),
    readFile(new URL('../Code/Frontend/lib/types.ts', import.meta.url), 'utf8'),
  ]);
  const spec = JSON.parse(specText);
  const generatedPaths = [...generated.matchAll(/^    "([^"]+)": \{$/gm)].map(match => match[1]);
  assert.deepEqual(generatedPaths.sort(), Object.keys(spec.paths).sort());

  const schemaAliases = [...aliases.matchAll(/components\['schemas'\]\['([^']+)'\]/g)].map(match => match[1]);
  assert.ok(schemaAliases.length > 0, 'named API aliases are present');
  for (const schema of schemaAliases) {
    assert.ok(spec.components.schemas[schema], `OpenAPI schema ${schema} exists`);
  }
});
