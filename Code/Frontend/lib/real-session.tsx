'use client';

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import type { AuthChangeEvent, Session as AuthSession } from '@supabase/auth-js';
import { ApiError, api } from './api';
import { SessionContext, type Session } from './session-types';
import type { Actor } from './types';
import { createRealSessionGuard } from './real-session-guard';
import {
  clearRealAuthMemory,
  clearRealAuthStorage,
  clearRealAuthVerifier,
  getRealAuthClient,
  getRealAuthConfig,
} from './supabase-auth';

type RealAuthClient = ReturnType<typeof getRealAuthClient>;
const useClientLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect;

function authError(status: number, message: string) {
  return new ApiError(status, 'real_auth_verification_failed', message);
}

function beforeAccountChangeAccepted(): boolean {
  return typeof window !== 'undefined' &&
    window.dispatchEvent(new Event('intraspot:before-account-change', { cancelable: true }));
}

export function RealSessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState({
    actor: null as Actor | null,
    token: null as string | null,
    label: null as string | null,
    authLoading: true,
    error: null as ApiError | null,
    version: 0,
  });
  const [authGuard] = useState(createRealSessionGuard);
  const verifiedActor = useRef<Actor | null>(null);
  const authClient = useRef<RealAuthClient | null>(null);
  const mounted = useRef(false);

  async function verifyActor(
    client: RealAuthClient,
    userId: string,
    accessToken: string,
    attempt: number,
  ) {
    try {
      const actor = await api<Actor>('/me', { token: accessToken });
      if (
        !mounted.current ||
        !authGuard.isCurrent({ generation: attempt, userId, accessToken })
      ) {
        return;
      }
      if (actor.id !== userId) throw authError(401, 'The signed-in account could not be verified. Sign in again.');
      verifiedActor.current = actor;
      setState(previous => ({
        ...previous,
        actor,
        token: accessToken,
        label: null,
        authLoading: false,
        error: null,
      }));
    } catch (error) {
      if (
        !mounted.current ||
        !authGuard.isCurrent({ generation: attempt, userId, accessToken })
      ) {
        return;
      }

      const status = error instanceof ApiError ? error.status : 0;
      const message = status === 401
        ? 'The signed-in account could not be verified. Sign in again.'
        : 'The local IntraSpot API could not verify this account. Check that it is running and retry.';
      const safeError = authError(status, message);

      if (status === 401) {
        const { hadAccount } = authGuard.beginLogout();
        verifiedActor.current = null;
        clearRealAuthStorage();
        setState(previous => ({
          ...previous,
          actor: null,
          token: null,
          label: null,
          authLoading: false,
          error: safeError,
          version: previous.version + (hadAccount ? 1 : 0),
        }));
        void client.signOut({ scope: 'local' }).catch(() => undefined);
        return;
      }

      verifiedActor.current = null;
      setState(previous => ({
        ...previous,
        actor: null,
        token: accessToken,
        label: null,
        authLoading: false,
        error: safeError,
      }));
    }
  }

  useClientLayoutEffect(() => {
    mounted.current = true;
    let active = true;
    let unsubscribe: (() => void) | null = null;

    if (!getRealAuthConfig()) {
      queueMicrotask(() => {
        if (active) {
          setState(previous => ({
            ...previous,
            authLoading: false,
            error: authError(0, 'Google sign-in is not configured for isolated development.'),
          }));
        }
      });
      return () => {
        active = false;
        mounted.current = false;
        authGuard.invalidate();
      };
    }

    try {
      const client = getRealAuthClient();
      authClient.current = client;
      const { data } = client.onAuthStateChange((event: AuthChangeEvent, session: AuthSession | null) => {
        if (!active) return;
        const decision = authGuard.receive(event, session);
        if (!decision.accepted) {
          clearRealAuthMemory();
          void client.stopAutoRefresh().catch(() => undefined);
          return;
        }
        const attempt = decision.generation;

        if (!decision.accessToken || !decision.userId) {
          const hadAccount = decision.hadAccount;
          verifiedActor.current = null;
          if (event === 'SIGNED_OUT') clearRealAuthMemory();
          setState(previous => ({
            ...previous,
            actor: null,
            token: null,
            label: null,
            authLoading: false,
            error: event === 'INITIAL_SESSION' ? null : previous.error,
            version: previous.version + (hadAccount ? 1 : 0),
          }));
          return;
        }

        const userId = decision.userId;
        const token = decision.accessToken;
        const changedAccount = decision.changedAccount;
        if (changedAccount) verifiedActor.current = null;
        const shouldVerify = event !== 'TOKEN_REFRESHED' || verifiedActor.current?.id !== userId;

        setState(previous => ({
          ...previous,
          actor: changedAccount ? null : previous.actor,
          token,
          label: null,
          authLoading: shouldVerify,
          error: shouldVerify ? null : previous.error,
          version: previous.version + (changedAccount ? 1 : 0),
        }));

        if (shouldVerify) {
          queueMicrotask(() => {
            if (active) void verifyActor(client, userId, token, attempt);
          });
        }
      });
      unsubscribe = () => data.subscription.unsubscribe();
    } catch {
      queueMicrotask(() => {
        if (active) {
          setState(previous => ({
            ...previous,
            authLoading: false,
            error: authError(0, 'Google sign-in is not configured for isolated development.'),
          }));
        }
      });
    }

    return () => {
      active = false;
      mounted.current = false;
      authGuard.invalidate();
      unsubscribe?.();
    };
  }, []);

  async function selectAccount(): Promise<void> {
    throw new ApiError(0, 'fixture_auth_disabled', 'Fictional account selection is unavailable in isolated development mode.');
  }

  async function signInWithGoogle(): Promise<void> {
    const config = getRealAuthConfig();
    if (!config) {
      const error = authError(0, 'Google sign-in is not configured for isolated development.');
      setState(previous => ({ ...previous, error, authLoading: false }));
      throw error;
    }
    if (!beforeAccountChangeAccepted()) return;

    try {
      const client = authClient.current ?? getRealAuthClient();
      authClient.current = client;
      authGuard.invalidate();
      setState(previous => ({ ...previous, error: null }));
      clearRealAuthVerifier();
      const { error } = await client.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: config.callbackUrl,
          scopes: 'openid email profile',
        },
      });
      if (error) throw new Error('OAuth start failed.');
    } catch {
      clearRealAuthVerifier();
      const error = authError(0, 'Google sign-in could not be started. Retry.');
      setState(previous => ({ ...previous, authLoading: false, error }));
      throw error;
    }
  }

  function signOut(): void {
    if (!beforeAccountChangeAccepted()) return;
    const client = authClient.current;
    const { hadAccount } = authGuard.beginLogout();
    verifiedActor.current = null;
    clearRealAuthVerifier();
    clearRealAuthMemory();
    setState(previous => ({
      ...previous,
      actor: null,
      token: null,
      label: null,
      authLoading: false,
      error: null,
      version: previous.version + (hadAccount ? 1 : 0),
    }));
    if (client) {
      void client.stopAutoRefresh().catch(() => undefined);
      void client.signOut({ scope: 'local' })
        .catch(() => undefined)
        .finally(clearRealAuthMemory);
    }
  }

  async function refreshActor(): Promise<void> {
    const client = authClient.current;
    const ticket = authGuard.captureVerification();
    if (!client || !ticket) return;
    setState(previous => ({ ...previous, authLoading: true, error: null }));
    await verifyActor(client, ticket.userId, ticket.accessToken, ticket.generation);
  }

  const value: Session = {
    ...state,
    selectAccount,
    signInWithGoogle,
    signOut,
    refreshActor,
  };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
