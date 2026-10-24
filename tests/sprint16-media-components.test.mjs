import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import {mediaApiPath} from '../Code/Frontend/features/media/media-url.ts';

const frontend = new URL('../Code/Frontend/', import.meta.url);
const read = path => readFile(new URL(path, frontend), 'utf8');

test('media URLs accept only relative API media paths with one UUID and no query data', () => {
  const id = '550e8400-e29b-41d4-a716-446655440000';
  assert.equal(mediaApiPath(`/api/v1/media/${id}`), `/media/${id}`);
  for (const value of [
    `https://example.test/api/v1/media/${id}`,
    `//example.test/api/v1/media/${id}`,
    `/api/v1/media/${id}?token=secret`,
    `/api/v1/media/${id}#fragment`,
    `/api/v1/media/../${id}`,
    `/media/${id}`,
  ]) assert.equal(mediaApiPath(value), null, value);
});

test('protected images fetch blobs with an abort signal and revoke their object URL', async () => {
  const source = await read('features/media/MediaImage.tsx');
  assert.match(source, /api<Blob>\(path,\s*\{\s*token,\s*responseType:\s*"blob",\s*signal:\s*controller\.signal\s*\}\)/s);
  assert.match(source, /controller\.abort\(\)/);
  assert.match(source, /URL\.createObjectURL\(blob\)/);
  assert.match(source, /URL\.revokeObjectURL\(/);
  assert.match(source, /image\.token === token/);
  assert.match(source, /const path = mediaApiPath\(mediaUrl\);[\s\S]*if \(!path\) return;/);
  assert.doesNotMatch(source, /setImage\(null\)|if \(!path\) \{\s*setImage\(/);
  assert.doesNotMatch(source, /[?&]token=|\$\{token\}/);
});

test('uploader sends the selected image as a raw blob and exposes localized form feedback', async () => {
  const source = await read('features/media/MediaUploader.tsx');
  const messages = await read('features/media/messages.ts');
  assert.match(source, /method:\s*"POST"[\s\S]*body:\s*selectedFile/);
  assert.match(source, /method:\s*"DELETE"/);
  assert.match(source, /ifMatch/);
  assert.match(source, /accept="image\/jpeg,image\/png,image\/webp"/);
  assert.match(source, /role="status"/);
  assert.match(source, /role="alert"/);
  assert.match(source, /aria-describedby=/);
  assert.doesNotMatch(source, /FormData/);
  assert.match(messages, /export const mediaMessages: Record<string, string>/);
  assert.match(messages, /"Club logo"/);
  assert.match(messages, /"Choose image file"/);
  assert.match(messages, /"Remove image"/);
});

test('uploader reports mutation lifetime and tells a draft editor to reload after version conflicts', async () => {
  const uploader = await read('features/media/MediaUploader.tsx');
  const editor = await read('features/events/DraftEditor.tsx');
  assert.match(uploader, /onBusyChange\?: \(busy: boolean\) => void/);
  assert.match(uploader, /onBusyChange\?\.\(true\);[\s\S]*finally \{[\s\S]*onBusyChange\?\.\(false\);/);
  assert.match(uploader, /error\.status === 409 \|\| error\.status === 428\)\) onConflict\?\.\(\)/);
  assert.match(editor, /const mediaBusyRef = useRef\(false\)/);
  assert.match(editor, /mediaBusyRef\.current = busy;[\s\S]*setMediaBusy\(busy\)/);
  assert.match(editor, /publishing \|\| mediaBusyRef\.current/);
  assert.match(editor, /function updateField<K extends keyof DraftForm>\(field: K, value: DraftForm\[K\]\) \{\s*updateForm\(\{\s*\.\.\.\(formRef\.current \?\? form\), \[field\]: value\s*\}\);/);
  assert.match(editor, /accountSwitchAcceptedRef\.current \|\| mediaBusyRef\.current/);
  assert.match(editor, /mediaBusyRef\.current \|\| mutationInFlightRef\.current/);
  assert.match(editor, /mediaBusyRef\.current \|\|[\s\S]*publishIssues\(latestForm\)/);
  assert.match(editor, /mediaStartRevisionRef\.current = busy \? editRevisionRef\.current : null/);
  assert.match(editor, /!isDirty &&[\s\S]*!mediaBusy &&[\s\S]*!saving/);
  assert.match(editor, /disabled=\{publishing \|\| reloading \|\| mediaBusy\}/);
  assert.match(editor, /disabled=\{!canPublish \|\| mediaBusy\}/);
  assert.match(editor, /onBusyChange=\{onBannerBusyChange\}[\s\S]*onConflict=\{onBannerConflict\}/);
});

test('draft banner controls require a saved version and adopt mutation versions without replacing the form', async () => {
  const source = await read('features/events/DraftEditor.tsx');
  const disabledBlock = source.match(/const mediaMutationDisabled = Boolean\(([\s\S]*?)\n  \);/)?.[1];
  assert.ok(disabledBlock);
  assert.match(disabledBlock, /!hasDraftVersion[\s\S]*mediaBusy[\s\S]*isDirty[\s\S]*publishing/);
  assert.doesNotMatch(disabledBlock, /\.current/);
  assert.match(source, /ifMatch=\{currentDraft\.draft_version \?\? undefined\}/);
  assert.match(source, /banner_url: result\.media_url/);
  assert.match(source, /draft_version: result\.draft_version/);
  assert.match(source, /formRef\.current = nextForm;[\s\S]*setFormState\(nextForm\)/);
});

test('event artwork prefers an uploaded banner and retains the existing theme fixtures as fallback', async () => {
  const source = await read('app/event-artwork.tsx');
  const editor = await read('features/events/DraftEditor.tsx');
  assert.ok(source.indexOf('if (event.banner_url)') < source.indexOf('if (key === "heritage"'));
  assert.match(source, /<MediaImage/);
  assert.match(source, /src="\/artwork\/heritage\.jpg"/);
  assert.match(source, /LOCAL FIXTURE ILLUSTRATION/);
  assert.match(editor, /event=\{currentDraft\}[\s\S]*?token=\{token\}/);
  assert.match(editor, /banner_url: currentDraft\.banner_url[\s\S]*?token=\{token\}/);
});
