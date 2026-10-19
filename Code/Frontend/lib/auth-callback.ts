import { isValidPKCEFlowId } from './auth-storage';

export type AuthCallbackCapture = {
  code: string | null;
  flowId: string | null;
  hasProviderError: boolean;
};

export type AuthCallbackStatus = 'verifying' | 'failed' | 'unavailable';
export type AuthCallbackFailure =
  | 'provider_rejected'
  | 'callback_code_missing'
  | 'callback_invalid'
  | 'configuration_unavailable'
  | 'verifier_missing'
  | 'verifier_mismatch'
  | 'exchange_expired'
  | 'exchange_network_failed'
  | 'exchange_rejected';
export type AuthCallbackExchangeCell = { current: Promise<AuthCallbackStatus> | null };

// Never render provider messages, URLs, or arbitrary error properties.
export function classifyAuthExchangeFailure(error: unknown): AuthCallbackFailure {
  const detail = error && typeof error === 'object'
    ? error as { name?: unknown; code?: unknown }
    : {};
  if (detail.name === 'AuthPKCECodeVerifierMissingError') return 'verifier_missing';
  if (detail.code === 'bad_code_verifier') return 'verifier_mismatch';
  if (detail.code === 'flow_state_not_found' || detail.code === 'flow_state_expired') return 'exchange_expired';
  if (detail.name === 'AuthRetryableFetchError' || detail.name === 'TypeError') return 'exchange_network_failed';
  return 'exchange_rejected';
}

export function scrubAuthCallbackUrl(
  href: string,
  history: { state: unknown; replaceState(data: unknown, unused: string, url?: string | URL | null): void },
): AuthCallbackCapture {
  const url = new URL(href);
  const fragment = new URLSearchParams(url.hash.slice(1));
  const capture = {
    code: url.searchParams.get('code'),
    flowId: url.searchParams.get('sb_flow_id'),
    hasProviderError: ['error', 'error_code', 'error_description', 'error_uri']
      .some(key => url.searchParams.has(key) || fragment.has(key)),
  };
  history.replaceState(history.state, '', url.pathname);
  return capture;
}

export async function exchangeAuthCallback(
  capture: AuthCallbackCapture,
  dependencies: {
    isConfigured(): boolean;
    getClient(): {
      exchangeCodeForSession(
        code: string,
        options?: { flowId?: string },
      ): Promise<{ error: unknown | null }>;
    };
    clearVerifier(): void;
    reportFailure?(reason: AuthCallbackFailure): void;
  },
): Promise<AuthCallbackStatus> {
  if (
    capture.hasProviderError ||
    !capture.code ||
    capture.code.length > 4096 ||
    (capture.flowId !== null && !isValidPKCEFlowId(capture.flowId))
  ) {
    dependencies.reportFailure?.(capture.hasProviderError
      ? 'provider_rejected'
      : !capture.code ? 'callback_code_missing' : 'callback_invalid');
    dependencies.clearVerifier();
    return 'failed';
  }
  if (!dependencies.isConfigured()) {
    dependencies.reportFailure?.('configuration_unavailable');
    dependencies.clearVerifier();
    return 'unavailable';
  }

  try {
    const client = dependencies.getClient();
    const { error } = await client.exchangeCodeForSession(
      capture.code,
      capture.flowId ? { flowId: capture.flowId } : undefined,
    );
    if (error) dependencies.reportFailure?.(classifyAuthExchangeFailure(error));
    return error ? 'failed' : 'verifying';
  } catch (error) {
    dependencies.reportFailure?.(classifyAuthExchangeFailure(error));
    return 'failed';
  } finally {
    dependencies.clearVerifier();
  }
}

export function getAuthCallbackExchange(
  cell: AuthCallbackExchangeCell,
  capture: AuthCallbackCapture,
  dependencies: Parameters<typeof exchangeAuthCallback>[1],
): Promise<AuthCallbackStatus> {
  if (!cell.current) cell.current = exchangeAuthCallback(capture, dependencies);
  return cell.current;
}
