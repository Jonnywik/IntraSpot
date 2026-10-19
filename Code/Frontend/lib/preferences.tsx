'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { api } from './api';
import { useSession } from './session';

export type Preferences = {
  language: 'en' | 'fil';
  theme: 'light' | 'dark' | 'system';
  text_size: 'standard' | 'large' | 'extra_large';
  high_contrast: boolean;
  reduced_motion: boolean;
  decoration_paused: boolean;
  show_flash: boolean;
};

export type PreferenceKey = keyof Preferences;
export type PreferencesStatus = 'loading' | 'saving' | 'saved' | 'error';

export const DEFAULT_PREFERENCES: Preferences = {
  language: 'en',
  theme: 'light',
  text_size: 'standard',
  high_contrast: false,
  reduced_motion: false,
  decoration_paused: false,
  show_flash: true,
};

type PreferencesResponse = Preferences & {
  initialized: boolean;
  updated_at: string | null;
};

type PreferenceScope = {
  kind: 'account' | 'guest';
  identityKey: string;
  activationKey: string;
  token: string | null;
};

type Runtime = {
  identityKey: string;
  activationKey: string;
  kind: PreferenceScope['kind'];
  token: string | null;
  preferences: Preferences;
  ready: boolean;
  status: PreferencesStatus;
  error: string | null;
  dirty: Partial<Preferences>;
  guestLoaded: boolean;
  guestNeedsSave: boolean;
  epoch: number;
  savePromise: Promise<void> | null;
  resumeRequested: boolean;
};

type ViewState = {
  activationKey: string | null;
  preferences: Preferences;
  status: PreferencesStatus;
  error: string | null;
  ready: boolean;
};

type PreferencesContextValue = {
  preferences: Preferences;
  setPreference<K extends PreferenceKey>(key: K, value: Preferences[K]): void;
  resetPreferences(): void;
  status: PreferencesStatus;
  error: string | null;
  retry(): void;
  isAccount: boolean;
  ready: boolean;
  resolvedReducedMotion: boolean;
};

const PreferencesContext = createContext<PreferencesContextValue | null>(null);
const STORAGE_KEY = 'intraspot.preferences.v1';
const PREFERENCE_KEYS = Object.keys(DEFAULT_PREFERENCES) as PreferenceKey[];
const LOAD_ERROR = 'Your preferences could not be loaded. Your current choices are still available; retry to sync them.';
const SAVE_ERROR = 'Your changes could not be saved. Your choices are still available; retry to save them.';
const STORAGE_READ_ERROR = 'This browser could not read saved preferences. Your current choices are still available; retry to sync them.';
const STORAGE_SAVE_ERROR = 'This browser could not store your preferences. Your changes are still available on this page; retry to save them.';
const PENDING_ERROR = 'Some preference changes are waiting to be saved. Retry to sync them.';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function decodePreferences(value: unknown): Preferences {
  if (!isRecord(value)) throw new Error('Invalid preferences response.');
  const { language, theme, text_size, high_contrast, reduced_motion, decoration_paused } = value;
  const show_flash = Object.prototype.hasOwnProperty.call(value, 'show_flash') ? value.show_flash : true;
  if (language !== 'en' && language !== 'fil') throw new Error('Invalid preferences language.');
  if (theme !== 'light' && theme !== 'dark' && theme !== 'system') throw new Error('Invalid preferences theme.');
  if (text_size !== 'standard' && text_size !== 'large' && text_size !== 'extra_large') {
    throw new Error('Invalid preferences text size.');
  }
  if (typeof high_contrast !== 'boolean' || typeof reduced_motion !== 'boolean' || typeof decoration_paused !== 'boolean') {
    throw new Error('Invalid preferences accessibility options.');
  }
  if (typeof show_flash !== 'boolean') throw new Error('Invalid flash event preference.');
  return { language, theme, text_size, high_contrast, reduced_motion, decoration_paused, show_flash };
}

function decodeResponse(value: unknown): PreferencesResponse {
  if (!isRecord(value) || typeof value.initialized !== 'boolean' ||
    (value.updated_at !== null && typeof value.updated_at !== 'string')) {
    throw new Error('Invalid preferences response metadata.');
  }
  return { ...decodePreferences(value), initialized: value.initialized, updated_at: value.updated_at };
}

function decodeGuestRecord(value: unknown): Preferences {
  if (!isRecord(value) || value.version !== 1) throw new Error('Invalid saved preferences.');
  return decodePreferences(value.preferences);
}

function dirtyCount(runtime: Runtime): number {
  return Object.keys(runtime.dirty).length;
}

function snapshot(runtime: Runtime, activationKey: string): ViewState {
  return {
    activationKey,
    preferences: runtime.preferences,
    status: runtime.status,
    error: runtime.error,
    ready: runtime.ready,
  };
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const actorId = session.actor?.id ?? null;
  const currentScope = useMemo<PreferenceScope | null>(() => {
    if (session.authLoading) return null;
    if (actorId && session.token) {
      return {
        kind: 'account',
        identityKey: `account:${actorId}`,
        activationKey: `account:${actorId}:session:${session.version}`,
        token: session.token,
      };
    }
    return {
      kind: 'guest',
      identityKey: 'guest-device',
      activationKey: `guest-device:session:${session.version}`,
      token: null,
    };
  }, [actorId, session.authLoading, session.token, session.version]);

  const scopeRef = useRef<PreferenceScope | null>(currentScope);
  const runtimeMap = useRef(new Map<string, Runtime>());
  const activeRuntime = useRef<Runtime | null>(null);
  const [view, setView] = useState<ViewState>({
    activationKey: null,
    preferences: DEFAULT_PREFERENCES,
    status: 'loading',
    error: null,
    ready: false,
  });
  const [systemDark, setSystemDark] = useState(false);
  const [systemReducedMotion, setSystemReducedMotion] = useState(false);

  const isCurrent = useCallback((runtime: Runtime, activationKey: string) =>
    activeRuntime.current === runtime &&
    runtime.activationKey === activationKey &&
    scopeRef.current?.activationKey === activationKey,
  []);

  const publish = useCallback((runtime: Runtime, activationKey = runtime.activationKey) => {
    if (isCurrent(runtime, activationKey)) setView(snapshot(runtime, activationKey));
  }, [isCurrent]);

  const writeGuest = useCallback((runtime: Runtime, activationKey: string) => {
    if (runtime.kind !== 'guest' || !isCurrent(runtime, activationKey)) return;
    if (!runtime.guestLoaded) {
      runtime.status = 'error';
      runtime.error = STORAGE_READ_ERROR;
      runtime.guestNeedsSave = true;
      publish(runtime, activationKey);
      return;
    }
    runtime.status = 'saving';
    runtime.error = null;
    runtime.guestNeedsSave = true;
    publish(runtime, activationKey);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, preferences: runtime.preferences }));
      runtime.dirty = {};
      runtime.guestNeedsSave = false;
      runtime.status = 'saved';
      runtime.error = null;
    } catch {
      runtime.status = 'error';
      runtime.error = STORAGE_SAVE_ERROR;
      runtime.guestNeedsSave = true;
    }
    publish(runtime, activationKey);
  }, [isCurrent, publish]);

  const loadRuntime = useCallback(async (
    runtime: Runtime,
    activationKey: string,
    signal?: AbortSignal,
  ) => {
    if (!isCurrent(runtime, activationKey)) return;
    await Promise.resolve();
    if (signal?.aborted || !isCurrent(runtime, activationKey)) return;
    runtime.status = 'loading';
    runtime.error = null;
    publish(runtime, activationKey);
    try {
      if (runtime.kind === 'guest') {
        if (!runtime.guestLoaded) {
          const saved = window.localStorage.getItem(STORAGE_KEY);
          const preferences = saved === null ? DEFAULT_PREFERENCES : decodeGuestRecord(JSON.parse(saved));
          runtime.preferences = { ...preferences, ...runtime.dirty };
          runtime.guestLoaded = true;
        }
        runtime.ready = true;
        if (runtime.guestNeedsSave || dirtyCount(runtime) > 0) {
          writeGuest(runtime, activationKey);
        } else {
          runtime.status = 'saved';
          runtime.error = null;
          publish(runtime, activationKey);
        }
        return;
      }

      const response = decodeResponse(await api<unknown>('/me/preferences', {
        token: runtime.token,
        signal,
      }));
      if (signal?.aborted || !isCurrent(runtime, activationKey)) return;
      runtime.preferences = { ...decodePreferences(response), ...runtime.dirty };
      runtime.ready = true;
      if (dirtyCount(runtime) > 0) {
        runtime.status = 'error';
        runtime.error = PENDING_ERROR;
      } else {
        runtime.status = 'saved';
        runtime.error = null;
      }
      publish(runtime, activationKey);
    } catch {
      if (signal?.aborted || !isCurrent(runtime, activationKey)) return;
      runtime.ready = true;
      runtime.status = 'error';
      runtime.error = runtime.kind === 'guest' ? STORAGE_READ_ERROR : LOAD_ERROR;
      publish(runtime, activationKey);
    }
  }, [isCurrent, publish, writeGuest]);

  const startSave = useCallback(function startSaveOperation(runtime: Runtime, activationKey: string) {
    if (!isCurrent(runtime, activationKey) || !runtime.ready || dirtyCount(runtime) === 0) return;
    if (runtime.kind === 'guest') {
      writeGuest(runtime, activationKey);
      return;
    }
    if (runtime.savePromise) {
      runtime.resumeRequested = true;
      return;
    }

    runtime.status = 'saving';
    runtime.error = null;
    publish(runtime, activationKey);
    const run = async () => {
      while (isCurrent(runtime, activationKey) && dirtyCount(runtime) > 0) {
        const batch = runtime.dirty;
        runtime.dirty = {};
        const token = runtime.token;
        try {
          const response = decodeResponse(await api<unknown>('/me/preferences', {
            token,
            method: 'PATCH',
            body: batch,
          }));
          if (!isCurrent(runtime, activationKey)) {
            runtime.dirty = { ...batch, ...runtime.dirty };
            return;
          }
          runtime.preferences = { ...decodePreferences(response), ...runtime.dirty };
          if (dirtyCount(runtime) === 0) {
            runtime.status = 'saved';
            runtime.error = null;
          } else {
            runtime.status = 'saving';
            runtime.error = null;
          }
          publish(runtime, activationKey);
        } catch {
          runtime.dirty = { ...batch, ...runtime.dirty };
          if (isCurrent(runtime, activationKey)) {
            runtime.status = 'error';
            runtime.error = SAVE_ERROR;
            runtime.resumeRequested = false;
            publish(runtime, activationKey);
          }
          return;
        }
      }
    };

    const pending = run().finally(() => {
      if (runtime.savePromise !== pending) return;
      runtime.savePromise = null;
      const activeKey = runtime.activationKey;
      if (!isCurrent(runtime, activeKey) || !runtime.ready) return;
      if (runtime.resumeRequested && !runtime.error && dirtyCount(runtime) > 0) {
        runtime.resumeRequested = false;
        startSaveOperation(runtime, activeKey);
      } else if (!runtime.error && dirtyCount(runtime) > 0) {
        runtime.status = 'error';
        runtime.error = PENDING_ERROR;
        publish(runtime, activeKey);
      } else if (dirtyCount(runtime) === 0) {
        runtime.resumeRequested = false;
      }
    });
    runtime.savePromise = pending;
  }, [isCurrent, publish, writeGuest]);

  const setPreference = useCallback(<K extends PreferenceKey>(key: K, value: Preferences[K]) => {
    const scope = scopeRef.current;
    const runtime = activeRuntime.current;
    if (!scope || !runtime || runtime.activationKey !== scope.activationKey || !runtime.ready) return;
    if (runtime.preferences[key] === value) return;
    runtime.preferences = { ...runtime.preferences, [key]: value };
    runtime.dirty = { ...runtime.dirty, [key]: value };
    if (runtime.kind === 'guest') runtime.guestNeedsSave = true;
    runtime.error = null;
    runtime.status = 'saving';
    publish(runtime, scope.activationKey);
    startSave(runtime, scope.activationKey);
  }, [publish, startSave]);

  const resetPreferences = useCallback(() => {
    const scope = scopeRef.current;
    const runtime = activeRuntime.current;
    if (!scope || !runtime || runtime.activationKey !== scope.activationKey || !runtime.ready) return;
    const isDefault = PREFERENCE_KEYS.every(key => runtime.preferences[key] === DEFAULT_PREFERENCES[key]);
    if (isDefault && !runtime.error && dirtyCount(runtime) === 0) return;
    runtime.preferences = { ...DEFAULT_PREFERENCES };
    runtime.dirty = { ...DEFAULT_PREFERENCES };
    if (runtime.kind === 'guest') {
      // Explicit reset may replace a corrupt stored record that could not be read.
      runtime.guestLoaded = true;
      runtime.guestNeedsSave = true;
    }
    runtime.error = null;
    runtime.status = 'saving';
    publish(runtime, scope.activationKey);
    startSave(runtime, scope.activationKey);
  }, [publish, startSave]);

  const retry = useCallback(() => {
    const scope = scopeRef.current;
    const runtime = activeRuntime.current;
    if (!scope || !runtime || runtime.activationKey !== scope.activationKey || !runtime.ready) return;
    runtime.error = null;
    if (runtime.kind === 'account' && dirtyCount(runtime) > 0) {
      runtime.status = 'saving';
      publish(runtime, scope.activationKey);
      startSave(runtime, scope.activationKey);
      return;
    }
    if (runtime.kind === 'guest' && (runtime.guestNeedsSave || dirtyCount(runtime) > 0) && runtime.guestLoaded) {
      runtime.status = 'saving';
      publish(runtime, scope.activationKey);
      writeGuest(runtime, scope.activationKey);
      return;
    }
    void loadRuntime(runtime, scope.activationKey);
  }, [loadRuntime, publish, startSave, writeGuest]);

  useEffect(() => {
    scopeRef.current = currentScope;
  }, [currentScope]);

  useEffect(() => {
    if (!currentScope) {
      activeRuntime.current = null;
      return;
    }

    let runtime = runtimeMap.current.get(currentScope.identityKey);
    if (!runtime) {
      runtime = {
        identityKey: currentScope.identityKey,
        activationKey: currentScope.activationKey,
        kind: currentScope.kind,
        token: currentScope.token,
        preferences: DEFAULT_PREFERENCES,
        ready: false,
        status: 'loading',
        error: null,
        dirty: {},
        guestLoaded: false,
        guestNeedsSave: false,
        epoch: 0,
        savePromise: null,
        resumeRequested: false,
      };
      runtimeMap.current.set(currentScope.identityKey, runtime);
    }
    const activationKey = currentScope.activationKey;
    const epoch = ++runtime.epoch;
    runtime.activationKey = activationKey;
    runtime.kind = currentScope.kind;
    runtime.token = currentScope.token;
    runtime.ready = false;
    activeRuntime.current = runtime;

    const controller = new AbortController();
    void loadRuntime(runtime, activationKey, controller.signal);
    return () => {
      controller.abort();
      if (runtime?.epoch === epoch && activeRuntime.current === runtime) activeRuntime.current = null;
    };
  }, [currentScope, loadRuntime]);

  useEffect(() => {
    const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updateDark = () => setSystemDark(darkQuery.matches);
    const updateMotion = () => setSystemReducedMotion(motionQuery.matches);
    const initialDark = window.setTimeout(updateDark, 0);
    const initialMotion = window.setTimeout(updateMotion, 0);
    if (darkQuery.addEventListener) darkQuery.addEventListener('change', updateDark);
    else darkQuery.addListener(updateDark);
    if (motionQuery.addEventListener) motionQuery.addEventListener('change', updateMotion);
    else motionQuery.addListener(updateMotion);
    return () => {
      window.clearTimeout(initialDark);
      window.clearTimeout(initialMotion);
      if (darkQuery.removeEventListener) darkQuery.removeEventListener('change', updateDark);
      else darkQuery.removeListener(updateDark);
      if (motionQuery.removeEventListener) motionQuery.removeEventListener('change', updateMotion);
      else motionQuery.removeListener(updateMotion);
    };
  }, []);

  const viewMatchesScope = currentScope !== null && view.activationKey === currentScope.activationKey;
  const preferences = viewMatchesScope ? view.preferences : DEFAULT_PREFERENCES;
  const ready = viewMatchesScope && !session.authLoading && view.ready;
  const status = ready ? view.status : 'loading';
  const error = ready ? view.error : null;
  const resolvedTheme = preferences.theme === 'system'
    ? (systemDark ? 'dark' : 'light')
    : preferences.theme;
  const resolvedReducedMotion = preferences.reduced_motion || systemReducedMotion;

  useEffect(() => {
    const root = document.documentElement;
    root.lang = preferences.language;
    root.dataset.theme = resolvedTheme;
    root.dataset.textSize = preferences.text_size;
    root.dataset.highContrast = String(preferences.high_contrast);
    root.dataset.reducedMotion = String(resolvedReducedMotion);
  }, [preferences, resolvedReducedMotion, resolvedTheme]);

  const value = useMemo<PreferencesContextValue>(() => ({
    preferences,
    setPreference,
    resetPreferences,
    status,
    error,
    retry,
    isAccount: Boolean(currentScope?.kind === 'account'),
    ready,
    resolvedReducedMotion,
  }), [currentScope?.kind, error, preferences, ready, resetPreferences, resolvedReducedMotion, retry, setPreference, status]);

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesContextValue {
  const preferences = useContext(PreferencesContext);
  if (!preferences) throw new Error('Preferences provider is missing.');
  return preferences;
}
