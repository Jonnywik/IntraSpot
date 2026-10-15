'use client';
import { usePathname } from 'next/navigation';
import { SiteHeader } from '@/app/site-header';
import { useSession } from '@/lib/session';
import type { ReactNode } from 'react';
export function ApplicationShell({children}: {children: ReactNode}) {
  const path = usePathname();
  const {version} = useSession();
  const management = ['/workspace', '/admin', '/draft'].includes(path);
  return <><SiteHeader/><main id="main-content" className={`workspace ${management ? 'management' : 'attendee'}`}>
    <div key={version}>{children}</div>
  </main><footer className="site-footer">IntraSpot · Same people. Brighter tomorrows.<br/>Local fictional-data MVP · not approved for real-user release.</footer></>;
}
