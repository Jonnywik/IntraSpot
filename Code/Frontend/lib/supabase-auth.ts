import { GoTrueClient } from '@supabase/auth-js';
import { createAuthStorage, resolveRealAuthConfig, type RealAuthConfig } from './auth-storage';

type AuthRuntime = {
  client: GoTrueClient;
  config: RealAuthConfig;
  storage: ReturnType<typeof createAuthStorage>;
};

let runtime: AuthRuntime | null = null;

export function getRealAuthConfig(): RealAuthConfig | null {
  if (typeof window === 'undefined') return null;
  return resolveRealAuthConfig(
    {
      authMode: process.env.NEXT_PUBLIC_AUTH_MODE,
      localDemo: process.env.NEXT_PUBLIC_LOCAL_DEMO,
      apiUrl: process.env.NEXT_PUBLIC_API_URL,
      supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL,
      supabasePublishableKey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
    },
    window.location,
  );
}

function createClientStorageKey(): string {
  const bytes = new Uint8Array(16);
  if (!window.crypto || typeof window.crypto.getRandomValues !== 'function') {
    throw new Error('Secure local session storage is unavailable.');
  }
  window.crypto.getRandomValues(bytes);
  return 'intraspot-auth-' + Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

export function getRealAuthClient(): GoTrueClient {
  const config = getRealAuthConfig();
  if (!config) throw new Error('Isolated development sign-in is not configured.');

  if (runtime) {
    if (
      runtime.config.supabaseUrl === config.supabaseUrl &&
      runtime.config.supabasePublishableKey === config.supabasePublishableKey
    ) {
      return runtime.client;
    }
    runtime.storage.clearAll();
    runtime = null;
  }

  const storage = createAuthStorage(config.projectRef);
  const client = new GoTrueClient({
    url: config.supabaseUrl + '/auth/v1',
    headers: { apikey: config.supabasePublishableKey },
    storageKey: createClientStorageKey(),
    storage: storage.adapter,
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
    flowType: 'pkce',
  });
  runtime = { client, config, storage };
  return client;
}

export function clearRealAuthVerifier() {
  if (runtime) {
    runtime.storage.clearVerifier();
    return;
  }
  const config = getRealAuthConfig();
  if (config) createAuthStorage(config.projectRef).clearVerifier();
}

export function clearRealAuthMemory() {
  runtime?.storage.clearMemory();
}

export function clearRealAuthStorage() {
  if (runtime) {
    runtime.storage.clearAll();
    return;
  }
  const config = getRealAuthConfig();
  if (config) createAuthStorage(config.projectRef).clearAll();
}
