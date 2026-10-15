'use client';
import { createContext, useContext, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from './api';
import type { Actor, DemoAccount } from './types';

interface Session {
  actor: Actor | null; token: string | null; label: string | null;
  authLoading: boolean; error: ApiError | null; version: number;
  selectAccount(account: DemoAccount): Promise<void>;
  signOut(): void; refreshActor(): Promise<void>;
}
const SessionContext = createContext<Session | null>(null);
export function SessionProvider({children}: {children: ReactNode}) {
  const [state, setState] = useState({actor: null as Actor | null, token: null as string | null,
    label: null as string | null, authLoading: false, error: null as ApiError | null, version: 0});
  const generation = useRef(0);
  async function selectAccount(account: DemoAccount) {
    const attempt = ++generation.current;
    setState(previous => ({...previous, actor: null, token: null, label: null, error: null, authLoading: true, version: previous.version + 1}));
    try {
      const actor = await api<Actor>('/me', {token: account.token});
      if (attempt === generation.current) setState(previous => ({...previous, actor, token: account.token, label: account.label, authLoading: false}));
    } catch (error) {
      if (attempt === generation.current) setState(previous => ({...previous, authLoading: false,
        error: error instanceof ApiError ? error : new ApiError(0, 'sign_in_failed', 'Select a fictional account again.')}));
    }
  }
  function signOut() {
    generation.current++;
    setState(previous => ({actor: null, token: null, label: null, authLoading: false, error: null, version: previous.version + 1}));
  }
  async function refreshActor() {
    if (!state.token) return;
    const attempt = generation.current;
    const actor = await api<Actor>('/me', {token: state.token});
    if (attempt === generation.current) setState(previous => ({...previous, actor}));
  }
  return <SessionContext.Provider value={{...state, selectAccount, signOut, refreshActor}}>{children}</SessionContext.Provider>;
}
export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('Session provider is missing.');
  return session;
}
