import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {runInNewContext} from 'node:vm';
import test from 'node:test';
import {ApiError} from '../Code/Frontend/lib/api.ts';
import {isRetryableApiError, recoveryMessage} from '../Code/Frontend/lib/recovery.ts';
import {messages} from '../Code/Frontend/lib/messages.ts';

const frontend = new URL('../Code/Frontend/', import.meta.url);
const require = createRequire(new URL('../Code/Frontend/package.json', import.meta.url));
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const ts = require('typescript');
const read = path => readFile(new URL(path, frontend), 'utf8');

function dataUrl(source) {
  return 'data:text/javascript;base64,' + Buffer.from(source, 'utf8').toString('base64');
}

function translate(language) {
  return (english, values = {}) => (messages[english]?.[language] ?? english)
    .replace(/\{([A-Za-z0-9_]+)\}/g, (match, name) =>
      Object.hasOwn(values, name) ? String(values[name]) : match);
}

function transpile(source) {
  const result = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
    reportDiagnostics: true,
  });
  const errors = (result.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error);
  assert.deepEqual(errors, [], 'recovery feedback TypeScript must parse and transpile');
  return result.outputText;
}

const recoveryModuleUrl = dataUrl(transpile(await read('lib/recovery.ts')));
const reactUrl = dataUrl(`
  import React from ${JSON.stringify(pathToFileURL(require.resolve('react')).href)};
  export const useEffect = React.useEffect;
  export const useRef = React.useRef;
`);
const jsxRuntimeUrl = dataUrl(`
  import runtime from ${JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href)};
  export const jsx = runtime.jsx;
  export const jsxs = runtime.jsxs;
  export const Fragment = runtime.Fragment;
`);
const i18nUrl = dataUrl(`export function useT() {
  return (message, values = {}) => message.replace(/\\{([A-Za-z0-9_]+)\\}/g, (match, name) =>
    Object.hasOwn(values, name) ? String(values[name]) : match);
}`);
const preferencesUrl = dataUrl('export function usePreferences() { return {preferences: {language: "en"}}; }');
let feedbackSource = transpile(await read('components/feedback.tsx'));
for (const [specifier, url] of [
  ['react/jsx-runtime', jsxRuntimeUrl],
  ['react', reactUrl],
  ['@/lib/i18n', i18nUrl],
  ['@/lib/preferences', preferencesUrl],
  ['@/lib/recovery', recoveryModuleUrl],
]) {
  feedbackSource = feedbackSource.replace(new RegExp(`from (["'])${specifier}\\1`, 'g'), `from ${JSON.stringify(url)}`);
}
const {Feedback} = await import(dataUrl(feedbackSource));

test('recovery copy exposes retry timing safely in English and Filipino', () => {
  assert.equal(recoveryMessage(new ApiError(429, 'rate_limited', 'private response', 1), translate('en')),
    'Too many requests. Please wait one second before trying again.');
  assert.equal(recoveryMessage(new ApiError(429, 'rate_limited', 'private response', 47), translate('fil')),
    'Napakaraming kahilingan. Maghintay nang 47 segundo bago sumubok muli.');
  assert.equal(recoveryMessage(new ApiError(429, 'rate_limited', 'private response'), translate('en')),
    'Too many requests. Please wait before trying again.');
  assert.equal(recoveryMessage(new ApiError(429, 'rate_limited', 'private response', 0), translate('en')),
    'Too many requests. You can try again now.');
  assert.equal(recoveryMessage(new ApiError(503, 'temporarily_unavailable', 'private response'), translate('en')),
    'The service is starting or temporarily unavailable. Please wait a moment, then retry.');
});

test('shared feedback renders 429 and cold-start 503 as focused, announced recovery alerts', () => {
  const limited = renderToStaticMarkup(React.createElement(Feedback, {
    error: new ApiError(429, 'rate_limited', 'private response', 47),
    onRetry() {},
    focusError: true,
  }));
  assert.match(limited, /role="alert" aria-live="assertive" aria-atomic="true"/);
  assert.match(limited, /tabindex="-1"/);
  assert.match(limited, /Too many requests\. Please wait 47 seconds before trying again\./);
  assert.match(limited, />Retry</);
  assert.doesNotMatch(limited, /private response/);

  const unavailable = renderToStaticMarkup(React.createElement(Feedback, {
    error: new ApiError(503, 'temporarily_unavailable', 'private response'),
    onRetry() {},
    focusError: true,
  }));
  assert.match(unavailable, /The service is starting or temporarily unavailable/);
  assert.match(unavailable, /role="alert" aria-live="assertive"/);
  assert.doesNotMatch(unavailable, /private response/);
});

test('registration retries 429 with the saved request payload and idempotency key', async () => {
  const source = await read('features/registrations/RegistrationAction.tsx');
  const recovery = await read('lib/recovery.ts');
  assert.match(source, /isRetryableApiError\(error\)/);
  assert.match(recovery, /error\.status === 429/);
  assert.match(source, /const savedAttempt = previousAttempt[\s\S]*?: \{ eventId: event\.id, key: window\.crypto\.randomUUID\(\), payload \}/);
  assert.match(source, /body: savedAttempt\.payload/);
  assert.match(source, /idempotencyKey: savedAttempt\.key/);
  assert.match(source, /inlineError\.current\?\.focus\(\)/);
  assert.match(source, /outsideError\.current\?\.focus\(\)/);
  assert.match(source, /role="alert" aria-live="assertive" aria-atomic="true" tabIndex=\{-1\}/);
  assert.match(source, /if \(registrations\.loading \|\| registrations\.error\)/);
  assert.match(source, /if \(!registrations\.error\) \{[\s\S]*?trigger\.current\?\.focus\(\)/);
});

test('event-detail retry moves focus to the loaded heading and waitlist outcomes stay announced', async () => {
  const detail = await read('features/events/EventDetail.tsx');
  const registration = await read('features/registrations/RegistrationAction.tsx');
  const myEvents = await read('features/registrations/MyEvents.tsx');
  assert.match(detail, /<Feedback[\s\S]*onRetry=\{retryEventDetails\} focusError/);
  assert.match(detail, /<h1 ref=\{heading\} tabIndex=\{-1\}>/);
  assert.match(detail, /if \(eventResource\.data\) heading\.current\?\.focus\(\)/);
  assert.match(detail, /role="status" aria-live="polite" aria-atomic="true"/);
  assert.match(registration, /role="status" aria-live="polite" tabIndex=\{-1\} ref=\{outcome\}/);
  assert.match(registration, /if \(submittedResult\) outcome\.current\?\.focus\(\)/);
  assert.match(registration, /result\.status === 'waitlisted'/);
  assert.match(myEvents, /<Feedback loading=\{loading\} error=\{error\} onRetry=\{retryRegistrations\} focusError>/);
  assert.match(myEvents, /if \(!error\) registrationPanel\.current\?\.focus\(\)/);
  const feedback = await read('components/feedback.tsx');
  assert.match(feedback, /if \(error && focusError && retrying\.current\)/);
  assert.match(feedback, /if \(loading && retrying\.current && focusError\)/);
});

test('429, 503, and waitlist recovery messages have Filipino translations', () => {
  for (const english of [
    'Too many requests. Please wait before trying again.',
    'Too many requests. Please wait one second before trying again.',
    'Too many requests. Please wait {seconds} seconds before trying again.',
    'Too many requests. You can try again now.',
    'The service is starting or temporarily unavailable. Please wait a moment, then retry.',
  ]) {
    assert.ok(messages[english]?.fil, `missing Filipino translation: ${english}`);
    assert.notEqual(messages[english].fil, english);
  }
  for (const status of [0, 429, 500, 503]) {
    assert.equal(isRetryableApiError({status}), true);
  }
  assert.equal(isRetryableApiError({status: 400}), false);
});

test('changed recovery callers parse as TypeScript and TSX', async () => {
  for (const path of [
    'components/feedback.tsx',
    'features/events/EventDetail.tsx',
    'features/registrations/RegistrationAction.tsx',
    'features/registrations/MyEvents.tsx',
    'lib/recovery.ts',
    'lib/messages.ts',
  ]) {
    transpile(await read(path));
  }
});

test('My Events mutation success focuses a named status that survives refresh without focus steals', async () => {
  const output = ts.transpileModule(await read('features/registrations/MyEvents.tsx'), {
    compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
  }).outputText;
  function* elements(node) {
    if (Array.isArray(node)) {
      for (const child of node) yield* elements(child);
    } else if (node?.props) {
      yield node;
      yield* elements(node.props.children);
    }
  }

  for (const action of ['withdraw', 'accept', 'decline']) {
    const registration = {
      id: 'qa29-registration', event_id: 'qa29-event', event_title: 'QA29 event', organization_name: 'QA29 club',
      status: action === 'withdraw' ? 'confirmed' : 'reconfirmation_required', is_past: false,
      starts_at: new Date(Date.now() + 3_600_000).toISOString(),
      ends_at: new Date(Date.now() + 7_200_000).toISOString(),
      reconfirm_revision: 1, reconfirm_deadline: new Date(Date.now() + 1_800_000).toISOString(),
    };
    const resource = {data: [registration], loading: false, error: null, reload() {
      resource.data = null;
      resource.loading = true;
    }};
    const slots = [];
    const focused = [];
    let cursor = 0;
    let effects = [];
    const hooks = {
      useState(initial) {
        const index = cursor++;
        if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
        return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
      },
      useRef(initial) {
        const index = cursor++;
        return slots[index] ??= {current: initial};
      },
      useEffect(callback, dependencies) {
        const index = cursor++;
        const previous = slots[index];
        if (!previous || dependencies.some((value, position) => !Object.is(value, previous[position]))) effects.push(callback);
        slots[index] = dependencies;
      },
    };
    const imports = {
      react: hooks,
      'react/jsx-runtime': require('react/jsx-runtime'),
      '@/lib/api': {ApiError, api: async () => ({})},
      '@/lib/i18n': {useT: () => translate('en')},
      '@/lib/session': {useSession: () => ({actor: {id: 'qa29-account'}, token: 'qa29-token', authLoading: false})},
      '@/lib/preferences': {usePreferences: () => ({preferences: {language: 'en'}})},
      '@/lib/use-api-resource': {useApiResource: () => resource},
      'next/link': {default: 'a'},
    };
    const context = {
      exports: {}, AbortController,
      window: {setTimeout: () => 1, setInterval: () => 1, clearTimeout() {}, clearInterval() {}},
      require: specifier => imports[specifier] ?? {
        default: {}, Feedback: 'Feedback', EventCalendar: 'EventCalendar', SavedEvents: 'SavedEvents', FeaturedBadge: 'FeaturedBadge',
        intervalsOverlap: () => false,
      },
    };
    runInNewContext(output + '\nexports.MyEventsContent = MyEventsContent;', context);
    function render() {
      cursor = 0;
      effects = [];
      const nodes = [...elements(context.exports.MyEventsContent({initialTab: action === 'withdraw' ? 'confirmed' : 'pending'}))];
      for (const node of nodes) {
        if (node.type === 'p' && node.props.role === 'status' && node.props.ref) {
          node.props.ref.current ??= {focus: () => focused.push(node.props['aria-label'])};
        }
      }
      for (const effect of effects) effect();
      return nodes;
    }

    const initial = render();
    assert.deepEqual(focused, [], `${action}: initial rendering must not move focus`);
    const card = initial.find(node => node.type?.name === 'RegistrationCard');
    assert.ok(card, `${action}: the registration action must be reachable`);
    if (action === 'withdraw') card.props.onWithdraw(registration);
    else card.props.onReconfirm(registration, action === 'accept');
    await new Promise(setImmediate);

    const expected = action === 'withdraw' ? 'Registration withdrawn for QA29 event.'
      : action === 'accept' ? 'Your seat for QA29 event is confirmed.' : 'You declined your seat for QA29 event.';
    const success = render().find(node => node.props['aria-label'] === expected);
    assert.ok(success, `${action}: success must remain present while registration cards reload`);
    assert.equal(success.props.role, 'status');
    assert.equal(success.props.tabIndex, 0);
    assert.equal(success.props['aria-live'], 'polite');
    assert.equal(success.props['aria-atomic'], 'true');
    assert.equal(success.props.children, expected);
    assert.deepEqual(focused, [expected], `${action}: successful mutation must focus its status once`);

    resource.loading = false;
    resource.data = [];
    assert.ok(render().some(node => node.props['aria-label'] === expected));
    resource.data = [registration];
    render();
    assert.deepEqual(focused, [expected], `${action}: refresh and polling must not refocus the success status`);
  }
});
