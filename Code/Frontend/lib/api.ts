export class ApiError extends Error {
  status: number;
  code: string;
  retryAfterSeconds?: number;
  constructor(status: number, code: string, message: string, retryAfterSeconds?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    if (retryAfterSeconds !== undefined) this.retryAfterSeconds = retryAfterSeconds;
  }
}

const MAX_RETRY_AFTER_SECONDS = 3600;
const IMF_FIXDATE = /^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} GMT$/;

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const header = value.trim();
  if (/^\d+$/.test(header)) return Math.min(Number(header), MAX_RETRY_AFTER_SECONDS);
  if (!IMF_FIXDATE.test(header)) return undefined;

  const timestamp = Date.parse(header);
  if (!Number.isFinite(timestamp) || new Date(timestamp).toUTCString() !== header) return undefined;
  return Math.min(MAX_RETRY_AFTER_SECONDS, Math.max(0, Math.ceil((timestamp - Date.now()) / 1000)));
}

const RESERVED_DNS_SUFFIXES = ['localhost', 'local', 'test', 'example', 'invalid', 'internal', 'onion', 'arpa'];

function frontendDeployment(): 'local' | 'hosted' | null {
  const value = process.env.NEXT_PUBLIC_DEPLOYMENT;
  if (value === undefined) return 'local';
  return value === 'local' || value === 'hosted' ? value : null;
}

function exactHostedRoot(value?: string): URL | null {
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
      url.protocol !== 'https:' || !publicDnsHost || url.port || url.username || url.password ||
      url.pathname !== '/' || url.search || url.hash ||
      (value !== url.origin && value !== `${url.origin}/`)
    ) return null;
    return url;
  } catch {
    return null;
  }
}

export function localDemoEnabled(): boolean {
  return frontendDeployment() === 'local' &&
    (!process.env.NEXT_PUBLIC_AUTH_MODE || process.env.NEXT_PUBLIC_AUTH_MODE === 'fixture') &&
    process.env.NEXT_PUBLIC_LOCAL_DEMO === 'true' &&
    typeof window !== 'undefined' && ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
}

export async function api<T>(path: string, options: {
  token?: string | null; method?: string; body?: unknown;
  idempotencyKey?: string; signal?: AbortSignal;
  ifMatch?: string;
  responseType?: 'blob';
} = {}): Promise<T> {
  if (!path.startsWith('/') || path.startsWith('//')) {
    throw new ApiError(0, 'invalid_api_path', 'An internal API path is required.');
  }
  let pathname: string;
  try { pathname = decodeURIComponent(path.split(/[?#]/, 1)[0]); }
  catch { throw new ApiError(0, 'invalid_api_path', 'An internal API path is required.'); }
  if (pathname.includes('\\') || pathname.split('/').some(part => part === '.' || part === '..') || path.includes('#')) {
    throw new ApiError(0, 'invalid_api_path', 'An internal API path is required.');
  }
  const deployment = frontendDeployment();
  let base: URL;
  if (deployment === 'hosted') {
    const apiRoot = exactHostedRoot(process.env.NEXT_PUBLIC_API_URL);
    const frontendRoot = exactHostedRoot(process.env.NEXT_PUBLIC_FRONTEND_ORIGIN);
    const currentOrigin = typeof window === 'undefined' ? undefined : window.location.origin;
    if (
      process.env.NEXT_PUBLIC_AUTH_MODE !== 'supabase' ||
      process.env.NEXT_PUBLIC_LOCAL_DEMO !== 'false' ||
      !apiRoot || !frontendRoot ||
      (typeof window !== 'undefined' && currentOrigin !== frontendRoot.origin)
    ) throw new ApiError(0, 'hosted_config_invalid', 'Hosted API configuration is invalid.');
    base = apiRoot;
  } else {
    if (deployment !== 'local') {
      throw new ApiError(0, 'deployment_config_invalid', 'Frontend deployment configuration is invalid.');
    }
    base = new URL(process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001');
    if (base.protocol !== 'http:' || !['localhost', '127.0.0.1'].includes(base.hostname) || base.username || base.password) {
      throw new ApiError(0, 'local_api_required', 'This MVP connects only to a local backend.');
    }
    if (process.env.NEXT_PUBLIC_AUTH_MODE === 'supabase' && base.href !== 'http://127.0.0.1:8011/') {
      throw new ApiError(0, 'isolated_api_required', 'Google development sign-in requires its separate local backend.');
    }
  }
  const headers: Record<string, string> = {};
  const binaryBody = typeof Blob !== 'undefined' && options.body instanceof Blob;
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.body !== undefined) headers['Content-Type'] = binaryBody ? (options.body as Blob).type : 'application/json';
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
  if (options.ifMatch) headers['If-Match'] = `"${options.ifMatch}"`;
  let response: Response;
  try {
    response = await fetch(`${base.origin}/api/v1${path}`, {
      method: options.method || 'GET', headers,
      body: options.body === undefined ? undefined : binaryBody ? options.body as Blob : JSON.stringify(options.body),
      signal: options.signal, cache: 'no-store', credentials: 'omit',
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'connection_failed', deployment === 'hosted'
      ? 'Cannot reach the IntraSpot API. Check that it is available, then retry.'
      : 'Cannot reach the local backend. Check it is running, then retry.');
  }
  if (response.ok && options.responseType === 'blob') return await response.blob() as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status,
    body?.error?.code || 'request_failed',
    response.status === 503
      ? deployment === 'hosted'
        ? 'The IntraSpot API is temporarily unavailable. Please retry shortly.'
        : 'The local backend is temporarily unavailable. Check that it is running, then retry.'
      : body?.error?.message || 'The request could not be completed. Please retry.',
    parseRetryAfter(response.headers.get('Retry-After')));
  return body as T;
}
