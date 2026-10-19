'use client';

import Link from 'next/link';
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from 'react';
import type { components } from '@/lib/api.generated';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { useSession } from '@/lib/session';
import type { AvailabilityWindow, DiscoveryPreferences as DiscoveryPreferencesData } from '@/lib/types';
import styles from './discovery-preferences.module.css';

type DiscoveryPreferencesResponse = components['schemas']['DiscoveryPreferencesResponse'];
type DiscoveryPreferencesPatch = components['schemas']['DiscoveryPreferencesPatch'];

type AvailabilityRow = {
  id: string;
  weekday: AvailabilityWindow['weekday'];
  startTime: string;
  endTime: string;
  endsAtMidnight: boolean;
};

type ParsedAvailability =
  | { windows: AvailabilityWindow[]; error: null }
  | { windows: null; error: string };

type RetryAction = 'load' | 'save' | 'clear' | null;
type EditorStatus = 'loading' | 'ready' | 'dirty' | 'saving' | 'error';

type EditorState = {
  scopeKey: string | null;
  loaded: boolean;
  hasSavedPreferences: boolean;
  area: string;
  rows: AvailabilityRow[];
  status: EditorStatus;
  error: string | null;
  validationError: string | null;
  retryAction: RetryAction;
};

const EMPTY_EDITOR: EditorState = {
  scopeKey: null,
  loaded: false,
  hasSavedPreferences: false,
  area: '',
  rows: [],
  status: 'loading',
  error: null,
  validationError: null,
  retryAction: null,
};

const LOAD_ERROR = 'Could not load discovery preferences.';
const SAVE_ERROR = 'Could not save discovery preferences. Your changes are still here.';
const CLEAR_ERROR = 'Could not clear discovery preferences. Your current values are still here.';

const WEEKDAYS = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
  { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' },
] as const;

function minuteToTime(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return String(hours).padStart(2, '0') + ':' + String(remainder).padStart(2, '0');
}

function timeToMinute(value: string): number | null {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(value);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

function parseAvailabilityRows(rows: AvailabilityRow[]): ParsedAvailability {
  if (rows.length > 28) return { windows: null, error: 'You can add up to 28 windows.' };

  const windows: AvailabilityWindow[] = [];
  for (const row of rows) {
    if (!Number.isInteger(row.weekday) || row.weekday < 0 || row.weekday > 6) {
      return { windows: null, error: 'Choose a weekday for each window.' };
    }
    const startMinute = timeToMinute(row.startTime);
    const endMinute = row.endsAtMidnight ? 1440 : timeToMinute(row.endTime);
    if (startMinute === null || endMinute === null) {
      return { windows: null, error: 'Enter valid times for each window.' };
    }
    if (endMinute <= startMinute) {
      return { windows: null, error: 'End time must be later than start time.' };
    }
    windows.push({
      weekday: row.weekday,
      start_minute: startMinute,
      end_minute: endMinute,
    });
  }

  return { windows, error: null };
}

export function DiscoveryPreferences() {
  const t = useT();
  const { actor, token, authLoading, version } = useSession();
  const signedIn = Boolean(actor && token);
  const scopeKey = signedIn && token ? String(version) + ':' + token : null;

  const [editor, setEditor] = useState<EditorState>(EMPTY_EDITOR);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const rowSequence = useRef(0);
  const writeController = useRef<AbortController | null>(null);
  const headingId = useId();
  const areaId = useId();
  const areaHelpId = useId();
  const validationId = useId();

  const createRow = useCallback((value?: AvailabilityWindow): AvailabilityRow => {
    rowSequence.current += 1;
    const endsAtMidnight = value?.end_minute === 1440;
    return {
      id: 'availability-' + rowSequence.current,
      weekday: value?.weekday ?? 0,
      startTime: minuteToTime(value?.start_minute ?? 9 * 60),
      endTime: endsAtMidnight ? '23:59' : minuteToTime(value?.end_minute ?? 17 * 60),
      endsAtMidnight,
    };
  }, []);

  useEffect(() => {
    if (authLoading || !signedIn || !token || !scopeKey) return;

    const requestScope = scopeKey;
    const controller = new AbortController();
    let active = true;

    void api<DiscoveryPreferencesResponse>('/me/discovery-preferences', {
      token,
      signal: controller.signal,
    }).then(response => {
      if (controller.signal.aborted || !active) return;
      const preferences: DiscoveryPreferencesData = response;
      setEditor({
        scopeKey: requestScope,
        loaded: true,
        hasSavedPreferences: preferences.updated_at !== null,
        area: preferences.coarse_area ?? '',
        rows: preferences.availability.map(createRow),
        status: 'ready',
        error: null,
        validationError: null,
        retryAction: null,
      });
    }).catch(() => {
      if (controller.signal.aborted || !active) return;
      setEditor({
        scopeKey: requestScope,
        loaded: false,
        hasSavedPreferences: false,
        area: '',
        rows: [],
        status: 'error',
        error: LOAD_ERROR,
        validationError: null,
        retryAction: 'load',
      });
    });

    return () => {
      active = false;
      controller.abort();
      writeController.current?.abort();
      writeController.current = null;
    };
  }, [authLoading, createRow, loadAttempt, scopeKey, signedIn, token]);

  const currentEditor = editor.scopeKey === scopeKey ? editor : EMPTY_EDITOR;
  const loaded = currentEditor.loaded;
  const saving = currentEditor.status === 'saving';
  const editable = loaded && !saving;

  function changeArea(value: string) {
    if (!scopeKey) return;
    setEditor(current => current.scopeKey === scopeKey && current.loaded ? {
      ...current,
      area: value,
      status: 'dirty',
      error: null,
      validationError: null,
      retryAction: null,
    } : current);
  }

  function changeWindow(id: string, changes: Partial<Omit<AvailabilityRow, 'id'>>) {
    if (!scopeKey) return;
    setEditor(current => current.scopeKey === scopeKey && current.loaded ? {
      ...current,
      rows: current.rows.map(row => row.id === id ? { ...row, ...changes } : row),
      status: 'dirty',
      error: null,
      validationError: null,
      retryAction: null,
    } : current);
  }

  function addWindow() {
    if (!scopeKey || !editable || currentEditor.rows.length >= 28) return;
    const row = createRow();
    setEditor(current => current.scopeKey === scopeKey && current.loaded && current.rows.length < 28 ? {
      ...current,
      rows: [...current.rows, row],
      status: 'dirty',
      error: null,
      validationError: null,
      retryAction: null,
    } : current);
  }

  function removeWindow(id: string) {
    if (!scopeKey || !editable) return;
    setEditor(current => current.scopeKey === scopeKey && current.loaded ? {
      ...current,
      rows: current.rows.filter(row => row.id !== id),
      status: 'dirty',
      error: null,
      validationError: null,
      retryAction: null,
    } : current);
  }

  async function persist(action: 'save' | 'clear', body: DiscoveryPreferencesPatch) {
    if (!token || !scopeKey) return;
    const requestScope = scopeKey;
    const controller = new AbortController();
    writeController.current?.abort();
    writeController.current = controller;
    setEditor(current => current.scopeKey === requestScope ? {
      ...current,
      status: 'saving',
      error: null,
      validationError: null,
      retryAction: null,
    } : current);

    try {
      const response = await api<DiscoveryPreferencesResponse>('/me/discovery-preferences', {
        token,
        method: 'PATCH',
        body,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const preferences: DiscoveryPreferencesData = response;
      const rows = preferences.availability.map(createRow);
      setEditor(current => current.scopeKey === requestScope ? {
        scopeKey: requestScope,
        loaded: true,
        hasSavedPreferences: preferences.updated_at !== null,
        area: preferences.coarse_area ?? '',
        rows,
        status: 'ready',
        error: null,
        validationError: null,
        retryAction: null,
      } : current);
    } catch {
      if (controller.signal.aborted) return;
      setEditor(current => current.scopeKey === requestScope ? {
        ...current,
        loaded: true,
        status: 'error',
        error: action === 'save' ? SAVE_ERROR : CLEAR_ERROR,
        retryAction: action,
      } : current);
    } finally {
      if (writeController.current === controller) writeController.current = null;
    }
  }

  async function save() {
    if (!token || !scopeKey || !currentEditor.loaded || saving) return;
    const parsed = parseAvailabilityRows(currentEditor.rows);
    if (parsed.windows === null) {
      setEditor(current => current.scopeKey === scopeKey ? {
        ...current,
        status: 'dirty',
        error: null,
        validationError: parsed.error,
        retryAction: null,
      } : current);
      return;
    }
    const body: DiscoveryPreferencesPatch = {
      coarse_area: currentEditor.area.trim() || null,
      availability: parsed.windows,
    };
    await persist('save', body);
  }

  async function clear() {
    if (!token || !scopeKey || !currentEditor.loaded || saving) return;
    await persist('clear', { coarse_area: null, availability: [] });
  }

  function retry() {
    if (editor.scopeKey !== scopeKey) return;
    if (editor.retryAction === 'load') {
      setEditor(current => current.scopeKey === scopeKey ? {
        ...current,
        status: 'loading',
        error: null,
        retryAction: null,
      } : current);
      setLoadAttempt(current => current + 1);
    }
    else if (editor.retryAction === 'save') void save();
    else if (editor.retryAction === 'clear') void clear();
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void save();
  }

  const heading = <h2 className={styles.heading} id={headingId}>{t('Discovery preferences')}</h2>;

  if (authLoading) {
    return (
      <section className={styles.panel + ' panel stack'} aria-labelledby={headingId} aria-busy="true">
        {heading}
        <p className={styles.feedback} role="status">{t('Loading discovery preferences…')}</p>
      </section>
    );
  }

  if (!actor || !token || !scopeKey) {
    return (
      <section className={styles.panel + ' panel stack'} aria-labelledby={headingId}>
        {heading}
        <p className={styles.description}>{t('Sign in to save private discovery preferences.')}</p>
      </section>
    );
  }

  const busy = currentEditor.status === 'loading' || saving;
  const canSave = loaded && !saving && (
    currentEditor.status === 'dirty' ||
    (currentEditor.status === 'error' && currentEditor.retryAction !== 'load')
  );
  const canClear = loaded && !saving && (
    currentEditor.status === 'dirty' ||
    Boolean(currentEditor.area.trim()) ||
    currentEditor.rows.length > 0
  );

  return (
    <section className={styles.panel + ' panel stack'} aria-labelledby={headingId} aria-busy={busy}>
      {heading}
      <p className={styles.description}>{t('These preferences are private to your account.')}</p>

      {currentEditor.status === 'loading' ? (
        <p className={styles.feedback} role="status">{t('Loading discovery preferences…')}</p>
      ) : null}
      {currentEditor.status === 'saving' ? (
        <p className={styles.feedback} role="status" aria-live="polite">{t('Saving discovery preferences…')}</p>
      ) : null}
      {currentEditor.status === 'ready' ? (
        <p className={styles.feedback} role="status" aria-live="polite">
          {currentEditor.hasSavedPreferences
            ? t('Your discovery preferences are saved.')
            : t('No discovery preferences saved yet.')}
        </p>
      ) : null}
      {currentEditor.status === 'dirty' ? (
        <p className={styles.feedback} role="status" aria-live="polite">{t('You have unsaved changes.')}</p>
      ) : null}
      {currentEditor.error ? (
        <div className={styles.errorActions}>
          <p className={'error ' + styles.feedback} role="alert">{t(currentEditor.error)}</p>
          {currentEditor.retryAction ? (
            <button className="button button-secondary" type="button" onClick={retry}>
              {t('Retry')}
            </button>
          ) : null}
        </div>
      ) : null}

      {loaded ? (
        <form className={styles.form} noValidate onSubmit={submit}>
          <section className={styles.section} aria-labelledby={headingId + '-area'}>
            <h3 className={styles.sectionHeading} id={headingId + '-area'}>{t('Area')}</h3>
            <label className={styles.field} htmlFor={areaId}>
              <span>{t('Broad named area (not a street address)')}</span>
              <input
                id={areaId}
                type="text"
                maxLength={80}
                autoComplete="off"
                value={currentEditor.area}
                aria-describedby={areaHelpId}
                disabled={!editable}
                onChange={event => changeArea(event.currentTarget.value)}
              />
            </label>
            <p className={styles.help} id={areaHelpId}>
              {t('For example, Ermita or Manila. Leave blank if you do not want area matches.')}
            </p>
          </section>

          <section className={styles.section} aria-labelledby={headingId + '-availability'}>
            <h3 className={styles.sectionHeading} id={headingId + '-availability'}>
              {t('Weekly availability (Manila time)')}
            </h3>
            <p className={styles.help}>{t('Add times when you are free to attend events.')}</p>
            <p className={styles.help}>
              {t('For overnight availability, add one row ending at midnight and another for the next day.')}
            </p>
            <p className={styles.help}>{t('You can add up to 28 windows.')}</p>

            {currentEditor.validationError ? (
              <p className={'error ' + styles.feedback} id={validationId} role="alert">
                {t(currentEditor.validationError)}
              </p>
            ) : null}

            <div className={styles.windows}>
              {currentEditor.rows.map((row, index) => {
                const rowId = headingId + '-' + row.id;
                return (
                  <fieldset className={styles.window} key={row.id} disabled={!editable}>
                    <legend>{t('Availability window {number}', { number: index + 1 })}</legend>
                    <div className={styles.fields}>
                      <label className={styles.field} htmlFor={rowId + '-day'}>
                        <span>{t('Day')}</span>
                        <select
                          id={rowId + '-day'}
                          value={row.weekday}
                          onChange={event => changeWindow(row.id, {
                            weekday: Number(event.currentTarget.value) as AvailabilityWindow['weekday'],
                          })}
                        >
                          {WEEKDAYS.map(day => (
                            <option value={day.value} key={day.value}>{t(day.label)}</option>
                          ))}
                        </select>
                      </label>
                      <label className={styles.field} htmlFor={rowId + '-start'}>
                        <span>{t('Start time')}</span>
                        <input
                          id={rowId + '-start'}
                          type="time"
                          step={60}
                          value={row.startTime}
                          aria-invalid={Boolean(currentEditor.validationError)}
                          aria-describedby={currentEditor.validationError ? validationId : undefined}
                          onChange={event => changeWindow(row.id, { startTime: event.currentTarget.value })}
                        />
                      </label>
                      <label className={styles.field} htmlFor={rowId + '-end'}>
                        <span>{t('End time')}</span>
                        <input
                          id={rowId + '-end'}
                          type="time"
                          step={60}
                          value={row.endTime}
                          disabled={!editable || row.endsAtMidnight}
                          aria-invalid={Boolean(currentEditor.validationError)}
                          aria-describedby={currentEditor.validationError ? validationId : undefined}
                          onChange={event => changeWindow(row.id, { endTime: event.currentTarget.value })}
                        />
                      </label>
                    </div>
                    <label className={styles.midnight} htmlFor={rowId + '-midnight'}>
                      <input
                        id={rowId + '-midnight'}
                        type="checkbox"
                        checked={row.endsAtMidnight}
                        onChange={event => changeWindow(row.id, { endsAtMidnight: event.currentTarget.checked })}
                      />
                      <span>{t('Ends at midnight (24:00)')}</span>
                    </label>
                    <button
                      className="button button-secondary"
                      type="button"
                      onClick={() => removeWindow(row.id)}
                    >
                      {t('Remove availability window {number}', { number: index + 1 })}
                    </button>
                  </fieldset>
                );
              })}
            </div>

            <button
              className="button button-secondary"
              type="button"
              onClick={addWindow}
              disabled={!editable || currentEditor.rows.length >= 28}
            >
              {t('Add availability window')}
            </button>
          </section>

          <p className={styles.help}>
            {t('Your profile interests power interest matches.')}
            {' '}
            <Link href="/profile">{t('Manage profile interests')}</Link>
          </p>

          <div className={styles.actions}>
            <button className="button" type="submit" disabled={!canSave}>
              {t('Save discovery preferences')}
            </button>
            <button className="button button-secondary" type="button" onClick={clear} disabled={!canClear}>
              {t('Clear discovery preferences')}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
