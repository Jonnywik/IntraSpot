'use client';
import Link from 'next/link';
import { useState } from 'react';
import { Feedback } from '@/components/feedback';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import { formatDate, formatTime } from '@/lib/date';
import { api } from '@/lib/api';
import type { Notification } from '@/lib/types';
function notificationTitle(kind: string) {
  if (kind.startsWith('membership')) return 'Club membership';
  if (kind === 'chat_message') return 'Event chat';
  if (kind.startsWith('report') || kind.startsWith('personal') || kind.startsWith('safety')) return 'Safety review';
  if (kind === 'waitlist_promoted' || kind === 'registration_approved') return 'Attendance confirmed';
  if (kind.includes('reconfirm') || kind.includes('material')) return 'Event update';
  if (kind.includes('review')) return 'Registration review';
  if (kind.includes('reject')) return 'Registration decision';
  if (kind.includes('cancel') || kind.includes('capacity')) return 'Registration update';
  return 'Event notification';
}
export default function NotificationsPage() {
  const {token} = useSession();
  const resource = useApiResource<Notification[]>(token ? '/me/notifications' : null, token, 30000);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function markRead(notice: Notification) {
    if (!token || working) return;
    setWorking(notice.id); setError(null);
    try {
      await api<Notification>(`/me/notifications/${notice.id}/read`, {token, method: 'POST'});
      resource.reload();
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Please retry.'); }
    finally { setWorking(null); }
  }
  return <section className="stack"><h1>Notifications</h1>{!token ? <p className="panel">Select a local fictional account to see your notifications.</p> :
    <Feedback {...resource} onRetry={resource.reload}>
      <p className="muted">In-app updates refresh while this page is open. No email or push notifications.</p>
      {error && <p role="alert" className="panel error">{error}</p>}
      {resource.data?.length === 0 && <p className="panel muted">No notifications yet.</p>}
      {resource.data?.map(notice => <article className="panel" key={notice.id}><h2>{notificationTitle(notice.kind)}</h2><span className="status-chip">{notice.read_at ? 'Read' : 'Unread'}</span><p>{notice.message}</p>
        <p className="muted">{formatDate(notice.created_at)} · {formatTime(notice.created_at)}</p>
        <div className="actions"><Link className="button button-secondary" href={!notice.event_id && notice.org_id
          ? `/organizations?orgId=${encodeURIComponent(notice.org_id)}` : notice.kind === 'chat_message'
          ? `/chat?eventId=${notice.event_id}` : `/events?eventId=${notice.event_id}`}>
          {!notice.event_id && notice.org_id ? 'View club membership' : notice.kind === 'chat_message' ? 'Open event chat' : 'View event'}</Link>
        {!notice.read_at && <button className="button button-secondary" type="button" disabled={working !== null}
          onClick={() => void markRead(notice)}>{working === notice.id ? 'Saving…' : 'Mark as read'}</button>}</div></article>)}
    </Feedback>}</section>;
}
