'use client';

import { useCallback } from 'react';
import { usePreferences } from './preferences';
import { messages } from './messages';
import { sharedMessages } from './shared-messages';
import { eventMessages } from './event-messages';
import { socialMessages } from './social-messages';
import { attendeeMessages } from './attendee-messages';
import { workspaceMessages } from './workspace-messages';
import { platformMessages } from './platform-messages';
import { draftMessages } from './draft-messages';
import { inboxMessages } from './inbox-messages';
import { mobileMessages } from './mobile-messages';
import { discoveryMessages } from './discovery-messages';
import { announcementMessages } from './announcement-messages';
import { announcementReportMessages } from './announcement-report-messages';
import { authMessages } from './auth-messages';
import { mediaMessages } from '@/features/media/messages';
import { planningMessages } from '@/features/planning/messages';
import { featuredMessages } from '@/features/featured/messages';
import { personaMessages } from '@/features/personas/messages';
import { ownershipMessages } from '@/features/ownership/messages';
import { attendanceMessages } from '@/features/attendance/messages';
import { safetyMessages } from '@/features/eventsafety/messages';

const filipinoMessages: Record<string, string> = {...sharedMessages, ...eventMessages, ...socialMessages, ...attendeeMessages,
  ...workspaceMessages, ...platformMessages, ...draftMessages, ...inboxMessages, ...mobileMessages, ...discoveryMessages,
  ...announcementMessages, ...announcementReportMessages, ...authMessages, ...mediaMessages, ...planningMessages, ...featuredMessages, ...personaMessages, ...ownershipMessages, ...attendanceMessages, ...safetyMessages};

export type TranslationValues = Record<string, string | number>;
export type Translate = (english: string, values?: TranslationValues) => string;

export function useT(): Translate {
  const { preferences } = usePreferences();
  const language = preferences.language;
  return useCallback((english: string, values?: TranslationValues) => {
    const template = messages[english]?.[language]
      ?? (language === 'fil' ? filipinoMessages[english] : undefined)
      ?? english;
    return template.replace(/\{([A-Za-z0-9_]+)\}/g, (match, name: string) =>
      values && Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match,
    );
  }, [language]);
}
