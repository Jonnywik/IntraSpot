import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';

if (existsSync('.env.real.local')) process.loadEnvFile('.env.real.local');
assert.equal(process.env.NEXT_PUBLIC_AUTH_MODE, 'supabase', 'Configure the isolated real-development profile first.');
assert.equal(process.env.NEXT_PUBLIC_LOCAL_DEMO, 'false', 'Fictional accounts must be disabled.');
assert.equal(process.env.NEXT_PUBLIC_API_URL, 'http://127.0.0.1:8011', 'Real development requires its separate API.');
assert.match(process.env.NEXT_PUBLIC_SUPABASE_URL ?? '', /^https:\/\/[a-z0-9-]{8,64}\.supabase\.co$/);
assert.match(process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? '', /^sb_publishable_[A-Za-z0-9_-]{10,256}$/);
process.env.INTRASPOT_FRONTEND_PROFILE = 'real';
const require = createRequire(import.meta.url);
for (const args of [
  [resolve('scripts/check-public-assets.mjs')],
  [require.resolve('next/dist/bin/next'), 'build'],
  [resolve('scripts/check-public-assets.mjs'), 'out-real'],
]) {
  const result = spawnSync(process.execPath, args, {env: process.env, stdio: 'inherit', windowsHide: true});
  if (result.error || result.status !== 0) process.exit(result.status || 1);
}
