'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useSession } from '@/lib/session';
import { LocalSignIn } from '@/features/identity/LocalSignIn';
import { Icon } from '@/components/icon';

const tabs = [
  {href: '/', label: 'Discover', icon: 'home' as const},
  {href: '/my-events', label: 'My Events', icon: 'calendar' as const},
  {href: '/chat', label: 'Chat', icon: 'chat' as const},
  {href: '/settings', label: 'Settings', icon: 'settings' as const},
];
export function SiteHeader() {
  const path = usePathname();
  const {actor} = useSession();
  const navigation = tabs.map(tab => <Link key={tab.href} href={tab.href}
    aria-current={path === tab.href ? 'page' : undefined}>
    <Icon name={tab.icon}/><span>{tab.label}</span></Link>);
  return <>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="site-header"><div className="header-inner">
      <Link className="wordmark" href="/">IntraSpot</Link>
      <nav className="desktop-nav" aria-label="Main navigation">{navigation}</nav>
      <div className="utilities">
        <Link className="desktop-only" href="/organizations">Clubs</Link>
        {actor?.eligible && <Link className="desktop-only" href="/workspace">Organization</Link>}
        {actor?.platform_admin && <Link className="desktop-only" href="/admin">Platform admin</Link>}
        <Link href="/notifications" aria-label="Notifications"><Icon name="bell"/></Link>
        <Link className="avatar" href="/profile" aria-label="Profile">{actor?.nickname?.slice(0, 2).toUpperCase() || 'PL'}</Link>
      </div>
    </div></header>
    <div className="local-demo-bar"><span>LOCAL MVP · FICTIONAL ACCOUNTS ONLY</span><div className="local-account-controls"><LocalSignIn/></div></div>
    <nav className="mobile-nav" aria-label="Mobile navigation">{navigation}</nav>
  </>;
}
