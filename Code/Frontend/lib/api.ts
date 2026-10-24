export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export function localDemoEnabled(): boolean {
  return (!process.env.NEXT_PUBLIC_AUTH_MODE || process.env.NEXT_PUBLIC_AUTH_MODE === 'fixture') &&
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
  const base = new URL(process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001');
  if (base.protocol !== 'http:' || !['localhost', '127.0.0.1'].includes(base.hostname) || base.username || base.password) {
    throw new ApiError(0, 'local_api_required', 'This MVP connects only to a local backend.');
  }
  if (process.env.NEXT_PUBLIC_AUTH_MODE === 'supabase' && base.href !== 'http://127.0.0.1:8011/') {
    throw new ApiError(0, 'isolated_api_required', 'Google development sign-in requires its separate local backend.');
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
    throw new ApiError(0, 'connection_failed', 'Cannot reach the local backend. Check it is running, then retry.');
  }
  if (response.ok && options.responseType === 'blob') return await response.blob() as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status,
    body?.error?.code || 'request_failed',
    body?.error?.message || 'The request could not be completed. Please retry.');
  return body as T;
}
