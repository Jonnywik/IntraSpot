'use client';
import {createContext} from 'react';
import type {ApiError} from './api';
import type {Actor, DemoAccount} from './types';

export interface Session {
  actor: Actor | null; token: string | null; label: string | null;
  authLoading: boolean; error: ApiError | null; version: number;
  selectAccount(account: DemoAccount): Promise<void>;
  signInWithGoogle(): Promise<void>;
  signOut(): void;
  refreshActor(): Promise<void>;
}

export const SessionContext = createContext<Session | null>(null);
