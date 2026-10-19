'use client';

import Link from 'next/link';
import { type ReactNode, useEffect, useState } from 'react';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import { formatDate, formatTime } from '@/lib/date';
import type { MyOrganizations, MyRegistration, Organization } from '@/lib/types';

export function DiscoveryLayout({children}: {children: ReactNode}) {
  const {actor, token} = useSession();
  const t = useT();
  const realDevelopment = process.env.NEXT_PUBLIC_AUTH_MODE === 'supabase';
  const {preferences:{language}} = usePreferences();
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const query = window.matchMedia('(min-width: 1000px)');
    const update = () => setWide(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  const clubs = useApiResource<MyOrganizations>(wide && actor?.eligible && token ? '/me/organizations' : null, token);
  const publicClubs = useApiResource<Organization[]>(wide && !actor?.eligible ? '/organizations' : null);
  const registrations = useApiResource<MyRegistration[]>(wide && actor?.eligible && token ? '/me/registrations' : null, token, 30000);
  const upcoming = (registrations.data ?? []).filter(row => !row.is_past && row.status === 'confirmed')
    .sort((a,b) => (a.starts_at ?? '').localeCompare(b.starts_at ?? '') || a.event_id.localeCompare(b.event_id)).slice(0,3);
  const pending = (registrations.data ?? []).filter(row => !row.is_past && ['pending','reconfirmation_required'].includes(row.status)).length;
  const waitlisted = (registrations.data ?? []).filter(row => !row.is_past && row.status === 'waitlisted').length;
  return <div className="discovery-layout">
    <aside className="discovery-sidebar discovery-left" aria-label={t('Your community')}>
      <section className="sidebar-section">
        <p className="eyebrow">{t('Your community')}</p>
        <h2>{actor?.eligible ? t('Your clubs') : t('Explore PLM clubs')}</h2>
        {clubs.loading || publicClubs.loading ? <p className="muted" role="status">{t('Loading…')}</p> : null}
        {clubs.error || publicClubs.error ? <p className="muted">{t('Clubs could not load.')} <button className="text-action" type="button" onClick={() => {clubs.reload(); publicClubs.reload();}}>{t('Retry')}</button></p> : null}
        {actor?.eligible ? <>
          {(clubs.data?.grants ?? []).slice(0,5).map(club => <Link className="sidebar-link" href={`${club.accreditation_status === 'approved' ? '/organizations' : '/workspace'}?orgId=${encodeURIComponent(club.org_id)}`} key={club.org_id}><span className="club-monogram" aria-hidden="true">{club.org_name.slice(0,1)}</span><span>{club.org_name}</span></Link>)}
          {!clubs.loading && !clubs.error && clubs.data?.grants.length === 0 && <p className="muted">{t('Find a club that feels like you.')}</p>}
        </> : (publicClubs.data ?? []).slice(0,4).map(club => <Link className="sidebar-link" href={`/organizations?orgId=${encodeURIComponent(club.id)}`} key={club.id}><span className="club-monogram" aria-hidden="true">{club.name.slice(0,1)}</span><span>{club.name}</span></Link>)}
        <Link className="text-action" href="/organizations">{t('Browse clubs')} <span aria-hidden="true">→</span></Link>
      </section>
      <section className="sidebar-section sidebar-shortcuts">
        <h2>{t('Quick access')}</h2>
        <Link className="sidebar-link" href="/my-events">{t('My Events')} <span aria-hidden="true">↗</span></Link>
        <Link className="sidebar-link" href="/chat">{t('Event chats')} <span aria-hidden="true">↗</span></Link>
        <Link className="sidebar-link" href="/profile">{t('Your profile')} <span aria-hidden="true">↗</span></Link>
      </section>
      <p className="sidebar-signature">{t('Same people. Brighter tomorrows.')}</p>
    </aside>
    <div className="discovery-feed-column">{children}</div>
    <aside className="discovery-sidebar discovery-right" aria-label={t('Coming up')}>
      <section className="panel sidebar-agenda">
        <p className="eyebrow">{t('Make room for connection')}</p>
        <h2>{actor?.eligible ? t('Coming up') : t('A place to belong')}</h2>
        {actor?.eligible ? <>
          {registrations.loading && <p className="muted" role="status">{t('Loading…')}</p>}
          {registrations.error && <p className="muted">{t('Your events could not load.')} <button className="text-action" type="button" onClick={registrations.reload}>{t('Retry')}</button></p>}
          {upcoming.map(row => <Link className="agenda-event" href={`/events?eventId=${encodeURIComponent(row.event_id)}`} key={row.id}><span className="agenda-date">{row.starts_at ? formatDate(row.starts_at,language) : t('Date unavailable')}</span><strong>{row.event_title}</strong><span>{row.starts_at ? formatTime(row.starts_at,language) : ''}</span><span className="status-chip confirmed">{t('Confirmed')}</span></Link>)}
          {!registrations.loading && !registrations.error && upcoming.length === 0 && <p className="muted">{t('Your next confirmed event will appear here.')}</p>}
          {pending > 0 && <p className="sidebar-status">{t('Requests needing attention: {count}', {count:pending})}</p>}
          {waitlisted > 0 && <p className="sidebar-status">{t('On the waitlist: {count}', {count:waitlisted})}</p>}
          <Link className="button button-secondary" href="/my-events">{t('View My Events')}</Link>
        </> : <>
          <p className="muted">{t('Browse public events from PLM organizations. Registration is for current PLM students and faculty.')}</p>
          <ol className="welcome-steps"><li>{t('Find something you love.')}</li><li>{realDevelopment ? t('Sign in with an eligible PLM Google account.') : t('Choose an eligible sample PLM account.')}</li><li>{t('Register and meet your community.')}</li></ol>
          <Link className="button button-secondary" href="/settings">{t('Make it comfortable')}</Link>
        </>}
      </section>
    </aside>
  </div>;
}
