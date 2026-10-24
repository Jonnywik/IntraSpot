'use client';

import {useEffect, useId, useMemo, useRef, useState, useSyncExternalStore, type MouseEvent, type SyntheticEvent} from 'react';
import {ApiError, api} from '@/lib/api';
import {usePreferences} from '@/lib/preferences';
import {formatDate, formatTime} from '@/lib/date';
import {useT} from '@/lib/i18n';
import {
  canLoadAttendance,
  captureAttendanceCommand,
  DESKTOP_ATTENDANCE_QUERY,
  filterAttendanceAttendees,
  isUncertainAttendanceFailure,
  matchesAttendanceCommand,
  registrationReferenceFromLabel,
} from './attendance-helpers.mjs';
import type {AttendanceAuditOut, AttendanceCommand, AttendanceMutationOut, AttendanceOut} from './types';
import styles from './attendance-panel.module.css';

type Resource = {attendance: AttendanceOut; history: AttendanceAuditOut[]};
type Feedback = {key: string; tone: 'success' | 'warning' | 'error'};

function subscribeDesktop(onChange: () => void) {
  if (typeof window === 'undefined') return () => {};
  const query = window.matchMedia(DESKTOP_ATTENDANCE_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

function getDesktopSnapshot() {
  return typeof window !== 'undefined' && window.matchMedia(DESKTOP_ATTENDANCE_QUERY).matches;
}

function apiStatus(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null;
}

export function AttendancePanel({eventId, token}: {eventId: string; token: string}) {
  if (!eventId || !token) return null;
  return <AttendancePanelContent key={`${eventId}\u0000${token}`} eventId={eventId} token={token} />;
}

function AttendancePanelContent({eventId, token}: {eventId: string; token: string}) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const isDesktop = useSyncExternalStore(subscribeDesktop, getDesktopSnapshot, () => false);
  const [expanded, setExpanded] = useState(false);
  const [resource, setResource] = useState<Resource | null>(null);
  const [readStatus, setReadStatus] = useState<'idle' | 'loading' | 'ready' | 'error' | 'forbidden'>('idle');
  const [loading, setLoading] = useState(false);
  const [requiredRevision, setRequiredRevision] = useState(0);
  const requiredRevisionRef = useRef(0);
  const [loadedRevision, setLoadedRevision] = useState(-1);
  const [query, setQuery] = useState('');
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [attempt, setAttempt] = useState<AttendanceCommand | null>(null);
  const attemptRef = useRef<AttendanceCommand | null>(null);
  const [working, setWorking] = useState(false);
  const workingRef = useRef(false);
  const [confirmation, setConfirmation] = useState<{context: object; isOpen: boolean; version: number} | null>(null);
  const context = useMemo(() => Object.freeze({eventId, token}), [eventId, token]);
  const contentId = useId();
  const attendancePath = `/events/${encodeURIComponent(eventId)}/attendance`;
  const historyPath = `${attendancePath}/history`;
  const active = canLoadAttendance({isDesktop, isExpanded: expanded, eventId, token});
  const readControllerRef = useRef<AbortController | null>(null);
  const mutationControllerRef = useRef<AbortController | null>(null);
  const refreshRef = useRef<(() => Promise<void>) | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  const focusReturnRef = useRef<HTMLElement | null>(null);

  useEffect(() => () => {
    refreshRef.current = null;
    readControllerRef.current?.abort();
    mutationControllerRef.current?.abort();
    attemptRef.current = null;
  }, []);

  useEffect(() => {
    if (!active) return;
    let disposed = false;
    let fetching = false;
    let refreshQueued = false;
    let controller: AbortController | null = null;

    const refresh = async () => {
      if (disposed) return;
      if (fetching) {
        refreshQueued = true;
        return;
      }
      fetching = true;
      setLoading(true);
      try {
        do {
          refreshQueued = false;
          controller = new AbortController();
          readControllerRef.current = controller;
          const revision = requiredRevisionRef.current;
          setReadStatus(current => current === 'ready' ? 'ready' : 'loading');
          try {
            const [attendance, history] = await Promise.all([
              api<AttendanceOut>(attendancePath, {token, signal: controller.signal}),
              api<AttendanceAuditOut[]>(historyPath, {token, signal: controller.signal}),
            ]);
            if (disposed || controller.signal.aborted) return;
            if (revision !== requiredRevisionRef.current) {
              refreshQueued = true;
              continue;
            }
            if (!attendance || attendance.event_id !== eventId || !Array.isArray(history)) {
              throw new Error('Attendance response could not be confirmed.');
            }
            setResource({attendance, history});
            setReadStatus('ready');
            setLoadedRevision(revision);
          } catch (error) {
            if (disposed || controller.signal.aborted) return;
            if (revision !== requiredRevisionRef.current) {
              refreshQueued = true;
              continue;
            }
            if ([401, 403].includes(apiStatus(error) ?? -1)) {
              attemptRef.current = null;
              setAttempt(null);
              setResource(null);
              setLoadedRevision(-1);
              setReadStatus('forbidden');
              setFeedback({key: 'Your sign-in or staff access has ended.', tone: 'error'});
              return;
            }
            setReadStatus('error');
            if (!refreshQueued) return;
          } finally {
            if (readControllerRef.current === controller) readControllerRef.current = null;
          }
        } while (refreshQueued && !disposed);
      } finally {
        fetching = false;
        if (!disposed) setLoading(false);
      }
    };

    refreshRef.current = refresh;
    void refresh();
    return () => {
      disposed = true;
      controller?.abort();
      if (readControllerRef.current === controller) readControllerRef.current = null;
      if (refreshRef.current === refresh) refreshRef.current = null;
    };
  }, [active, attendancePath, eventId, historyPath, token]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (confirmation) {
      if (!dialog.open) {
        dialog.showModal();
        cancelRef.current?.focus();
      }
    } else if (dialog.open) {
      dialog.close();
      window.requestAnimationFrame(() => {
        if (focusReturnRef.current?.isConnected) focusReturnRef.current.focus();
        else panelRef.current?.focus();
      });
    }
  }, [confirmation]);

  function requireFreshState() {
    const next = requiredRevisionRef.current + 1;
    requiredRevisionRef.current = next;
    setRequiredRevision(next);
  }

  function refreshAfterResponse() {
    requireFreshState();
    void refreshRef.current?.();
  }

  const fresh = Boolean(resource && readStatus === 'ready' && loadedRevision === requiredRevision && !loading);
  const canStartAction = Boolean(active && token && fresh && resource?.attendance.writable && !attempt && !working);
  const visibleAttendees = useMemo(
    () => filterAttendanceAttendees(resource?.attendance.attendees ?? [], query),
    [resource, query],
  );

  async function sendCommand(command: AttendanceCommand, retry: boolean) {
    if (!active || workingRef.current || command.token !== token || command.eventId !== eventId || !matchesAttendanceCommand(command, context)) return;
    if (retry) {
      if (attemptRef.current !== command) return;
    } else {
      if (!canStartAction || attemptRef.current || !resource || command.version !== resource.attendance.version) {
        if (active && resource && command.version !== resource.attendance.version) {
          setFeedback({key: 'The attendance changed while you were reviewing it. Current state, roster, and history have been refreshed. Review before making another change.', tone: 'warning'});
          refreshAfterResponse();
        }
        return;
      }
      attemptRef.current = command;
      setAttempt(command);
    }

    workingRef.current = true;
    setWorking(true);
    const controller = new AbortController();
    mutationControllerRef.current = controller;
    try {
      const result = await api<AttendanceMutationOut>(command.path, {
        method: command.kind === 'session' ? 'POST' : 'PUT',
        token: command.token,
        body: command.body,
        signal: controller.signal,
      });
      if (!result || result.event_id !== eventId || result.version !== command.version + 1 ||
        result.is_open !== command.sessionOpen || result.registration_id !== command.registrationId ||
        result.attended !== (command.kind === 'mark' ? command.value : null)) {
        throw new Error('Attendance response could not be confirmed.');
      }
      if (controller.signal.aborted) return;
      attemptRef.current = null;
      setAttempt(null);
      setFeedback({key: 'Attendance change recorded.', tone: 'success'});
      refreshAfterResponse();
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = apiStatus(error);
      if (status === 401 || status === 403) {
        attemptRef.current = null;
        setAttempt(null);
        setResource(null);
        setLoadedRevision(-1);
        setReadStatus('forbidden');
        setFeedback({key: 'Your sign-in or staff access has ended.', tone: 'error'});
      } else if (status === 409) {
        attemptRef.current = null;
        setAttempt(null);
        setFeedback({key: 'The attendance changed while you were reviewing it. Current state, roster, and history have been refreshed. Review before making another change.', tone: 'warning'});
        refreshAfterResponse();
      } else if (isUncertainAttendanceFailure(status)) {
        setFeedback({key: 'The attendance change could not be confirmed. Retry the same request.', tone: 'warning'});
        refreshAfterResponse();
      } else {
        attemptRef.current = null;
        setAttempt(null);
        setFeedback({key: 'The attendance change was rejected. Current state, roster, and history are refreshing.', tone: 'error'});
        refreshAfterResponse();
      }
    } finally {
      if (!controller.signal.aborted) {
        if (mutationControllerRef.current === controller) mutationControllerRef.current = null;
        workingRef.current = false;
        setWorking(false);
      }
    }
  }

  function startCommand(kind: 'session' | 'mark', registrationId: string | null, value: boolean, version: number) {
    if (!canStartAction || !resource || attemptRef.current || workingRef.current) return;
    if (version !== resource.attendance.version) {
      setFeedback({key: 'The attendance changed while you were reviewing it. Current state, roster, and history have been refreshed. Review before making another change.', tone: 'warning'});
      refreshAfterResponse();
      return;
    }
    try {
      const command = captureAttendanceCommand({
        context,
        eventId,
        token,
        kind,
        registrationId,
        value,
        sessionOpen: kind === 'session' ? value : resource.attendance.is_open,
        version,
        clientKey: window.crypto.randomUUID(),
      });
      void sendCommand(command, false);
    } catch {
      setFeedback({key: 'A secure request key could not be created. Please use an updated browser.', tone: 'error'});
    }
  }

  function openSessionConfirmation(event: MouseEvent<HTMLButtonElement>) {
    if (!canStartAction || !resource) return;
    focusReturnRef.current = event.currentTarget;
    setConfirmation({context, isOpen: !resource.attendance.is_open, version: resource.attendance.version});
  }

  function cancelConfirmation(event?: SyntheticEvent<HTMLDialogElement>) {
    event?.preventDefault();
    setConfirmation(null);
  }

  function confirmSession() {
    const reviewed = confirmation;
    const current = resource?.attendance;
    setConfirmation(null);
    if (!canStartAction || !reviewed || reviewed.context !== context || !current || reviewed.version !== current.version || reviewed.isOpen === current.is_open) {
      setFeedback({key: 'The attendance changed while you were reviewing it. Current state, roster, and history have been refreshed. Review before making another change.', tone: 'warning'});
      refreshAfterResponse();
      return;
    }
    startCommand('session', null, reviewed.isOpen, reviewed.version);
  }

  function retryAttendanceRefresh() {
    setReadStatus('loading');
    requireFreshState();
    void refreshRef.current?.();
  }

  if (!isDesktop) return null;

  const attendance = resource?.attendance;
  const sessionStatus = attendance?.is_open ? 'Open' : 'Closed';
  const rosterEmpty = Boolean(attendance && attendance.attendees.length === 0);
  const filteredEmpty = Boolean(attendance?.attendees.length && visibleAttendees.length === 0);
  const retryableAttempt = attempt && matchesAttendanceCommand(attempt, context) ? attempt : null;

  return (
    <section ref={panelRef} className={styles.root} tabIndex={-1} aria-label={t('Manual attendance')}>
      <button
        className={`button button-secondary ${styles.expandButton}`}
        type="button"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => {
          const next = !expanded;
          setExpanded(next);
          setResource(null);
          setReadStatus(next ? 'loading' : 'idle');
          setLoading(false);
          setLoadedRevision(-1);
          setQuery('');
          setFeedback(null);
        }}
      >
        <span aria-hidden="true">{expanded ? '−' : '+'}</span>
        {t('Manual attendance')}
      </button>

      <div id={contentId} className={styles.content} hidden={!expanded}>
        <header className={styles.header}>
          <div>
            <h3>{t('Attendance')}</h3>
            <p className={styles.muted}>{t('Check-in is available only for confirmed attendees while the session is open.')}</p>
          </div>
          {attendance && (
            <span className={styles.sessionStatus} data-open={attendance.is_open} aria-live="polite">
              <span aria-hidden="true">●</span>
              {t('Check-in is {status}', {status: t(sessionStatus)})}
            </span>
          )}
        </header>

        {loading && <p className={styles.muted} role="status">{resource ? t('Refreshing attendance…') : t('Loading attendance…')}</p>}
        {readStatus === 'forbidden' && <p className="panel error" role="alert">{t('Your sign-in or staff access has ended.')}</p>}
        {readStatus === 'error' && (
          <div className="panel error" role="alert">
            <p>{t('Could not load attendance.')}</p>
            <button className="button button-secondary" type="button" onClick={retryAttendanceRefresh}>{t('Retry attendance refresh')}</button>
          </div>
        )}
        {feedback && <p className={`panel ${feedback.tone === 'success' ? 'success' : feedback.tone === 'error' ? 'error' : ''}`} role={feedback.tone === 'error' ? 'alert' : 'status'}>{t(feedback.key)}</p>}

        {retryableAttempt && (
          <div className={styles.retryBox}>
            <p>{t('Retrying reuses the original version and request key.')}</p>
            <button className="button button-secondary" type="button" disabled={working || readStatus === 'forbidden'} onClick={() => void sendCommand(retryableAttempt, true)}>
              {working ? t('Refreshing attendance…') : t('Retry same attendance request')}
            </button>
          </div>
        )}

        {attendance && readStatus !== 'forbidden' && (
          <>
            <p className={styles.counts} aria-live="polite">
              {t('Checked in {checked} of {confirmed} confirmed attendees.', {
                checked: attendance.checked_in_count,
                confirmed: attendance.confirmed_count,
              })}
            </p>
            {!attendance.writable && <p className={styles.muted}>{t('Attendance is read-only because this event is not published and approved.')}</p>}
            {attendance.writable && !attendance.is_open && <p className={styles.muted}>{t('The check-in session must be open before changing attendee check-ins.')}</p>}
            <div className={styles.actions}>
              <button className="button" type="button" disabled={!canStartAction} onClick={openSessionConfirmation}>
                {t(attendance.is_open ? 'Close check-in' : 'Open check-in')}
              </button>
              <button className="button button-secondary" type="button" disabled={loading} onClick={retryAttendanceRefresh}>
                {t('Refresh attendance')}
              </button>
            </div>
            {attendance.attendees.length > 0 && (
              <label className={styles.search}>
                {t('Search confirmed attendees by registration reference')}
                <input type="search" value={query} onChange={event => setQuery(event.target.value)} />
              </label>
            )}
            {rosterEmpty ? <p className={styles.muted}>{t('No confirmed attendees.')}</p> : filteredEmpty ? (
              <p className={styles.muted}>{t('No confirmed attendees match this registration reference.')}</p>
            ) : (
              <ul className={styles.roster}>
                {visibleAttendees.map(attendee => (
                  <li className={styles.attendee} key={attendee.registration_id}>
                    <span className={styles.label}>{t('Registration reference: {reference}', {reference: registrationReferenceFromLabel(attendee.participant_label)})}</span>
                    <span className={styles.attendeeStatus} data-checked-in={attendee.attended}>
                      <span aria-hidden="true">{attendee.attended ? '✓' : '○'}</span>
                      {t(attendee.attended ? 'Checked in' : 'Not checked in')}
                    </span>
                    <button
                      className="button button-secondary"
                      type="button"
                      disabled={!canStartAction || !attendance.is_open}
                      aria-label={t(attendee.attended ? 'Clear check-in for registration {reference}' : 'Check in registration {reference}', {reference: registrationReferenceFromLabel(attendee.participant_label)})}
                      onClick={() => startCommand('mark', attendee.registration_id, !attendee.attended, attendance.version)}
                    >
                      {t(attendee.attended ? 'Clear check-in' : 'Check in')}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className={styles.correctionNote}>{t('Clearing a check-in is an attendance correction. It does not withdraw a registration.')}</p>
            <details className={styles.history}>
              <summary>{t('Attendance history ({count})', {count: resource?.history.length ?? 0})}</summary>
              {!resource?.history.length ? <p className={styles.muted}>{t('No attendance history yet.')}</p> : (
                <ol className={styles.historyList}>
                  {resource.history.map(entry => {
                    const summary = entry.action === 'session'
                      ? t(entry.value ? 'Check-in session opened' : 'Check-in session closed')
                      : entry.value
                        ? t('An attendee was checked in.')
                        : t('An attendee check-in was cleared.');
                    const valueLabel = (value: boolean) => {
                      if (entry.action === 'session') return t(value ? 'Open' : 'Closed');
                      return t(value ? 'Checked in' : 'Not checked in');
                    };
                    const validTime = Number.isFinite(Date.parse(entry.created_at));
                    return (
                      <li key={entry.id} className={styles.historyEntry}>
                        <p>{summary}</p>
                        {entry.registration_id && <span className={styles.historyReference}>{t('Registration reference: {reference}', {reference: entry.registration_id})}</span>}
                        <span className={styles.historyReference}>{t('Staff reference: {reference}', {reference: entry.actor_id})}</span>
                        <span>{t('Changed from {previous} to {current}', {previous: valueLabel(entry.previous_value), current: valueLabel(entry.value)})}</span>
                        <span>{t('Version {version}', {version: entry.version})}</span>
                        <time dateTime={entry.created_at}>
                          {validTime
                            ? `${formatDate(entry.created_at, language)} · ${formatTime(entry.created_at, language)} (${t('Manila time')})`
                            : entry.created_at}
                        </time>
                      </li>
                    );
                  })}
                </ol>
              )}
            </details>
          </>
        )}
        {resource && loadedRevision !== requiredRevision && !loading && readStatus !== 'forbidden' && (
          <p className={styles.muted} role="status">{t('Refreshing current attendance before new actions…')}</p>
        )}
      </div>

      <dialog
        ref={dialogRef}
        className={styles.dialog}
        aria-labelledby={`${contentId}-confirm-title`}
        onCancel={cancelConfirmation}
      >
        {confirmation && (
          <div className={styles.dialogContent}>
            <h3 id={`${contentId}-confirm-title`}>{t(confirmation.isOpen ? 'Open check-in?' : 'Close check-in?')}</h3>
            <p>{t(confirmation.isOpen
              ? 'This opens staff check-in for confirmed attendees.'
              : 'This closes staff check-in. Confirmed check-ins remain recorded.')}</p>
            <div className={styles.dialogActions}>
              <button ref={cancelRef} className="button button-secondary" type="button" onClick={() => cancelConfirmation()}>{t('Cancel')}</button>
              <button className="button" type="button" disabled={working} onClick={confirmSession}>{t('Confirm')}</button>
            </div>
          </div>
        )}
      </dialog>
    </section>
  );
}
