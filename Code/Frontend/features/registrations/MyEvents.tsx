'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Feedback } from '@/components/feedback';
import { ApiError, api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import { useApiResource } from '@/lib/use-api-resource';
import { useSession } from '@/lib/session';
import type { MyRegistration, Registration } from '@/lib/types';
import attendeeStyles from '@/features/attendee-pages.module.css';
import { EventCalendar } from '@/features/planning/EventCalendar';
import { SavedEvents } from '@/features/planning/SavedEvents';
import { intervalsOverlap } from '@/features/planning/calendar';
import planningStyles from '@/features/planning/planning.module.css';
import { eventChatAvailable } from './presentation';
import { FeaturedBadge } from '@/features/featured/FeaturedBadge';

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
type Translate = ReturnType<typeof useT>;

const registrationTabOrder: RegistrationTab[] = ['pending', 'confirmed', 'waitlist', 'past'];

function formatDeadline(value: string | null | undefined, language: 'en' | 'fil') {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  return `${formatDate(value, language)} · ${formatTime(value, language)}`;
}

function statusLabel(status: RegistrationStatus, t: Translate) {
  const labels: Record<RegistrationStatus, string> = {
    confirmed: t('Confirmed'),
    waitlisted: t('Waitlist'),
    pending: t('Pending'),
    reconfirmation_required: t('Reconfirmation required'),
    cancelled: t('Cancelled'),
    rejected: t('Rejected'),
  };
  return labels[status];
}

function eventDetailsHref(eventId: string) {
  return `/events?eventId=${encodeURIComponent(eventId)}`;
}

function eventDate(startsAt: string | null, t: Translate, language: 'en' | 'fil') {
  return startsAt ? `${formatDate(startsAt, language)} · ${formatTime(startsAt, language)}` : t('Event date unavailable');
}

function WaitlistDetails({ registration }: { registration: AttendeeMyRegistration }) {
  const t = useT();
  const waitlistMessage = !registration.waitlist_message || registration.waitlist_message === 'You are on the waitlist. No estimated wait time is available.'
    ? t('You are on the waitlist. No estimated wait time is available.')
    : registration.waitlist_message;
  return (
    <div className="stack">
      <p>{t('Waitlist position: {position}.', { position: registration.waitlist_position ?? t('Not provided') })}</p>
      {waitlistMessage ? <p>{waitlistMessage}</p> : null}
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
  const t = useT();
  const { preferences: { language } } = usePreferences();
  const active = ['confirmed', 'waitlisted', 'pending'].includes(registration.status);
  const chatAvailable = eventChatAvailable(registration.status, registration.ends_at, now);
  const canWithdraw = !registration.is_past && active &&
    now !== null &&
    registration.starts_at !== null &&
    Date.parse(registration.starts_at) > now;
  const reviewDeadline = formatDeadline(registration.review_deadline, language);
  const reviewDeadlineAt = registration.review_deadline ? Date.parse(registration.review_deadline) : Number.NaN;
  const reconfirmDeadline = formatDeadline(registration.reconfirm_deadline, language);
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
          {registration.is_featured && <FeaturedBadge />}
          <h2>{registration.event_title ?? t('Event details unavailable')}</h2>
        </div>
        <span className={`status-chip ${registration.status} ${attendeeStyles.statusBadge}`}>{statusLabel(registration.status, t)}</span>
      </header>
      <p>{eventDate(registration.starts_at, t, language)}</p>
      {registration.status === 'waitlisted' ? <WaitlistDetails registration={registration} /> : null}
      {registration.status === 'pending' ? (
        <>
          <p>
            {reviewDeadline
              ? t('Your request is awaiting organizer review. A seat is reserved for you until {deadline}.', { deadline: reviewDeadline })
              : t('Your request is awaiting organizer review. A seat is reserved for you while it is reviewed.')}
            {!reviewDeadline ? ` ${t('Refresh your registrations for the current review deadline.')}` : ''}
            {reviewDeadline && now !== null && reviewDeadlineAt <= now ? ` ${t('The deadline has passed; refresh to check the current status.')}` : ''}
          </p>
          {reviewDeadline && now !== null && reviewDeadlineAt <= now ? (
            <button className="button button-secondary" type="button" onClick={onRefresh}>{t('Refresh registrations')}</button>
          ) : null}
        </>
      ) : null}
      {registration.status === 'reconfirmation_required' ? (
        <div className="stack">
          <p>
            {responseAlreadySubmitted
              ? t('Your response was received. Refresh registrations to check the updated status.')
              : t('Your seat is reserved. Accept or decline by {deadline}.', { deadline: reconfirmDeadline ?? t('the organizer-set deadline') })}
          </p>
          {!hasCurrentReconfirmation ? (
            <p className="muted">{t('The current request details are unavailable. Refresh registrations before responding.')}</p>
          ) : null}
          {hasCurrentReconfirmation && now !== null && reconfirmDeadlineAt <= now ? (
            <p className="muted" role="status">{t('The deadline has passed. Refresh registrations to check the current status.')}</p>
          ) : null}
          {now === null ? <p className="muted" role="status">{t('Checking the response deadline…')}</p> : null}
          {canReconfirm && !reconfirmError && !responseAlreadySubmitted ? (
            <div className="actions">
              <button className="button" type="button" onClick={() => onReconfirm(registration, true)} disabled={reconfirming}>
                {reconfirming ? t('Saving…') : t('Accept and keep my seat')}
              </button>
              <button className="button button-secondary" type="button" onClick={() => onReconfirm(registration, false)} disabled={reconfirming}>
                {t('Decline seat')}
              </button>
            </div>
          ) : null}
          {reconfirmError ? (
            <div className="panel error" role="alert">
              <p>{t(reconfirmError.message)}</p>
              <p>{t('Refresh registrations to check whether your response took effect.')}</p>
              <button className="button button-secondary" type="button" onClick={onRefresh}>{t('Refresh registrations')}</button>
            </div>
          ) : null}
        </div>
      ) : null}
      {registration.status === 'cancelled' ? <p className="muted">{t('This registration is cancelled.')}</p> : null}
      {registration.status === 'rejected' ? <p className="muted">{t('This registration request was rejected.')}</p> : null}
      <div className="actions">
        <Link className="button button-secondary" href={eventDetailsHref(registration.event_id)}>
          {t('Event details')}
        </Link>
        {chatAvailable ? (
          <Link className="button button-secondary" href={`/chat?eventId=${encodeURIComponent(registration.event_id)}`}>
            {t('Open event chat')}
          </Link>
        ) : null}
        {canWithdraw ? (
          <button className="button button-danger" type="button" onClick={() => onWithdraw(registration)} disabled={withdrawing}>
            {withdrawing ? t('Withdrawing…') : t('Withdraw registration')}
          </button>
        ) : null}
      </div>
      {withdrawError ? (
        <div className="panel error" role="alert">
          <p>{t(withdrawError.message)}</p>
          <p>{t('Refresh your registrations to check the current status before trying again.')}</p>
          <button className="button button-secondary" type="button" onClick={onRefresh}>{t('Refresh registrations')}</button>
        </div>
      ) : null}
    </article>
  );
}

function FutureCancellation({ registration }: { registration: AttendeeMyRegistration }) {
  const t = useT();
  const { preferences: { language } } = usePreferences();
  return (
    <article className="event-card stack">
      <header>
        <div>
          <p className="muted">{registration.organization_name}</p>
          <h3>{registration.event_title ?? t('Event details unavailable')}</h3>
          {registration.is_featured && <FeaturedBadge />}
        </div>
        <span className={`status-chip ${registration.status} ${attendeeStyles.statusBadge}`}>{statusLabel(registration.status, t)}</span>
      </header>
      <p className="muted">
        {registration.status === 'rejected' ? t('This registration request was rejected.') : t('This registration is cancelled.')}
        {' '}{t('The event is still upcoming.')}
      </p>
      <p>{eventDate(registration.starts_at, t, language)}</p>
      <div className="actions">
        <Link className="button button-secondary" href={eventDetailsHref(registration.event_id)}>
          {t('Event details')}
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
  const t = useT();
  const { actor, token, authLoading } = useSession();
  const path = actor && token ? '/me/registrations' : null;
  const { data, loading, error, reload } = useApiResource<AttendeeMyRegistration[]>(path, token);
  const [tab, setTab] = useState<RegistrationTab>(initialTab);
  const [section, setSection] = useState<'registrations' | 'saved'>('registrations');
  const [view, setView] = useState<'list' | 'calendar'>('list');
  const [now, setNow] = useState<number | null>(null);
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null);
  const [withdrawError, setWithdrawError] = useState<{ id: string; error: Error } | null>(null);
  const [withdrawSuccess, setWithdrawSuccess] = useState<string | null>(null);
  const [reconfirmingId, setReconfirmingId] = useState<string | null>(null);
  const [reconfirmError, setReconfirmError] = useState<{ id: string; error: Error } | null>(null);
  const [reconfirmSuccess, setReconfirmSuccess] = useState<string | null>(null);
  const [submittedReconfirmations, setSubmittedReconfirmations] = useState<Record<string, number>>({});
  const mutation = useRef<AbortController | null>(null);
  const tabButtons = useRef<Partial<Record<RegistrationTab, HTMLButtonElement>>>({});

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
      setWithdrawError({ id: registration.id, error: new Error(t('Withdrawals are available only before the event starts.')) });
      return;
    }

    const requestController = new AbortController();
    mutation.current = requestController;
    setWithdrawingId(registration.id);
    setWithdrawError(null);
    setWithdrawSuccess(null);
    try {
      await api<AttendeeRegistration>(`/events/${encodeURIComponent(registration.event_id)}/registrations/me`, {
        token,
        method: 'DELETE',
        signal: requestController.signal,
      });
      if (!requestController.signal.aborted) {
        setWithdrawSuccess(t('Registration withdrawn for {event}.', { event: registration.event_title ?? t('this event') }));
        reload();
      }
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
          ? t('Your seat for {event} is confirmed.', { event: registration.event_title ?? t('this event') })
          : t('You declined your seat for {event}.', { event: registration.event_title ?? t('this event') }));
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
      <section className={`stack ${attendeeStyles.eventsPage}`}>
        <header className="page-heading"><p className="eyebrow">{t('YOUR EVENTS')}</p><h1>{t('My Events')}</h1></header>
        <p className="panel muted" role="status">{t('Checking your account…')}</p>
      </section>
    );
  }

  if (!actor || !token) {
    return (
      <section className={`stack ${attendeeStyles.eventsPage}`}>
        <header className="page-heading"><p className="eyebrow">{t('YOUR EVENTS')}</p><h1>{t('My Events')}</h1></header>
        <p className="panel muted">{t('Sign in from the header to view your registrations.')}</p>
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
  const tabCounts: Record<RegistrationTab, number> = {
    pending: registrations.filter((registration) => !registration.is_past && (registration.status === 'pending' || registration.status === 'reconfirmation_required')).length,
    confirmed: registrations.filter((registration) => !registration.is_past && registration.status === 'confirmed').length,
    waitlist: registrations.filter((registration) => !registration.is_past && registration.status === 'waitlisted').length,
    past: registrations.filter((registration) => registration.is_past).length,
  };
  const tabLabels: Record<RegistrationTab, string> = {
    pending: t('Pending'),
    confirmed: t('Confirmed'),
    waitlist: t('Waitlist'),
    past: t('Past'),
  };
  const conflictingIds = new Set<string>();
  if (now !== null) {
    const currentConfirmed = registrations.filter((registration) =>
      registration.status === 'confirmed' &&
      registration.ends_at !== null &&
      Date.parse(registration.ends_at) > now);
    for (let left = 0; left < currentConfirmed.length; left += 1) {
      for (let right = left + 1; right < currentConfirmed.length; right += 1) {
        const first = currentConfirmed[left];
        const second = currentConfirmed[right];
        if (intervalsOverlap(first.starts_at, first.ends_at, second.starts_at, second.ends_at)) {
          conflictingIds.add(first.id);
          conflictingIds.add(second.id);
        }
      }
    }
  }
  const ownConfirmedConflicts = registrations.filter((registration) => conflictingIds.has(registration.id));

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, currentTab: RegistrationTab) {
    const index = registrationTabOrder.indexOf(currentTab);
    const nextTab = event.key === 'ArrowRight'
      ? registrationTabOrder[(index + 1) % registrationTabOrder.length]
      : event.key === 'ArrowLeft'
        ? registrationTabOrder[(index - 1 + registrationTabOrder.length) % registrationTabOrder.length]
        : event.key === 'Home'
          ? registrationTabOrder[0]
          : event.key === 'End'
            ? registrationTabOrder[registrationTabOrder.length - 1]
            : null;
    if (!nextTab) return;
    event.preventDefault();
    setTab(nextTab);
    tabButtons.current[nextTab]?.focus();
  }

  function renderRegistrationCard(registration: AttendeeMyRegistration) {
    return (
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
    );
  }

  const emptyRegistrationMessage = tab === 'past'
    ? t('Past registrations will appear here.')
    : tab === 'waitlist'
      ? t('You have no upcoming waitlist registrations.')
      : tab === 'pending'
        ? t('You have no pending approvals or reconfirmation requests.')
        : t('You have no upcoming confirmed registrations.');

  return (
    <section className={`stack ${attendeeStyles.eventsPage}`}>
      <header className="page-heading">
        <p className="eyebrow">{t('YOUR EVENTS')}</p>
        <h1>{t('My Events')}</h1>
      </header>

      <div className={planningStyles.sectionControls} role="group" aria-label={t('Event sections')}>
        <button className={planningStyles.control} type="button" aria-pressed={section === 'registrations'} onClick={() => setSection('registrations')}>
          {t('Registrations')}
        </button>
        <button className={planningStyles.control} type="button" aria-pressed={section === 'saved'} onClick={() => setSection('saved')}>
          {t('Saved')}
        </button>
      </div>
      <div className={planningStyles.viewControls} role="group" aria-label={t('Event view')}>
        <button className={planningStyles.control} type="button" aria-pressed={view === 'list'} onClick={() => setView('list')}>
          {t('List')}
        </button>
        <button className={planningStyles.control} type="button" aria-pressed={view === 'calendar'} onClick={() => setView('calendar')}>
          {t('Calendar')}
        </button>
      </div>

      {section === 'saved' ? <SavedEvents view={view} /> : (
        <>
      <div className={attendeeStyles.registrationTabs} role="tablist" aria-label={t('Registration status')}>
        {registrationTabOrder.map((registrationTab) => (
          <button
            key={registrationTab}
            ref={(element) => { tabButtons.current[registrationTab] = element ?? undefined; }}
            className={attendeeStyles.registrationTab}
            type="button"
            role="tab"
            id={`registration-tab-${registrationTab}`}
            aria-controls="registration-panel"
            aria-selected={tab === registrationTab}
            tabIndex={tab === registrationTab ? 0 : -1}
            onClick={() => setTab(registrationTab)}
            onKeyDown={(event) => handleTabKeyDown(event, registrationTab)}
          >
            <span>{tabLabels[registrationTab]}</span>
            {data ? <span className={attendeeStyles.tabCount}>{tabCounts[registrationTab]}</span> : null}
          </button>
        ))}
      </div>
      {reconfirmSuccess ? <p className="panel muted" role="status">{reconfirmSuccess}</p> : null}
      {withdrawSuccess ? <p className="panel success" role="status">{withdrawSuccess}</p> : null}
      {tab === 'confirmed' && ownConfirmedConflicts.length ? (
        <aside className="panel muted" role="status">
          <p>{t('Schedule conflicts with your confirmed events:')}</p>
          <ul>
            {ownConfirmedConflicts.map((registration) => (
              <li key={registration.id}>
                {registration.event_title ?? t('Event details unavailable')}
                {' — '}{registration.organization_name}
              </li>
            ))}
          </ul>
          <p>{t('Schedule conflict advisory only; it does not affect registration.')}</p>
        </aside>
      ) : null}

      <div id="registration-panel" className={attendeeStyles.registrationPanel} role="tabpanel" aria-labelledby={`registration-tab-${tab}`} tabIndex={0}>
        <Feedback loading={loading} error={error ? new Error(t(error.message)) : null} onRetry={reload}>
          <div className="stack">
            {visibleRegistrations.length
              ? view === 'list'
                ? <div className="feed">{visibleRegistrations.map(renderRegistrationCard)}</div>
                : (
                  <EventCalendar
                    mode="registrations"
                    registrations={visibleRegistrations}
                    renderRegistration={renderRegistrationCard}
                    emptyMessage={emptyRegistrationMessage}
                  />
                )
              : view === 'calendar'
                ? (
                  <EventCalendar
                    mode="registrations"
                    registrations={visibleRegistrations}
                    renderRegistration={renderRegistrationCard}
                    emptyMessage={emptyRegistrationMessage}
                  />
                )
                : <p className="panel empty-state muted">{emptyRegistrationMessage}</p>}

            {futureCancellations.length ? (
              <section className="stack" aria-labelledby="closed-upcoming-title">
                <div>
                  <h2 id="closed-upcoming-title">{t('Closed upcoming registrations')}</h2>
                  <p className="muted">{t('These registrations are closed, and the API still marks their events as upcoming.')}</p>
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
      </div>
        </>
      )}
    </section>
  );
}
