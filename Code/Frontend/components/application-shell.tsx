'use client';
import { usePathname } from 'next/navigation';
import { SiteHeader } from '@/app/site-header';
import { useSession } from '@/lib/session';
import type { ReactNode } from 'react';
import { useT } from '@/lib/i18n';
import { DiscoveryLayout } from './discovery-layout';
export function ApplicationShell({children}: {children: ReactNode}) {
  const path = usePathname();
  const {version} = useSession();
  const t = useT();
  const management = ['/workspace', '/admin', '/draft'].includes(path);
  return <><SiteHeader/><main id="main-content" className={`workspace ${management ? 'management' : 'attendee'} ${path === '/' ? 'discovery-workspace' : path === '/chat' ? 'chat-workspace' : ''}`}>
    {path === '/auth/callback' ? <div>{children}</div> :
      <div key={version}>{path === '/' ? <DiscoveryLayout>{children}</DiscoveryLayout> : children}</div>}
  </main><footer className="site-footer">IntraSpot · {t('Same people. Brighter tomorrows.')}<br/>{process.env.NEXT_PUBLIC_AUTH_MODE === 'supabase'
    ? t('Isolated Google development sign-in · not approved for real-user release.')
    : t('Local fictional-data MVP · not approved for real-user release.')}</footer></>;
}
