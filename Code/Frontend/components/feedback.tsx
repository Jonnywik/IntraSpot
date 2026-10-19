'use client';
import type { ReactNode } from 'react';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
export function Feedback({loading, error, onRetry, children}: {
  loading?: boolean; error?: Error | null; onRetry?: () => void; children?: ReactNode;
}) {
  const t = useT();
  const {preferences:{language}} = usePreferences();
  if (loading) return <div role="status" className="panel muted feedback-content"><span className="loading-indicator" aria-hidden="true"/><p>{t('Loading…')}</p></div>;
  if (error) {
    const translated = t(error.message);
    const message = language === 'fil' && translated === error.message
      ? t('The request could not be completed. Please retry.') : translated;
    return <div role="alert" className="panel error"><p>{message}</p>{onRetry && <button type="button" className="button button-secondary" onClick={onRetry}>{t('Retry')}</button>}</div>;
  }
  return <>{children}</>;
}
