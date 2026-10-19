'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { ChatWorkspace } from '@/features/communication/ChatWorkspace';
import { useT } from '@/lib/i18n';
import { useSession } from '@/lib/session';

function ChatRoute() {
  const eventId = useSearchParams().get('eventId');
  const { version } = useSession();
  return <ChatWorkspace key={`${version}:${eventId ?? 'inbox'}`} eventId={eventId} />;
}

export default function ChatPage() {
  const t = useT();
  return (
    <Suspense fallback={<p className="panel muted" role="status">{t('Loading event chats…')}</p>}>
      <ChatRoute />
    </Suspense>
  );
}
