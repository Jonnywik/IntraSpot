'use client';
import { useEffect, useRef, type ReactNode } from 'react';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import { recoveryMessage } from '@/lib/recovery';
export function Feedback({loading, error, onRetry, focusError = false, loadingMessage = 'Loading…', children}: {
  loading?: boolean; error?: Error | null; onRetry?: () => void; focusError?: boolean; loadingMessage?: string; children?: ReactNode;
}) {
  const t = useT();
  const {preferences:{language}} = usePreferences();
  const errorPanel = useRef<HTMLDivElement>(null);
  const loadingPanel = useRef<HTMLDivElement>(null);
  const retrying = useRef(false);
  useEffect(() => {
    if (error && focusError && retrying.current) {
      retrying.current = false;
      errorPanel.current?.focus();
    }
  }, [error, focusError]);
  useEffect(() => {
    if (loading && retrying.current && focusError) loadingPanel.current?.focus();
  }, [loading, focusError]);
  useEffect(() => {
    if (!loading && !error) retrying.current = false;
  }, [loading, error]);
  if (loading) return <div ref={loadingPanel} tabIndex={focusError ? -1 : undefined} role="status" aria-live="polite" className="panel muted feedback-content"><span className="loading-indicator" aria-hidden="true"/><p>{t(loadingMessage)}</p></div>;
  if (error) {
    const translated = recoveryMessage(error, t);
    const message = language === 'fil' && translated === error.message
      ? t('The request could not be completed. Please retry.') : translated;
    return <div ref={errorPanel} tabIndex={focusError ? -1 : undefined} role="alert" aria-live="assertive" aria-atomic="true" className="panel error"><p>{message}</p>{onRetry && <button type="button" className="button button-secondary" onClick={() => { retrying.current = focusError; onRetry(); }}>{t('Retry')}</button>}</div>;
  }
  return <>{children}</>;
}
