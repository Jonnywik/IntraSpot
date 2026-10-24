'use client';

import {useCallback, useEffect, useRef, useState, useSyncExternalStore} from 'react';
import {ApiError} from '@/lib/api';
import {usePreferences} from '@/lib/preferences';
import {safetyMessages} from './messages';
import {DESKTOP_SAFETY_QUERY} from './safety-helpers.mjs';

type ReadStatus = 'idle' | 'loading' | 'ready' | 'error' | 'forbidden';
type Loader<T> = (signal: AbortSignal) => Promise<T>;

function subscribeDesktop(onChange: () => void) {
  if (typeof window === 'undefined') return () => {};
  const query = window.matchMedia(DESKTOP_SAFETY_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

function getDesktopSnapshot() {
  return typeof window !== 'undefined' && window.matchMedia(DESKTOP_SAFETY_QUERY).matches;
}

function apiStatus(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null;
}

export function useDesktopManagement() {
  return useSyncExternalStore(subscribeDesktop, getDesktopSnapshot, () => false);
}

export function useSafetyTranslate() {
  const {preferences} = usePreferences();
  return useCallback((english: string, values?: Record<string, string | number>) => {
    const template = preferences.language === 'fil' ? safetyMessages[english] ?? english : english;
    return template.replace(/\{([A-Za-z0-9_]+)\}/g, (match, name: string) =>
      values && Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match,
    );
  }, [preferences.language]);
}

export function useSafetyResource<T>(enabled: boolean, contextKey: string, loader: Loader<T>) {
  const refreshRef = useRef<(() => void) | null>(null);
  const [snapshot, setSnapshot] = useState<{
    contextKey: string;
    data: T | null;
    status: Exclude<ReadStatus, 'idle' | 'loading'>;
    revision: number;
  } | null>(null);
  const [requested, setRequested] = useState<{contextKey: string; revision: number} | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let fetching = false;
    let refreshQueued = false;
    let requiredRevision = 0;
    let controller: AbortController | null = null;

    const load = async () => {
      if (disposed) return;
      if (fetching) {
        refreshQueued = true;
        return;
      }
      fetching = true;
      try {
        do {
          refreshQueued = false;
          const requestRevision = requiredRevision;
          const requestController = new AbortController();
          controller = requestController;
          try {
            const data = await loader(requestController.signal);
            if (disposed || requestController.signal.aborted) return;
            if (requestRevision !== requiredRevision) {
              refreshQueued = true;
              continue;
            }
            setSnapshot({contextKey, data, status: 'ready', revision: requestRevision});
          } catch (error) {
            if (disposed || requestController.signal.aborted) return;
            if (requestRevision !== requiredRevision) {
              refreshQueued = true;
              continue;
            }
            setSnapshot(current => ({
              contextKey,
              data: current?.contextKey === contextKey ? current.data : null,
              status: [401, 403].includes(apiStatus(error) ?? -1) ? 'forbidden' : 'error',
              revision: requestRevision,
            }));
            if (!refreshQueued) return;
          } finally {
            if (controller === requestController) controller = null;
          }
        } while (refreshQueued && !disposed);
      } finally {
        fetching = false;
      }
    };

    const refresh = () => {
      if (disposed) return;
      requiredRevision += 1;
      setRequested({contextKey, revision: requiredRevision});
      if (fetching) {
        refreshQueued = true;
        return;
      }
      void load();
    };

    refreshRef.current = refresh;
    void load();
    return () => {
      disposed = true;
      controller?.abort();
      if (refreshRef.current === refresh) refreshRef.current = null;
    };
  }, [enabled, contextKey, loader]);

  const refresh = useCallback(() => {
    refreshRef.current?.();
  }, []);
  const currentSnapshot = snapshot?.contextKey === contextKey ? snapshot : null;
  const requestedRevision = requested?.contextKey === contextKey ? requested.revision : 0;
  const current = currentSnapshot?.revision === requestedRevision;
  const status: ReadStatus = !enabled ? 'idle' : current ? currentSnapshot.status : 'loading';
  const data = enabled ? currentSnapshot?.data ?? null : null;
  const loading = status === 'loading';
  return {
    data,
    status,
    loading,
    fresh: status === 'ready' && data !== null && current && !loading,
    refresh,
  };
}
