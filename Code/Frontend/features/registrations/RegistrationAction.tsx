'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { PublicEvent, Registration } from '@/lib/types';
import { EventPersonaSharing } from '@/features/personas/EventPersonaSharing';
import type { RegistrationBlockWarning } from '@/features/personas/types';
import styles from '@/features/events/attendee-events.module.css';
import { ConflictWarning } from '@/features/planning/ConflictWarning';

type AttendeeRegistration = Omit<Registration, 'status'> & {
  status: 'confirmed' | 'waitlisted' | 'pending' | 'reconfirmation_required' | 'cancelled' | 'rejected';
  review_deadline?: string | null;
  reconfirm_deadline?: string | null;
};

function formatDeadline(value: string | null | undefined, language: 'en' | 'fil') {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  return `${formatDate(value, language)} · ${formatTime(value, language)}`;
}

export function RegistrationAction({ event, onOutcome }: { event: PublicEvent; onOutcome?: () => void }) {
  const { actor, token } = useSession();
  return <RegistrationActionSession key={`${event.id}:${actor?.id ?? 'guest'}:${token ?? ''}`} event={event} onOutcome={onOutcome} />;
}

function RegistrationActionSession({ event, onOutcome }: { event: PublicEvent; onOutcome?: () => void }) {
  const { actor, token, authLoading } = useSession();
  const t = useT();
  const { preferences } = usePreferences();
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [submittedResult, setResult] = useState<AttendeeRegistration | null>(null);
  const registrations = useApiResource<AttendeeRegistration[]>(token && actor?.eligible ? '/me/registrations' : null, token);
  const result = submittedResult ?? registrations.data?.find(item =>
    item.event_id === event.id && ['confirmed', 'waitlisted', 'pending', 'reconfirmation_required'].includes(item.status),
  ) ?? null;
  const [personaShared, setPersonaShared] = useState(false);
  const [blockWarning, setBlockWarning] = useState(false);
  const [serverWarning, setServerWarning] = useState(false);
  const [blockWarningAcknowledged, setBlockWarningAcknowledged] = useState(false);
  const [warningState, setWarningState] = useState<'idle' | 'loading' | 'clear' | 'warning' | 'error'>('idle');
  const [now, setNow] = useState<number | null>(null);
  const attemptKey = useRef<{
    eventId: string;
    key: string;
    payload: { persona_shared: boolean; blocked_attendee_acknowledged: boolean };
  } | null>(null);
  const controller = useRef<AbortController | null>(null);
  const warningController = useRef<AbortController | null>(null);
  const dialog = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const outcome = useRef<HTMLDivElement>(null);
  const confirmationDialogId = `registration-confirmation-${event.id}`;
  const confirmationTitleId = `${confirmationDialogId}-title`;
  const confirmationFactsId = `${confirmationDialogId}-facts`;
  const personaHelpId = `${confirmationDialogId}-persona-help`;
  const blockWarningHelpId = `${confirmationDialogId}-block-warning-help`;

  useEffect(() => () => {
    controller.current?.abort();
    warningController.current?.abort();
  }, []);

  useEffect(() => {
    const firstUpdate = window.setTimeout(() => setNow(Date.now()), 0);
    const clock = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      window.clearTimeout(firstUpdate);
      window.clearInterval(clock);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const returnFocus = trigger.current;
    dialog.current?.focus();
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeConfirmation();
        return;
      }
      if (event.key !== 'Tab' || !dialog.current) return;
      const focusable = Array.from(dialog.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ));
      if (!focusable.length) {
        event.preventDefault();
        dialog.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!dialog.current.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      window.removeEventListener('keydown', closeOnEscape);
      if (returnFocus?.isConnected) returnFocus.focus();
    };
  }, [open]);

  useEffect(() => {
    if (submittedResult) outcome.current?.focus();
  }, [submittedResult]);

  async function refreshBlockWarning() {
    if (!token) return;
    const requestController = new AbortController();
    warningController.current?.abort();
    warningController.current = requestController;
    setWarningState('loading');
    try {
      const response = await api<RegistrationBlockWarning>(
        `/events/${encodeURIComponent(event.id)}/registration-block-warning`,
        { token, signal: requestController.signal },
      );
      if (requestController.signal.aborted) return;
      setBlockWarning(response.warning);
      setWarningState(response.warning ? 'warning' : 'clear');
    } catch {
      if (!requestController.signal.aborted) setWarningState('error');
    } finally {
      if (warningController.current === requestController) warningController.current = null;
    }
  }

  function closeConfirmation() {
    warningController.current?.abort();
    setOpen(false);
  }

  const retryable = error !== null && (error.status === 0 || error.status >= 500);
  const blockedWarningConflict = error?.code === 'blocked_attendee_warning';
  const requiresBlockAcknowledgement = blockWarning || serverWarning;
  const registrationErrorMessage = blockedWarningConflict
    ? t('A block warning needs your attention before you register.')
    : error ? t(error.message) : null;
  const profileClue = error !== null &&
    ['profile_incomplete', 'registration_ineligible', 'plm_email_required'].includes(error.code);
  const registrationMode = event.registration_mode;
  const approvalRequired = registrationMode === 'approval';
  const isFull = event.remaining_spots <= 0;
  const startsAt = Date.parse(event.starts_at);
  const eventStarted = error?.code === 'event_started' ||
    (now !== null && (!Number.isFinite(startsAt) || startsAt <= now));
  const actionLabel = isFull ? t('Join waitlist') : approvalRequired ? t('Request to register') : t('Register');
  const personaConsentId = `registration-persona-${event.id}`;

  function openConfirmation() {
    if (!Number.isFinite(startsAt) || startsAt <= Date.now()) {
      setNow(Date.now());
      return;
    }
    if (error && retryable && attemptKey.current?.eventId === event.id) {
      setOpen(true);
      return;
    }
    if (error && !retryable) {
      attemptKey.current = null;
      setError(null);
    }
    setBlockWarning(false);
    setServerWarning(false);
    setBlockWarningAcknowledged(false);
    setWarningState('loading');
    setOpen(true);
    void refreshBlockWarning();
  }

  async function submitRegistration() {
    if (!token || !actor?.eligible || !actor.profile_complete || submitting) return;
    const previousAttempt = attemptKey.current?.eventId === event.id ? attemptKey.current : null;
    if (warningState === 'loading' || (warningState === 'idle' && !previousAttempt)) return;
    if (requiresBlockAcknowledgement && !blockWarningAcknowledged) return;
    if (!Number.isFinite(startsAt) || startsAt <= Date.now()) {
      setNow(Date.now());
      closeConfirmation();
      return;
    }

    const payload = {
      persona_shared: approvalRequired && personaShared,
      blocked_attendee_acknowledged: blockWarningAcknowledged,
    };
    const savedAttempt = previousAttempt &&
      previousAttempt.payload.persona_shared === payload.persona_shared &&
      previousAttempt.payload.blocked_attendee_acknowledged === payload.blocked_attendee_acknowledged
      ? previousAttempt
      : { eventId: event.id, key: window.crypto.randomUUID(), payload };
    attemptKey.current = savedAttempt;

    const requestController = new AbortController();
    controller.current?.abort();
    controller.current = requestController;
    setSubmitting(true);
    setError(null);

    try {
      const registration = await api<AttendeeRegistration>(`/events/${encodeURIComponent(event.id)}/registrations`, {
        token,
        method: 'POST',
        body: savedAttempt.payload,
        idempotencyKey: savedAttempt.key,
        signal: requestController.signal,
      });
      if (requestController.signal.aborted) return;
      attemptKey.current = null;
      setResult(registration);
      setOpen(false);
      onOutcome?.();
    } catch (caught) {
      if (requestController.signal.aborted) return;
      if (caught instanceof ApiError && caught.code === 'blocked_attendee_warning') {
        attemptKey.current = null;
        setError(caught);
        setServerWarning(true);
        setBlockWarning(true);
        setBlockWarningAcknowledged(false);
        void refreshBlockWarning();
      } else {
        setError(caught instanceof ApiError
        ? caught
        : new ApiError(0, 'request_failed', 'The registration result could not be confirmed. Retry with the same request key.'));
      }
    } finally {
      if (!requestController.signal.aborted) setSubmitting(false);
      if (controller.current === requestController) controller.current = null;
    }
  }

  if (authLoading && !actor) {
    return <p className="muted" role="status">{t('Checking registration access…')}</p>;
  }
  if (!token || !actor) {
    return <p className="muted">{t('Sign in from the header to register for this event.')}</p>;
  }
  if (result) {
    const reviewDeadline = formatDeadline(result.review_deadline, preferences.language);
    const reconfirmDeadline = formatDeadline(result.reconfirm_deadline, preferences.language);
    const outcomeStyle = result.status === 'confirmed'
      ? styles.registrationConfirmed
      : result.status === 'pending'
        ? styles.registrationPending
        : result.status === 'waitlisted'
          ? styles.registrationWaitlisted
          : result.status === 'reconfirmation_required'
            ? styles.registrationReconfirmation
            : result.status === 'rejected'
              ? styles.registrationRejected
              : styles.registrationCancelled;
    return (
      <div className={`panel stack ${styles.registrationOutcome} ${outcomeStyle}`} role="status" aria-live="polite" tabIndex={-1} ref={outcome}>
        {result.status === 'confirmed' ? <p>{t('Your registration is confirmed.')}</p> : null}
        {result.status === 'confirmed' ? (
          <EventPersonaSharing
            key={`${event.id}:${actor.id}:${token}`}
            eventId={event.id}
            actorId={actor.id}
            token={token}
          />
        ) : null}
        {result.status === 'pending' ? (
          <div>
            <p>{reviewDeadline
              ? t('Your request is pending organizer approval. A seat is reserved for you until {deadline}.', { deadline: reviewDeadline })
              : t('Your request is pending organizer approval. A seat is reserved for you while it is reviewed.')}
            </p>
            {!reviewDeadline ? <p>{t('Check My Events for the current review deadline.')}</p> : null}
          </div>
        ) : null}
        {result.status === 'reconfirmation_required' ? (
          <p>{reconfirmDeadline
            ? t('A seat is reserved while you reconfirm by {deadline}.', { deadline: reconfirmDeadline })
            : t('A seat is reserved while you reconfirm. Check My Events for the current deadline.')}
          </p>
        ) : null}
        {result.status === 'waitlisted' ? (
          <div className="stack">
            <p>{t('Waitlist position: {position}.', { position: result.waitlist_position ?? t('Not provided') })}</p>
            <p>{t(result.waitlist_message ?? 'You are on the waitlist. No estimated wait time is available.')}</p>
          </div>
        ) : null}
        {result.status === 'rejected' ? <p>{t('This registration was rejected.')}</p> : null}
        {result.status === 'cancelled' ? <p>{t('This registration was cancelled.')}</p> : null}
        <Link className="button button-secondary" href={`/my-events?tab=${now !== null && Date.parse(event.ends_at) <= now ? 'past' : result.status === 'waitlisted' ? 'waitlist' : result.status === 'pending' || result.status === 'reconfirmation_required' ? 'pending' : 'confirmed'}`}>{t('View My Events')}</Link>
      </div>
    );
  }
  if (!actor.eligible) {
    return <p className="muted">{t('Registration requires an eligible PLM account.')} <Link href="/profile">{t('Review your profile')}</Link>.</p>;
  }
  if (!actor.profile_complete) {
    return <p className="muted">{t('Complete your profile before registering.')} <Link href="/profile">{t('Update your profile')}</Link>.</p>;
  }

  if (eventStarted) {
    return (
      <div className="stack">
        <button className="button button-secondary" type="button" disabled>{t('Registration is closed.')}</button>
        <p className="muted" role="status">
          {error?.code === 'event_started' ? t(error.message) : t('Registration is closed because the event has started.')}
        </p>
      </div>
    );
  }
  if (now === null) {
    return <p className="muted" role="status">{t('Checking availability…')}</p>;
  }
  if (registrations.loading) return <p className="muted" role="status">{t('Checking registration access…')}</p>;
  if (registrations.error) return <div className="panel error" role="alert">
    <p>{t(registrations.error.message)}</p>
    <button className="button button-secondary" type="button" onClick={registrations.reload}>{t('Retry')}</button>
  </div>;

  return (
    <div className="stack">
      <button
        className="button"
        type="button"
        onClick={openConfirmation}
        ref={trigger}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={confirmationDialogId}
      >
        {actionLabel}
      </button>

      {error && !open ? (
        <div className="panel error" role="alert">
          <p>{registrationErrorMessage}</p>
          {profileClue ? <p><Link href="/profile">{t('Review your profile before trying again.')}</Link></p> : null}
          {retryable ? (
            <button className="button button-secondary" type="button" onClick={() => { setOpen(true); void submitRegistration(); }}>
              {t('Retry registration')}
            </button>
          ) : null}
        </div>
      ) : null}

      {open ? (
        <div
          className={`sheet ${styles.registrationSheet}`}
          role="presentation"
        >
          <section
            id={confirmationDialogId}
            className={`stack ${styles.registrationSheetPanel}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby={confirmationTitleId}
            aria-describedby={confirmationFactsId}
            tabIndex={-1}
            ref={dialog}
          >
            <div>
              <p className="eyebrow">{t('Registration')}</p>
              <h2 id={confirmationTitleId}>
                {isFull ? t('Join the waitlist') : approvalRequired ? t('Request organizer approval') : t('Confirm your registration')}
              </h2>
            </div>
            <dl className={styles.registrationFacts} id={confirmationFactsId}>
              <div><dt>{t('Date and time')}</dt><dd>{formatDate(event.starts_at, preferences.language)} · {formatTime(event.starts_at, preferences.language)}</dd></div>
              <div><dt>{t('Venue')}</dt><dd>{event.venue_name}<br />{event.venue_address}</dd></div>
              <div><dt>{t('Cost')}</dt><dd>{event.cost_label}</dd></div>
              <div><dt>{t('Attendance mode')}</dt><dd>
                {isFull
                  ? approvalRequired
                    ? t('Waitlist first; organizer review begins only if a place becomes available.')
                    : t('Join the waitlist; registration is confirmed if a place becomes available.')
                  : approvalRequired
                    ? t('Organizer approval required; your seat is reserved while they review your request.')
                    : t('Instant confirmation.')}
              </dd></div>
            </dl>
            <ConflictWarning eventId={event.id} />
            {approvalRequired ? (
              <div className={`stack ${styles.personaConsentBlock}`}>
                <label className={styles.personaConsent} htmlFor={personaConsentId}>
                  <input
                    id={personaConsentId}
                    type="checkbox"
                    checked={personaShared}
                    disabled={submitting || (retryable && error !== null)}
                    aria-describedby={personaHelpId}
                    onChange={(change) => setPersonaShared(change.target.checked)}
                  />
                  <span>{t("Share my nickname, age bracket, tags, pronouns, and icebreaker with this event's authorized reviewers if my request is reviewed.")}</span>
                </label>
                <p className="muted" id={personaHelpId}>
                  {t("This optional choice starts unchecked and applies only to this event. It does not change your profile's global visibility.")}
                </p>
                {!isFull && event.review_window_minutes ? (
                  <p className="muted">
                    {t('Organizer review window: up to {minutes} minutes; the event start may shorten it.', { minutes: event.review_window_minutes })}
                  </p>
                ) : null}
              </div>
            ) : null}
            {warningState === 'loading' ? <p role="status">{t('Checking for a block warning…')}</p> : null}
            {warningState === 'error' && !serverWarning ? (
              <div role="alert">
                <p className="muted">{t('The warning could not be checked. You may continue, but the server will check before accepting registration.')}</p>
                <button className="button button-secondary" type="button" onClick={() => void refreshBlockWarning()}>
                  {t('Retry block warning check')}
                </button>
              </div>
            ) : null}
            {requiresBlockAcknowledgement ? (
              <section className={`panel error ${styles.personaConsentBlock}`} role="alert" aria-describedby={blockWarningHelpId}>
                <p id={blockWarningHelpId}>{t(serverWarning
                  ? 'The server found that someone you blocked is confirmed for this event. Their identity is not shown.'
                  : 'Someone you blocked is confirmed for this event. Their identity is not shown.')}</p>
                {blockedWarningConflict ? <p>{registrationErrorMessage}</p> : null}
                {serverWarning && warningState === 'error' ? (
                  <div>
                    <p>{t('We could not refresh the warning. Confirm to proceed; the server will check again before admission.')}</p>
                    <button className="button button-secondary" type="button" onClick={() => void refreshBlockWarning()}>
                      {t('Retry block warning check')}
                    </button>
                  </div>
                ) : null}
                <label className={styles.personaConsent} htmlFor={`${confirmationDialogId}-block-acknowledged`}>
                  <input
                    id={`${confirmationDialogId}-block-acknowledged`}
                    type="checkbox"
                    checked={blockWarningAcknowledged}
                    disabled={submitting || warningState === 'loading' || (retryable && error !== null)}
                    aria-describedby={blockWarningHelpId}
                    onChange={change => setBlockWarningAcknowledged(change.target.checked)}
                  />
                  <span>{t('I understand and want to continue with registration.')}</span>
                </label>
              </section>
            ) : null}
            {error && !blockedWarningConflict ? (
              <div className="panel error" role="alert" aria-live="assertive">
                <p>{registrationErrorMessage}</p>
                {profileClue ? <p><Link href="/profile">{t('Review your profile before trying again.')}</Link></p> : null}
              </div>
            ) : null}
            <div className={`actions ${styles.sheetActions}`}>
              {(!error || retryable || blockedWarningConflict) ? (
                <button
                  className="button"
                  type="button"
                  onClick={() => { void submitRegistration(); }}
                  disabled={submitting || warningState === 'loading' || (requiresBlockAcknowledgement && !blockWarningAcknowledged)}
                  aria-live="polite"
                >
                  {submitting
                    ? t('Submitting…')
                    : blockedWarningConflict
                      ? t('Continue with registration')
                      : error
                      ? t('Retry registration')
                      : isFull
                        ? t('Join waitlist')
                        : approvalRequired
                          ? t('Send registration request')
                          : t('Confirm your registration')}
                </button>
              ) : null}
              <button className="button button-secondary" type="button" onClick={closeConfirmation} disabled={submitting}>
                {error && !retryable ? t('Close') : t('Cancel')}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
