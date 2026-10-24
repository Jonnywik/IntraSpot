'use client';

import {useEffect, useState} from 'react';
import {ApiError, api} from '@/lib/api';
import {formatDate, formatTime} from '@/lib/date';
import {useT} from '@/lib/i18n';
import {usePreferences} from '@/lib/preferences';
import type {EventConflictsOut} from '@/lib/types';
import {usePlanningSession} from './use-planning-session';
import styles from './planning.module.css';

type ConflictState = {key: string; conflicts: EventConflictsOut | null; loading: boolean; error: string | null};

export function ConflictWarning({eventId, revision = 0}: {eventId: string; revision?: number}) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const {actor, token, authLoading, identity, createRequest} = usePlanningSession();
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<ConflictState | null>(null);
  const queryKey = identity + '\u0000' + eventId + '\u0000' + String(revision) + '\u0000' + String(refresh);

  useEffect(() => {
    if (authLoading || !actor || !token) return;
    const request = createRequest();
    void api<EventConflictsOut>('/me/event-conflicts/' + encodeURIComponent(eventId), {
      token,
      signal: request.controller.signal,
    }).then((conflicts) => {
      if (request.isCurrent()) {
        setState({key: queryKey, conflicts, loading: false, error: null});
      }
    }).catch((error: unknown) => {
      if (request.isCurrent()) {
        const message = error instanceof ApiError && error.status === 401
          ? 'Your sign-in expired. Sign in again to continue.'
          : 'Could not check schedule conflicts. Please retry.';
        setState({key: queryKey, conflicts: null, loading: false, error: message});
      }
    }).finally(request.release);
    return () => {
      request.controller.abort();
      request.release();
    };
  }, [actor, authLoading, createRequest, eventId, queryKey, token]);

  if (authLoading && !actor) return <p className="muted" role="status">{t('Checking your account…')}</p>;
  if (!actor || !token) return <p className="muted">{t('Sign in to check schedule conflicts.')}</p>;

  const current = state?.key === queryKey
    ? state
    : {key: queryKey, conflicts: null, loading: true, error: null};
  if (current.loading) return <p className="muted" role="status">{t('Checking for schedule conflicts…')}</p>;
  if (current.error) {
    return (
      <div className="panel error" role="alert">
        <p>{t(current.error)}</p>
        <button className="button button-secondary" type="button" onClick={() => setRefresh((value) => value + 1)}>{t('Retry')}</button>
      </div>
    );
  }
  if (!current.conflicts) return null;
  if (!current.conflicts.conflicts.length) return <p className="panel muted" role="status">{t('No schedule conflicts found.')}</p>;

  return (
    <aside className={'panel ' + styles.planning} aria-label={t('Schedule conflicts with your confirmed events:')}>
      <p>{t('Schedule conflicts with your confirmed events:')}</p>
      <ul>
        {current.conflicts.conflicts.map((event) => (
          <li key={event.event_id}>
            <strong>{event.title}</strong>
            {' — '}{event.organization_name}
            {' · '}{formatDate(event.starts_at, language)}{' · '}{formatTime(event.starts_at, language)}
          </li>
        ))}
      </ul>
      <p className="muted">{t('Schedule conflict advisory only; it does not affect registration.')}</p>
    </aside>
  );
}
