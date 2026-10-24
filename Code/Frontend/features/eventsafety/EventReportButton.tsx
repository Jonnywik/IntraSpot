'use client';

import {useEffect, useRef, useState, type FormEvent} from 'react';
import {ApiError, api} from '@/lib/api';
import {captureSafetyCommand, isUncertainSafetyFailure, matchesSafetyCommand, type SafetyCommand} from './safety-helpers.mjs';
import type {EventReportInput, EventReportReceipt, SafetyReportReason} from './types';
import {SafetyDialog} from './SafetyDialog';
import {useSafetyTranslate} from './use-safety-ui';
import styles from './eventsafety.module.css';

function statusOf(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null;
}

type Feedback = {contextKey: string; key: string; tone: 'success' | 'warning' | 'error'};

export function EventReportButton({eventId, token}: {eventId: string; token: string}) {
  const t = useSafetyTranslate();
  const contextKey = JSON.stringify([eventId, token]);
  const path = `/events/${encodeURIComponent(eventId)}/event-reports`;
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<SafetyReportReason | ''>('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [receivedContext, setReceivedContext] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<{contextKey: string; command: SafetyCommand} | null>(null);
  const attemptRef = useRef<SafetyCommand | null>(null);
  const mutationRef = useRef<AbortController | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  useEffect(() => () => {
    mutationRef.current?.abort();
    mutationRef.current = null;
    attemptRef.current = null;
  }, [contextKey]);

  async function sendReport(command: SafetyCommand, retry: boolean) {
    if (busyRef.current || !matchesSafetyCommand(command, contextKey)) return;
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
      const result = await api<EventReportReceipt>(command.path, {
        method: 'POST', token, body: command.body as EventReportInput, signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (!result || result.event_id !== eventId || typeof result.id !== 'string' || !result.id) {
        throw new Error('The report receipt could not be confirmed.');
      }
      attemptRef.current = null;
      setAttempt(null);
      setReceivedContext(contextKey);
      setFeedback({contextKey, key: 'Your event safety report was received.', tone: 'success'});
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = statusOf(error);
      if (isUncertainSafetyFailure(status)) {
        setFeedback({contextKey, key: 'We could not confirm whether your report was received. Retry the same report to check its saved result.', tone: 'warning'});
      } else {
        attemptRef.current = null;
        setAttempt(null);
        setFeedback({
          contextKey,
          key: status === 401 || status === 403
            ? 'Your sign-in or event access has ended.'
            : 'The report could not be submitted. Refresh the event and try again.',
          tone: 'error',
        });
      }
    } finally {
      if (!controller.signal.aborted) {
        if (mutationRef.current === controller) mutationRef.current = null;
        busyRef.current = false;
        setBusy(false);
      }
    }
  }

  function confirmReport(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!reason || receivedContext === contextKey || attemptRef.current) return;
    setOpen(false);
    try {
      const command = captureSafetyCommand(contextKey, path, {
        reason,
        client_key: window.crypto.randomUUID(),
      });
      void sendReport(command, false);
    } catch {
      setFeedback({contextKey, key: 'A secure request key could not be created. Please use an updated browser.', tone: 'error'});
    }
  }

  const visibleAttempt = attempt?.contextKey === contextKey ? attempt.command : null;
  const visibleFeedback = feedback?.contextKey === contextKey ? feedback : null;
  const received = receivedContext === contextKey;

  return (
    <section className={styles.root} aria-label={t('Report event for safety review')}>
      <button
        ref={triggerRef}
        className="button button-secondary"
        type="button"
        disabled={!token || received || busy || Boolean(visibleAttempt)}
        onClick={() => { setReason(''); setOpen(true); }}
      >
        {t('Report event')}
      </button>
      <p className={styles.muted}>{t('Choose a reason. Reporting does not automatically hide an event.')}</p>
      {visibleFeedback && <p className={styles.feedback} data-tone={visibleFeedback.tone} role={visibleFeedback.tone === 'error' ? 'alert' : 'status'}>{t(visibleFeedback.key)}</p>}
      {visibleAttempt && (
        <div className={styles.attempt}>
          <button className="button button-secondary" type="button" disabled={busy} onClick={() => void sendReport(visibleAttempt, true)}>
            {t(busy ? 'Submitting report…' : 'Retry same report')}
          </button>
        </div>
      )}
      <SafetyDialog
        open={open}
        title={t('Report event for safety review')}
        description={t('Choose a reason. Reporting does not automatically hide an event.')}
        confirmLabel={t('Submit report')}
        onCancel={() => setOpen(false)}
        onConfirm={() => confirmReport()}
        returnFocusRef={triggerRef}
        t={t}
      >
        <label className={styles.field}>
          {t('Reason')}
          <select required value={reason} onChange={event => setReason(event.target.value as SafetyReportReason | '')}>
            <option value="">{t('Select a reason')}</option>
            <option value="safety">{t('Safety concern')}</option>
            <option value="deception">{t('Deception')}</option>
          </select>
        </label>
      </SafetyDialog>
    </section>
  );
}
