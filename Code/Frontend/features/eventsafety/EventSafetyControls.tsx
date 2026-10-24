'use client';

import {useCallback, useEffect, useRef, useState, type MouseEvent} from 'react';
import {ApiError, api} from '@/lib/api';
import {captureSafetyCommand, isUncertainSafetyFailure, matchesSafetyCommand, type SafetyCommand} from './safety-helpers.mjs';
import type {EventSafetyAction, EventSafetyInput, EventSafetyOut} from './types';
import {SafetyDialog} from './SafetyDialog';
import {useDesktopManagement, useSafetyResource, useSafetyTranslate} from './use-safety-ui';
import styles from './eventsafety.module.css';

function statusOf(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null;
}

type Feedback = {contextKey: string; key: string; tone: 'success' | 'warning' | 'error'};
type Confirmation = {contextKey: string; action: EventSafetyAction; version: number};

const actionLabels: Record<EventSafetyAction, string> = {
  hide: 'Hide event',
  restore: 'Restore the hide you manage',
  remove: 'Permanently remove event',
  cancel: 'Cancel event',
};

const confirmationText: Record<EventSafetyAction, string> = {
  hide: 'Hide this event from public discovery? Existing participants can continue using the event.',
  restore: 'Restore only the hide you manage? Any other hide or terminal state remains in effect.',
  remove: 'Permanently remove this event? It cannot be restored. Registration records and audit history are retained.',
  cancel: 'Cancel this event? It cannot be reopened. Registration records and audit history are retained.',
};

export function EventSafetyControls({eventId, token}: {eventId: string; token: string}) {
  const isDesktop = useDesktopManagement();
  if (!isDesktop) return null;
  return <EventSafetyControlsContext key={JSON.stringify([eventId, token])} eventId={eventId} token={token} />;
}

function EventSafetyControlsContext({eventId, token}: {eventId: string; token: string}) {
  const t = useSafetyTranslate();
  const contextKey = JSON.stringify([eventId, token]);
  const path = `/events/${encodeURIComponent(eventId)}/safety`;
  const [expanded, setExpanded] = useState(false);
  const [resourceEpoch, setResourceEpoch] = useState(0);
  const active = expanded && Boolean(eventId && token);
  const loader = useCallback(async (signal: AbortSignal) => {
    const result = await api<EventSafetyOut>(path, {token, signal});
    if (!result || result.event_id !== eventId) throw new Error('The event safety response did not match this event.');
    return result;
  }, [eventId, path, token]);
  const resource = useSafetyResource(active, JSON.stringify([contextKey, resourceEpoch]), loader);
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
      const result = await api<EventSafetyOut>(command.path, {
        method: 'POST', token, body: command.body as EventSafetyInput, signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (!result || result.event_id !== eventId || result.version !== Number(command.body.version) + 1) {
        throw new Error('The event safety change could not be confirmed.');
      }
      attemptRef.current = null;
      setAttempt(null);
      setFeedback({contextKey, key: 'The event safety change was saved.', tone: 'success'});
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = statusOf(error);
      if (status === 409) {
        attemptRef.current = null;
        setAttempt(null);
        setFeedback({contextKey, key: 'This event changed while you were reviewing it. Refresh and review the latest safety status before making another change.', tone: 'warning'});
      } else if (isUncertainSafetyFailure(status)) {
        setFeedback({contextKey, key: 'The event safety change could not be confirmed. Retry the same request.', tone: 'warning'});
      } else {
        attemptRef.current = null;
        setAttempt(null);
        setFeedback({
          contextKey,
          key: status === 401 || status === 403
            ? 'Your sign-in or staff access has ended.'
            : 'The event safety change was rejected. Refresh the latest status before trying again.',
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

  function openConfirmation(action: EventSafetyAction, event: MouseEvent<HTMLButtonElement>) {
    const current = resource.data;
    if (!resource.fresh || !current || busyRef.current || attemptRef.current) return;
    const allowed = action === 'hide' ? current.can_hide
      : action === 'restore' ? current.can_restore
        : action === 'remove' ? current.can_remove : current.can_cancel;
    if (allowed !== true) return;
    returnFocusRef.current = event.currentTarget;
    setConfirmation({contextKey, action, version: current.version});
  }

  function confirmAction() {
    const reviewed = confirmation;
    const current = resource.data;
    setConfirmation(null);
    if (!reviewed || reviewed.contextKey !== contextKey || !resource.fresh || !current || current.version !== reviewed.version) {
      setFeedback({contextKey, key: 'This event changed while you were reviewing it. Refresh and review the latest safety status before making another change.', tone: 'warning'});
      resource.refresh();
      return;
    }
    try {
      const command = captureSafetyCommand(contextKey, path, {
        action: reviewed.action,
        version: reviewed.version,
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
  const actions: Array<[EventSafetyAction, boolean]> = current ? [
    ['hide', current.can_hide === true],
    ['restore', current.can_restore === true],
    ['remove', current.can_remove === true],
    ['cancel', current.can_cancel === true],
  ] : [];

  return (
    <section className={`${styles.root} ${styles.desktopOnly}`} aria-label={t('Event safety controls')}>
      <button className="button button-secondary" type="button" aria-expanded={expanded} onClick={() => {
        if (!expanded) setResourceEpoch(value => value + 1);
        setExpanded(value => !value);
      }}>
        {t('Event safety controls')}
      </button>
      {expanded && (
        <div className={styles.panel} aria-busy={resource.loading || busy}>
          <div className={styles.heading}>
            <h3>{t('Event safety controls')}</h3>
            <button className="button button-secondary" type="button" disabled={resource.loading} onClick={resource.refresh}>{t('Refresh safety status')}</button>
          </div>
          {resource.loading && <p className={styles.muted} role="status">{t('Loading event safety controls…')}</p>}
          {resource.status === 'forbidden' && <p className="panel error" role="alert">{t('Your sign-in or staff access has ended.')}</p>}
          {resource.status === 'error' && <div className={styles.feedback} data-tone="error" role="alert"><p>{t('The event safety status could not be loaded.')}</p><button className="button button-secondary" type="button" onClick={resource.refresh}>{t('Retry loading safety status')}</button></div>}
          {visibleFeedback && <p className={styles.feedback} data-tone={visibleFeedback.tone} role={visibleFeedback.tone === 'error' ? 'alert' : 'status'}>{t(visibleFeedback.key)}</p>}
          {visibleAttempt && <div className={styles.attempt}><p>{t('The event safety change could not be confirmed. Retry the same request.')}</p><button className="button button-secondary" type="button" disabled={busy} onClick={() => void sendCommand(visibleAttempt, true)}>{t(busy ? 'Saving safety change…' : 'Retry same safety request')}</button></div>}
          {current && (
            <>
              <div className={styles.statusList} aria-live="polite">
                <span className={styles.status} data-active={current.org_hidden}><span aria-hidden="true">●</span>{t('Organization hide')}: {t(current.org_hidden ? 'Hidden' : 'Not hidden')}</span>
                <span className={styles.status} data-active={current.platform_hidden}><span aria-hidden="true">●</span>{t('Platform hide')}: {t(current.platform_hidden ? 'Hidden' : 'Not hidden')}</span>
                {current.removed && <span className={styles.status} data-active="true"><span aria-hidden="true">●</span>{t('Event removed')}</span>}
                {current.cancelled && <span className={styles.status} data-active="true"><span aria-hidden="true">●</span>{t('Event cancelled')}</span>}
              </div>
              <p className={styles.muted}>{t(current.registration_available ? 'New admissions available' : 'New admissions unavailable')}</p>
              <p className={styles.muted}>{t('Hiding an event does not remove existing confirmed participation or chat.')}</p>
              {resource.fresh && !visibleAttempt && <div className={styles.actions}>
                {actions.filter(([, allowed]) => allowed).map(([action]) => (
                  <button
                    key={action}
                    className={`button ${action === 'remove' || action === 'cancel' ? 'button-danger' : 'button-secondary'}`}
                    type="button"
                    disabled={busy}
                    onClick={event => openConfirmation(action, event)}
                  >{t(actionLabels[action])}</button>
                ))}
              </div>}
            </>
          )}
          {current && !resource.fresh && !resource.loading && <p className={styles.muted} role="status">{t('Refreshing current event safety status…')}</p>}
        </div>
      )}
      <SafetyDialog
        open={expanded && Boolean(confirmation?.contextKey === contextKey)}
        title={confirmation ? t(actionLabels[confirmation.action]) : ''}
        description={confirmation ? t(confirmationText[confirmation.action]) : ''}
        confirmLabel={confirmation ? t(actionLabels[confirmation.action]) : t('Confirm')}
        confirmDisabled={busy}
        onCancel={() => setConfirmation(null)}
        onConfirm={confirmAction}
        returnFocusRef={returnFocusRef}
        t={t}
      />
    </section>
  );
}
