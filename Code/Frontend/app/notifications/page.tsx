'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Feedback } from '@/components/feedback';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import { formatDate, formatTime } from '@/lib/date';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import type { Notification } from '@/lib/types';
import {
  notificationCategory,
  notificationDestination,
  type NotificationCategory,
} from '@/features/notifications/inbox';
import styles from '@/features/notifications/notifications.module.css';

type Translate = ReturnType<typeof useT>;

// Only exact backend-authored notification messages are localized here. Unknown
// messages are rendered as received so authored content is never translated.
const SYSTEM_NOTIFICATION_MESSAGES: Record<string, string> = {
  'Your organization membership request was approved.': 'Your organization membership request was approved.',
  'Your organization membership request was not approved.': 'Your organization membership request was not approved.',
  'You have a new organization membership invitation.': 'You have a new organization membership invitation.',
  'An organization membership invitation was accepted.': 'An organization membership invitation was accepted.',
  'An organization membership invitation was declined.': 'An organization membership invitation was declined.',
  'An organization membership invitation is no longer available.': 'An organization membership invitation is no longer available.',
  'You have left the organization.': 'You have left the organization.',
  'Your organization membership was removed.': 'Your organization membership was removed.',
  'Your organization membership role was updated.': 'Your organization membership role was updated.',
  'A spot opened. Your attendance is now confirmed.': 'A spot opened. Your attendance is now confirmed.',
  'An event from your organization has changed. Review the updated event details.': 'An event from your organization has changed. Review the updated event details.',
  'Your registration is awaiting event-organizer review.': 'Your registration is awaiting event-organizer review.',
  'A registration is waiting for your event review.': 'A registration is waiting for your event review.',
  'A spot opened. Your registration is awaiting event-organizer review.': 'A spot opened. Your registration is awaiting event-organizer review.',
  'Your registration was removed because its review window expired.': 'Your registration was removed because its review window expired.',
  'Your registration is still awaiting review. The review window was extended once.': 'Your registration is still awaiting review. The review window was extended once.',
  'A registration assigned to you still awaits review during its extension window.': 'A registration assigned to you still awaits review during its extension window.',
  'Your registration has reached the final review stage.': 'Your registration has reached the final review stage.',
  'A registration is waiting for final event review.': 'A registration is waiting for final event review.',
  'Your registration was removed because reconfirmation was not received in time.': 'Your registration was removed because reconfirmation was not received in time.',
  'Your event registration was approved.': 'Your event registration was approved.',
  'Your event registration was not approved.': 'Your event registration was not approved.',
  'Your event registration is confirmed for the updated event details.': 'Your event registration is confirmed for the updated event details.',
  'Your registration was cancelled as requested.': 'Your registration was cancelled as requested.',
  'An event registration ended because your organization membership ended.': 'An event registration ended because your organization membership ended.',
  'Event details changed. Review your registration status and any reconfirmation request.': 'Event details changed. Review your registration status and any reconfirmation request.',
  'New message in an event chat.': 'New message in an event chat.',
  'Your safety report was received.': 'Your safety report was received.',
  'A safety report involving you or content you authored is under review.': 'A safety report involving you or content you authored is under review.',
  'A safety report requires review.': 'A safety report requires review.',
  'A safety report was escalated for platform review.': 'A safety report was escalated for platform review.',
  'A safety report involving you or content you authored is under platform review.': 'A safety report involving you or content you authored is under platform review.',
  'A safety report requires platform review.': 'A safety report requires platform review.',
  'A safety report was resolved.': 'A safety report was resolved.',
  'A safety warning was issued after review.': 'A safety warning was issued after review.',
  'A safety review involving you or your content was closed.': 'A safety review involving you or your content was closed.',
  'A safety report review was completed.': 'A safety report review was completed.',
  'A safety report was closed after its review window.': 'A safety report was closed after its review window.',
  'A safety review involving you or your content was closed after its review window.': 'A safety review involving you or your content was closed after its review window.',
  'A safety report reached its review deadline.': 'A safety report reached its review deadline.',
};

const SYSTEM_ERROR_MESSAGES: Record<string, string> = {
  'Authentication could not be verified.': 'Authentication could not be verified.',
  'Notification was not found.': 'Notification was not found.',
  'Cannot reach the local backend. Check it is running, then retry.': 'Cannot reach the local backend. Check it is running, then retry.',
  'The request could not be completed. Please retry.': 'The request could not be completed. Please retry.',
  'Request could not be completed.': 'Request could not be completed.',
  'Check the required fields and their formats.': 'Check the required fields and their formats.',
  'Please retry.': 'Please retry.',
};

function notificationTitle(kind: string, t: Translate) {
  if (kind === 'membership_attendance_ended') return t('Registration update');
  if (kind.startsWith('membership')) return t('Club membership');
  if (kind === 'chat_message') return t('Event chat');
  if (kind.startsWith('report') || kind.startsWith('personal') || kind.startsWith('safety')) return t('Safety review');
  if (kind === 'waitlist_promoted' || kind === 'registration_approved') return t('Attendance confirmed');
  if (kind.includes('reconfirm') || kind.includes('material')) return t('Event update');
  if (kind.includes('review')) return t('Registration review');
  if (kind.includes('reject')) return t('Registration decision');
  if (kind.includes('cancel') || kind.includes('capacity')) return t('Registration update');
  return t('Event notification');
}

function notificationMessage(message: string, t: Translate) {
  const literal = SYSTEM_NOTIFICATION_MESSAGES[message];
  return literal ? t(literal) : message;
}

function systemErrorMessage(message: string, t: Translate) {
  const literal = SYSTEM_ERROR_MESSAGES[message];
  return literal ? t(literal) : message;
}

const CATEGORY_OPTIONS: { value: NotificationCategory; label: string }[] = [
  { value: 'registrations', label: 'Registrations' },
  { value: 'clubs', label: 'Clubs' },
  { value: 'chat', label: 'Chat' },
  { value: 'safety', label: 'Safety' },
];

export default function NotificationsPage() {
  const t = useT();
  const { preferences } = usePreferences();
  const { actor, token } = useSession();
  const resource = useApiResource<Notification[]>(token ? '/me/notifications' : null, token, 30000);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [readOverrides, setReadOverrides] = useState<Record<string, true>>({});
  const [stateFilter, setStateFilter] = useState<'all' | 'unread'>('all');
  const [categoryFilter, setCategoryFilter] = useState<NotificationCategory | 'all'>('all');
  const [readConfirmation, setReadConfirmation] = useState(false);

  const notifications = resource.data ?? [];
  const isRead = (notice: Notification) => readOverrides[notice.id] ?? Boolean(notice.read_at);
  const unreadCount = notifications.filter(notice => !isRead(notice)).length;
  const stateFiltered = stateFilter === 'unread'
    ? notifications.filter(notice => !isRead(notice))
    : notifications;
  const categoryCounts = Object.fromEntries(CATEGORY_OPTIONS.map(({ value }) => [
    value,
    stateFiltered.filter(notice => notificationCategory(notice.kind) === value).length,
  ])) as Record<NotificationCategory, number>;
  const visibleNotifications = categoryFilter === 'all'
    ? stateFiltered
    : stateFiltered.filter(notice => notificationCategory(notice.kind) === categoryFilter);

  async function markRead(notice: Notification) {
    if (!token || working || isRead(notice)) return;
    setWorking(notice.id);
    setError(null);
    setReadConfirmation(false);
    try {
      await api<Notification>(`/me/notifications/${notice.id}/read`, { token, method: 'POST' });
      setReadOverrides(previous => ({ ...previous, [notice.id]: true }));
      setReadConfirmation(true);
      resource.reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Please retry.');
    } finally {
      setWorking(null);
    }
  }

  return (
    <section className="stack">
      <h1>{t('Notifications')}</h1>
      {!token ? <p className="panel">{t('Sign in to see your notifications.')}</p> : (
        <Feedback {...resource} onRetry={resource.reload}>
          <div className={styles.inboxContent}>
            <p className="muted">{t('In-app updates refresh while this page is open. No email or push notifications.')}</p>
            {error ? <p role="alert" className="panel error">{systemErrorMessage(error, t)}</p> : null}
            {readConfirmation ? <p className="panel" role="status">{t('Notification marked as read.')}</p> : null}
            {resource.data !== null ? (
              <>
                <p className="muted">
                  {t('Showing {count} notifications. Only the latest 100 are included; filters apply to this list.', { count: notifications.length })}
                </p>

                <div className={styles.filters}>
                  <div className={styles.filterGroup} role="group" aria-label={t('Notification status filter')}>
                    {(['all', 'unread'] as const).map(filter => {
                      const label = filter === 'all' ? 'All' : 'Unread';
                      const count = filter === 'all' ? notifications.length : unreadCount;
                      return (
                        <button
                          className={styles.filterButton}
                          type="button"
                          aria-pressed={stateFilter === filter}
                          aria-label={t('{label}, {count} notifications', { label: t(label), count })}
                          onClick={() => setStateFilter(filter)}
                          key={filter}
                        >
                          {t(label)} <span className={styles.filterCount} aria-hidden="true">{count}</span>
                        </button>
                      );
                    })}
                  </div>

                  <div className={styles.filterGroup} role="group" aria-label={t('Notification category filter')}>
                    <button
                      className={styles.filterButton}
                      type="button"
                      aria-pressed={categoryFilter === 'all'}
                      aria-label={t('{label}, {count} notifications', {
                        label: t('All categories'),
                        count: stateFiltered.length,
                      })}
                      onClick={() => setCategoryFilter('all')}
                    >
                      {t('All categories')} <span className={styles.filterCount} aria-hidden="true">{stateFiltered.length}</span>
                    </button>
                    {CATEGORY_OPTIONS.map(({ value, label }) => (
                      <button
                        className={styles.filterButton}
                        type="button"
                        aria-pressed={categoryFilter === value}
                        aria-label={t('{label}, {count} notifications', { label: t(label), count: categoryCounts[value] })}
                        onClick={() => setCategoryFilter(value)}
                        key={value}
                      >
                        {t(label)} <span className={styles.filterCount} aria-hidden="true">{categoryCounts[value]}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {notifications.length === 0 ? (
                  <p className="panel muted">{t('No notifications yet.')}</p>
                ) : visibleNotifications.length === 0 ? (
                  <p className="panel muted" role="status">
                    {stateFilter === 'unread' && categoryFilter === 'all'
                      ? t('You’re all caught up.')
                      : t('No notifications match these filters.')}
                  </p>
                ) : (
                  <ul className={styles.notificationList} aria-label={t('Notifications')}>
                    {visibleNotifications.map(notice => {
                      const read = isRead(notice);
                      const category = notificationCategory(notice.kind);
                      const categoryLabel = CATEGORY_OPTIONS.find(option => option.value === category)?.label ?? 'Registrations';
                      const destination = notificationDestination(notice, actor);
                      return (
                        <li key={notice.id}>
                          <article className={`panel ${styles.notification} ${read ? '' : styles.unread}`}>
                            <div className={styles.notificationHeading}>
                              <h2>{notificationTitle(notice.kind, t)}</h2>
                              <div className={styles.badges}>
                                <span className="status-chip">{read ? t('Read') : t('Unread')}</span>
                                <span className={styles.categoryBadge}>{t(categoryLabel)}</span>
                              </div>
                            </div>
                            <p className={styles.message}>{notificationMessage(notice.message, t)}</p>
                            <p className={`muted ${styles.timestamp}`}>
                              {formatDate(notice.created_at, preferences.language)} · {formatTime(notice.created_at, preferences.language)}
                            </p>
                            <div className={styles.actions}>
                              {destination ? (
                                <Link className="button button-secondary" href={destination.href}>{t(destination.label)}</Link>
                              ) : null}
                              {!read ? (
                                <button
                                  className="button button-secondary"
                                  type="button"
                                  disabled={working !== null}
                                  onClick={() => void markRead(notice)}
                                >
                                  {working === notice.id ? t('Saving…') : t('Mark as read')}
                                </button>
                              ) : null}
                            </div>
                          </article>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </>
            ) : null}
          </div>
        </Feedback>
      )}
    </section>
  );
}
