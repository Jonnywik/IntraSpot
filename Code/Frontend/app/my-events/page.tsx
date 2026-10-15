'use client';

import { MyEvents } from '@/features/registrations/MyEvents';
import { Suspense } from 'react';

export default function MyEventsPage() {
  return <Suspense fallback={<p role="status">Loading your events…</p>}><MyEvents /></Suspense>;
}
