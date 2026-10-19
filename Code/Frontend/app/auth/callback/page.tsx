'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSession } from '@/lib/session';
import { useT } from '@/lib/i18n';
import {
  getAuthCallbackExchange,
  scrubAuthCallbackUrl,
  type AuthCallbackCapture,
  type AuthCallbackStatus,
  type AuthCallbackFailure,
} from '@/lib/auth-callback';
import {
  clearRealAuthVerifier,
  getRealAuthClient,
  getRealAuthConfig,
} from '@/lib/supabase-auth';

type CallbackStatus = 'checking' | 'verifying' | 'success' | 'failed' | 'unavailable';
const useClientLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect;

export default function AuthCallbackPage() {
  const t = useT();
  const { actor, token, authLoading, error, refreshActor } = useSession();
  const [status, setStatus] = useState<CallbackStatus>('checking');
  const [diagnostic, setDiagnostic] = useState<string | null>(null);
  const failureReason = useRef<AuthCallbackFailure | null>(null);
  const callback = useRef<AuthCallbackCapture | null>(null);
  const exchangePromise = useRef<Promise<AuthCallbackStatus> | null>(null);
  const captured = useRef(false);

  useClientLayoutEffect(() => {
    if (captured.current) return;
    captured.current = true;
    callback.current = scrubAuthCallbackUrl(window.location.href, window.history);
  }, []);

  useEffect(() => {
    const capture = callback.current;
    if (!capture) return;
    let active = true;
    void getAuthCallbackExchange(exchangePromise, capture, {
      isConfigured: () => Boolean(getRealAuthConfig()),
      getClient: getRealAuthClient,
      clearVerifier: clearRealAuthVerifier,
      reportFailure: reason => { failureReason.current = reason; },
    }).then(nextStatus => {
      if (active) {
        setDiagnostic(failureReason.current);
        setStatus(nextStatus);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const visibleStatus: CallbackStatus = status === 'verifying' && !authLoading
    ? token && actor
      ? 'success'
      : error
        ? 'failed'
        : status
    : status;

  useEffect(() => {
    if (visibleStatus !== 'verifying') return;
    const timeout = window.setTimeout(() => {
      setDiagnostic('local_verification_timeout');
      setStatus('failed');
    }, 15_000);
    return () => window.clearTimeout(timeout);
  }, [visibleStatus]);

  const message = visibleStatus === 'success'
    ? 'Your development session is ready. Continue to IntraSpot.'
    : visibleStatus === 'unavailable'
      ? 'Google sign-in is not configured for isolated development.'
      : visibleStatus === 'failed'
        ? 'The Google sign-in response could not be completed. Start again.'
        : visibleStatus === 'verifying'
          ? 'Checking the Google sign-in response…'
          : 'Checking the Google sign-in response…';

  return (
    <section className="page-shell" aria-labelledby="auth-callback-title">
        <h1 id="auth-callback-title">{t('Google sign-in')}</h1>
        <p role={visibleStatus === 'failed' || visibleStatus === 'unavailable' ? 'alert' : 'status'}>
          {t(message)}
        </p>
        {(visibleStatus === 'failed' || visibleStatus === 'unavailable') && (
          <p>
            {t('Development diagnostic')}: <code>{diagnostic ??
              (error?.status === 401 ? 'local_verification_rejected' : 'local_verification_failed')}</code>
          </p>
        )}
        {visibleStatus === 'failed' && token && (
          <button
            className="button button-secondary"
            type="button"
            onClick={() => {
              setStatus('verifying');
              setDiagnostic(null);
              void refreshActor();
            }}
          >
            {t('Retry local verification')}
          </button>
        )}
        <p><Link href="/">{t('Continue to IntraSpot')}</Link></p>
    </section>
  );
}
