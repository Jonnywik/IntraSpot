'use client';

import {useEffect, useRef, useState} from 'react';
import {ApiError, api} from '@/lib/api';
import {useT} from '@/lib/i18n';
import type {SavedEventState} from '@/lib/types';
import {usePlanningSession} from './use-planning-session';
import styles from './planning.module.css';

type ButtonState = {
  key: string;
  loading: boolean;
  saved: SavedEventState | null;
  error: string | null;
  busy: boolean;
  notice: string | null;
};

export function SaveEventButton({eventId}: {eventId: string}) {
  const t = useT();
  const {actor, token, authLoading, identity, createRequest} = usePlanningSession();
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<ButtonState | null>(null);
  const currentKey = identity + '\u0000' + eventId;
  const queryKey = currentKey + '\u0000' + refresh;
  const mutation = useRef<AbortController | null>(null);

  useEffect(() => {
    if (authLoading || !actor || !token) return;
    const request = createRequest();
    void api<SavedEventState>('/me/saved-events/' + encodeURIComponent(eventId), {
      token,
      signal: request.controller.signal,
    }).then((saved) => {
      if (request.isCurrent()) {
        setState({key: queryKey, loading: false, saved, error: null, busy: false, notice: null});
      }
    }).catch((error: unknown) => {
      if (request.isCurrent()) {
        const message = error instanceof ApiError && error.status === 401
          ? 'Your sign-in expired. Sign in again to continue.'
          : 'Could not check saved status. Please retry.';
        setState({key: queryKey, loading: false, saved: null, error: message, busy: false, notice: null});
      }
    }).finally(request.release);
    return () => {
      request.controller.abort();
      request.release();
    };
  }, [actor, authLoading, createRequest, eventId, queryKey, token]);

  const current = state?.key === queryKey
    ? state
    : {key: queryKey, loading: Boolean(!authLoading && actor && token), saved: null, error: null, busy: false, notice: null};

  async function toggleSaved() {
    if (!token || !actor || !current.saved || current.busy || mutation.current) return;
    const remove = current.saved.saved;
    const request = createRequest();
    mutation.current = request.controller;
    setState({...current, busy: true, error: null, notice: null});
    try {
      const saved = await api<SavedEventState>('/me/saved-events/' + encodeURIComponent(eventId), {
        token,
        method: remove ? 'DELETE' : 'PUT',
        signal: request.controller.signal,
      });
      if (request.isCurrent()) {
        setState({
          key: queryKey,
          loading: false,
          saved,
          error: null,
          busy: false,
          notice: saved.saved ? 'Saved privately for your planning.' : 'Removed from saved events.',
        });
      }
    } catch (error) {
      if (request.isCurrent()) {
        const message = error instanceof ApiError && error.status === 401
          ? 'Your sign-in expired. Sign in again to continue.'
          : 'Could not update this saved event. Please retry.';
        setState({...current, loading: false, busy: false, error: message, notice: null});
      }
    } finally {
      if (mutation.current === request.controller) mutation.current = null;
      request.release();
    }
  }

  if (authLoading && !actor) return <p className="muted" role="status">{t('Checking your account…')}</p>;
  if (!actor || !token) return <p className="muted">{t('Sign in from the header to save events to your private plan.')}</p>;

  return (
    <div className={styles.planning}>
      {current.loading ? <p className="muted" role="status">{t('Checking saved status…')}</p> : null}
      {current.saved ? (
        <button
          className="button button-secondary"
          type="button"
          aria-pressed={current.saved.saved}
          disabled={current.loading || current.busy}
          onClick={() => void toggleSaved()}
        >
          {current.busy
            ? t(current.saved.saved ? 'Removing…' : 'Saving…')
            : t(current.saved.saved ? 'Remove saved event' : 'Save event')}
        </button>
      ) : null}
      <p className="muted">{t('Saved events are private and do not reserve a seat.')}</p>
      {current.notice ? <p className="panel success" role="status">{t(current.notice)}</p> : null}
      {current.error ? (
        <div className="panel error" role="alert">
          <p>{t(current.error)}</p>
          <button className="button button-secondary" type="button" onClick={() => setRefresh((value) => value + 1)}>{t('Retry')}</button>
        </div>
      ) : null}
    </div>
  );
}
