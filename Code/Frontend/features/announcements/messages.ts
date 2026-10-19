'use client';

import { useT } from '@/lib/i18n';

export type AnnouncementMessage = {
  key: string;
  values?: Record<string, string | number>;
};

export function useAnnouncementText() {
  return useT();
}

export function announcementApiMessage(error: unknown, action: string): AnnouncementMessage {
  if (error instanceof Error && 'status' in error) {
    const status = Number((error as Error & { status?: number }).status);
    if (status === 401) return { key: 'Your sign-in expired. Sign in again, then retry.' };
    if (status === 403) return { key: 'This action is unavailable for this account.' };
    if (status === 404) return { key: 'This announcement is no longer available.' };
    if (status === 409) {
      if (action === 'Create announcement') {
        return { key: 'The create request could not be confirmed. Your content and request key are preserved. Retry the same announcement.' };
      }
      if (action === 'Reaction update') {
        return { key: 'The reaction could not be updated. Your choice is preserved; retry the same reaction.' };
      }
      return { key: 'The announcement changed since you loaded it. Your edits are still here. Reload the latest version to continue.' };
    }
  }
  return { key: 'The request could not be completed. Check your connection and retry.' };
}
