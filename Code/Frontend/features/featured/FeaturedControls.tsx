'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { ApiError, api } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { useApiResource } from '@/lib/use-api-resource';
import { usePreferences } from '@/lib/preferences';
import type { FeaturedDecision, FeaturedDecisionAction, FeaturedRequest, FeaturedRequestStatus } from './types';
import styles from './featured.module.css';

type DisplayStatus = FeaturedRequestStatus | 'scheduled' | 'active';
type ReviewAction = 'approve' | 'reject' | 'revoke';

const statusMessages: Record<DisplayStatus, string> = {
  pending: 'Pending review',
  paused: 'Paused — review required',
  approved: 'Approved',
  scheduled: 'Scheduled',
  active: 'Active',
  expired: 'Expired',
  rejected: 'Rejected',
  revoked: 'Revoked',
};

const actionMessages: Record<FeaturedDecisionAction, string> = {
  requested: 'Requested',
  approved: 'Approved',
  rejected: 'Rejected',
  revoked: 'Revoked',
  paused: 'Paused — review required',
};

function formatManilaDateTime(value: string, language: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return new Intl.DateTimeFormat(language === 'fil' ? 'fil-PH' : 'en-PH', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Manila',
  }).format(date);
}

function manilaInputValue(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Manila',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

function manilaInputTime(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  const timestamp = Date.parse(`${value}:00+08:00`);
  if (!Number.isFinite(timestamp) || manilaInputValue(new Date(timestamp)) !== value) return null;
  return timestamp;
}

function useFeatureTime() {
  const [time, setTime] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setTime(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);
  return time;
}

function displayStatus(request: FeaturedRequest, now: number): DisplayStatus {
  const eventStartsAt = Date.parse(request.event.starts_at);
  if (request.status === 'expired') return 'expired';
  if ((request.status === 'pending' || request.status === 'paused') && Number.isFinite(eventStartsAt) && now >= eventStartsAt) {
    return 'expired';
  }
  if (request.status !== 'approved') return request.status;
  const startsAt = request.starts_at === null ? now : Date.parse(request.starts_at);
  const endsAt = Date.parse(request.ends_at ?? '');
  if (![startsAt, endsAt, eventStartsAt].every(Number.isFinite)) return 'approved';
  if (now >= Math.min(endsAt, eventStartsAt)) return 'expired';
  return now < startsAt ? 'scheduled' : 'active';
}

function statusClass(status: DisplayStatus): string {
  return `${styles.status} ${styles[`status${status[0].toUpperCase()}${status.slice(1)}`]}`;
}

function decisionText(decision: FeaturedDecision, t: ReturnType<typeof useT>, language: string): string {
  return t('Decision: {action} by {actorId} on {date}', {
    action: t(actionMessages[decision.action]),
    actorId: decision.actor_id,
    date: formatManilaDateTime(decision.created_at, language),
  });
}

export function FeaturedRequestControl({eventId, eventStartsAt, orgId, token}: {
  eventId: string;
  eventStartsAt: string | null;
  orgId: string;
  token: string;
}) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const requestPath = `/organizations/${encodeURIComponent(orgId)}/featured-requests`;
  const history = useApiResource<FeaturedRequest[]>(requestPath, token);
  const [working, setWorking] = useState(false);
  const [feedback, setFeedback] = useState<{message: string; error: boolean} | null>(null);
  const eligibilityNow = useFeatureTime();
  const mutationInFlight = useRef(false);
  const eventStart = eventStartsAt ? Date.parse(eventStartsAt) : Number.NaN;
  const eventStartKnown = Number.isFinite(eventStart);
  const eventStarted = eventStartKnown && eligibilityNow >= eventStart;

  const eventRequests = (history.data ?? [])
    .filter(request => request.event_id === eventId)
    .sort((first, second) => Date.parse(second.requested_at) - Date.parse(first.requested_at));
  const openRequest = eventRequests.find(request => {
    const status = displayStatus(request, eligibilityNow);
    return ['pending', 'paused', 'approved', 'scheduled', 'active'].includes(status);
  });

  async function submitRequest() {
    if (!token || working || mutationInFlight.current || openRequest) return;
    if (!eventStartKnown) {
      setFeedback({message: t('Event start time is unavailable. Request eligibility cannot be confirmed.'), error: true});
      return;
    }
    if (Date.now() >= eventStart) {
      setFeedback({message: t('The event has started; a featured request cannot be submitted.'), error: true});
      return;
    }
    mutationInFlight.current = true;
    setWorking(true);
    setFeedback(null);
    try {
      await api<FeaturedRequest>(`/events/${encodeURIComponent(eventId)}/featured-requests`, {
        token,
        method: 'POST',
      });
      setFeedback({message: t('The featured request is up to date.'), error: false});
      history.reload();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setFeedback({message: t('The request changed. Your history has been refreshed.'), error: false});
        history.reload();
      } else if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        setFeedback({message: t('Your sign-in or organization access has ended.'), error: true});
      } else {
        setFeedback({message: t('The request could not be submitted. Please retry.'), error: true});
      }
    } finally {
      mutationInFlight.current = false;
      setWorking(false);
    }
  }

  const headingId = useId();
  return (
    <section className={`panel ${styles.root}`} aria-labelledby={headingId}>
      <h3 id={headingId}>{t('Featured placement')}</h3>
      {feedback && <p className={feedback.error ? 'error' : 'success'} role={feedback.error ? 'alert' : 'status'}>{feedback.message}</p>}
      {history.loading && !history.data && <p role="status">{t('Loading featured request history…')}</p>}
      {history.error && (
        <div className="error" role="alert">
          <p>{t(history.error.status === 401 || history.error.status === 403
            ? 'Your sign-in or organization access has ended.'
            : 'The featured request history could not be loaded.')}</p>
          <button className="button button-secondary" type="button" onClick={history.reload}>{t('Retry loading history')}</button>
        </div>
      )}
      {eventStartKnown && (
        <p className={styles.meta}>{t('Event starts {date}', {date: formatManilaDateTime(eventStartsAt!, language)})}</p>
      )}
      {!eventStartKnown && <p className={styles.meta} role="status">{t('Event start time is unavailable. Request eligibility cannot be confirmed.')}</p>}
      {eventStarted && (
        <p className={styles.meta}>
          {history.data && !history.error && !eventRequests.length
            ? <><span className={statusClass('expired')}>{t('Expired')}</span>{' '}{t('This event has started. No featured request was submitted.')}</>
            : t('The event has started; a featured request cannot be submitted.')}
        </p>
      )}
      {history.data && !history.error && (
        <>
          {!eventRequests.length && !eventStarted ? (
            <p className="muted">{t('No featured request history for this event.')}</p>
          ) : eventRequests.length ? (
            <ol className={styles.historyList} aria-label={t('Featured request history ({count})', {count: eventRequests.length})}>
              {eventRequests.map(request => {
                const status = displayStatus(request, eligibilityNow);
                return (
                  <li className={styles.historyItem} key={request.id}>
                    <span className={statusClass(status)}>{t(statusMessages[status])}</span>
                    <p className={styles.meta}>{t('Requested by {actorId} on {date}', {
                      actorId: request.requested_by,
                      date: formatManilaDateTime(request.requested_at, language),
                    })}</p>
                    {request.starts_at && request.ends_at && (
                      <p className={styles.meta}>{t('Placement window: {start} – {end}', {
                        start: formatManilaDateTime(request.starts_at, language),
                        end: formatManilaDateTime(request.ends_at, language),
                      })}</p>
                    )}
                    {request.decisions.map(decision => (
                      <p className={styles.meta} key={decision.id}>{decisionText(decision, t, language)}</p>
                    ))}
                  </li>
                );
              })}
            </ol>
          ) : null}
          {eventStartKnown && !eventStarted && !openRequest && (
            <button className="button button-secondary" type="button" onClick={() => void submitRequest()} disabled={working || history.loading}>
              {working ? t('Loading featured request history…') : eventRequests.length ? t('Request again') : t('Request featured placement')}
            </button>
          )}
        </>
      )}
    </section>
  );
}

function FeaturedAdminRow({request, token, onRefresh, now}: {
  request: FeaturedRequest;
  token: string;
  onRefresh: (kind: 'changed' | 'conflict') => void;
  now: number;
}) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const ids = useId();
  const [startNow, setStartNow] = useState(true);
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [working, setWorking] = useState<ReviewAction | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<{
    action: ReviewAction;
    version: number;
    title: string;
    schedule: {starts_at: string | null; ends_at: string} | null;
  } | null>(null);
  const confirmationDialog = useRef<HTMLDialogElement>(null);
  const mutationInFlight = useRef(false);
  const status = displayStatus(request, now);
  const canReview = status === 'pending' || status === 'paused';
  const canRevoke = status === 'approved' || status === 'scheduled' || status === 'active';
  const startId = `${ids}-start`;
  const endId = `${ids}-end`;
  const errorId = `${ids}-schedule-error`;
  const nowInput = manilaInputValue(new Date(Math.ceil(now / 60_000) * 60_000));
  const eventStartInput = manilaInputValue(request.event.starts_at);
  const endMinimum = startNow ? nowInput : startsAt || nowInput;

  useEffect(() => {
    const dialog = confirmationDialog.current;
    if (!dialog) return;
    const desktop = window.matchMedia('(min-width: 768px)');
    const sync = () => {
      if (!desktop.matches) {
        dialog.close();
        setConfirmation(null);
      } else if (confirmation && !dialog.open) dialog.showModal();
      else if (!confirmation && dialog.open) dialog.close();
    };
    sync();
    desktop.addEventListener('change', sync);
    return () => desktop.removeEventListener('change', sync);
  }, [confirmation]);

  function scheduleBody(): {starts_at: string | null; ends_at: string} | null {
    const startTime = startNow ? Date.now() : manilaInputTime(startsAt);
    const endTime = manilaInputTime(endsAt);
    const eventStart = Date.parse(request.event.starts_at);
    if (startTime === null || endTime === null || !Number.isFinite(eventStart)) {
      setErrorKey('Choose a valid Manila start and end time.');
      return null;
    }
    if (!startNow && startTime < Date.now()) {
      setErrorKey('An explicit start cannot be in the past.');
      return null;
    }
    if (endTime <= startTime || endTime > eventStart) {
      setErrorKey('The end must be after the start and no later than the event start.');
      return null;
    }
    return {
      starts_at: startNow ? null : new Date(startTime).toISOString(),
      ends_at: new Date(endTime).toISOString(),
    };
  }

  function askDecision(action: ReviewAction) {
    if (working || mutationInFlight.current) return;
    const schedule = action === 'approve' ? scheduleBody() : null;
    if (action === 'approve' && !schedule) return;
    setConfirmation({action, schedule, version: request.version, title: request.event.title});
  }

  async function decide() {
    if (!confirmation || working || mutationInFlight.current) return;
    const {action, schedule, version} = confirmation;
    setConfirmation(null);
    mutationInFlight.current = true;
    setWorking(action);
    setErrorKey(null);
    try {
      await api<FeaturedRequest>(`/platform-admin/featured-requests/${encodeURIComponent(request.id)}/decisions`, {
        token,
        method: 'POST',
        body: action === 'approve'
          ? {action, version, starts_at: schedule!.starts_at, ends_at: schedule!.ends_at}
          : {action, version},
      });
      onRefresh('changed');
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setErrorKey('This request or schedule changed while you were reviewing it. The queue has been refreshed.');
        onRefresh('conflict');
      } else if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        setErrorKey('Your platform review access has ended.');
      } else {
        setErrorKey('The action could not be completed. Please retry.');
      }
    } finally {
      mutationInFlight.current = false;
      setWorking(null);
    }
  }

  return (
    <li className={styles.queueItem}>
      <article className={styles.requestCard} aria-labelledby={`${ids}-title`}>
        <header className={styles.requestHeading}>
          <div>
            <h3 id={`${ids}-title`}>{request.event.title}</h3>
            <p className={styles.meta}>{t('Organized by {organization}', {organization: request.event.organization_name})}</p>
          </div>
          <span className={statusClass(status)}>{t(statusMessages[status])}</span>
        </header>
        <p className={styles.meta}>{t('Event starts {date}', {date: formatManilaDateTime(request.event.starts_at, language)})}</p>
        <a href={`/events?eventId=${encodeURIComponent(request.event.id)}`}>{t('View public event details')}</a>
        <p className={styles.meta}>{t('Requested by {actorId} on {date}', {
          actorId: request.requested_by,
          date: formatManilaDateTime(request.requested_at, language),
        })}</p>
        {request.starts_at && request.ends_at && (
          <p className={styles.meta}>{t('Placement window: {start} – {end}', {
            start: formatManilaDateTime(request.starts_at, language),
            end: formatManilaDateTime(request.ends_at, language),
          })}</p>
        )}
        <details className={styles.audit}>
          <summary>{t('Decision history ({count})', {count: request.decisions.length})}</summary>
          {request.decisions.length ? (
            <ol className={styles.auditList}>
              {request.decisions.map(decision => <li key={decision.id}>{decisionText(decision, t, language)}</li>)}
            </ol>
          ) : <p className="muted">{t('No featured request history for this event.')}</p>}
        </details>

        {canReview && (
          <div className={styles.schedule}>
            <h4>{t('Platform review')}</h4>
            <label className={styles.checkbox}>
              <input type="checkbox" checked={startNow} onChange={event => { setStartNow(event.currentTarget.checked); setErrorKey(null); }} />
              {t('Start now (Asia/Manila)')}
            </label>
            {!startNow && (
              <div className="field">
                <label htmlFor={startId}>{t('Start date and time (Asia/Manila)')}</label>
                <input id={startId} type="datetime-local" value={startsAt} min={nowInput} max={eventStartInput || undefined}
                  onChange={event => { setStartsAt(event.currentTarget.value); setErrorKey(null); }} />
              </div>
            )}
            <div className="field">
              <label htmlFor={endId}>{t('End date and time (Asia/Manila)')}</label>
              <input id={endId} type="datetime-local" value={endsAt} min={endMinimum} max={eventStartInput || undefined} required
                aria-invalid={Boolean(errorKey)} aria-describedby={errorKey ? errorId : undefined}
                onChange={event => { setEndsAt(event.currentTarget.value); setErrorKey(null); }} />
            </div>
            {errorKey && <p id={errorId} className="error" role="alert">{t(errorKey)}</p>}
            <div className={styles.actions}>
              <button className="button" type="button" disabled={working !== null} onClick={() => askDecision('approve')}>
                {working === 'approve' ? t('Platform review') : t('Approve')}
              </button>
              <button className="button button-secondary" type="button" disabled={working !== null} onClick={() => askDecision('reject')}>
                {working === 'reject' ? t('Platform review') : t('Reject')}
              </button>
            </div>
          </div>
        )}
        {canRevoke && (
          <div className={styles.actions}>
            <button className="button button-danger" type="button" disabled={working !== null} onClick={() => askDecision('revoke')}>
              {working === 'revoke' ? t('Platform review') : t('Revoke')}
            </button>
          </div>
        )}
        {errorKey && !canReview && <p className="error" role="alert">{t(errorKey)}</p>}
        <dialog ref={confirmationDialog} className={styles.confirmDialog}
          aria-labelledby={`${ids}-confirmation-title`}
          onCancel={event => { event.preventDefault(); setConfirmation(null); }}
          onClose={() => setConfirmation(null)}>
          {confirmation && <div className={styles.confirmationContent}>
            <h4 id={`${ids}-confirmation-title`}>{confirmation.action === 'approve'
              ? t('Approve featured placement for {title}?', {title: confirmation.title})
              : confirmation.action === 'reject'
                ? t('Reject the featured placement request for {title}?', {title: confirmation.title})
                : t('Revoke featured placement for {title}?', {title: confirmation.title})}</h4>
            {confirmation.schedule && <p>{t('Placement window: {start} – {end}', {
              start: confirmation.schedule.starts_at ? formatManilaDateTime(confirmation.schedule.starts_at, language) : t('Start now (Asia/Manila)'),
              end: formatManilaDateTime(confirmation.schedule.ends_at, language),
            })}</p>}
            <div className={styles.actions}>
              <button className="button button-secondary" type="button" autoFocus onClick={() => setConfirmation(null)}>{t('Go back')}</button>
              <button className="button" type="button" onClick={() => void decide()}>{t('Confirm decision')}</button>
            </div>
          </div>}
        </dialog>
      </article>
    </li>
  );
}

export function FeaturedAdminQueue({token}: {token: string}) {
  const t = useT();
  const now = useFeatureTime();
  const queue = useApiResource<FeaturedRequest[]>('/platform-admin/featured-requests', token);
  const [notice, setNotice] = useState<string | null>(null);
  const headingId = useId();

  function refresh(kind?: 'changed' | 'conflict') {
    setNotice(kind === 'conflict'
      ? t('This request or schedule changed while you were reviewing it. The queue has been refreshed.')
      : kind === 'changed' ? t('The featured request decision was recorded.') : null);
    queue.reload();
  }

  return (
    <section className={`panel ${styles.root}`} aria-labelledby={headingId}>
      <header className={styles.queueHeading}>
        <div>
          <p className="eyebrow">{t('Platform review')}</p>
          <h2 id={headingId}>{t('Featured-event requests')}</h2>
        </div>
        <button className="button button-secondary" type="button" disabled={queue.loading} onClick={() => refresh()}>{t('Refresh queue')}</button>
      </header>
      <p className={styles.materialNotice}>{t('Material changes to the event date or time, venue, banner or graphic, capacity, or cost pause a pending or approved request and require fresh platform review.')}</p>
      <p className={styles.meta}>{t('Paused requests must be reviewed directly; they are not reinstated automatically.')}</p>
      {notice && <p className="success" role="status">{notice}</p>}
      {queue.loading && !queue.data && <p role="status">{t('Loading featured requests…')}</p>}
      {queue.error && (
        <div className="error" role="alert">
          <p>{t(queue.error.status === 401 || queue.error.status === 403
            ? 'Your platform review access has ended.'
            : 'The featured request queue could not be loaded.')}</p>
          <button className="button button-secondary" type="button" onClick={() => refresh()}>{t('Retry loading queue')}</button>
        </div>
      )}
      {queue.data && !queue.error && (queue.data.length ? (
        <ol className={styles.queueList}>
          {queue.data.map(request => (
            <FeaturedAdminRow key={`${token}:${request.id}`} request={request} token={token} onRefresh={refresh} now={now} />
          ))}
        </ol>
      ) : <p className="empty-state muted">{t('No featured requests are available.')}</p>)}
    </section>
  );
}
