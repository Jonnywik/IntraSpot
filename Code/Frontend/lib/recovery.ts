import type { Translate } from './i18n';

type RecoveryError = { message: string; status?: number; retryAfterSeconds?: number };

export function recoveryMessage(error: RecoveryError, t: Translate): string {
  if (error.status === 429) {
    const seconds = error.retryAfterSeconds;
    if (typeof seconds === 'number' && Number.isFinite(seconds) && seconds > 0) {
      const wait = Math.ceil(seconds);
      return wait === 1
        ? t('Too many requests. Please wait one second before trying again.')
        : t('Too many requests. Please wait {seconds} seconds before trying again.', { seconds: wait });
    }
    return error.retryAfterSeconds === 0
      ? t('Too many requests. You can try again now.')
      : t('Too many requests. Please wait before trying again.');
  }
  if (error.status === 503) {
    return t('The service is starting or temporarily unavailable. Please wait a moment, then retry.');
  }
  return t(error.message);
}

export function isRetryableApiError(error: { status: number } | null): boolean {
  return error !== null && (error.status === 0 || error.status === 429 || error.status >= 500);
}
