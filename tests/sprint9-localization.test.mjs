import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {messages} from '../Code/Frontend/lib/messages.ts';
import {sharedMessages} from '../Code/Frontend/lib/shared-messages.ts';
import {eventMessages} from '../Code/Frontend/lib/event-messages.ts';
import {socialMessages} from '../Code/Frontend/lib/social-messages.ts';
import {attendeeMessages} from '../Code/Frontend/lib/attendee-messages.ts';
import {workspaceMessages} from '../Code/Frontend/lib/workspace-messages.ts';
import {platformMessages} from '../Code/Frontend/lib/platform-messages.ts';
import {draftMessages} from '../Code/Frontend/lib/draft-messages.ts';
import {inboxMessages} from '../Code/Frontend/lib/inbox-messages.ts';
import {mobileMessages} from '../Code/Frontend/lib/mobile-messages.ts';
import {discoveryMessages} from '../Code/Frontend/lib/discovery-messages.ts';
import {announcementMessages} from '../Code/Frontend/lib/announcement-messages.ts';
import {announcementReportMessages} from '../Code/Frontend/lib/announcement-report-messages.ts';
import {authMessages} from '../Code/Frontend/lib/auth-messages.ts';
import {mediaMessages} from '../Code/Frontend/features/media/messages.ts';
import {planningMessages} from '../Code/Frontend/features/planning/messages.ts';
import {featuredMessages} from '../Code/Frontend/features/featured/messages.ts';
import {personaMessages} from '../Code/Frontend/features/personas/messages.ts';
import {ownershipMessages} from '../Code/Frontend/features/ownership/messages.ts';
import {attendanceMessages} from '../Code/Frontend/features/attendance/messages.ts';
import {safetyMessages} from '../Code/Frontend/features/eventsafety/messages.ts';
import {formatDate, formatTime} from '../Code/Frontend/lib/date.ts';

const dictionaries = [sharedMessages,eventMessages,socialMessages,attendeeMessages,
  workspaceMessages,platformMessages,draftMessages,inboxMessages,mobileMessages,discoveryMessages,
  announcementMessages,announcementReportMessages,authMessages,mediaMessages,planningMessages,featuredMessages,personaMessages,ownershipMessages,attendanceMessages,safetyMessages];
const filipino = {...Object.fromEntries(Object.entries(messages).map(([key,value])=>[key,value.fil])),...Object.assign({},...dictionaries)};
const placeholders = value => [...value.matchAll(/\{([A-Za-z0-9_]+)\}/g)].map(match=>match[1]).sort();

test('Filipino interface messages preserve all named values and contain nonblank translations', () => {
  for (const [english, translated] of Object.entries(filipino)) {
    assert.equal(typeof translated,'string',english);
    assert.ok(translated.trim().length>0,english);
    assert.deepEqual(placeholders(translated),placeholders(english),english);
  }
});

test('Attendee and management interface literal messages have Filipino translations', async () => {
  const ts = createRequire(new URL('../Code/Frontend/package.json',import.meta.url))('typescript');
  const files = [
    'app/site-header.tsx','app/settings/page.tsx','app/profile/page.tsx','app/notifications/page.tsx',
    'components/application-shell.tsx','components/discovery-layout.tsx','components/heritage-decoration.tsx',
    'components/feedback.tsx','features/identity/LocalSignIn.tsx','features/events/DiscoverFeed.tsx',
    'features/events/EventDetail.tsx','features/registrations/RegistrationAction.tsx',
    'features/registrations/MyEvents.tsx','features/communication/ChatWorkspace.tsx',
    'features/communication/EventSocial.tsx','features/communication/ContentSafetyControls.tsx',
    'features/events/DraftEditor.tsx','features/organizations/workspace-page.tsx',
    'features/organizations/admin-page.tsx','features/organizations/shared.tsx',
    'features/organizations/RegistrationReview.tsx','features/organizations/EventChanges.tsx',
    'features/memberships/StaffMembership.tsx','features/moderation/report-queue.tsx',
    'app/draft/page.tsx','app/workspace/page.tsx',
    'features/preferences/DiscoveryPreferences.tsx',
    'features/moderation/AnnouncementReportQueue.tsx',
    'features/announcements/AnnouncementReader.tsx',
    'features/announcements/AnnouncementManager.tsx',
    'features/identity/GoogleSignIn.tsx','app/auth/callback/page.tsx',
    'features/planning/SaveEventButton.tsx','features/planning/ConflictWarning.tsx',
    'features/planning/SavedEvents.tsx','features/planning/EventCalendar.tsx',
    'features/featured/FeaturedControls.tsx','features/featured/FeaturedBadge.tsx',
    'features/personas/PersonaActions.tsx','features/personas/BlockList.tsx',
    'features/personas/EventPersonaSharing.tsx',
    'features/ownership/OwnershipTransferPanel.tsx',
    'features/attendance/AttendancePanel.tsx',
    'features/eventsafety/EventReportButton.tsx','features/eventsafety/EventSafetyControls.tsx',
    'features/eventsafety/EventSafetyQueue.tsx','features/eventsafety/OrganizationSuspensionPanel.tsx',
    'features/eventsafety/SafetyDialog.tsx',
  ];
  const missing = new Set();
  for (const file of files) {
    const text = await readFile(new URL(`../Code/Frontend/${file}`,import.meta.url),'utf8');
    const source = ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
    const visit = node => {
      if (ts.isCallExpression(node) && ['t', 'text'].includes(node.expression.getText(source)) &&
        node.arguments[0] && ts.isStringLiteralLike(node.arguments[0]) && !filipino[node.arguments[0].text]) {
        missing.add(`${file}: ${node.arguments[0].text}`);
      }
      ts.forEachChild(node,visit);
    };
    visit(source);
  }
  assert.deepEqual([...missing].sort(),[]);
});

test('Date formatting uses the chosen language independently while preserving Manila time', () => {
  const instant = '2026-10-15T16:30:00Z';
  assert.equal(formatDate(instant,'fil'),new Intl.DateTimeFormat('fil-PH',{timeZone:'Asia/Manila',dateStyle:'medium'}).format(new Date(instant)));
  assert.equal(formatTime(instant,'fil'),new Intl.DateTimeFormat('fil-PH',{timeZone:'Asia/Manila',timeStyle:'short'}).format(new Date(instant)));
  assert.equal(formatDate(instant),formatDate(instant,'en'));
  assert.notEqual(formatDate(instant,'fil'),formatDate(instant,'en'));
});
