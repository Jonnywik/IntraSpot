import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {api, ApiError} from '../Code/Frontend/lib/api.ts';

const environmentNames = [
  'NEXT_PUBLIC_DEPLOYMENT',
  'NEXT_PUBLIC_AUTH_MODE',
  'NEXT_PUBLIC_LOCAL_DEMO',
  'NEXT_PUBLIC_API_URL',
  'NEXT_PUBLIC_FRONTEND_ORIGIN',
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

function useLocalConfig() {
  process.env.NEXT_PUBLIC_DEPLOYMENT = 'local';
  process.env.NEXT_PUBLIC_AUTH_MODE = 'fixture';
  process.env.NEXT_PUBLIC_LOCAL_DEMO = 'true';
  process.env.NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8001';
}

function useHostedConfig() {
  process.env.NEXT_PUBLIC_DEPLOYMENT = 'hosted';
  process.env.NEXT_PUBLIC_AUTH_MODE = 'supabase';
  process.env.NEXT_PUBLIC_LOCAL_DEMO = 'false';
  process.env.NEXT_PUBLIC_API_URL = 'https://api.intraspot.example.com';
  process.env.NEXT_PUBLIC_FRONTEND_ORIGIN = 'https://intraspot.example.com';
  Object.defineProperty(globalThis, 'window', {configurable: true, value: {
    location: {origin: 'https://intraspot.example.com', hostname: 'intraspot.example.com'},
  }});
}

function errorResponse(status, code, message, headers = {}) {
  return new Response(JSON.stringify({error: {code, message}}), {status, headers});
}

test('429 Retry-After seconds are attached while response status and code stay intact', async () => {
  useLocalConfig();
  globalThis.fetch = async () => errorResponse(429, 'rate_limited', 'Wait before trying again.', {'Retry-After': '47'});

  await assert.rejects(api('/me'), error => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 429);
    assert.equal(error.code, 'rate_limited');
    assert.equal(error.message, 'Wait before trying again.');
    assert.equal(error.retryAfterSeconds, 47);
    return true;
  });
});

test('Retry-After HTTP-dates parse safely and values are capped to one hour', async () => {
  useLocalConfig();
  let retryAfter = new Date(Date.now() + 120_000).toUTCString();
  globalThis.fetch = async () => errorResponse(429, 'rate_limited', 'Try again.', {'Retry-After': retryAfter});
  await assert.rejects(api('/me'), error => {
    assert.ok(error.retryAfterSeconds > 0 && error.retryAfterSeconds <= 120);
    return true;
  });

  retryAfter = 'Wed, 21 Oct 2015 07:28:00 GMT';
  await assert.rejects(api('/me'), error => error.retryAfterSeconds === 0);
  retryAfter = '999999999999999999999999999999999999';
  await assert.rejects(api('/me'), error => error.retryAfterSeconds === 3600);
  retryAfter = 'Wed, 21 Oct 2099 07:28:00 GMT';
  await assert.rejects(api('/me'), error => error.retryAfterSeconds === 3600);
});

test('invalid Retry-After headers are ignored without losing 429 status or code', async () => {
  useLocalConfig();
  let retryAfter = '';
  globalThis.fetch = async () => errorResponse(429, 'rate_limited', 'Try again.', {'Retry-After': retryAfter});

  for (const invalid of ['bogus', '-1', '1.5', 'Mon, 32 Jan 2026 00:00:00 GMT']) {
    retryAfter = invalid;
    await assert.rejects(api('/me'), error => {
      assert.equal(error.status, 429);
      assert.equal(error.code, 'rate_limited');
      assert.equal(error.retryAfterSeconds, undefined);
      return true;
    });
  }
});

test('503 errors use safe retryable wording for local and hosted connections', async () => {
  const privateServerText = 'server-private-detail-sentinel';
  for (const [configure, expectedMessage] of [
    [useLocalConfig, 'The local backend is temporarily unavailable. Check that it is running, then retry.'],
    [useHostedConfig, 'The IntraSpot API is temporarily unavailable. Please retry shortly.'],
  ]) {
    configure();
    globalThis.fetch = async () => errorResponse(503, 'temporarily_unavailable', privateServerText, {'Retry-After': '30'});
    await assert.rejects(api('/me'), error => {
      assert.equal(error.status, 503);
      assert.equal(error.code, 'temporarily_unavailable');
      assert.equal(error.message, expectedMessage);
      assert.equal(error.message.includes(privateServerText), false);
      assert.equal(error.retryAfterSeconds, 30);
      return true;
    });
  }
});

test('connection failures give safe recoverable wording for local and hosted configurations', async () => {
  const privateNetworkText = 'network-private-detail-sentinel';
  for (const [configure, expectedMessage] of [
    [useLocalConfig, 'Cannot reach the local backend. Check it is running, then retry.'],
    [useHostedConfig, 'Cannot reach the IntraSpot API. Check that it is available, then retry.'],
  ]) {
    configure();
    globalThis.fetch = async () => { throw new Error(privateNetworkText); };
    await assert.rejects(api('/me'), error => {
      assert.equal(error.status, 0);
      assert.equal(error.code, 'connection_failed');
      assert.equal(error.message, expectedMessage);
      assert.equal(error.message.includes(privateNetworkText), false);
      return true;
    });
  }
});

test('mutation requests are never retried implicitly and explicit retry keeps the same key and request', async () => {
  useLocalConfig();
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({url: String(url), method: options.method, headers: {...options.headers}, body: options.body});
    return requests.length === 1
      ? errorResponse(429, 'rate_limited', 'Try again.', {'Retry-After': '1'})
      : new Response(JSON.stringify({saved: true}), {status: 200});
  };
  const originalRequest = {
    token: 'test-token-sentinel',
    method: 'POST',
    body: {title: 'Meeting notes'},
    idempotencyKey: 'sprint27-idempotency-test-key',
  };

  await assert.rejects(api('/announcements', originalRequest), error => error.retryAfterSeconds === 1);
  assert.equal(requests.length, 1, 'the failed mutation was sent exactly once');

  assert.deepEqual(await api('/announcements', originalRequest), {saved: true});
  assert.equal(requests.length, 2, 'only the explicit retry sends another request');
  assert.deepEqual(requests, [0, 1].map(() => ({
    url: 'http://127.0.0.1:8001/api/v1/announcements',
    method: 'POST',
    headers: {
      Authorization: 'Bearer test-token-sentinel',
      'Content-Type': 'application/json',
      'Idempotency-Key': 'sprint27-idempotency-test-key',
    },
    body: JSON.stringify(originalRequest.body),
  })));
});
