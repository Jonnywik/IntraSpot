import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const read = path => readFile(new URL('../' + path, import.meta.url), 'utf8');

test('persona feature DTOs alias the generated API schemas', async () => {
  const source = await read('Code/Frontend/features/personas/types.ts');
  assert.match(source, /import type \{ components \} from '@\/lib\/api\.generated'/);
  assert.match(source, /PersonaProjection = components\['schemas'\]\['PersonaOut'\]/);
  assert.match(source, /EventPersonaVisibility = components\['schemas'\]\['PersonaVisibilityOut'\]/);
  assert.match(source, /OutgoingBlock = components\['schemas'\]\['UserBlockOut'\]/);
  assert.match(source, /RegistrationBlockWarning = components\['schemas'\]\['RegistrationBlockWarning'\]/);
});

test('profile edits preserve optional text explicitly and keep broad sharing opt-in', async () => {
  const source = await read('Code/Frontend/app/profile/page.tsx');
  assert.match(source, /pronouns: profile\.pronouns \?\? ''/);
  assert.match(source, /icebreaker: profile\.icebreaker \?\? ''/);
  assert.match(source, /personaVisible: profile\.persona_visible \?\? false/);
  assert.match(source, /pronouns: fields\.pronouns\.trim\(\) \|\| null/);
  assert.match(source, /icebreaker: fields\.icebreaker\.trim\(\) \|\| null/);
  assert.match(source, /persona_visible: fields\.personaVisible/);
  assert.match(source, /id="profile-pronouns"[\s\S]*?maxLength=\{40\}/);
  assert.match(source, /id="profile-icebreaker"[\s\S]*?maxLength=\{300\}/);
  assert.match(source, /id="profile-persona-visible"[\s\S]*?checked=\{fields\.personaVisible\}/);
  assert.match(source, /interest or vibe tags, pronouns, and icebreaker in event comment contexts/);
  assert.match(source, /Event-only sharing and approval reviewer consent are separate choices\./);
});

test('encountered-member persona is explicit-open, text-only, private-safe, and blockable when unavailable', async () => {
  const [actions, safety] = await Promise.all([
    read('Code/Frontend/features/personas/PersonaActions.tsx'),
    read('Code/Frontend/features/communication/ContentSafetyControls.tsx'),
  ]);
  assert.match(safety, /const canReport = !item\.mine && item\.author_id !== actor\.id && !item\.locally_hidden/);
  assert.match(safety, /\{canReport && actor \? \([\s\S]*?<PersonaActions/);
  assert.match(actions, /if \(!open \|\| !token\)/);
  assert.match(actions, /\/events\/\$\{encodeURIComponent\(eventId\)\}\/personas\/\$\{encodeURIComponent\(targetUserId\)\}/);
  assert.match(actions, /setPersona\(null\);\s*setState\('unavailable'\)/);
  assert.match(actions, /state === 'loaded' && persona \?/);
  const loadedBranchEnd = actions.indexOf(') : null}', actions.indexOf("state === 'loaded' && persona ?"));
  const blockAction = actions.indexOf("{t('Block member')}");
  assert.ok(loadedBranchEnd >= 0 && blockAction > loadedBranchEnd, 'block action must remain available when persona data is unavailable');
  assert.match(actions, /<dialog[\s\S]*?aria-labelledby=\{blockTitleId\}[\s\S]*?aria-describedby=\{blockHelpId\}/);
  assert.match(actions, /dialog\.showModal\(\)[\s\S]*?cancelButton\.current\?\.focus\(\)/);
  assert.match(actions, /autoFocus/);
  assert.match(actions, /Blocking hides each other's text personas[\s\S]*?group chats[\s\S]*?delete messages[\s\S]*?cancel either registration/);
  assert.match(actions, /PUT/);
  assert.match(actions, /notifyPersonaAccessChanged\(targetUserId\)/);
  assert.match(actions, /setInterval\([\s\S]*?30_000/);
  assert.doesNotMatch(actions, /email|image|avatar|birth_date/i);
});

test('outgoing blocks expose opaque IDs only and support idempotent-style unblock UI', async () => {
  const source = await read('Code/Frontend/features/personas/BlockList.tsx');
  assert.match(source, /api<OutgoingBlock\[]>\('\/me\/blocks'/);
  assert.match(source, /\/me\/blocks\/\$\{encodeURIComponent\(userId\)\}/);
  assert.match(source, /method: 'DELETE'/);
  assert.match(source, /block\.user_id/);
  assert.doesNotMatch(source, /block\.nickname|block\.email|block\.avatar/i);
  assert.match(source, /notifyPersonaAccessChanged\(userId\)/);
});

test('confirmed attendees can manage event-only sharing and expiry cannot leave a stale checked control', async () => {
  const [registration, sharing] = await Promise.all([
    read('Code/Frontend/features/registrations/RegistrationAction.tsx'),
    read('Code/Frontend/features/personas/EventPersonaSharing.tsx'),
  ]);
  assert.match(registration, /result\.status === 'confirmed'[\s\S]*?<EventPersonaSharing/);
  assert.match(sharing, /\/events\/\$\{encodeURIComponent\(eventId\)\}\/persona-visibility/);
  assert.match(sharing, /method: 'PUT'[\s\S]*?body: \{ visible \}/);
  assert.match(sharing, /checked=\{effectiveVisible\}/);
  assert.match(sharing, /disabled=\{saving \|\| loading \|\| loadError \|\| expired\}/);
  assert.match(sharing, /setTimeout\([\s\S]*?expiresAt - Date\.now\(\)/);
  assert.match(sharing, /addEventListener\('focus', refresh\)/);
  assert.match(sharing, /addEventListener\('visibilitychange', onVisibilityChange\)/);
  assert.match(sharing, /Event sharing has expired\./);
});

test('registration block warning is anonymous, explicit, server-authoritative, and part of retry payload identity', async () => {
  const source = await read('Code/Frontend/features/registrations/RegistrationAction.tsx');
  assert.match(source, /\/events\/\$\{encodeURIComponent\(event\.id\)\}\/registration-block-warning/);
  assert.match(source, /blocked_attendee_acknowledged: blockWarningAcknowledged/);
  assert.match(source, /body: savedAttempt\.payload/);
  assert.match(source, /idempotencyKey: savedAttempt\.key/);
  assert.match(source, /previousAttempt\.payload\.persona_shared === payload\.persona_shared/);
  assert.match(source, /previousAttempt\.payload\.blocked_attendee_acknowledged === payload\.blocked_attendee_acknowledged/);
  assert.match(source, /\? previousAttempt\s*: \{ eventId: event\.id, key: window\.crypto\.randomUUID\(\), payload \}/);
  assert.match(source, /disabled=\{submitting \|\| \(retryable && error !== null\)\}/);
  assert.match(source, /disabled=\{submitting \|\| warningState === 'loading' \|\| \(retryable && error !== null\)\}/);
  assert.match(source, /caught\.code === 'blocked_attendee_warning'/);
  assert.match(source, /setServerWarning\(true\)/);
  assert.match(source, /Someone you blocked is confirmed for this event\. Their identity is not shown\./);
  assert.match(source, /I understand and want to continue with registration\./);
  assert.match(source, /The warning could not be checked\.[\s\S]*?server will check before accepting registration/);
  assert.match(source, /Retry block warning check/);
  assert.doesNotMatch(source, /blocked_attendee_acknowledged:\s*true/);
});

test('all new feature strings are merged through the named personaMessages export', async () => {
  const [messages, profile, persona, blocks, sharing, registration] = await Promise.all([
    read('Code/Frontend/features/personas/messages.ts'),
    read('Code/Frontend/app/profile/page.tsx'),
    read('Code/Frontend/features/personas/PersonaActions.tsx'),
    read('Code/Frontend/features/personas/BlockList.tsx'),
    read('Code/Frontend/features/personas/EventPersonaSharing.tsx'),
    read('Code/Frontend/features/registrations/RegistrationAction.tsx'),
  ]);
  assert.match(messages, /export const personaMessages:/);
  assert.match(profile, /Enable broad text visibility/);
  assert.match(persona, /View text profile/);
  assert.match(blocks, /Blocked members/);
  assert.match(sharing, /Event-only text sharing/);
  assert.match(registration, /blocked_attendee_acknowledged/);
  for (const key of [
    'Pronouns (optional)',
    'Icebreaker (optional)',
    'Leave blank to clear this optional value.',
    'Enable broad text visibility',
    'New profiles start private. Turn this on only if you want eligible members to see this text in event comment contexts and authorized shared event chats.',
    'Event-only sharing and approval reviewer consent are separate choices.',
    'This text profile is unavailable.',
    'Blocking hides each other\'s text personas. It does not remove either of you from group chats, delete messages, or cancel either registration.',
    'Only the account IDs you blocked appear here. Nicknames are not shown.',
    'Event sharing has expired.',
    'Event sharing could not be saved. Please retry.',
    'Someone you blocked is confirmed for this event. Their identity is not shown.',
    'The server found that someone you blocked is confirmed for this event. Their identity is not shown.',
    'I understand and want to continue with registration.',
    'The warning could not be checked. You may continue, but the server will check before accepting registration.',
    'We could not refresh the warning. Confirm to proceed; the server will check again before admission.',
    'Retry block warning check',
  ]) {
    assert.ok(messages.includes(`'${key}':`) || messages.includes(`"${key}":`), `Missing persona translation: ${key}`);
  }
});
