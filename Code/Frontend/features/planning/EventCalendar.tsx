'use client';

import {useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode} from 'react';
import {formatDate} from '@/lib/date';
import {usePreferences} from '@/lib/preferences';
import {useT} from '@/lib/i18n';
import type {SavedEventOut} from '@/lib/types';
import {eventsForManilaDay, getManilaDateKey, isValidDateInterval, manilaMonthDays, shiftCalendarMonth} from './calendar';
import styles from './planning.module.css';

type RegistrationCalendarRow = {
  id: string;
  starts_at: string | null;
  ends_at: string | null;
  status: string;
};

type RegistrationCalendarProps<T extends RegistrationCalendarRow> = {
  mode: 'registrations';
  registrations: readonly T[];
  renderRegistration: (registration: T) => ReactNode;
  emptyMessage: string;
};

type SavedCalendarProps = {
  mode: 'saved';
  savedEvents: readonly SavedEventOut[];
  renderSavedEvent: (savedEvent: SavedEventOut) => ReactNode;
  emptyMessage: string;
};

type Props<T extends RegistrationCalendarRow> = RegistrationCalendarProps<T> | SavedCalendarProps;

type CalendarEntry = {
  key: string;
  starts_at: string | null;
  ends_at: string | null;
  status: string;
  content: ReactNode;
};

const initialManilaDay = getManilaDateKey(new Date()) ?? '2000-01-01';

function statusStyle(status: string): string {
  if (status === 'confirmed') return styles.confirmed;
  if (status === 'waitlisted') return styles.waitlisted;
  if (status === 'pending') return styles.pending;
  if (status === 'reconfirmation_required') return styles.reconfirmation;
  if (status === 'cancelled') return styles.cancelled;
  if (status === 'rejected') return styles.rejected;
  return styles.saved;
}

function dayAfter(day: string, amount: number): string {
  const [year, month, date] = day.split('-').map(Number);
  const next = new Date(Date.UTC(year, month - 1, date + amount));
  return String(next.getUTCFullYear()).padStart(4, '0') + '-' +
    String(next.getUTCMonth() + 1).padStart(2, '0') + '-' + String(next.getUTCDate()).padStart(2, '0');
}

export function EventCalendar<T extends RegistrationCalendarRow>(props: Props<T>) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  const today = initialManilaDay;
  const [selectedDay, setSelectedDay] = useState(today);
  const [focusDay, setFocusDay] = useState(today);
  const dayButtons = useRef(new Map<string, HTMLButtonElement>());
  const focusAfterUpdate = useRef(false);
  const [displayMonth, setDisplayMonth] = useState(() => {
    const [year, month] = today.split('-').map(Number);
    return {year, month};
  });

  const entries: CalendarEntry[] = props.mode === 'registrations'
    ? props.registrations.map((registration) => ({
      key: registration.id,
      starts_at: registration.starts_at,
      ends_at: registration.ends_at,
      status: registration.status,
      content: props.renderRegistration(registration),
    }))
    : props.savedEvents.map((savedEvent) => ({
      key: savedEvent.event_id,
      starts_at: savedEvent.event?.starts_at ?? null,
      ends_at: savedEvent.event?.ends_at ?? null,
      status: 'saved',
      content: props.renderSavedEvent(savedEvent),
    }));

  const monthDays = useMemo(() => manilaMonthDays(displayMonth.year, displayMonth.month), [displayMonth]);
  const scheduled = entries.filter((entry) => isValidDateInterval(entry.starts_at, entry.ends_at));
  const undated = entries.filter((entry) => !isValidDateInterval(entry.starts_at, entry.ends_at));
  const selectedEntries = eventsForManilaDay(scheduled, selectedDay);
  const locale = language === 'fil' ? 'fil-PH' : 'en-PH';
  const monthLabel = new Intl.DateTimeFormat(locale, {timeZone: 'Asia/Manila', month: 'long', year: 'numeric'})
    .format(new Date(Date.UTC(displayMonth.year, displayMonth.month - 1, 15, 12)));
  const weekdayLabels = Array.from({length: 7}, (_, index) => new Intl.DateTimeFormat(locale, {
    timeZone: 'Asia/Manila',
    weekday: 'short',
  }).format(new Date(Date.UTC(2023, 0, index + 1, 12))));

  useEffect(() => {
    if (!focusAfterUpdate.current) return;
    focusAfterUpdate.current = false;
    dayButtons.current.get(focusDay)?.focus();
  }, [focusDay, monthDays]);

  function chooseDay(day: string) {
    setSelectedDay(day);
    setFocusDay(day);
    const [year, month] = day.split('-').map(Number);
    setDisplayMonth({year, month});
  }

  function moveMonth(amount: number) {
    const next = shiftCalendarMonth(displayMonth.year, displayMonth.month, amount);
    if (!next) return;
    const currentDay = Number(selectedDay.slice(-2));
    const lastDay = new Date(Date.UTC(next.year, next.month, 0)).getUTCDate();
    const day = String(Math.min(currentDay, lastDay)).padStart(2, '0');
    const nextSelected = String(next.year).padStart(4, '0') + '-' + String(next.month).padStart(2, '0') + '-' + day;
    setDisplayMonth(next);
    setSelectedDay(nextSelected);
    setFocusDay(nextSelected);
  }

  function markerGroups(day: string) {
    const groups = new Map<string, {label: string; shortLabel: string; count: number; style: string}>();
    const statusLabels: Record<string, {label: string; shortLabel: string}> = {
      confirmed: {label: t('Confirmed'), shortLabel: t('Conf.')},
      waitlisted: {label: t('Waitlist'), shortLabel: t('Wait')},
      pending: {label: t('Pending'), shortLabel: t('Pend')},
      reconfirmation_required: {label: t('Reconfirmation required'), shortLabel: t('Re')},
      cancelled: {label: t('Cancelled'), shortLabel: t('Can')},
      rejected: {label: t('Rejected'), shortLabel: t('Rej')},
      saved: {label: t('Saved'), shortLabel: t('Save')},
    };
    for (const entry of eventsForManilaDay(scheduled, day)) {
      const label = statusLabels[entry.status] ?? statusLabels.saved;
      const existing = groups.get(entry.status);
      groups.set(entry.status, {
        label: label.label,
        shortLabel: label.shortLabel,
        count: (existing?.count ?? 0) + 1,
        style: statusStyle(entry.status),
      });
    }
    return [...groups.entries()];
  }

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, day: string) {
    const amount = event.key === 'ArrowRight' ? 1
      : event.key === 'ArrowLeft' ? -1
        : event.key === 'ArrowDown' ? 7
          : event.key === 'ArrowUp' ? -7
            : 0;
    if (!amount) return;
    event.preventDefault();
    focusAfterUpdate.current = true;
    chooseDay(dayAfter(day, amount));
  }

  return (
    <section className={styles.calendar} aria-label={t('Calendar')}>
      {entries.length === 0 ? <p className="panel empty-state muted">{props.emptyMessage}</p> : null}
      <div className={styles.monthControls}>
        <button className={styles.monthButton} type="button" onClick={() => moveMonth(-1)} aria-label={t('Previous month')}>‹</button>
        <h2 aria-live="polite">{monthLabel}</h2>
        <button className={styles.monthButton} type="button" onClick={() => moveMonth(1)} aria-label={t('Next month')}>›</button>
        <button className={styles.monthButton} type="button" onClick={() => chooseDay(today)}>{t('Today')}</button>
      </div>
      <div className={styles.weekdayGrid} aria-hidden="true">
        {weekdayLabels.map((weekday, index) => <span className={styles.weekday} key={index}>{weekday}</span>)}
      </div>
      <div className={styles.dayGrid} role="group" aria-label={monthLabel}>
        {monthDays.map((day) => {
          const dayMarkers = markerGroups(day);
          const isOutsideMonth = Number(day.slice(5, 7)) !== displayMonth.month;
          const dayLabel = formatDate(day + 'T12:00:00+08:00', language);
          const count = eventsForManilaDay(scheduled, day).length;
          const markerSummary = dayMarkers.map(([, marker]) => marker.label + (marker.count > 1 ? ', ' + marker.count : '')).join(', ');
          return (
            <button
              className={styles.dayButton + (isOutsideMonth ? ' ' + styles.outsideMonth : '')}
              type="button"
              key={day}
              ref={(button) => {
                if (button) dayButtons.current.set(day, button);
                else dayButtons.current.delete(day);
              }}
              aria-label={dayLabel + ', ' + count + ' ' + t('events') + (markerSummary ? ', ' + markerSummary : '')}
              aria-pressed={selectedDay === day}
              aria-current={today === day ? 'date' : undefined}
              tabIndex={focusDay === day ? 0 : -1}
              onClick={() => chooseDay(day)}
              onKeyDown={(event) => moveFocus(event, day)}
            >
              <span className={styles.dayNumber}>{Number(day.slice(-2))}</span>
              <span className={styles.markers}>
                {dayMarkers.map(([key, marker]) => (
                  <span className={styles.marker + ' ' + marker.style} key={key}>
                    {marker.shortLabel}
                    {marker.count > 1 ? <span className={styles.markerCount}> · {marker.count}</span> : null}
                  </span>
                ))}
              </span>
            </button>
          );
        })}
      </div>
      <ul className={styles.legend} aria-label={t('Calendar status legend')}>
        {[
          ['confirmed', t('Confirmed')],
          ['waitlisted', t('Waitlist')],
          ['pending', t('Pending')],
          ['reconfirmation_required', t('Reconfirmation required')],
          ['cancelled', t('Cancelled')],
          ['rejected', t('Rejected')],
          ['saved', t('Saved')],
        ].map(([status, label]) => (
          <li key={status}>
            <span className={styles.legendMark + ' ' + statusStyle(status)} aria-hidden="true" />
            <span>{label}</span>
          </li>
        ))}
      </ul>
      <section className={styles.selectedDay} aria-labelledby="planning-selected-day">
        <h3 id="planning-selected-day" aria-live="polite">{formatDate(selectedDay + 'T12:00:00+08:00', language)}</h3>
        {selectedEntries.length
          ? selectedEntries.map((entry) => <div key={entry.key}>{entry.content}</div>)
          : <p className="panel empty-state muted">{t('Select a date to view events.')}</p>}
      </section>
      {undated.length ? (
        <section className={styles.undated} aria-labelledby="planning-undated-title">
          <h3 id="planning-undated-title">{t('Events without a date')}</h3>
          {undated.map((entry) => <div key={entry.key}>{entry.content}</div>)}
        </section>
      ) : null}
    </section>
  );
}
