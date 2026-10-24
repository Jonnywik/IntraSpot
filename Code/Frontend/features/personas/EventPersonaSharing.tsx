'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import type { EventPersonaVisibility } from './types';
import styles from './personas.module.css';

type EventSharingProps = {
  eventId: string;
  token: string;
  actorId: string;
};

export function EventPersonaSharing(props: EventSharingProps) {
  return <EventPersonaSharingSession key={`${props.eventId}:${props.actorId}:${props.token}`} {...props} />;
}

function EventPersonaSharingSession({ eventId, token, actorId }: EventSharingProps) {
  const t = useT();
  const { preferences } = usePreferences();
  const [visibility, setVisibility] = useState<EventPersonaVisibility | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [revision, setRevision] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const loadRequest = useRef<AbortController | null>(null);
  const saveRequest = useRef<AbortController | null>(null);
  const id = useId();
  const contextKey = `${eventId}:${actorId}:${token}`;

  useEffect(() => {
    const load = (clearFirst: boolean) => {
      if (saveRequest.current) return;
      const controller = new AbortController();
      loadRequest.current?.abort();
      loadRequest.current = controller;
      if (clearFirst) {
        setVisibility(null);
        setLoading(true);
      }
      setLoadError(false);
      void api<EventPersonaVisibility>(`/events/${encodeURIComponent(eventId)}/persona-visibility`, {
        token,
        signal: controller.signal,
      }).then(result => {
        if (!controller.signal.aborted) setVisibility(result);
      }).catch(() => {
        if (!controller.signal.aborted) setLoadError(true);
      }).finally(() => {
        if (!controller.signal.aborted) setLoading(false);
        if (loadRequest.current === controller) loadRequest.current = null;
      });
    };
    const initialLoad = window.setTimeout(() => load(false), 0);
    const refresh = () => {
      setNow(Date.now());
      setSaveSuccess(false);
      load(false);
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.clearTimeout(initialLoad);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      loadRequest.current?.abort();
      saveRequest.current?.abort();
    };
  }, [contextKey, eventId, revision, token]);

  useEffect(() => () => {
    loadRequest.current?.abort();
    saveRequest.current?.abort();
  }, []);

  useEffect(() => {
    const expiresAt = visibility?.visible && visibility.expires_at ? Date.parse(visibility.expires_at) : NaN;
    if (!Number.isFinite(expiresAt) || expiresAt <= now) return;
    const timer = window.setTimeout(() => {
      setNow(Date.now());
      setRevision(value => value + 1);
    }, Math.max(0, expiresAt - Date.now()) + 1);
    return () => window.clearTimeout(timer);
  }, [now, visibility]);

  async function updateVisibility(visible: boolean) {
    if (!visibility || saving) return;
    const controller = new AbortController();
    loadRequest.current?.abort();
    saveRequest.current?.abort();
    saveRequest.current = controller;
    setSaving(true);
    setSaveError(false);
    setSaveSuccess(false);
    try {
      const updated = await api<EventPersonaVisibility>(`/events/${encodeURIComponent(eventId)}/persona-visibility`, {
        token,
        method: 'PUT',
        body: { visible },
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setVisibility(updated);
        setSaveSuccess(true);
      }
    } catch {
      if (!controller.signal.aborted) setSaveError(true);
    } finally {
      if (!controller.signal.aborted) setSaving(false);
      if (saveRequest.current === controller) saveRequest.current = null;
    }
  }

  const expiresAt = visibility?.expires_at ? Date.parse(visibility.expires_at) : NaN;
  const expired = visibility !== null && (!Number.isFinite(expiresAt) || now >= expiresAt);
  const effectiveVisible = Boolean(visibility?.visible && !expired);
  const expiry = expired
    ? t('Event sharing has expired.')
    : visibility?.expires_at && Number.isFinite(expiresAt)
      ? t('Event sharing expires {date}.', { date: formatDate(visibility.expires_at, preferences.language) })
      : null;

  return (
    <section className={`panel ${styles.section}`} aria-labelledby={`${id}-heading`}>
      <h2 id={`${id}-heading`}>{t('Event-only text sharing')}</h2>
      <p id={`${id}-help`}>{t('This choice ends when the event ends. It is separate from broad profile visibility and approval reviewer consent.')}</p>
      {loading ? <p role="status">{t('Checking event sharing…')}</p> : null}
      {loadError ? (
        <div role="alert">
          <p>{t('We could not load event sharing.')}</p>
          <button className="button button-secondary" type="button" onClick={() => setRevision(value => value + 1)}>
            {t('Retry event sharing')}
          </button>
        </div>
      ) : null}
      {visibility ? (
        <label className={styles.actions} htmlFor={`${id}-visible`}>
          <input
            id={`${id}-visible`}
            type="checkbox"
            checked={effectiveVisible}
            disabled={saving || loading || loadError || expired}
            aria-describedby={`${id}-help`}
            onChange={event => void updateVisibility(event.target.checked)}
          />
          <span>{t('Share my text persona with confirmed attendees of this event')}</span>
        </label>
      ) : null}
      {expiry ? <p className="muted">{expiry}</p> : null}
      {saving ? <p role="status">{t('Saving event sharing…')}</p> : null}
      {saveError ? <p className={styles.error} role="alert">{t('Event sharing could not be saved. Please retry.')}</p> : null}
      {saveSuccess ? <p className={styles.status} role="status">{t('Event sharing saved.')}</p> : null}
    </section>
  );
}
