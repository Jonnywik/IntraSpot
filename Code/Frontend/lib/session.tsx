'use client';
import { useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, ApiError, localDemoEnabled } from './api';
import type { Actor, DemoAccount } from './types';
import {SessionContext, type Session} from './session-types';
import {RealSessionProvider} from './real-session';

const LOCAL_ACCOUNT_KEY = 'intraspot.fictional-account';
function rememberAccount(label: string | null) {
  try {
    if (label) sessionStorage.setItem(LOCAL_ACCOUNT_KEY, label);
    else sessionStorage.removeItem(LOCAL_ACCOUNT_KEY);
  } catch { /* Local sign-in remains usable when browser storage is unavailable. */ }
}
function FictionalSessionProvider({children}: {children: ReactNode}) {
  const [state, setState] = useState({actor: null as Actor | null, token: null as string | null,
    label: null as string | null, authLoading: true, error: null as ApiError | null, version: 0});
  const generation = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted || generation.current !== 0) return;
      if (!localDemoEnabled()) {
        setState(previous => ({...previous, authLoading:false}));
        return;
      }
      let savedLabel: string | null = null;
      try { savedLabel = sessionStorage.getItem(LOCAL_ACCOUNT_KEY); } catch {
        setState(previous => ({...previous, authLoading:false}));
        return;
      }
      if (!savedLabel) {
        setState(previous => ({...previous, authLoading:false}));
        return;
      }
      const attempt = ++generation.current;
      setState(previous => ({...previous, authLoading:true}));
      try {
        const accounts = await api<DemoAccount[]>('/local-demo/accounts', {signal:controller.signal});
        const account = accounts.find(item => item.label === savedLabel);
        if (!account) throw new Error('Local account unavailable');
        const actor = await api<Actor>('/me', {token:account.token, signal:controller.signal});
        if (!controller.signal.aborted && attempt === generation.current) {
          setState(previous => ({...previous, actor, token:account.token, label:account.label, authLoading:false, version:previous.version+1}));
        }
      } catch {
        if (!controller.signal.aborted && attempt === generation.current) {
          rememberAccount(null);
          setState(previous => ({...previous, actor:null, token:null, label:null, authLoading:false}));
        }
      }
    });
    return () => controller.abort();
  }, []);
  async function selectAccount(account: DemoAccount) {
    if (!window.dispatchEvent(new Event('intraspot:before-account-change', {cancelable: true}))) return;
    const attempt = ++generation.current;
    rememberAccount(null);
    setState(previous => ({...previous, actor: null, token: null, label: null, error: null, authLoading: true, version: previous.version + 1}));
    try {
      const actor = await api<Actor>('/me', {token: account.token});
      if (attempt === generation.current) {
        rememberAccount(account.label);
        setState(previous => ({...previous, actor, token: account.token, label: account.label, authLoading: false}));
      }
    } catch (error) {
      if (attempt === generation.current) setState(previous => ({...previous, authLoading: false,
        error: error instanceof ApiError ? error : new ApiError(0, 'sign_in_failed', 'Select a fictional account again.')}));
    }
  }
  function signOut() {
    if (!window.dispatchEvent(new Event('intraspot:before-account-change', {cancelable: true}))) return;
    generation.current++;
    rememberAccount(null);
    setState(previous => ({actor: null, token: null, label: null, authLoading: false, error: null, version: previous.version + 1}));
  }
  async function refreshActor() {
    if (!state.token) return;
    const attempt = generation.current;
    const actor = await api<Actor>('/me', {token: state.token});
    if (attempt === generation.current) setState(previous => ({...previous, actor}));
  }
  async function signInWithGoogle() {
    throw new ApiError(0, 'real_auth_unavailable', 'Google sign-in is available only in isolated development.');
  }
  return <SessionContext.Provider value={{...state, selectAccount, signInWithGoogle, signOut, refreshActor}}>{children}</SessionContext.Provider>;
}
export function SessionProvider({children}: {children: ReactNode}) {
  return process.env.NEXT_PUBLIC_AUTH_MODE === 'supabase'
    ? <RealSessionProvider>{children}</RealSessionProvider>
    : <FictionalSessionProvider>{children}</FictionalSessionProvider>;
}
export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('Session provider is missing.');
  return session;
}
