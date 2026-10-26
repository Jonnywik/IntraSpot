import { readdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { getFrontendDeployment, resolveHostedConfig } from '../lib/auth-storage.ts';

const NEXT_ENV_FILES = ['.env', '.env.production', '.env.production.local', '.env.local'];
const SCANNED_EXTENSIONS = new Set(['.css', '.cjs', '.html', '.js', '.json', '.map', '.mjs', '.pem', '.svg', '.txt']);
const CREDENTIAL_PATTERNS = [
  /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/,
  /sb_secret_[A-Za-z0-9_-]{10,}/,
  /GOCSPX-[A-Za-z0-9_-]{10,}/,
  /-----BEGIN (?:RSA |EC )?PRIVATE KEY-----/,
  /postgres(?:ql)?(?:\+\w+)?:\/\/[^\s"'<>:@/]+:[^\s"'<>/@]+@/i,
];

export function validateHostedBuildEnvironment(environment, entryNames) {
  if (NEXT_ENV_FILES.some(file => entryNames.includes(file))) {
    throw new Error('Hosted builds require a clean build directory without auto-loaded environment files.');
  }
  const config = resolveHostedConfig({
    deployment: environment.NEXT_PUBLIC_DEPLOYMENT,
    authMode: environment.NEXT_PUBLIC_AUTH_MODE,
    localDemo: environment.NEXT_PUBLIC_LOCAL_DEMO,
    apiUrl: environment.NEXT_PUBLIC_API_URL,
    frontendOrigin: environment.NEXT_PUBLIC_FRONTEND_ORIGIN,
    supabaseUrl: environment.NEXT_PUBLIC_SUPABASE_URL,
    supabasePublishableKey: environment.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  });
  if (getFrontendDeployment(environment.NEXT_PUBLIC_DEPLOYMENT) !== 'hosted' || !config) {
    throw new Error('Hosted frontend configuration is invalid.');
  }
  return config;
}

export async function assertNoHostedCredentialArtifacts(root) {
  async function inspect(folder) {
    for (const entry of await readdir(folder, {withFileTypes: true})) {
      const target = resolve(folder, entry.name);
      if (entry.isDirectory()) {
        await inspect(target);
      } else if (entry.isFile() && SCANNED_EXTENSIONS.has(entry.name.slice(entry.name.lastIndexOf('.')).toLowerCase())) {
        const content = await readFile(target, 'utf8');
        if (CREDENTIAL_PATTERNS.some(pattern => pattern.test(content))) {
          throw new Error('Hosted export contains a credential artifact.');
        }
      }
    }
  }
  await inspect(root);
}

function runNode(args, environment) {
  const result = spawnSync(process.execPath, args, {
    env: environment,
    stdio: 'inherit',
    windowsHide: true,
  });
  if (result.error) throw new Error('Hosted build step could not start.');
  return result.status ?? 1;
}

export async function buildHosted() {
  validateHostedBuildEnvironment(process.env, await readdir(process.cwd()));
  const environment = {...process.env, INTRASPOT_HOSTED_BUILD_GUARD: 'verified'};
  const require = createRequire(import.meta.url);
  const steps = [
    [resolve('scripts/check-public-assets.mjs')],
    [require.resolve('next/dist/bin/next'), 'build'],
    [resolve('scripts/check-public-assets.mjs'), 'out-hosted'],
  ];
  for (const args of steps) {
    const status = runNode(args, environment);
    if (status !== 0) return status;
  }
  await assertNoHostedCredentialArtifacts(resolve('out-hosted'));
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    process.exitCode = await buildHosted();
  } catch (error) {
    console.error(error instanceof Error ? error.message : 'Hosted build failed.');
    process.exitCode = 1;
  }
}
