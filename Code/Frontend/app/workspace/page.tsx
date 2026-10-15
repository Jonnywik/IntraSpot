'use client';

import { Suspense } from 'react';
import { OrganizationWorkspacePage } from '@/features/organizations/workspace-page';

export default function WorkspacePage() {
  return (
    <Suspense fallback={<p className="panel muted" role="status">Loading workspace…</p>}>
      <OrganizationWorkspacePage />
    </Suspense>
  );
}
