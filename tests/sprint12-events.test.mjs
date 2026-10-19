import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';

const [feed, detail, draft, attendeeStyles, draftStyles] = await Promise.all([
  readFile(new URL('../Code/Frontend/features/events/DiscoverFeed.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/EventDetail.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/DraftEditor.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/attendee-events.module.css', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/features/events/draft-editor.module.css', import.meta.url), 'utf8'),
]);

test('For You uses the API order and composes sort with search and My Clubs', () => {
  assert.match(feed, /aria-label=\{t\("Sort by"\)\}/);
  assert.match(feed, /"for_you"[\s\S]*"upcoming"[\s\S]*"newest"/);
  assert.match(feed, /const defaultSort: EventSort = token \? "for_you" : "upcoming"/);
  assert.match(feed, /parameters\.set\("sort", sort\)/);
  assert.match(feed, /parameters\.set\("q", search\)/);
  assert.match(feed, /parameters\.set\("my_clubs", "true"\)/);
  assert.match(feed, /\{token && <option value="for_you">/);
  assert.doesNotMatch(feed, /\.sort\s*\(/);
  assert.match(feed, /href="\/settings"/);
  assert.match(feed, /Tags and area names match exactly, ignoring capitalization and extra spaces\./);
  assert.match(feed, /<details className=\{styles.rankingHint\}>/);
});

test('recommendation chips use only ordered controlled codes and labels', () => {
  for (const code of ['club', 'interests', 'area', 'availability']) {
    assert.ok(feed.includes('"' + code + '"'), 'missing controlled reason ' + code);
  }
  assert.match(feed, /function recommendationReasons\(/);
  assert.match(feed, /RECOMMENDATION_REASONS\.filter\(\(reason\) => matched\.has\(reason\)\)/);
  assert.match(feed, /token && sort === "for_you" \? recommendationReasons\(event\) : \[\]/);
  assert.match(feed, /t\(RECOMMENDATION_LABELS\[reason\]\)/);
  assert.doesNotMatch(feed, /t\(event\.(?:tags|coarse_area|recommendation_reasons)/);
  assert.match(attendeeStyles, /\.reasonChips\s*\{/);
  assert.match(attendeeStyles, /\.rankingHint\s*\{/);
});

test('public event metadata tolerates legacy responses and stays separate from personal reasons', () => {
  assert.match(detail, /function publicEventTags\(event: PublicEvent\): string\[\]/);
  assert.match(detail, /"tags" in event/);
  assert.match(detail, /Array\.isArray\(event\.tags\)/);
  assert.match(detail, /function publicEventArea\(event: PublicEvent\): string \| null/);
  assert.match(detail, /"coarse_area" in event/);
  assert.match(detail, /typeof event\.coarse_area !== "string"/);
  assert.match(detail, /t\("Broad area"\)/);
  assert.match(detail, /t\("Tags"\)/);
  assert.doesNotMatch(detail, /recommendation_reasons/);
});

test('draft metadata round-trips through form, autosave and both preview paths without becoming required', () => {
  assert.match(draft, /aria-label=\{t\("Tags \(optional\)"\)\}/);
  assert.match(draft, /aria-label=\{t\("Broad area \(optional\)"\)\}/);
  assert.match(draft, /tagsText: eventTags\(draft\)\.join\(", "\)/);
  assert.match(draft, /coarseArea: eventCoarseArea\(draft\)/);
  assert.match(draft, /tags: tagsFromText\(form\.tagsText\)/);
  assert.match(draft, /coarse_area: form\.coarseArea\.trim\(\) \|\| null/);
  assert.match(draft, /MAX_EVENT_TAGS = 16/);
  assert.match(draft, /MAX_EVENT_TAG_LENGTH = 64/);
  assert.match(draft, /MAX_COARSE_AREA_LENGTH = 80/);
  assert.match(draft, /tags=\{eventTags\(currentDraft\)\}/);
  assert.match(draft, /coarseArea=\{eventCoarseArea\(currentDraft\)\}/);
  assert.match(draft, /tags=\{tagsFromText\(form\.tagsText\)\}/);
  assert.match(draft, /coarseArea=\{form\.coarseArea\.trim\(\)\}/);
  assert.match(draft, /Use a broad place name, not an address\./);
  assert.match(draftStyles, /\.fieldHint\s*\{/);

  const publishValidation = draft.slice(draft.indexOf('function publishIssues'), draft.indexOf('function isDraftConflict'));
  assert.doesNotMatch(publishValidation, /tagsText|coarseArea/);
  assert.doesNotMatch([feed, detail, draft].join('\n'), /\bas\s+any\b/);
});
