'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { useSession } from '@/lib/session';
import { LocalSignIn } from '@/features/identity/LocalSignIn';
import {GoogleSignIn} from '@/features/identity/GoogleSignIn';
import { Icon } from '@/components/icon';
import { useT } from '@/lib/i18n';

const tabs = [
  {href: '/', label: 'Discover', icon: 'home' as const},
  {href: '/my-events', label: 'My Events', icon: 'calendar' as const},
  {href: '/chat', label: 'Chat', icon: 'chat' as const},
  {href: '/settings', label: 'Settings', icon: 'settings' as const},
];
export function SiteHeader() {
  const path = usePathname();
  const {actor} = useSession();
  const t = useT();
  const realDevelopment = process.env.NEXT_PUBLIC_AUTH_MODE === 'supabase';
  const mobileNavigation = useRef<HTMLElement>(null);
  useEffect(() => {
    const navigation = mobileNavigation.current;
    if (!navigation) return;
    const measure = () => document.documentElement.style.setProperty(
      '--mobile-nav-height', `${navigation.getBoundingClientRect().height}px`,
    );
    const observer = new ResizeObserver(measure);
    observer.observe(navigation);
    measure();
    return () => {
      observer.disconnect();
      document.documentElement.style.removeProperty('--mobile-nav-height');
    };
  }, []);
  const navigation = tabs.map(tab => <Link key={tab.href} href={tab.href}
    aria-current={path === tab.href || tab.href === '/' && path === '/events' ? 'page' : undefined}>
    <Icon name={tab.icon}/><span>{t(tab.label)}</span></Link>);
  return <>
    <a className="skip-link" href="#main-content">{t('Skip to content')}</a>
    <header className="site-header"><div className="header-inner">
      <Link className="wordmark" href="/">IntraSpot</Link>
      <nav className="desktop-nav" aria-label={t('Main navigation')}>{navigation}</nav>
      <div className="utilities">
        <Link className="desktop-only" href="/organizations">{t('Clubs')}</Link>
        {actor?.eligible && <Link className="desktop-only" href="/workspace">{t('Organization')}</Link>}
        {actor?.platform_admin && <Link className="desktop-only" href="/admin">{t('Platform admin')}</Link>}
        <Link className="utility-icon" href="/notifications" aria-label={t('Notifications')}><Icon name="bell"/></Link>
        <Link className="avatar" href="/profile" aria-label={t('Profile')}>{actor?.nickname?.slice(0, 2).toUpperCase() || 'PL'}</Link>
      </div>
    </div></header>
    <div className="local-demo-bar"><span>{realDevelopment ? t('ISOLATED DEVELOPMENT · GOOGLE SIGN-IN') : t('LOCAL MVP · FICTIONAL ACCOUNTS ONLY')}</span><div className="local-account-controls">{realDevelopment ? <GoogleSignIn/> : <LocalSignIn/>}</div></div>
    <nav ref={mobileNavigation} className="mobile-nav" aria-label={t('Mobile navigation')}>{navigation}</nav>
  </>;
}
