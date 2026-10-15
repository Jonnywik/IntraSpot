'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useSession } from '@/lib/session';
import type { PublicEvent, Registration } from '@/lib/types';

type AttendeeRegistration = Omit<Registration, 'status'> & {
  status: 'confirmed' | 'waitlisted' | 'pending' | 'reconfirmation_required' | 'cancelled' | 'rejected';
  review_deadline?: string | null;
  reconfirm_deadline?: string | null;
};

function formatDeadline(value: string | null | undefined) {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  return `${formatDate(value)} · ${formatTime(value)}`;
}

export function RegistrationAction({ event, onOutcome }: { event: PublicEvent; onOutcome?: () => void }) {
  const { actor, token, authLoading } = useSession();
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<AttendeeRegistration | null>(null);
  const [personaShared, setPersonaShared] = useState(false);
  const [now, setNow] = useState<number | null>(null);
  const attemptKey = useRef<{ eventId: string; key: string; personaShared: boolean } | null>(null);
  const controller = useRef<AbortController | null>(null);
  const dialog = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const outcome = useRef<HTMLDivElement>(null);

  useEffect(() => () => controller.current?.abort(), []);

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
        setOpen(false);
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
    if (result) outcome.current?.focus();
  }, [result]);

  const retryable = error !== null && (error.status === 0 || error.status >= 500);
  const profileClue = error !== null &&
    ['profile_incomplete', 'registration_ineligible', 'plm_email_required'].includes(error.code);
  const registrationMode = event.registration_mode;
  const approvalRequired = registrationMode === 'approval';
  const isFull = event.remaining_spots <= 0;
  const startsAt = Date.parse(event.starts_at);
  const eventStarted = error?.code === 'event_started' ||
    (now !== null && (!Number.isFinite(startsAt) || startsAt <= now));
  const actionLabel = isFull ? 'Join waitlist' : approvalRequired ? 'Request to register' : 'Register';
  const personaConsentId = `registration-persona-${event.id}`;

  function openConfirmation() {
    if (!Number.isFinite(startsAt) || startsAt <= Date.now()) {
      setNow(Date.now());
      return;
    }
    if (error && !retryable) {
      attemptKey.current = null;
      setError(null);
    }
    setOpen(true);
  }

  async function submitRegistration() {
    if (!token || !actor?.eligible || !actor.profile_complete || submitting) return;
    if (!Number.isFinite(startsAt) || startsAt <= Date.now()) {
      setNow(Date.now());
      setOpen(false);
      return;
    }

    const savedAttempt = attemptKey.current?.eventId === event.id
      ? attemptKey.current
      : { eventId: event.id, key: window.crypto.randomUUID(), personaShared: approvalRequired && personaShared };
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
        body: { persona_shared: savedAttempt.personaShared },
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
      setError(caught instanceof ApiError
        ? caught
        : new ApiError(0, 'request_failed', 'The registration result could not be confirmed. Retry with the same request key.'));
    } finally {
      if (!requestController.signal.aborted) setSubmitting(false);
      if (controller.current === requestController) controller.current = null;
    }
  }

  if (authLoading && !actor) {
    return <p className="muted" role="status">Checking your registration access…</p>;
  }
  if (!token || !actor) {
    return <p className="muted">Sign in from the header to register for this event.</p>;
  }
  if (result) {
    const reviewDeadline = formatDeadline(result.review_deadline);
    const reconfirmDeadline = formatDeadline(result.reconfirm_deadline);
    return (
      <div className="panel stack" role="status" tabIndex={-1} ref={outcome}>
        {result.status === 'confirmed' ? <p>Your registration is confirmed.</p> : null}
        {result.status === 'pending' ? (
          <p>
            Your request is pending organizer approval. A seat is reserved for you
            {reviewDeadline ? ` until ${reviewDeadline}` : ' while it is reviewed'}.
            {!reviewDeadline ? ' Check My Events for the current review deadline.' : ''}
          </p>
        ) : null}
        {result.status === 'reconfirmation_required' ? (
          <p>
            A seat is reserved while you reconfirm
            {reconfirmDeadline ? ` by ${reconfirmDeadline}` : '. Check My Events for the current deadline'}.
          </p>
        ) : null}
        {result.status === 'waitlisted' ? (
          <div className="stack">
            <p>Waitlist position: {result.waitlist_position ?? 'Not provided'}.</p>
            {result.waitlist_message ? <p>{result.waitlist_message}</p> : null}
          </div>
        ) : null}
        {result.status === 'rejected' ? <p>Your registration request was rejected.</p> : null}
        {result.status === 'cancelled' ? <p>Registration status: Cancelled.</p> : null}
        <Link className="button button-secondary" href={`/my-events?tab=${result.status === 'waitlisted' ? 'waitlist' : result.status === 'pending' || result.status === 'reconfirmation_required' ? 'pending' : 'confirmed'}`}>View My Events</Link>
      </div>
    );
  }
  if (!actor.eligible) {
    return <p className="muted">Registration requires an eligible PLM account. Review your <Link href="/profile">profile</Link>.</p>;
  }
  if (!actor.profile_complete) {
    return <p className="muted">Complete your profile before registering. <Link href="/profile">Update your profile</Link>.</p>;
  }

  if (eventStarted) {
    return (
      <div className="stack">
        <button className="button button-secondary" type="button" disabled>Registration closed</button>
        <p className="muted" role="status">
          {error?.code === 'event_started' ? error.message : 'Registration is closed because the event has started.'}
        </p>
      </div>
    );
  }
  if (now === null) {
    return <p className="muted" role="status">Checking event availability…</p>;
  }

  return (
    <div className="stack">
      <button className="button" type="button" onClick={openConfirmation} ref={trigger}>
        {actionLabel}
      </button>

      {error && !open ? (
        <div className="panel error" role="alert">
          <p>{error.message}</p>
          {profileClue ? <p>Review your <Link href="/profile">profile</Link> before trying again.</p> : null}
          {retryable ? (
            <button className="button button-secondary" type="button" onClick={() => { setOpen(true); void submitRegistration(); }}>
              Retry registration
            </button>
          ) : null}
        </div>
      ) : null}

      {open ? (
        <div
          className="sheet"
          role="presentation"
        >
          <section
            className="stack"
            role="dialog"
            aria-modal="true"
            aria-labelledby="registration-confirmation-title"
            tabIndex={-1}
            ref={dialog}
          >
            <div>
              <p className="eyebrow">REGISTRATION</p>
              <h2 id="registration-confirmation-title">
                {isFull ? 'Join the waitlist' : approvalRequired ? 'Request organizer approval' : 'Confirm your registration'}
              </h2>
            </div>
            <div className="stack">
              <p><strong>Date and time</strong><br />{formatDate(event.starts_at)} · {formatTime(event.starts_at)}</p>
              <p><strong>Venue</strong><br />{event.venue_name}<br />{event.venue_address}</p>
              <p><strong>Cost</strong><br />{event.cost_label}</p>
              <p><strong>Attendance mode</strong><br />
                {isFull
                  ? approvalRequired
                    ? 'Waitlist first; organizer review begins only if a place becomes available.'
                    : 'Join the waitlist; registration is confirmed if a place becomes available.'
                  : approvalRequired
                    ? 'Organizer approval required; your seat is reserved while they review your request.'
                    : 'Instant confirmation.'}
              </p>
            </div>
            {approvalRequired ? (
              <div className="stack">
                <label htmlFor={personaConsentId}>
                  <input
                    id={personaConsentId}
                    type="checkbox"
                    checked={personaShared}
                    disabled={submitting || (retryable && error !== null)}
                    onChange={(change) => setPersonaShared(change.target.checked)}
                  />
                  Share my nickname, age bracket, tags, pronouns, and icebreaker with this event&apos;s authorized reviewers if my request is reviewed.
                </label>
                <p className="muted">
                  This optional choice starts unchecked and applies only to this event. It does not change your profile&apos;s global visibility.
                </p>
                {!isFull && event.review_window_minutes ? (
                  <p className="muted">
                    Organizer review window: up to {event.review_window_minutes} minutes; the event start may shorten it.
                  </p>
                ) : null}
              </div>
            ) : null}
            {error ? (
              <div className="panel error" role="alert">
                <p>{error.message}</p>
                {profileClue ? <p>Review your <Link href="/profile">profile</Link> before trying again.</p> : null}
              </div>
            ) : null}
            <div className="actions">
              {(!error || retryable) ? (
                <button className="button" type="button" onClick={() => { void submitRegistration(); }} disabled={submitting}>
                  {submitting
                    ? 'Submitting…'
                    : error
                      ? 'Retry registration'
                      : isFull
                        ? 'Join waitlist'
                        : approvalRequired
                          ? 'Send registration request'
                          : 'Confirm registration'}
                </button>
              ) : null}
              <button className="button button-secondary" type="button" onClick={() => setOpen(false)} disabled={submitting}>
                {error && !retryable ? 'Close' : 'Cancel'}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
