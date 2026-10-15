'use client';

import { useEffect, useState } from 'react';
import { Feedback } from '@/components/feedback';
import { api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { Registration as RegistrationResult, RegistrationReview as RegistrationReviewItem } from '@/lib/types';

function isSeatHolder(status: string) {
  return status === 'confirmed' || status === 'pending' || status === 'reconfirmation_required';
}

function stageLabel(stage: number | null | undefined) {
  if (stage === 1) return 'One-time extension';
  if (stage === 2) return 'Second review';
  return 'Initial review';
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

export function RegistrationReview({eventId, eventEndsAt}: {
  eventId: string;
  eventEndsAt: string | null;
}) {
  const {actor, token} = useSession();
  const [open, setOpen] = useState(false);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
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
      setMessage(decision === 'approve' ? 'Registration approved.' : 'Registration rejected.');
      queue.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'The decision could not be recorded.');
      queue.reload();
    } finally {
      setWorkingId(null);
    }
  }

  return (
    <details className="panel" onToggle={event => setOpen(event.currentTarget.open)}>
      <summary>Review registrations</summary>
      {open && (
        <div className="stack">
          <p className="muted">
            {registrations.filter(item => item.registration.status === 'pending').length} awaiting review · {' '}
            {registrations.filter(item => isSeatHolder(item.registration.status)).length} occupied seats, including pending reviews and reconfirmations.
          </p>
          {actionError && <p className="error" role="alert">{actionError}</p>}
          {message && <p role="status">{message}</p>}
          <Feedback loading={queue.loading} error={queue.error} onRetry={queue.reload}>
            {!registrations.length ? (
              <p className="empty-state muted">No registrations are waiting or holding a seat.</p>
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

                  return (
                    <article className="event-card stack" key={registration.id}>
                      <header>
                        <h3>{item.persona?.nickname && personaVisible
                          ? item.persona.nickname
                          : `Registrant ${item.user_id.slice(0, 8)}`}</h3>
                        <span className={`status-chip ${registration.status}`}>{registration.status.replace(/_/g, ' ')}</span>
                      </header>
                      {registration.from_waitlist && <p className="muted">This request came from the waitlist.</p>}
                      {registration.status === 'pending' && (
                        <p className="muted">
                          {stageLabel(registration.review_stage)}
                          {deadline && <> · Deadline: <time dateTime={deadline}>{formatDate(deadline)} · {formatTime(deadline)} (Manila)</time></>}
                        </p>
                      )}
                      {registration.status === 'reconfirmation_required' && deadline && (
                        <p className="muted">
                          Reconfirmation deadline: <time dateTime={deadline}>{formatDate(deadline)} · {formatTime(deadline)} (Manila)</time>
                        </p>
                      )}
                      {personaVisible && item.persona && (
                        <div>
                          <p>
                            {item.persona.age_bracket || 'Age not shared'}
                            {item.persona.pronouns ? ` · ${item.persona.pronouns}` : ''}
                          </p>
                          {item.persona.tags.length > 0 && <p>Interests: {item.persona.tags.join(', ')}</p>}
                          {item.persona.icebreaker && <p>{item.persona.icebreaker}</p>}
                        </div>
                      )}
                      {registration.status === 'pending' && firstReviewerExcluded && (
                        <p className="muted">A different authorized reviewer must decide at this escalated stage; the first reviewer is excluded.</p>
                      )}
                      {registration.status === 'pending' && canDecide && !assignedToCurrentReviewer && (
                        <p className="muted">The assigned reviewer is accountable for this deadline, but another authorized reviewer may decide while this stage is open.</p>
                      )}
                      {canDecide && (
                        <div className="actions">
                          <button
                            className="button"
                            type="button"
                            disabled={workingId !== null}
                            onClick={() => void decide(item, 'approve')}
                          >
                            {workingId === registration.id ? 'Saving…' : 'Approve'}
                          </button>
                          <button
                            className="button button-danger"
                            type="button"
                            disabled={workingId !== null}
                            onClick={() => void decide(item, 'reject')}
                          >
                            {workingId === registration.id ? 'Saving…' : 'Reject'}
                          </button>
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
