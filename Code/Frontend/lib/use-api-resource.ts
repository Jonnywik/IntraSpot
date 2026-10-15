'use client';
import { useEffect, useState } from 'react';
import { api, ApiError } from './api';

export function useApiResource<T>(path: string | null, token?: string | null, pollInterval = 0) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{key: string; data: T | null; loading: boolean; error: ApiError | null}>({key: '', data: null, loading: false, error: null});
  const key = `${path}\u0000${token || ''}\u0000${revision}`;
  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    let fetching = false;
    function fetchCurrent() {
      if (fetching || controller.signal.aborted) return;
      fetching = true;
      api<T>(path!, {token, signal: controller.signal}).then(data => {
        if (!controller.signal.aborted) setState({key, data, loading: false, error: null});
      }).catch(error => {
        if (!controller.signal.aborted) setState({key, data: null, loading: false, error: error instanceof ApiError ? error : new ApiError(0, 'request_failed', 'Please retry.')});
      }).finally(() => { fetching = false; });
    }
    fetchCurrent();
    const timer = pollInterval > 0 ? window.setInterval(() => {
      if (document.visibilityState === 'visible') fetchCurrent();
    }, pollInterval) : null;
    return () => { controller.abort(); if (timer !== null) window.clearInterval(timer); };
  }, [path, token, key, pollInterval]);
  const current = state.key === key;
  return {data: current ? state.data : null, error: current ? state.error : null,
    loading: path !== null && (!current || state.loading), reload: () => setRevision(value => value + 1)};
}
