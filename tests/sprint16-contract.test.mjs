import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {api} from '../Code/Frontend/lib/api.ts';

const originalFetch = globalThis.fetch;
const names = ['NEXT_PUBLIC_API_URL', 'NEXT_PUBLIC_AUTH_MODE'];
const original = Object.fromEntries(names.map(name => [name, process.env[name]]));
afterEach(() => {
  globalThis.fetch = originalFetch;
  for (const name of names) {
    if (original[name] === undefined) delete process.env[name];
    else process.env[name] = original[name];
  }
});

test('binary uploads retain origin guards and send image bytes with draft preconditions', async () => {
  process.env.NEXT_PUBLIC_AUTH_MODE = 'supabase';
  process.env.NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8011';
  const bytes = new Blob([new Uint8Array([0, 1, 2, 255])], {type: 'image/png'});
  let calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++;
    assert.equal(url, 'http://127.0.0.1:8011/api/v1/events/sample/banner');
    assert.equal(options.body, bytes);
    assert.equal(options.headers['Content-Type'], 'image/png');
    assert.equal(options.headers['If-Match'], '"version"');
    assert.equal(options.headers.Authorization, 'Bearer synthetic-test-token');
    assert.equal(options.credentials, 'omit');
    return Response.json({media_url: '/api/v1/media/sample'});
  };
  await api('/events/sample/banner', {method: 'POST', token: 'synthetic-test-token', body: bytes, ifMatch: 'version'});
  process.env.NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8001';
  await assert.rejects(api('/events/sample/banner', {method: 'POST', body: bytes}), error => error.code === 'isolated_api_required');
  assert.equal(calls, 1);
});

test('binary image reads preserve JSON errors and never mistake forbidden responses for images', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8001';
  delete process.env.NEXT_PUBLIC_AUTH_MODE;
  globalThis.fetch = async () => new Response(new Uint8Array([1, 2, 3]), {headers: {'Content-Type': 'image/webp'}});
  const image = await api('/media/sample', {responseType: 'blob'});
  assert.equal(image.type, 'image/webp');
  assert.equal(image.size, 3);
  globalThis.fetch = async () => Response.json({error: {code: 'media_not_found', message: 'Image is unavailable.'}}, {status: 404});
  await assert.rejects(api('/media/sample', {responseType: 'blob'}), error => error.code === 'media_not_found' && error.status === 404);
});
