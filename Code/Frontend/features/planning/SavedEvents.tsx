'use client';

import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import Link from 'next/link';
import {ApiError, api} from '@/lib/api';
import {formatDate, formatTime} from '@/lib/date';
import {useT} from '@/lib/i18n';
import {usePreferences} from '@/lib/preferences';
import type {SavedEventOut, SavedEventState} from '@/lib/types';
import {EventCalendar} from './EventCalendar';
import {FeaturedBadge} from '@/features/featured/FeaturedBadge';
import {usePlanningSession} from './use-planning-session';
import styles from './planning.module.css';

type SavedListState = {
  key: string;
  data: SavedEventOut[] | null;
  loading: boolean;
  error: string | null;
  removing: string | null;
};

function SavedEventCard({
  savedEvent,
  removing,
  onRemove,
}: {
  savedEvent: SavedEventOut;
  removing: boolean;
  onRemove: (eventId: string) => void;
}) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const event = savedEvent.event;
  return (
    <article className="event-card stack">
      <header>
        <div>
          <p className="muted">{event?.organization_name ?? t('Saved')}</p>
          {event?.is_featured && <FeaturedBadge />}
          <h3>{event?.title ?? t('Event unavailable')}</h3>
        </div>
      </header>
      {event ? (
        <>
          <p>
            {event.starts_at && Number.isFinite(Date.parse(event.starts_at))
              ? formatDate(event.starts_at, language) + ' · ' + formatTime(event.starts_at, language)
              : t('Event date unavailable')}
          </p>
          <p className="muted">{event.summary}</p>
          <Link className="button button-secondary" href={'/events?eventId=' + encodeURIComponent(savedEvent.event_id)}>
            {t('Event details')}
          </Link>
        </>
      ) : (
        <p className="muted">{t('This event is no longer publicly available. You can remove it from your saved list.')}</p>
      )}
      <button
        className="button button-secondary"
        type="button"
        disabled={removing}
        onClick={() => onRemove(savedEvent.event_id)}
      >
        {removing ? t('Removing…') : t('Remove saved event')}
      </button>
    </article>
  );
}

export function SavedEvents({view}: {view: 'list' | 'calendar'}) {
  const t = useT();
  const {actor, token, authLoading, identity, createRequest} = usePlanningSession();
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<SavedListState | null>(null);
  const mutation = useRef<AbortController | null>(null);
  const queryKey = identity + '\u0000saved-events\u0000' + String(refresh);
  const activeQueryKey = useRef(queryKey);

  useLayoutEffect(() => {
    activeQueryKey.current = queryKey;
  }, [queryKey]);

  useEffect(() => {
    if (authLoading || !actor || !token) return;
    const request = createRequest();
    void api<SavedEventOut[]>('/me/saved-events', {token, signal: request.controller.signal})
      .then((data) => {
        if (request.isCurrent()) {
          setState({key: queryKey, data, loading: false, error: null, removing: null});
        }
      })
      .catch((error: unknown) => {
        if (request.isCurrent()) {
          const message = error instanceof ApiError && error.status === 401
            ? 'Your sign-in expired. Sign in again to continue.'
            : 'Could not load saved events. Please retry.';
          setState({key: queryKey, data: null, loading: false, error: message, removing: null});
        }
      })
      .finally(request.release);
    return () => {
      request.controller.abort();
      request.release();
    };
  }, [actor, authLoading, createRequest, queryKey, token]);

  const current = state?.key === queryKey
    ? state
    : {key: queryKey, data: null, loading: Boolean(!authLoading && actor && token), error: null, removing: null};

  async function remove(eventId: string) {
    if (!actor || !token || !current.data || current.removing || mutation.current) return;
    const request = createRequest();
    mutation.current = request.controller;
    setState({...current, removing: eventId, error: null});
    try {
      const result = await api<SavedEventState>('/me/saved-events/' + encodeURIComponent(eventId), {
        token,
        method: 'DELETE',
        signal: request.controller.signal,
      });
      if (request.isCurrent()) {
        setState(!result.saved
          ? {...current, data: current.data.filter((item) => item.event_id !== eventId), removing: null, error: null}
          : {...current, removing: null, error: 'Could not update this saved event. Please retry.'});
      }
    } catch (error) {
      if (request.isCurrent() && activeQueryKey.current === queryKey) {
        const message = error instanceof ApiError && error.status === 401
          ? 'Your sign-in expired. Sign in again to continue.'
          : 'Could not update this saved event. Please retry.';
        setState({...current, removing: null, error: message});
      }
    } finally {
      if (mutation.current === request.controller) mutation.current = null;
      request.release();
    }
  }

  if (authLoading && !actor) return <p className="panel muted" role="status">{t('Checking your account…')}</p>;
  if (!actor || !token) return <p className="panel muted">{t('Sign in from the header to view your saved events.')}</p>;
  if (current.loading) return <p className="panel muted" role="status">{t('Loading saved events…')}</p>;
  if (current.error && !current.data) {
    return (
      <div className="panel error" role="alert">
        <p>{t(current.error)}</p>
        <button className="button button-secondary" type="button" onClick={() => setRefresh((value) => value + 1)}>{t('Retry')}</button>
      </div>
    );
  }
  if (!current.data) return null;

  const renderSavedEvent = (savedEvent: SavedEventOut) => (
    <SavedEventCard
      savedEvent={savedEvent}
      removing={current.removing === savedEvent.event_id}
      onRemove={(eventId) => void remove(eventId)}
    />
  );

  return (
    <section className={styles.planning} aria-labelledby="saved-events-heading" aria-busy={Boolean(current.removing)}>
      <h2 id="saved-events-heading">{t('Saved events')}</h2>
      <p className="muted">{t('Saved events are private and do not reserve a seat.')}</p>
      {current.error ? <p className="panel error" role="alert">{t(current.error)}</p> : null}
      {view === 'list'
        ? current.data.length
          ? <div className="feed">{current.data.map((savedEvent) => <div key={savedEvent.event_id}>{renderSavedEvent(savedEvent)}</div>)}</div>
          : <p className="panel empty-state muted">{t('You have no saved events yet.')}</p>
        : (
          <EventCalendar
            mode="saved"
            savedEvents={current.data}
            renderSavedEvent={renderSavedEvent}
            emptyMessage={t('You have no saved events yet.')}
          />
        )}
    </section>
  );
}
