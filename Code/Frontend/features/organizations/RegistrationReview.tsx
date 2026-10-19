'use client';

import { useEffect, useState } from 'react';
import { Feedback } from '@/components/feedback';
import { api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { Registration as RegistrationResult, RegistrationReview as RegistrationReviewItem } from '@/lib/types';
import styles from './workspace-page.module.css';

function isSeatHolder(status: string) {
  return status === 'confirmed' || status === 'pending' || status === 'reconfirmation_required';
}

function useCurrentTime() {
  const [currentTime, setCurrentTime] = useState<number | null>(null);
  useEffect(() => {
    const update = () => setCurrentTime(Date.now());
    const initialUpdate = window.setTimeout(update, 0);
    const interval = window.setInterval(update, 60_000);
    return () => {
      window.clearTimeout(initialUpdate);
      window.clearInterval(interval);
    };
  }, []);
  return currentTime;
}

function stageLabel(stage: number | null | undefined, t: (english: string) => string) {
  if (stage === 1) return t('One-time extension');
  if (stage === 2) return t('Second review');
  return t('Initial review');
}

function usePersonaWindow(eventEndsAt: string | null) {
  const [windowState, setWindowState] = useState<{eventEndsAt: string | null; isOpen: boolean}>({
    eventEndsAt: null,
    isOpen: false,
  });

  useEffect(() => {
    const eventEnd = eventEndsAt === null ? Number.NaN : Date.parse(eventEndsAt);
    let timer: number | undefined;

    function updateWindow() {
      const remaining = eventEnd - Date.now();
      const isOpen = Number.isFinite(eventEnd) && remaining > 0;
      setWindowState({eventEndsAt, isOpen});
      if (isOpen) timer = window.setTimeout(updateWindow, Math.min(remaining, 2_147_483_647));
    }

    const startTimer = window.setTimeout(updateWindow, 0);
    return () => {
      if (startTimer !== undefined) window.clearTimeout(startTimer);
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [eventEndsAt]);

  return windowState.eventEndsAt === eventEndsAt && windowState.isOpen;
}

export function RegistrationReview({eventId, eventEndsAt, isOpen: requestedOpen, onOpenChange, onReviewed}: {
  eventId: string;
  eventEndsAt: string | null;
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  onReviewed?: (feedback: {message: string; error: boolean}) => void;
}) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const currentTime = useCurrentTime();
  const {actor, token} = useSession();
  const [localOpen, setLocalOpen] = useState(false);
  const open = requestedOpen ?? localOpen;
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [confirmingDecision, setConfirmingDecision] = useState<{
    registrationId: string;
    decision: 'approve' | 'reject';
  } | null>(null);
  const queue = useApiResource<RegistrationReviewItem[]>(
    open && token ? `/events/${encodeURIComponent(eventId)}/registration-review` : null,
    token,
  );
  const registrations = queue.data ?? [];
  const personaWindowOpen = usePersonaWindow(eventEndsAt);

  async function decide(item: RegistrationReviewItem, decision: 'approve' | 'reject') {
    if (!token || workingId) return;
    setWorkingId(item.registration.id);
    setActionError(null);
    setMessage('');
    try {
      await api<RegistrationResult>(
        `/events/${encodeURIComponent(eventId)}/registrations/${encodeURIComponent(item.registration.id)}/decision`,
        {token, method: 'POST', body: {decision}},
      );
      const message = decision === 'approve' ? 'Registration approved.' : 'Registration rejected.';
      setMessage(t(message));
      queue.reload();
      onReviewed?.({message, error: false});
    } catch (error) {
      const message = error instanceof Error ? error.message : 'The decision could not be recorded.';
      setActionError(t(message));
      queue.reload();
      onReviewed?.({message, error: true});
    } finally {
      setWorkingId(null);
      setConfirmingDecision(null);
    }
  }

  return (
    <details
      className={`panel ${styles.toolDetails}`}
      open={open}
      onToggle={event => {
        const nextOpen = event.currentTarget.open;
        setLocalOpen(nextOpen);
        onOpenChange?.(nextOpen);
      }}
    >
      <summary>{t('Review registrations')}</summary>
      {open && (
        <div className={styles.toolBody}>
          {queue.data !== null && (
            <p className={styles.queueSummary}>
              <span className={styles.queueMetric}>
                {t('{count} awaiting review', {count: registrations.filter(item => item.registration.status === 'pending').length})}
              </span>
              <span className={styles.queueMetric}>
                {t('{count} occupied seats', {count: registrations.filter(item => isSeatHolder(item.registration.status)).length})}
              </span>
              <span className="muted">{t('Occupied seats include pending reviews and reconfirmations.')}</span>
            </p>
          )}
          {actionError && <p className="error" role="alert">{actionError}</p>}
          {message && <p role="status">{message}</p>}
          <Feedback loading={queue.loading} error={queue.error} onRetry={queue.reload}>
            {!registrations.length ? (
              <p className="empty-state muted">{t('No registrations are waiting or holding a seat.')}</p>
            ) : (
              <div className="feed">
                {registrations.map(item => {
                  const registration = item.registration;
                  const personaVisible = item.persona !== null && personaWindowOpen;
                  const assignedToCurrentReviewer = registration.reviewer_id === actor?.id;
                  const firstReviewerExcluded = registration.review_stage === 2 &&
                    actor?.id !== undefined && registration.first_reviewer_id === actor.id;
                  const canDecide = Boolean(actor?.id) && registration.status === 'pending' && !firstReviewerExcluded;
                  const deadline = registration.status === 'pending'
                    ? registration.review_deadline
                    : registration.reconfirm_deadline;
                  const deadlineTimestamp = deadline ? Date.parse(deadline) : Number.NaN;
                  const deadlineOverdue = currentTime !== null && deadlineTimestamp < currentTime;
                  const deadlineSoon = currentTime !== null && deadlineTimestamp >= currentTime &&
                    deadlineTimestamp <= currentTime + 24 * 60 * 60 * 1000;

                  return (
                    <article className={`event-card stack ${styles.reviewItem}`} key={registration.id}>
                      <header>
                        <h3>{item.persona?.nickname && personaVisible
                          ? item.persona.nickname
                          : t('Registrant {id}', {id: item.user_id.slice(0, 8)})}</h3>
                        <span className={`status-chip ${registration.status}`}>{t(registration.status.replace(/_/g, ' '))}</span>
                      </header>
                      {registration.from_waitlist && <p className="muted">{t('This request came from the waitlist.')}</p>}
                      {registration.status === 'pending' && (
                        <p className={`${styles.deadline} ${deadlineOverdue
                          ? styles.deadlineOverdue
                          : deadlineSoon
                            ? styles.deadlineSoon : ''}`}>
                          <strong>{stageLabel(registration.review_stage, t)}</strong>
                          {deadline && <>
                            <span className={styles.deadlineLabel}>{t('Review deadline')}</span>
                            <time dateTime={deadline}>{formatDate(deadline, language)} · {formatTime(deadline, language)} ({t('Manila time')})</time>
                            {deadlineOverdue && <span>{t('Overdue')}</span>}
                            {deadlineSoon && <span>{t('Due within 24 hours')}</span>}
                          </>}
                        </p>
                      )}
                      {registration.status === 'reconfirmation_required' && deadline && (
                        <p className={`${styles.deadline} ${deadlineOverdue
                          ? styles.deadlineOverdue
                          : deadlineSoon
                            ? styles.deadlineSoon : ''}`}>
                          <span className={styles.deadlineLabel}>{t('Reconfirmation deadline')}</span>
                          <time dateTime={deadline}>{formatDate(deadline, language)} · {formatTime(deadline, language)} ({t('Manila time')})</time>
                          {deadlineOverdue && <span>{t('Overdue')}</span>}
                          {deadlineSoon && <span>{t('Due within 24 hours')}</span>}
                        </p>
                      )}
                      {personaVisible && item.persona && (
                        <div>
                          <p>
                            {item.persona.age_bracket || t('Age not shared')}
                            {item.persona.pronouns ? ` · ${item.persona.pronouns}` : ''}
                          </p>
                          {item.persona.tags.length > 0 && <p>{t('Interests: {interests}', {interests: item.persona.tags.join(', ')})}</p>}
                          {item.persona.icebreaker && <p>{item.persona.icebreaker}</p>}
                        </div>
                      )}
                      {registration.status === 'pending' && firstReviewerExcluded && (
                        <p className="muted">{t('A different authorized reviewer must decide at this escalated stage; the first reviewer is excluded.')}</p>
                      )}
                      {registration.status === 'pending' && canDecide && !assignedToCurrentReviewer && (
                        <p className="muted">{t('The assigned reviewer is accountable for this deadline, but another authorized reviewer may decide while this stage is open.')}</p>
                      )}
                      {canDecide && (
                        <div className="actions">
                          <button
                            className="button"
                            type="button"
                            disabled={workingId !== null}
                            onClick={() => setConfirmingDecision({registrationId: registration.id, decision: 'approve'})}
                          >
                            {workingId === registration.id ? t('Saving…') : t('Approve')}
                          </button>
                          <button
                            className="button button-danger"
                            type="button"
                            disabled={workingId !== null}
                            onClick={() => setConfirmingDecision({registrationId: registration.id, decision: 'reject'})}
                          >
                            {workingId === registration.id ? t('Saving…') : t('Reject')}
                          </button>
                        </div>
                      )}
                      {confirmingDecision?.registrationId === registration.id && (
                        <div className={styles.decisionConfirm} role="group" aria-labelledby={`registration-decision-title-${registration.id}`}>
                          <h4 id={`registration-decision-title-${registration.id}`}>
                            {confirmingDecision.decision === 'approve' ? t('Confirm registration approval') : t('Confirm registration rejection')}
                          </h4>
                          <p>{confirmingDecision.decision === 'approve'
                            ? t('Approve this registration request?')
                            : t('Reject this registration request? This decision will be recorded for the applicant.')}</p>
                          <div className="actions">
                            <button
                              className={confirmingDecision.decision === 'approve' ? 'button' : 'button button-danger'}
                              type="button"
                              disabled={workingId !== null}
                              onClick={() => void decide(item, confirmingDecision.decision)}
                            >
                              {workingId === registration.id ? t('Saving…') : t('Confirm decision')}
                            </button>
                            <button
                              className="button button-secondary"
                              type="button"
                              disabled={workingId !== null}
                              onClick={() => setConfirmingDecision(null)}
                            >{t('Cancel')}</button>
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </Feedback>
        </div>
      )}
    </details>
  );
}
