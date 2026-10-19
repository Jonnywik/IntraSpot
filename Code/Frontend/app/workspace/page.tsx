'use client';

import { Suspense } from 'react';
import { OrganizationWorkspacePage } from '@/features/organizations/workspace-page';
import { useT } from '@/lib/i18n';

export default function WorkspacePage() {
  const t = useT();
  return (
    <Suspense fallback={<p className="panel muted" role="status">{t('Loading your organization workspace…')}</p>}>
      <OrganizationWorkspacePage />
    </Suspense>
  );
}
