'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useSession } from '@/lib/session';
import { MemberPortal } from '@/features/memberships/MemberPortal';

function MembershipPage() {
  const orgId = useSearchParams().get('orgId') ?? undefined;
  const { version } = useSession();
  return <MemberPortal key={`${version}:${orgId ?? 'all'}`} orgId={orgId} />;
}

export default function OrganizationsPage() {
  return <Suspense fallback={<p role="status">Loading organizations…</p>}><MembershipPage /></Suspense>;
}
