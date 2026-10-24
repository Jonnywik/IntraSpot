'use client';

import {useCallback, useEffect, useRef, useState, type MouseEvent} from 'react';
import {ApiError, api} from '@/lib/api';
import {formatDate, formatTime} from '@/lib/date';
import {usePreferences} from '@/lib/preferences';
import {captureSafetyCommand, isUncertainSafetyFailure, matchesSafetyCommand, type SafetyCommand} from './safety-helpers.mjs';
import type {SuspensionAction, SuspensionInput, SuspensionOut} from './types';
import {SafetyDialog} from './SafetyDialog';
import {useDesktopManagement, useSafetyResource, useSafetyTranslate} from './use-safety-ui';
import styles from './eventsafety.module.css';

function statusOf(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null;
}

type Feedback = {contextKey: string; key: string; tone: 'success' | 'warning' | 'error'};
type Confirmation = {contextKey: string; action: SuspensionAction; version: number; days: number | null};

export function OrganizationSuspensionPanel({orgId, token}: {orgId: string; token: string}) {
  const isDesktop = useDesktopManagement();
  if (!isDesktop) return null;
  return <OrganizationSuspensionContext key={JSON.stringify([orgId, token])} orgId={orgId} token={token} />;
}

function OrganizationSuspensionContext({orgId, token}: {orgId: string; token: string}) {
  const t = useSafetyTranslate();
  const {preferences} = usePreferences();
  const contextKey = JSON.stringify([orgId, token]);
  const path = `/organizations/${encodeURIComponent(orgId)}/suspension`;
  const [expanded, setExpanded] = useState(false);
  const [resourceEpoch, setResourceEpoch] = useState(0);
  const active = expanded && Boolean(orgId && token);
  const loader = useCallback(async (signal: AbortSignal) => {
    const result = await api<SuspensionOut>(path, {token, signal});
    if (!result || result.org_id !== orgId) throw new Error('The suspension response did not match this organization.');
    return result;
  }, [orgId, path, token]);
  const resource = useSafetyResource(active, JSON.stringify([contextKey, resourceEpoch]), loader);
  const [days, setDays] = useState(7);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [attempt, setAttempt] = useState<{contextKey: string; command: SafetyCommand} | null>(null);
  const attemptRef = useRef<SafetyCommand | null>(null);
  const mutationRef = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    return () => {
      mutationRef.current?.abort();
      mutationRef.current = null;
      attemptRef.current = null;
    };
  }, []);

  async function sendCommand(command: SafetyCommand, retry: boolean) {
    if (!active || busyRef.current || !matchesSafetyCommand(command, contextKey)) return;
    if (retry) {
      if (attemptRef.current !== command) return;
    } else if (attemptRef.current) {
      return;
    }
    if (!retry) {
      attemptRef.current = command;
      setAttempt({contextKey, command});
    }
    busyRef.current = true;
    setBusy(true);
    const controller = new AbortController();
    mutationRef.current?.abort();
    mutationRef.current = controller;
    try {
      const result = await api<SuspensionOut>(command.path, {
        method: 'POST', token, body: command.body as SuspensionInput, signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (!result || result.org_id !== orgId || result.version !== Number(command.body.version) + 1) {
        throw new Error('The suspension change could not be confirmed.');
      }
      attemptRef.current = null;
      setAttempt(null);
      setFeedback({contextKey, key: 'The suspension change was saved.', tone: 'success'});
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = statusOf(error);
      if (status === 409) {
        attemptRef.current = null;
        setAttempt(null);
        setFeedback({contextKey, key: 'The organization suspension changed while you were reviewing it. Refresh and review the latest status.', tone: 'warning'});
      } else if (isUncertainSafetyFailure(status)) {
        setFeedback({contextKey, key: 'The suspension change could not be confirmed. Retry the same request.', tone: 'warning'});
      } else {
        attemptRef.current = null;
        setAttempt(null);
        setFeedback({
          contextKey,
          key: status === 401 || status === 403
            ? 'Your sign-in or staff access has ended.'
            : 'The suspension change was rejected. Refresh the latest status before trying again.',
          tone: 'error',
        });
      }
    } finally {
      if (!controller.signal.aborted) {
        if (mutationRef.current === controller) mutationRef.current = null;
        busyRef.current = false;
        setBusy(false);
        resource.refresh();
      }
    }
  }

  function openConfirmation(action: SuspensionAction, event: MouseEvent<HTMLButtonElement>) {
    const current = resource.data;
    if (!resource.fresh || !current || current.can_manage !== true || busyRef.current || attemptRef.current) return;
    if (action === 'resume' && !current.is_suspended) return;
    if (action === 'suspend' && current.is_suspended) return;
    returnFocusRef.current = event.currentTarget;
    setConfirmation({contextKey, action, version: current.version, days: action === 'suspend' ? days : null});
  }

  function confirmAction() {
    const reviewed = confirmation;
    const current = resource.data;
    setConfirmation(null);
    if (!reviewed || reviewed.contextKey !== contextKey || !resource.fresh || !current || current.version !== reviewed.version || current.can_manage !== true) {
      setFeedback({contextKey, key: 'The organization suspension changed while you were reviewing it. Refresh and review the latest status.', tone: 'warning'});
      resource.refresh();
      return;
    }
    try {
      const command = captureSafetyCommand(contextKey, path, {
        action: reviewed.action,
        version: reviewed.version,
        days: reviewed.days,
        client_key: window.crypto.randomUUID(),
      });
      void sendCommand(command, false);
    } catch {
      setFeedback({contextKey, key: 'A secure request key could not be created. Please use an updated browser.', tone: 'error'});
    }
  }

  const current = resource.data;
  const visibleAttempt = attempt?.contextKey === contextKey ? attempt.command : null;
  const visibleFeedback = feedback?.contextKey === contextKey ? feedback : null;
  const until = current?.is_suspended && current.suspended_until ? Date.parse(current.suspended_until) : NaN;
  const selectedDays = confirmation?.action === 'suspend' ? confirmation.days ?? 7 : days;
  const dialogDescription = confirmation?.action === 'resume'
    ? t('Resume this organization now? Event hide and terminal states remain in effect.')
    : t('Suspend this organization for {days} days? Existing participants keep access, while new admissions stop.', {days: selectedDays});

  return (
    <section className={`${styles.root} ${styles.desktopOnly}`} aria-label={t('Organization suspension')}>
      <button className="button button-secondary" type="button" aria-expanded={expanded} onClick={() => {
        if (!expanded) setResourceEpoch(value => value + 1);
        setExpanded(value => !value);
      }}>
        {t('Organization suspension')}
      </button>
      {expanded && (
        <div className={styles.panel} aria-busy={resource.loading || busy}>
          <div className={styles.heading}>
            <h3>{t('Organization suspension')}</h3>
            <button className="button button-secondary" type="button" disabled={resource.loading} onClick={resource.refresh}>{t('Refresh safety status')}</button>
          </div>
          {resource.loading && <p className={styles.muted} role="status">{t('Loading organization suspension…')}</p>}
          {resource.status === 'forbidden' && <p className="panel error" role="alert">{t('Your sign-in or staff access has ended.')}</p>}
          {resource.status === 'error' && <div className={styles.feedback} data-tone="error" role="alert"><p>{t('The organization suspension status could not be loaded.')}</p><button className="button button-secondary" type="button" onClick={resource.refresh}>{t('Retry loading suspension')}</button></div>}
          {visibleFeedback && <p className={styles.feedback} data-tone={visibleFeedback.tone} role={visibleFeedback.tone === 'error' ? 'alert' : 'status'}>{t(visibleFeedback.key)}</p>}
          {visibleAttempt && <div className={styles.attempt}><p>{t('The suspension change could not be confirmed. Retry the same request.')}</p><button className="button button-secondary" type="button" disabled={busy} onClick={() => void sendCommand(visibleAttempt, true)}>{t(busy ? 'Saving suspension…' : 'Retry same suspension request')}</button></div>}
          {current && (
            <>
              <span className={styles.status} data-active={current.is_suspended} aria-live="polite"><span aria-hidden="true">●</span>{t(current.is_suspended ? 'Suspended' : 'Not suspended')}</span>
              {current.is_suspended && Number.isFinite(until) && <p className={styles.muted}>{t('Suspended until')}: <time dateTime={current.suspended_until ?? undefined}>{formatDate(current.suspended_until ?? '', preferences.language)} · {formatTime(current.suspended_until ?? '', preferences.language)} ({t('Manila time')})</time></p>}
              {current.can_manage === true && resource.fresh && !visibleAttempt && (
                <>
                  {current.is_suspended ? (
                    <button className="button button-secondary" type="button" disabled={busy} onClick={event => openConfirmation('resume', event)}>{t('Resume organization now')}</button>
                  ) : (
                    <div className={styles.actions}>
                      <label className={styles.field}>
                        {t('Choose suspension length')}
                        <select value={days} onChange={event => setDays(Number(event.target.value))}>
                          {Array.from({length: 30}, (_, index) => index + 1).map(value => <option key={value} value={value}>{t('{days} days', {days: value})}</option>)}
                        </select>
                      </label>
                      <button className="button button-danger" type="button" disabled={busy} onClick={event => openConfirmation('suspend', event)}>{t('Suspend organization')}</button>
                    </div>
                  )}
                </>
              )}
              {current && !resource.fresh && !resource.loading && <p className={styles.muted} role="status">{t('Refreshing current organization safety status…')}</p>}
            </>
          )}
        </div>
      )}
      <SafetyDialog
        open={expanded && Boolean(confirmation?.contextKey === contextKey)}
        title={confirmation?.action === 'resume' ? t('Resume organization now') : t('Suspend organization')}
        description={dialogDescription}
        confirmLabel={t('Confirm')}
        confirmDisabled={busy}
        onCancel={() => setConfirmation(null)}
        onConfirm={confirmAction}
        returnFocusRef={returnFocusRef}
        t={t}
      />
    </section>
  );
}
