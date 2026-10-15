'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { Feedback } from '@/components/feedback';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useApiResource } from '@/lib/use-api-resource';
import { useSession } from '@/lib/session';
import type { MyRegistration, Registration } from '@/lib/types';

type RegistrationStatus = 'confirmed' | 'waitlisted' | 'pending' | 'reconfirmation_required' | 'cancelled' | 'rejected';
type AttendeeRegistration = Omit<Registration, 'status'> & {
  status: RegistrationStatus;
  review_deadline?: string | null;
  reconfirm_deadline?: string | null;
  reconfirm_revision?: number | null;
};
type AttendeeMyRegistration = Omit<MyRegistration, 'status'> & {
  status: RegistrationStatus;
  review_deadline?: string | null;
  reconfirm_deadline?: string | null;
  reconfirm_revision?: number | null;
};
type RegistrationTab = 'pending' | 'confirmed' | 'waitlist' | 'past';

function formatDeadline(value: string | null | undefined) {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  return `${formatDate(value)} · ${formatTime(value)}`;
}

function statusLabel(status: RegistrationStatus) {
  if (status === 'waitlisted') return 'Waitlist';
  if (status === 'reconfirmation_required') return 'Reconfirmation required';
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function eventDetailsHref(eventId: string) {
  return `/events?eventId=${encodeURIComponent(eventId)}`;
}

function eventDate(startsAt: string | null) {
  return startsAt ? `${formatDate(startsAt)} · ${formatTime(startsAt)}` : 'Event date unavailable';
}

function WaitlistDetails({ registration }: { registration: AttendeeMyRegistration }) {
  return (
    <div className="stack">
      <p>Waitlist position: {registration.waitlist_position ?? 'Not provided'}.</p>
      {registration.waitlist_message ? <p>{registration.waitlist_message}</p> : null}
    </div>
  );
}

function RegistrationCard({
  registration,
  now,
  withdrawing,
  withdrawError,
  reconfirming,
  reconfirmError,
  submittedRevision,
  onWithdraw,
  onReconfirm,
  onRefresh,
}: {
  registration: AttendeeMyRegistration;
  now: number | null;
  withdrawing: boolean;
  withdrawError: Error | null;
  reconfirming: boolean;
  reconfirmError: Error | null;
  submittedRevision: number | null;
  onWithdraw: (registration: AttendeeMyRegistration) => void;
  onReconfirm: (registration: AttendeeMyRegistration, accept: boolean) => void;
  onRefresh: () => void;
}) {
  const active = ['confirmed', 'waitlisted', 'pending'].includes(registration.status);
  const canWithdraw = !registration.is_past && active &&
    now !== null &&
    registration.starts_at !== null &&
    Date.parse(registration.starts_at) > now;
  const reviewDeadline = formatDeadline(registration.review_deadline);
  const reviewDeadlineAt = registration.review_deadline ? Date.parse(registration.review_deadline) : Number.NaN;
  const reconfirmDeadline = formatDeadline(registration.reconfirm_deadline);
  const reconfirmDeadlineAt = registration.reconfirm_deadline ? Date.parse(registration.reconfirm_deadline) : Number.NaN;
  const hasCurrentReconfirmation = registration.status === 'reconfirmation_required' &&
    Number.isInteger(registration.reconfirm_revision) && Number.isFinite(reconfirmDeadlineAt);
  const responseAlreadySubmitted = hasCurrentReconfirmation && submittedRevision === registration.reconfirm_revision;
  const canReconfirm = hasCurrentReconfirmation && now !== null && reconfirmDeadlineAt > now && !registration.is_past;

  return (
    <article className="event-card stack">
      <header>
        <div>
          <p className="muted">{registration.organization_name}</p>
          <h2>{registration.event_title ?? 'Event details unavailable'}</h2>
        </div>
        <span className={`status-chip ${registration.status}`}>{statusLabel(registration.status)}</span>
      </header>
      <p>{eventDate(registration.starts_at)}</p>
      {registration.status === 'waitlisted' ? <WaitlistDetails registration={registration} /> : null}
      {registration.status === 'pending' ? (
        <>
          <p>
            Your request is awaiting organizer review. A seat is reserved for you
            {reviewDeadline ? ` until ${reviewDeadline}` : ' while it is reviewed'}.
            {!reviewDeadline ? ' Refresh your registrations for the current review deadline.' : ''}
            {reviewDeadline && now !== null && reviewDeadlineAt <= now ? ' The deadline has passed; refresh to check the current status.' : ''}
          </p>
          {reviewDeadline && now !== null && reviewDeadlineAt <= now ? (
            <button className="button button-secondary" type="button" onClick={onRefresh}>Refresh registrations</button>
          ) : null}
        </>
      ) : null}
      {registration.status === 'reconfirmation_required' ? (
        <div className="stack">
          <p>
            {responseAlreadySubmitted
              ? 'Your response was received. Refresh registrations to check the updated status.'
              : `Your seat is reserved. Accept or decline by ${reconfirmDeadline ?? 'the organizer-set deadline'}.`}
          </p>
          {!hasCurrentReconfirmation ? (
            <p className="muted">The current request details are unavailable. Refresh registrations before responding.</p>
          ) : null}
          {hasCurrentReconfirmation && now !== null && reconfirmDeadlineAt <= now ? (
            <p className="muted" role="status">The deadline has passed. Refresh registrations to check the current status.</p>
          ) : null}
          {now === null ? <p className="muted" role="status">Checking the response deadline…</p> : null}
          {canReconfirm && !reconfirmError && !responseAlreadySubmitted ? (
            <div className="actions">
              <button className="button" type="button" onClick={() => onReconfirm(registration, true)} disabled={reconfirming}>
                {reconfirming ? 'Saving…' : 'Accept and keep my seat'}
              </button>
              <button className="button button-secondary" type="button" onClick={() => onReconfirm(registration, false)} disabled={reconfirming}>
                Decline seat
              </button>
            </div>
          ) : null}
          {reconfirmError ? (
            <div className="panel error" role="alert">
              <p>{reconfirmError.message}</p>
              <p>Refresh registrations to check whether your response took effect.</p>
              <button className="button button-secondary" type="button" onClick={onRefresh}>Refresh registrations</button>
            </div>
          ) : null}
        </div>
      ) : null}
      {registration.status === 'cancelled' ? <p className="muted">This registration is cancelled.</p> : null}
      {registration.status === 'rejected' ? <p className="muted">This registration request was rejected.</p> : null}
      <div className="actions">
        <Link className="button button-secondary" href={eventDetailsHref(registration.event_id)}>
          Event details
        </Link>
        {registration.status === 'confirmed' ? (
          <Link className="button button-secondary" href={`/chat?eventId=${encodeURIComponent(registration.event_id)}`}>
            Open event chat
          </Link>
        ) : null}
        {canWithdraw ? (
          <button className="button button-danger" type="button" onClick={() => onWithdraw(registration)} disabled={withdrawing}>
            {withdrawing ? 'Withdrawing…' : 'Withdraw registration'}
          </button>
        ) : null}
      </div>
      {withdrawError ? (
        <div className="panel error" role="alert">
          <p>{withdrawError.message}</p>
          <p>Refresh your registrations to check the current status before trying again.</p>
          <button className="button button-secondary" type="button" onClick={onRefresh}>Refresh registrations</button>
        </div>
      ) : null}
    </article>
  );
}

function FutureCancellation({ registration }: { registration: AttendeeMyRegistration }) {
  return (
    <article className="event-card stack">
      <header>
        <div>
          <p className="muted">{registration.organization_name}</p>
          <h3>{registration.event_title ?? 'Event details unavailable'}</h3>
        </div>
        <span className={`status-chip ${registration.status}`}>{statusLabel(registration.status)}</span>
      </header>
      <p className="muted">
        {registration.status === 'rejected' ? 'This registration request was rejected.' : 'This registration is cancelled.'}
        {' '}The event is still upcoming.
      </p>
      <p>{eventDate(registration.starts_at)}</p>
      <div className="actions">
        <Link className="button button-secondary" href={eventDetailsHref(registration.event_id)}>
          Event details
        </Link>
      </div>
    </article>
  );
}

export function MyEvents() {
  const { version } = useSession();
  const requestedTab = useSearchParams().get('tab');
  const initialTab: RegistrationTab = requestedTab === 'pending' || requestedTab === 'waitlist' || requestedTab === 'past'
    ? requestedTab : 'confirmed';
  return <MyEventsContent key={`${version}:${initialTab}`} initialTab={initialTab} />;
}

function MyEventsContent({initialTab}: {initialTab: RegistrationTab}) {
  const { actor, token, authLoading } = useSession();
  const path = actor && token ? '/me/registrations' : null;
  const { data, loading, error, reload } = useApiResource<AttendeeMyRegistration[]>(path, token);
  const [tab, setTab] = useState<RegistrationTab>(initialTab);
  const [now, setNow] = useState<number | null>(null);
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null);
  const [withdrawError, setWithdrawError] = useState<{ id: string; error: Error } | null>(null);
  const [reconfirmingId, setReconfirmingId] = useState<string | null>(null);
  const [reconfirmError, setReconfirmError] = useState<{ id: string; error: Error } | null>(null);
  const [reconfirmSuccess, setReconfirmSuccess] = useState<string | null>(null);
  const [submittedReconfirmations, setSubmittedReconfirmations] = useState<Record<string, number>>({});
  const mutation = useRef<AbortController | null>(null);

  useEffect(() => {
    const firstUpdate = window.setTimeout(() => setNow(Date.now()), 0);
    const clock = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      window.clearTimeout(firstUpdate);
      window.clearInterval(clock);
      mutation.current?.abort();
    };
  }, []);

  async function withdraw(registration: AttendeeMyRegistration) {
    if (!token || mutation.current || !['confirmed', 'waitlisted', 'pending'].includes(registration.status)) return;
    const startsAt = registration.starts_at ? Date.parse(registration.starts_at) : Number.NaN;
    if (registration.is_past || !Number.isFinite(startsAt) || startsAt <= Date.now()) {
      setNow(Date.now());
      setWithdrawError({ id: registration.id, error: new Error('Withdrawals are available only before the event starts.') });
      return;
    }

    const requestController = new AbortController();
    mutation.current = requestController;
    setWithdrawingId(registration.id);
    setWithdrawError(null);
    try {
      await api<AttendeeRegistration>(`/events/${encodeURIComponent(registration.event_id)}/registrations/me`, {
        token,
        method: 'DELETE',
        signal: requestController.signal,
      });
      if (!requestController.signal.aborted) reload();
    } catch (caught) {
      if (!requestController.signal.aborted) {
        setWithdrawError({
          id: registration.id,
          error: caught instanceof Error ? caught : new ApiError(0, 'withdrawal_failed', 'The withdrawal could not be confirmed.'),
        });
      }
    } finally {
      if (!requestController.signal.aborted) setWithdrawingId(null);
      if (mutation.current === requestController) mutation.current = null;
    }
  }

  async function reconfirm(registration: AttendeeMyRegistration, accept: boolean) {
    if (!token || mutation.current || registration.status !== 'reconfirmation_required') return;
    const revision = registration.reconfirm_revision;
    const deadline = registration.reconfirm_deadline ? Date.parse(registration.reconfirm_deadline) : Number.NaN;
    if (typeof revision !== 'number' || !Number.isInteger(revision) || !Number.isFinite(deadline) || deadline <= Date.now()) {
      setReconfirmError({
        id: registration.id,
        error: new ApiError(409, 'reconfirmation_stale', 'The current reconfirmation request is unavailable or expired. Refresh registrations to check its status.'),
      });
      return;
    }

    const requestController = new AbortController();
    mutation.current = requestController;
    setReconfirmingId(registration.id);
    setReconfirmError(null);
    setReconfirmSuccess(null);
    try {
      await api<AttendeeRegistration>(`/events/${encodeURIComponent(registration.event_id)}/registrations/me/reconfirmation`, {
        token,
        method: 'POST',
        body: { accept, revision },
        signal: requestController.signal,
      });
      if (!requestController.signal.aborted) {
        setSubmittedReconfirmations((current) => ({ ...current, [registration.id]: revision }));
        setReconfirmSuccess(accept
          ? `Your seat for ${registration.event_title ?? 'this event'} is confirmed.`
          : `You declined your seat for ${registration.event_title ?? 'this event'}.`);
        reload();
      }
    } catch (caught) {
      if (!requestController.signal.aborted) {
        const cause = caught instanceof ApiError
          ? caught
          : new ApiError(0, 'reconfirmation_failed', 'Your response could not be confirmed. Refresh registrations before trying again.');
        const error = cause.status === 403
          ? new ApiError(403, cause.code, 'Your account is not authorized to change this registration. Refresh to check its current status.')
          : cause.status === 401
            ? new ApiError(401, cause.code, 'Your sign-in has expired. Sign in again, then refresh registrations.')
            : cause;
        setReconfirmError({ id: registration.id, error });
      }
    } finally {
      if (!requestController.signal.aborted) setReconfirmingId(null);
      if (mutation.current === requestController) mutation.current = null;
    }
  }

  if (authLoading && !actor) {
    return (
      <section className="stack">
        <header className="page-heading"><p className="eyebrow">YOUR EVENTS</p><h1>My Events</h1></header>
        <p className="panel muted" role="status">Checking your account…</p>
      </section>
    );
  }

  if (!actor || !token) {
    return (
      <section className="stack">
        <header className="page-heading"><p className="eyebrow">YOUR EVENTS</p><h1>My Events</h1></header>
        <p className="panel muted">Sign in from the header to view your registrations.</p>
      </section>
    );
  }

  function refreshRegistration(registrationId: string) {
    setWithdrawError((current) => current?.id === registrationId ? null : current);
    setReconfirmError((current) => current?.id === registrationId ? null : current);
    reload();
  }

  const registrations = data ?? [];
  const visibleRegistrations = registrations.filter((registration) => {
    if (tab === 'past') return registration.is_past;
    if (registration.is_past) return false;
    if (tab === 'pending') return registration.status === 'pending' || registration.status === 'reconfirmation_required';
    if (tab === 'confirmed') return registration.status === 'confirmed';
    return registration.status === 'waitlisted';
  });
  const futureCancellations = registrations.filter((registration) =>
    !registration.is_past && (registration.status === 'cancelled' || registration.status === 'rejected'));

  return (
    <section className="stack">
      <header className="page-heading">
        <p className="eyebrow">YOUR EVENTS</p>
        <h1>My Events</h1>
      </header>

      <div className="tabs" role="tablist" aria-label="Registration status">
        <button type="button" role="tab" aria-selected={tab === 'pending'} onClick={() => setTab('pending')}>
          Pending
        </button>
        <button type="button" role="tab" aria-selected={tab === 'confirmed'} onClick={() => setTab('confirmed')}>
          Confirmed
        </button>
        <button type="button" role="tab" aria-selected={tab === 'waitlist'} onClick={() => setTab('waitlist')}>
          Waitlist
        </button>
        <button type="button" role="tab" aria-selected={tab === 'past'} onClick={() => setTab('past')}>
          Past
        </button>
      </div>
      {reconfirmSuccess ? <p className="panel muted" role="status">{reconfirmSuccess}</p> : null}

      <Feedback loading={loading} error={error} onRetry={reload}>
        <div className="stack">
          {visibleRegistrations.length ? (
            <div className="feed">
              {visibleRegistrations.map((registration) => (
                <RegistrationCard
                  key={registration.id}
                  registration={registration}
                  now={now}
                  withdrawing={withdrawingId === registration.id}
                  withdrawError={withdrawError?.id === registration.id ? withdrawError.error : null}
                  reconfirming={reconfirmingId === registration.id}
                  reconfirmError={reconfirmError?.id === registration.id ? reconfirmError.error : null}
                  submittedRevision={submittedReconfirmations[registration.id] ?? null}
                  onWithdraw={(item) => { void withdraw(item); }}
                  onReconfirm={(item, accept) => { void reconfirm(item, accept); }}
                  onRefresh={() => refreshRegistration(registration.id)}
                />
              ))}
            </div>
          ) : (
            <p className="panel empty-state muted">
              {tab === 'past'
                ? 'Past registrations will appear here.'
                : tab === 'waitlist'
                  ? 'You have no upcoming waitlist registrations.'
                  : tab === 'pending'
                    ? 'You have no pending approvals or reconfirmation requests.'
                    : 'You have no upcoming confirmed registrations.'}
            </p>
          )}

          {futureCancellations.length ? (
            <section className="stack" aria-labelledby="closed-upcoming-title">
              <div>
                <h2 id="closed-upcoming-title">Closed upcoming registrations</h2>
                <p className="muted">These registrations are closed, and the API still marks their events as upcoming.</p>
              </div>
              <div className="feed">
                {futureCancellations.map((registration) => (
                  <FutureCancellation key={registration.id} registration={registration} />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </Feedback>
    </section>
  );
}
