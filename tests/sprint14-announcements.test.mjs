import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';

const paths = {
  reader: '../Code/Frontend/features/announcements/AnnouncementReader.tsx',
  manager: '../Code/Frontend/features/announcements/AnnouncementManager.tsx',
  messages: '../Code/Frontend/features/announcements/messages.ts',
  dictionary: '../Code/Frontend/lib/announcement-messages.ts',
  memberPortal: '../Code/Frontend/features/memberships/MemberPortal.tsx',
  workspace: '../Code/Frontend/features/organizations/workspace-page.tsx',
  styles: '../Code/Frontend/features/announcements/announcements.module.css',
  api: '../Code/Frontend/lib/api.ts',
};

const sources = Object.fromEntries(await Promise.all(
  Object.entries(paths).map(async ([name, path]) => [name, await readFile(new URL(path, import.meta.url), 'utf8')]),
));
const ts = createRequire(new URL('../Code/Frontend/package.json', import.meta.url))('typescript');

function sourceFile(name, content) {
  return ts.createSourceFile(name, content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
}

function functionText(content, filename, name) {
  const parsed = sourceFile(filename, content);
  let declaration;
  function visit(node) {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) declaration = node;
    if (!declaration) ts.forEachChild(node, visit);
  }
  visit(parsed);
  assert.ok(declaration, `${name} exists in ${filename}`);
  return declaration.getText(parsed);
}

function dictionaryKeys() {
  const parsed = sourceFile('announcement-messages.ts', sources.dictionary);
  let object;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(parsed) === 'announcementMessages') {
      object = node.initializer;
      while (object && (ts.isAsExpression(object) || ts.isParenthesizedExpression(object))) object = object.expression;
    }
    ts.forEachChild(node, visit);
  }
  visit(parsed);
  assert.ok(object && ts.isObjectLiteralExpression(object), 'announcementMessages is an object dictionary');
  return new Set(object.properties.map(property => property.name?.text).filter(Boolean));
}

test('announcement source files parse as TypeScript and TSX', () => {
  for (const [name, content] of Object.entries(sources)) {
    if (!['reader', 'manager', 'messages', 'memberPortal', 'workspace'].includes(name)) continue;
    const result = ts.transpileModule(content, {
      fileName: `${name}.tsx`,
      reportDiagnostics: true,
      compilerOptions: {target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX},
    });
    assert.deepEqual(result.diagnostics?.filter(item => item.category === ts.DiagnosticCategory.Error) ?? [], [], `${name} has no syntax errors`);
  }
});

test('every literal passed to announcement text lookup has an owned dictionary entry', () => {
  const keys = dictionaryKeys();
  const missing = new Set();
  for (const name of ['reader', 'manager']) {
    const parsed = sourceFile(`${name}.tsx`, sources[name]);
    function visit(node) {
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'text') {
        const key = node.arguments[0];
        if (key && (ts.isStringLiteral(key) || ts.isNoSubstitutionTemplateLiteral(key)) && !keys.has(key.text)) missing.add(key.text);
      }
      ts.forEachChild(node, visit);
    }
    visit(parsed);
  }
  assert.deepEqual([...missing], []);
  for (const required of [
    'Your sign-in expired. Sign in again, then retry.',
    'This action is unavailable for this account.',
    'This announcement is no longer available.',
    'The current announcement could not be reloaded. Your text is preserved.',
    'The create request could not be confirmed. Your content and request key are preserved. Retry the same announcement.',
    'The reaction could not be updated. Your choice is preserved; retry the same reaction.',
    'A report may already be open. Check your report receipts before trying again.',
    'The request could not be completed. Check your connection and retry.',
    'Publish', 'Edit', 'Remove', 'Hide', 'Restore',
  ]) assert.ok(keys.has(required), `dictionary includes ${required}`);
});

test('announcement copy uses the shared translation hook without another localization engine', () => {
  assert.match(sources.messages, /import \{ useT \} from '@\/lib\/i18n'/);
  assert.match(sources.messages, /return useT\(\);/);
  assert.doesNotMatch(sources.messages, /usePreferences|announcementMessages|replace\(/);
});

test('reaction network failures have a complete translated key without dropped interpolation values', () => {
  const source = functionText(sources.messages, 'messages.ts', 'announcementApiMessage')
    .replace(/^export /, '');
  const compiled = ts.transpileModule(source, {
    compilerOptions: {target: ts.ScriptTarget.ES2022},
  }).outputText;
  const explain = new Function(`${compiled}; return announcementApiMessage;`)();
  const failure = explain(new Error('Connection unavailable'), 'Reaction update');
  assert.ok(dictionaryKeys().has(failure.key));
  assert.doesNotMatch(failure.key, /\{[A-Za-z]+\}/, 'Reader errors do not display an unresolved action placeholder');
  assert.equal(failure.values, undefined);
});

test('reader uses shared reaction kinds and aborts older pages across account or organization scope changes', () => {
  for (const kind of ['interested', 'excited', 'support', 'kudos', 'wow', 'relate']) {
    assert.match(sources.reader, new RegExp(`kind: '${kind}'`));
  }
  assert.match(sources.reader, /body: \{ reaction: desired \}/);
  assert.match(sources.reader, /const olderController = useRef<AbortController \| null>\(null\)/);
  assert.match(sources.reader, /useEffect\(\(\) => \(\) => olderController\.current\?\.abort\(\), \[orgId, token\]\)/);
  assert.match(sources.reader, /\{ token, signal: controller\.signal \}/);
  assert.match(sources.reader, /if \(controller\.signal\.aborted\) return;\s*setOlder\(/);
  assert.match(sources.reader, /body: \{ reaction: desired \}[\s\S]*?signal: controller\.signal/);
  assert.match(sources.reader, /useEffect\(\(\) => \(\) => reactionController\.current\?\.abort\(\), \[announcement\.id, token\]\)/);
  assert.match(sources.reader, /useApiResource<ReactionSummary>\(reactionPath, token\)/);
  assert.match(sources.reader, /if \(controller\.signal\.aborted\) return;\s*setSummaryOverride\(updated\)/);
  assert.doesNotMatch(sources.reader, /setSummary\(null\)/);
  assert.match(sources.memberPortal, /key=\{`\$\{version\}:\$\{token \?\? 'guest'\}`\}/);
  assert.match(sources.memberPortal, /key=\{`\$\{selectedOrganization\.id\}:\$\{token \?\? 'guest'\}`\}/);
});

test('reports use the announcement safety API and do not hide content automatically', () => {
  assert.match(sources.reader, /\/announcements\/\$\{encodeURIComponent\(announcementId\)\}\/reports/);
  assert.match(sources.reader, /body: \{ reason \}/);
  assert.match(sources.reader, /token \? '\/me\/announcement-reports' : null/);
  assert.match(sources.reader, /\{token && \(/);
  assert.match(sources.reader, /A report does not hide this announcement automatically\./);
  assert.doesNotMatch(sources.reader, /ContentSafetyControls/);
  const reportForm = sources.reader.slice(sources.reader.indexOf('function AnnouncementReportForm'));
  assert.match(reportForm, /setReason\(''\)/);
  assert.match(reportForm, /catch \(caught\)[\s\S]*?setError\(/);
  assert.match(reportForm, /text\(error\.key, error\.values\)/);
  assert.match(reportForm, /useEffect\(\(\) => \(\) => reportController\.current\?\.abort\(\), \[announcementId, token\]\)/);
});

test('manager preserves create keys and submitted edits after failures', () => {
  assert.match(sources.manager, /createAttempt\?\.client_key \?\? (?:window\.)?crypto\.randomUUID\(\)/);
  assert.match(sources.manager, /createUncertain && createAttempt[\s\S]*?createAttempt\.title/);
  const create = functionText(sources.manager, 'AnnouncementManager.tsx', 'create');
  const catchBlock = create.slice(create.indexOf('} catch (caught)'));
  assert.doesNotMatch(catchBlock, /setCreateAttempt\(null\)/);
  assert.match(create, /setCreateAttempt\(null\)/);
  assert.match(sources.manager, /disabled=\{saving \|\| createUncertain/);
  assert.match(sources.manager, /Retry same announcement/);
  const saveEdit = functionText(sources.manager, 'AnnouncementManager.tsx', 'saveEdit');
  assert.match(saveEdit, /method: 'PATCH'/);
  assert.match(saveEdit, /ifMatch: String\(target\.version\)/);
  assert.match(sources.manager, /method: 'DELETE'[\s\S]*?ifMatch: String\(post\.version\)/);
  assert.match(sources.api, /headers\['If-Match'\] = `"\$\{options\.ifMatch\}"`/);
  assert.match(saveEdit, /catch \(caught\)[\s\S]*?setError\(announcementApiMessage/);
});

test('conflict reload reads the manager collection, preserving hidden and removed records', () => {
  const reload = functionText(sources.manager, 'AnnouncementManager.tsx', 'reloadConflict');
  const finder = functionText(sources.manager, 'AnnouncementManager.tsx', 'findManagedAnnouncement');
  assert.match(reload, /findManagedAnnouncement\(target\.id, controller\.signal\)/);
  assert.doesNotMatch(reload, /`\/announcements\/\$\{/);
  assert.match(finder, /\/organizations\/\$\{encodeURIComponent\(organizationId\)\}\/announcements\/manage\?/);
  assert.match(sources.manager, /\/announcements\/\$\{encodeURIComponent\(postId\)\}\/history/);
  assert.match(reload, /Your text is preserved/);
  assert.match(sources.manager, /conflict\.latest\.state === 'removed'/);
});

test('manager loads older records with scoped abort, deduplication, retry, and refresh reset', () => {
  assert.match(sources.manager, /const MANAGE_PAGE_SIZE = 100/);
  const loadOlder = functionText(sources.manager, 'AnnouncementManager.tsx', 'loadOlderAnnouncements');
  assert.match(loadOlder, /announcements\/manage\?limit=\$\{MANAGE_PAGE_SIZE\}&offset=\$\{offset\}/);
  assert.match(loadOlder, /\{ token, signal: controller\.signal \}/);
  assert.match(loadOlder, /if \(controller\.signal\.aborted\) return/);
  assert.match(loadOlder, /new Set\(\[\.\.\.firstPage, \.\.\.current\]\.map\(\(post\) => post\.id\)\)/);
  assert.match(loadOlder, /page\.filter\(\(post\)/);
  assert.match(loadOlder, /setNextOlderOffset\(offset \+ page\.length\)/);
  assert.match(loadOlder, /setHasMoreOlder\(page\.length === MANAGE_PAGE_SIZE\)/);

  const reload = functionText(sources.manager, 'AnnouncementManager.tsx', 'reloadAnnouncements');
  assert.match(reload, /olderController\.current\?\.abort\(\)/);
  assert.match(reload, /setOlder\(\[\]\)[\s\S]*?setOlderError\(false\)[\s\S]*?setHasMoreOlder\(null\)[\s\S]*?setNextOlderOffset\(null\)/);
  assert.ok(reload.indexOf('setOlder([])') < reload.indexOf('announcements.reload()'));
  for (const name of ['create', 'saveEdit', 'remove', 'reloadConflict']) {
    assert.match(functionText(sources.manager, 'AnnouncementManager.tsx', name), /reloadAnnouncements\(\)/);
  }
  assert.match(sources.manager, /olderController\.current\?\.abort\(\)[\s\S]*?\[sessionVersion, token, organizationId\]/);
  assert.match(sources.manager, /text\('Load older announcements'\)/);
  assert.match(sources.manager, /text\('Retry loading older announcements'\)/);
  assert.ok(dictionaryKeys().has('Loading older announcements…'));
});

test('reader and owner workspace integration use explicit audiences and desktop-only management', () => {
  assert.match(sources.reader, /'Public' : 'Members only'/);
  assert.match(sources.reader, /text\('Edited'\)/);
  assert.match(sources.memberPortal, /selectedOrganization\?\.accreditation_status === 'approved'/);
  assert.match(sources.workspace, /key=\{`\$\{sessionVersion\}:\$\{token\}:\$\{workspace\.id\}`\}/);
  assert.match(sources.workspace, /sessionVersion=\{version\}/);
  assert.match(sources.workspace, /role=\{workspace\.role\}/);
  assert.match(sources.manager, /role === 'owner' \|\| role === 'admin'/);
  assert.match(sources.manager, /announcements\/manage\?limit=100&offset=0/);
  assert.match(sources.styles, /@media \(max-width: 767px\)[\s\S]*?\.desktopManager\s*\{\s*display: none/);
  assert.match(sources.styles, /var\(--paper\)|var\(--line\)|var\(--ink\)/);
});
