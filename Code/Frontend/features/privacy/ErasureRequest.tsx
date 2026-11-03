'use client';

import {useEffect, useId, useMemo, useRef, useState} from 'react';
import {api} from '@/lib/api';
import {useT} from '@/lib/i18n';
import {usePreferences} from '@/lib/preferences';
import {useSession} from '@/lib/session';

type ErasureReceipt = {
  id: string;
  requested_at: string;
  due_at: string;
  completed_at: string | null;
  status: 'pending' | 'blocked' | 'processing' | 'completed';
  blocker_code: string | null;
  counts: Record<string, number>;
};

type Resource = {
  context: object;
  phase: 'loading' | 'ready' | 'error';
  receipt: ErasureReceipt | null;
  error: 'load' | 'submit' | null;
  submitted: boolean;
};

function formatReceiptDate(value: string, language: string): string | null {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return new Intl.DateTimeFormat(language === 'fil' ? 'fil-PH' : 'en-PH', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Manila',
  }).format(date);
}

export function ErasureRequest() {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const {actor, token, authLoading, version: sessionVersion} = useSession();
  const actorId = actor?.id ?? '';
  const accountContext = useMemo(() => ({actorId, sessionVersion}), [actorId, sessionVersion]);
  const headingId = useId();
  const confirmId = `${headingId}-confirm`;
  const [resource, setResource] = useState<Resource | null>(null);
  const [confirmation, setConfirmation] = useState<object | null>(null);
  const [submittingContext, setSubmittingContext] = useState<object | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const resourceContext = useMemo(() => ({accountContext, refreshVersion}), [accountContext, refreshVersion]);
  const mutationInFlight = useRef<object | null>(null);

  const current = resource?.context === resourceContext ? resource : null;
  const confirming = confirmation === accountContext;
  const submitting = submittingContext === accountContext;
  const signedIn = Boolean(actorId && token);

  useEffect(() => {
    if (authLoading || !signedIn || !token) return;

    const controller = new AbortController();
    api<ErasureReceipt | null>('/me/erasure-request', {token, signal: controller.signal})
      .then(receipt => {
        if (!controller.signal.aborted) {
          setResource({context: resourceContext, phase: 'ready', receipt, error: null, submitted: false});
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setResource({context: resourceContext, phase: 'error', receipt: null, error: 'load', submitted: false});
        }
      });
    return () => controller.abort();
  }, [authLoading, resourceContext, signedIn, token]);

  function refreshStatus() {
    setConfirmation(null);
    setRefreshVersion(value => value + 1);
  }

  async function submitRequest() {
    if (!signedIn || !token || !current || current.phase !== 'ready' || current.receipt || !confirming || mutationInFlight.current === accountContext) return;
    mutationInFlight.current = accountContext;
    setConfirmation(null);
    setSubmittingContext(accountContext);
    try {
      const receipt = await api<ErasureReceipt>('/me/erasure-request', {token, method: 'POST'});
      setResource(previous => previous?.context === resourceContext
        ? {context: resourceContext, phase: 'ready', receipt, error: null, submitted: true}
        : previous);
    } catch {
      setResource(previous => previous?.context === resourceContext
        ? {context: resourceContext, phase: 'error', receipt: null, error: 'submit', submitted: false}
        : previous);
    } finally {
      if (mutationInFlight.current === accountContext) mutationInFlight.current = null;
      setSubmittingContext(previous => previous === accountContext ? null : previous);
    }
  }

  function blockerMessage(code: string | null): string | null {
    if (!code) return null;
    if (code === 'owner_transfer_required') {
      return t('Transfer each organization you own to another eligible owner before erasure can proceed.');
    }
    if (code === 'platform_admin_replacement_required') {
      return t('An operator must appoint another platform administrator before erasure can proceed.');
    }
    return t('Resolve the account responsibility noted for this request before erasure can proceed.');
  }

  function statusLabel(status: ErasureReceipt['status']): string {
    switch (status) {
      case 'pending': return t('Pending');
      case 'blocked': return t('Blocked');
      case 'processing': return t('Processing');
      case 'completed': return t('Completed');
      default: return t('Status unavailable');
    }
  }

  function receiptTime(value: string) {
    const formatted = formatReceiptDate(value, language);
    return <time dateTime={formatted ? value : undefined}>{formatted ?? t('Date unavailable')}</time>;
  }

  const loading = authLoading || (signedIn && (!current || current.phase === 'loading')) || submitting;

  return (
    <section className="panel stack" aria-labelledby={headingId} aria-busy={loading || submitting}>
      <h2 id={headingId}>{t('Account erasure')}</h2>
      <p>{t('Request erasure of this signed-in account. Submitting a request does not delete the account immediately. An operator must review and complete it, with a target of 30 calendar days.')}</p>
      <p>{t('Before requesting, transfer any organization you own to another eligible owner. If you are the last platform administrator, a replacement must be appointed.')}</p>
      <p>{t('Account erasure does not change organization ownership or appoint a platform administrator automatically.')}</p>
      <p>{t('Your signed-in account identifies this request. We do not ask for or collect your email address.')}</p>

      {loading ? (
        <p role="status" aria-live="polite">{submitting ? t('Submitting erasure request…') : authLoading ? t('Checking sign-in…') : t('Loading erasure request…')}</p>
      ) : !signedIn ? (
        <p role="status">{t('Sign in to view or request erasure for this account.')}</p>
      ) : current?.phase === 'error' ? (
        <div className="stack" role="alert">
          <p>{t(current.error === 'submit'
            ? 'The request result could not be confirmed. Refresh the status before trying another request.'
            : 'The erasure request status could not be loaded. Retry to check again.')}</p>
          <button className="button button-secondary" type="button" onClick={refreshStatus}>
            {t(current.error === 'submit' ? 'Refresh request status' : 'Retry status check')}
          </button>
        </div>
      ) : current?.receipt ? (
        <div className="panel stack" aria-live="polite">
          {current.submitted ? <p role="status">{t('Request submitted. Keep the receipt ID below.')}</p> : null}
          <h3>{t('Erasure request receipt')}</h3>
          <p><strong>{t('Request status')}:</strong> {statusLabel(current.receipt.status)}</p>
          <p><strong>{t('Receipt ID')}:</strong> <code>{current.receipt.id}</code></p>
          <p>{t('Keep this receipt ID for your records.')}</p>
          <dl>
            <div><dt>{t('Requested on')}</dt><dd>{receiptTime(current.receipt.requested_at)}</dd></div>
            <div><dt>{t('Target completion date')}</dt><dd>{receiptTime(current.receipt.due_at)}</dd></div>
            {current.receipt.completed_at ? (
              <div><dt>{t('Completed on')}</dt><dd>{receiptTime(current.receipt.completed_at)}</dd></div>
            ) : null}
          </dl>
          {current.receipt.blocker_code || current.receipt.status === 'blocked' ? (
            <p className="error" role="alert">
              {blockerMessage(current.receipt.blocker_code) ?? t('Resolve the account responsibility noted for this request before erasure can proceed.')}
            </p>
          ) : null}
          <p>{t(current.receipt.status === 'completed'
            ? 'An operator has completed this erasure request.'
            : current.receipt.status === 'blocked'
              ? 'Resolve the blocker above. No organization ownership or platform administrator role will be changed automatically.'
              : current.receipt.status === 'processing'
                ? 'An operator is processing this request. The account has not been erased by this browser action.'
                : 'An operator must review this request. The account has not been erased by this browser action.')}</p>
          <details>
            <summary>{t('Included record counts')}</summary>
            {Object.entries(current.receipt.counts ?? {}).filter(([, count]) => Number.isSafeInteger(count) && count >= 0).length ? (
              <dl>
                {Object.entries(current.receipt.counts ?? {})
                  .filter(([, count]) => Number.isSafeInteger(count) && count >= 0)
                  .map(([category, count]) => (
                    <div key={category}>
                      <dt>{category.replaceAll('_', ' ')}</dt>
                      <dd>{t('{count} records', {count})}</dd>
                    </div>
                  ))}
              </dl>
            ) : <p>{t('No record counts are available.')}</p>}
          </details>
          <button className="button button-secondary" type="button" onClick={refreshStatus}>{t('Refresh request status')}</button>
        </div>
      ) : current?.phase === 'ready' ? (
        <div className="stack">
          <button
            className="button button-secondary"
            type="button"
            aria-expanded={confirming}
            aria-controls={confirmId}
            onClick={() => setConfirmation(confirming ? null : accountContext)}
          >
            {t(confirming ? 'Cancel' : 'Request account erasure')}
          </button>
          <section id={confirmId} className="panel stack" role="group" aria-labelledby={`${confirmId}-heading`} hidden={!confirming}>
            <h3 id={`${confirmId}-heading`}>{t('Confirm account erasure request')}</h3>
            <p>{t('I understand this is a request for account erasure, not an immediate deletion.')}</p>
            <button className="button" type="button" onClick={() => void submitRequest()} disabled={submitting}>
              {t('Confirm erasure request')}
            </button>
          </section>
        </div>
      ) : null}
    </section>
  );
}
