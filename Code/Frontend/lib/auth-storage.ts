export interface AuthStorageAdapter {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export interface RealAuthEnvironment {
  authMode?: string;
  localDemo?: string;
  deployment?: string;
  apiUrl?: string;
  frontendOrigin?: string;
  supabaseUrl?: string;
  supabasePublishableKey?: string;
}

export interface LocalBrowserLocation {
  protocol: string;
  hostname: string;
  port: string;
  origin: string;
}

export interface RealAuthConfig {
  projectRef: string;
  supabaseUrl: string;
  supabasePublishableKey: string;
  apiUrl: string;
  callbackUrl: string;
}

interface SessionStorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

interface VerifierEnvelope {
  version: 1;
  expiresAt: number;
  values: Record<string, string>;
}

const PKCE_SLOT_PREFIX = 'intraspot.auth.pkce.v1.';
const PKCE_TTL_MS = 10 * 60 * 1000;
const MAX_SLOT_LENGTH = 16_384;
const MAX_ENTRY_LENGTH = 4096;
const MAX_ENTRIES = 10;
const RESERVED_DNS_SUFFIXES = ['localhost', 'local', 'test', 'example', 'invalid', 'internal', 'onion', 'arpa'];

export interface HostedConfigEnvironment {
  deployment?: string;
  authMode?: string;
  localDemo?: string;
  apiUrl?: string;
  frontendOrigin?: string;
  supabaseUrl?: string;
  supabasePublishableKey?: string;
}

export interface HostedConfig {
  apiUrl: string;
  frontendOrigin: string;
  callbackUrl: string;
  projectRef: string;
  supabaseUrl: string;
  supabasePublishableKey: string;
}

export function getFrontendDeployment(value?: string): 'local' | 'hosted' | null {
  if (value === undefined) return 'local';
  return value === 'local' || value === 'hosted' ? value : null;
}

function exactHttpsRoot(value?: string): URL | null {
  if (!value || value !== value.trim()) return null;
  try {
    const url = new URL(value);
    const hostname = url.hostname.toLowerCase();
    const publicDnsHost = hostname.includes('.') && !hostname.endsWith('.') &&
      hostname.split('.').every(label => /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label)) &&
      !hostname.includes(':') && !hostname.startsWith('[') &&
      !/^\d+(?:\.\d+){3}$/.test(hostname) && !hostname.split('.').every(label => /^\d+$/.test(label)) &&
      !RESERVED_DNS_SUFFIXES.some(suffix => hostname === suffix || hostname.endsWith(`.${suffix}`)) &&
      hostname !== 'home.arpa' && !hostname.endsWith('.home.arpa');
    if (
      url.protocol !== 'https:' ||
      !publicDnsHost ||
      url.port ||
      url.username ||
      url.password ||
      url.pathname !== '/' ||
      url.search ||
      url.hash ||
      (value !== url.origin && value !== `${url.origin}/`)
    ) return null;
    return url;
  } catch {
    return null;
  }
}

export function resolveHostedConfig(
  environment: HostedConfigEnvironment,
  currentOrigin?: string,
): HostedConfig | null {
  if (
    getFrontendDeployment(environment.deployment) !== 'hosted' ||
    environment.authMode !== 'supabase' ||
    environment.localDemo !== 'false'
  ) return null;

  const apiUrl = exactHttpsRoot(environment.apiUrl);
  const frontendOrigin = exactHttpsRoot(environment.frontendOrigin);
  const supabaseUrl = exactHttpsRoot(environment.supabaseUrl);
  const publishableKey = environment.supabasePublishableKey ?? '';
  const projectMatch = supabaseUrl?.hostname.match(/^([a-z0-9-]{8,64})\.supabase\.co$/);
  if (
    !apiUrl || !frontendOrigin || !supabaseUrl || !projectMatch ||
    !/^sb_publishable_[A-Za-z0-9_-]{10,256}$/.test(publishableKey) ||
    (currentOrigin !== undefined && currentOrigin !== frontendOrigin.origin)
  ) return null;

  return {
    apiUrl: apiUrl.origin,
    frontendOrigin: frontendOrigin.origin,
    callbackUrl: `${frontendOrigin.origin}/auth/callback`,
    projectRef: projectMatch[1],
    supabaseUrl: supabaseUrl.origin,
    supabasePublishableKey: publishableKey,
  };
}

export function isValidPKCEFlowId(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9_-]{8,64}$/.test(value);
}

export function resolveRealAuthConfig(
  environment: RealAuthEnvironment,
  location: LocalBrowserLocation | null,
): RealAuthConfig | null {
  const deployment = getFrontendDeployment(environment.deployment ?? process.env.NEXT_PUBLIC_DEPLOYMENT);
  if (deployment === 'hosted') {
    if (!location || location.protocol !== 'https:') return null;
    const hosted = resolveHostedConfig({
      ...environment,
      deployment,
      frontendOrigin: environment.frontendOrigin ?? process.env.NEXT_PUBLIC_FRONTEND_ORIGIN,
    }, location.origin);
    if (!hosted) return null;
    return {
      projectRef: hosted.projectRef,
      supabaseUrl: hosted.supabaseUrl,
      supabasePublishableKey: hosted.supabasePublishableKey,
      apiUrl: hosted.apiUrl,
      callbackUrl: hosted.callbackUrl,
    };
  }
  if (deployment !== 'local') return null;

  if (
    environment.authMode !== 'supabase' ||
    environment.localDemo !== 'false' ||
    !location ||
    location.protocol !== 'http:' ||
    !['localhost', '127.0.0.1'].includes(location.hostname) ||
    location.port !== '3001'
  ) {
    return null;
  }

  const expectedOrigin = 'http://' + location.hostname + ':3001';
  if (location.origin !== expectedOrigin) return null;

  let apiUrl: URL;
  let supabaseUrl: URL;
  try {
    apiUrl = new URL(environment.apiUrl ?? '');
    supabaseUrl = new URL(environment.supabaseUrl ?? '');
  } catch {
    return null;
  }

  if (
    apiUrl.href !== 'http://127.0.0.1:8011/' ||
    apiUrl.username ||
    apiUrl.password ||
    apiUrl.search ||
    apiUrl.hash
  ) {
    return null;
  }

  const rawSupabaseUrl = environment.supabaseUrl ?? '';
  if (!/^https:\/\/[a-z0-9-]{8,64}\.supabase\.co$/.test(rawSupabaseUrl)) return null;

  const suffix = '.supabase.co';
  if (
    supabaseUrl.protocol !== 'https:' ||
    !supabaseUrl.hostname.endsWith(suffix) ||
    supabaseUrl.port ||
    supabaseUrl.pathname !== '/' ||
    supabaseUrl.username ||
    supabaseUrl.password ||
    supabaseUrl.search ||
    supabaseUrl.hash
  ) {
    return null;
  }

  const projectRef = supabaseUrl.hostname.slice(0, -suffix.length);
  if (!/^[a-z0-9-]{8,64}$/.test(projectRef)) return null;

  const publishableKey = environment.supabasePublishableKey ?? '';
  if (!/^sb_publishable_[A-Za-z0-9_-]{10,256}$/.test(publishableKey)) return null;

  return {
    projectRef,
    supabaseUrl: supabaseUrl.origin,
    supabasePublishableKey: publishableKey,
    apiUrl: 'http://127.0.0.1:8011',
    callbackUrl: expectedOrigin + '/auth/callback',
  };
}

function browserSessionStorage(): SessionStorageLike | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function verifierEntry(key: string): string | null {
  if (key.endsWith('-flows-code-verifier')) return 'index';
  const flow = /-flow-([A-Za-z0-9_-]{8,64})-code-verifier$/.exec(key);
  if (flow) return 'flow:' + flow[1];
  if (key.endsWith('-code-verifier')) return 'legacy';
  return null;
}

function isVerifierEntryKey(key: string): boolean {
  return key === 'index' || key === 'legacy' || /^flow:[A-Za-z0-9_-]{8,64}$/.test(key);
}

export function createAuthStorage(
  projectRef: string,
  options: { sessionStorage?: SessionStorageLike; now?: () => number } = {},
) {
  if (!/^[a-z0-9-]{8,64}$/.test(projectRef)) {
    throw new Error('A valid local Auth project is required.');
  }

  const memory = new Map<string, string>();
  const slotKey = PKCE_SLOT_PREFIX + projectRef;
  const now = options.now ?? Date.now;
  const getSessionStorage = () => options.sessionStorage ?? browserSessionStorage();

  function clearVerifier() {
    try {
      getSessionStorage()?.removeItem(slotKey);
    } catch {
      // The next sign-in will fail closed if same-tab verifier storage is unavailable.
    }
  }

  function readEnvelope(): VerifierEnvelope | null {
    const storage = getSessionStorage();
    if (!storage) return null;

    let raw: string | null;
    try {
      raw = storage.getItem(slotKey);
    } catch {
      return null;
    }
    if (!raw) return null;
    if (raw.length > MAX_SLOT_LENGTH) {
      clearVerifier();
      return null;
    }

    try {
      const candidate = JSON.parse(raw) as Partial<VerifierEnvelope>;
      if (
        candidate.version !== 1 ||
        typeof candidate.expiresAt !== 'number' ||
        !Number.isFinite(candidate.expiresAt) ||
        candidate.expiresAt <= now() ||
        !candidate.values ||
        typeof candidate.values !== 'object' ||
        Array.isArray(candidate.values)
      ) {
        clearVerifier();
        return null;
      }

      const values = candidate.values as Record<string, unknown>;
      const entries = Object.entries(values);
      if (
        entries.length > MAX_ENTRIES ||
        entries.some(([key, value]) =>
          !isVerifierEntryKey(key) || typeof value !== 'string' || value.length > MAX_ENTRY_LENGTH,
        )
      ) {
        clearVerifier();
        return null;
      }

      return {
        version: 1,
        expiresAt: candidate.expiresAt,
        values: values as Record<string, string>,
      };
    } catch {
      clearVerifier();
      return null;
    }
  }

  function writeEnvelope(envelope: VerifierEnvelope) {
    const storage = getSessionStorage();
    if (!storage) throw new Error('Same-tab PKCE storage is unavailable.');
    const raw = JSON.stringify(envelope);
    if (raw.length > MAX_SLOT_LENGTH) {
      clearVerifier();
      throw new Error('Same-tab PKCE storage is full.');
    }
    storage.setItem(slotKey, raw);
  }

  async function getItem(key: string): Promise<string | null> {
    if (key.endsWith('-code-verifier')) {
      const entry = verifierEntry(key);
      return entry ? readEnvelope()?.values[entry] ?? null : null;
    }
    return memory.get(key) ?? null;
  }

  async function setItem(key: string, value: string): Promise<void> {
    if (key.endsWith('-code-verifier')) {
      const entry = verifierEntry(key);
      if (!entry || value.length > MAX_ENTRY_LENGTH) {
        throw new Error('The PKCE verifier could not be stored safely.');
      }
      const envelope = readEnvelope();
      const values = { ...(envelope?.values ?? {}), [entry]: value };
      if (Object.keys(values).length > MAX_ENTRIES) {
        clearVerifier();
        throw new Error('Too many pending PKCE values.');
      }
      writeEnvelope({
        version: 1,
        expiresAt: now() + PKCE_TTL_MS,
        values,
      });
      return;
    }
    memory.set(key, value);
  }

  async function removeItem(key: string): Promise<void> {
    if (key.endsWith('-code-verifier')) {
      const entry = verifierEntry(key);
      if (!entry) return;
      const envelope = readEnvelope();
      if (!envelope || !(entry in envelope.values)) return;
      const values = { ...envelope.values };
      delete values[entry];
      if (Object.keys(values).length === 0) {
        clearVerifier();
      } else {
        writeEnvelope({ ...envelope, values });
      }
      return;
    }
    memory.delete(key);
  }

  return {
    adapter: { getItem, setItem, removeItem } satisfies AuthStorageAdapter,
    clearMemory: () => memory.clear(),
    clearVerifier,
    clearAll: () => {
      memory.clear();
      clearVerifier();
    },
  };
}
