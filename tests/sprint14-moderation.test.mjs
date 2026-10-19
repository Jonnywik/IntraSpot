import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';

const [queue, reportMessages, api] = await Promise.all([
  readFile(new URL('../Code/Frontend/features/moderation/AnnouncementReportQueue.tsx', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/lib/announcement-report-messages.ts', import.meta.url), 'utf8'),
  readFile(new URL('../Code/Frontend/lib/api.ts', import.meta.url), 'utf8'),
]);

test('announcement report review uses its dedicated generated contracts and version preconditions', () => {
  assert.match(queue, /import type \{ AnnouncementReportReceipt, AnnouncementReportReview \} from '@\/lib\/types'/);
  assert.match(queue, /export function AnnouncementReportQueue\(\{token\}: \{token: string\}\)/);
  assert.match(queue, /\/moderation\/announcement-reports/);
  assert.match(queue, /ifMatch: String\(selected\.post_version\)/);
  assert.match(queue, /error\.status === 409/);
  assert.match(queue, /queue\.reload\(\);\s*detail\.reload\(\);/);
  assert.match(api, /headers\['If-Match'\] = `"\$\{options\.ifMatch\}"`/);
});

test('evidence is rendered as escaped title and body text only while permitted', () => {
  assert.match(queue, /function parseEvidenceSnapshot\(evidence: string\)/);
  assert.match(queue, /typeof snapshot\.title !== 'string'/);
  assert.match(queue, /snapshot\.body !== null && typeof snapshot\.body !== 'string'/);
  assert.match(queue, /<dd>\{snapshot\.title\}<\/dd>/);
  assert.match(queue, /<dd>\{snapshot\.body \?\? ''\}<\/dd>/);
  assert.match(queue, /report\.status === 'open' && !deadlinePassed\(report, currentTime\) && report\.evidence !== null/);
  assert.match(queue, /const history = report\.decisions\.slice\(-8\)\.reverse\(\)/);
  assert.doesNotMatch(queue, /revision/i);
  assert.doesNotMatch(queue, /JSON\.stringify\(snapshot\)/);
});

test('selection and deadline refresh avoid render-created defaults and synchronous effect updates', () => {
  assert.match(queue, /const EMPTY_REPORTS: AnnouncementReportReview\[\] = \[\]/);
  assert.match(queue, /const reports = queue\.data \?\? EMPTY_REPORTS/);
  assert.match(queue, /const effectiveSelectedId = reports\.length[\s\S]*?reports\[0\]\.id/);
  assert.match(queue, /const selectedDeadline = selected\?\.deadline \?\? null/);
  assert.match(queue, /window\.setTimeout\([\s\S]*?\(\) => setCurrentTime\(Date\.now\(\)\)/);
  assert.match(queue, /\}, \[selectedDeadline\]\)/);
  assert.doesNotMatch(queue, /setSelectedId\(reports\[0\]\.id\)/);
  assert.doesNotMatch(queue, /if \(delay <= 0\)\s*\{\s*setCurrentTime/);
});

test('announcement safety system inbox messages have Filipino translations', () => {
  const backendMessages = [
    'Your announcement safety report was received.',
    'An announcement you authored is under platform safety review.',
    'An announcement safety report requires platform review.',
    'Your announcement safety report was resolved.',
    'A safety review of an announcement you authored was closed.',
    'An announcement safety review was completed.',
    'An announcement you authored was hidden after review.',
    'An announcement you authored was restored after review.',
    'An announcement you authored was removed after review.',
    'Your announcement safety report review window ended.',
    'A safety review involving an announcement you authored has ended.',
    'An announcement safety review window ended.',
  ];

  for (const message of backendMessages) {
    assert.ok(reportMessages.includes(`'${message}':`), `Missing translation for backend inbox message: ${message}`);
  }
});
