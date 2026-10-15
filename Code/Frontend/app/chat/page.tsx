'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { ChatWorkspace } from '@/features/communication/ChatWorkspace';
import { useSession } from '@/lib/session';

function ChatRoute() {
  const eventId = useSearchParams().get('eventId');
  const { version } = useSession();
  return <ChatWorkspace key={`${version}:${eventId ?? 'inbox'}`} eventId={eventId} />;
}

export default function ChatPage() {
  return (
    <Suspense fallback={<p className="panel muted" role="status">Loading event chats…</p>}>
      <ChatRoute />
    </Suspense>
  );
}
