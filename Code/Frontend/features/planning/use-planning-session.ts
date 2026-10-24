'use client';

import {useCallback, useEffect, useRef} from 'react';
import {useSession} from '@/lib/session';

export function usePlanningSession() {
  const {actor, token, version, authLoading} = useSession();
  const identity = String(version) + '\u0000' + (actor?.id ?? '') + '\u0000' + (token ?? '');
  const requests = useRef(new Set<AbortController>());

  useEffect(() => () => {
    for (const controller of requests.current) controller.abort();
    requests.current.clear();
  }, [identity]);

  const createRequest = useCallback(() => {
    const controller = new AbortController();
    requests.current.add(controller);
    return {
      controller,
      isCurrent: () => !controller.signal.aborted,
      release: () => requests.current.delete(controller),
    };
  }, []);

  return {actor, token, authLoading, identity, createRequest};
}
