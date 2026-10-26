import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import test from 'node:test';
import ts from '../Code/Frontend/node_modules/typescript/lib/typescript.js';

const frontend = new URL('../Code/Frontend/', import.meta.url);
const require = createRequire(new URL('../Code/Frontend/package.json', import.meta.url));
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const read = path => readFile(new URL(path, frontend), 'utf8');

function dataUrl(source) {
  return 'data:text/javascript;base64,' + Buffer.from(source, 'utf8').toString('base64');
}

function transpile(source, jsx = ts.JsxEmit.ReactJSX) {
  const result = ts.transpileModule(source, {
    compilerOptions: {
      jsx,
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
    reportDiagnostics: true,
  });
  const errors = (result.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error);
  assert.deepEqual(errors, [], 'Sprint 26 media TypeScript must parse and transpile');
  return result.outputText;
}

const apiModuleUrl = dataUrl(`
  export class ApiError extends Error {
    constructor(status, code, message = 'test error') {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.code = code;
    }
  }
  export async function api() { throw new Error('Static render must not call the API.'); }
`);
const reactModuleUrl = dataUrl(`
  import React from ${JSON.stringify(pathToFileURL(require.resolve('react')).href)};
  export const useId = React.useId;
  export const useRef = React.useRef;
  export const useState = React.useState;
`);
const jsxRuntimeModuleUrl = dataUrl(`
  import runtime from ${JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href)};
  export const jsx = runtime.jsx;
  export const jsxs = runtime.jsxs;
  export const Fragment = runtime.Fragment;
`);
const translateModuleUrl = dataUrl('export function useT() { return message => message; }');
const stylesModuleUrl = dataUrl('export default { root:"root", label:"label", input:"input", hint:"hint", actions:"actions", status:"status", error:"error" };');

async function importUploader() {
  const source = transpile(await read('features/media/MediaUploader.tsx'))
    .replaceAll('from "react"', `from ${JSON.stringify(reactModuleUrl)}`)
    .replaceAll('from "react/jsx-runtime"', `from ${JSON.stringify(jsxRuntimeModuleUrl)}`)
    .replaceAll('from "@/lib/api"', `from ${JSON.stringify(apiModuleUrl)}`)
    .replaceAll('from "@/lib/i18n"', `from ${JSON.stringify(translateModuleUrl)}`)
    .replaceAll('from "./MediaUploader.module.css"', `from ${JSON.stringify(stylesModuleUrl)}`);
  return import(dataUrl(source));
}

async function importErrorMessageHelper(source) {
  const helper = source.match(/function apiErrorMessage\([\s\S]*?\n}\n\nexport function MediaUploader/);
  assert.ok(helper, 'MediaUploader must retain its bounded API error mapper');
  const helperSource = `import { ApiError } from "@/lib/api";\n${helper[0]
    .replace(/\n\nexport function MediaUploader$/, '')
    .replace('function apiErrorMessage', 'export function apiErrorMessage')}`;
  const output = transpile(helperSource, ts.JsxEmit.Preserve)
    .replaceAll('from "@/lib/api"', `from ${JSON.stringify(apiModuleUrl)}`);
  return import(dataUrl(output));
}

test('media quota and storage outages map to actionable localized message keys', async () => {
  const source = await read('features/media/MediaUploader.tsx');
  const {apiErrorMessage} = await importErrorMessageHelper(source);
  const {ApiError} = await import(apiModuleUrl);
  const quota = 'Image storage is full. Ask an administrator to review stored images and free space. Your current image and selected file were not changed.';
  const unavailable = 'Image storage is temporarily unavailable. Your current image and selected file were not changed; try again later.';

  assert.equal(apiErrorMessage(new ApiError(413, 'media_quota_exceeded'), 'upload', false, key => key), quota);
  assert.equal(apiErrorMessage(new ApiError(503, 'media_storage_unavailable'), 'upload', false, key => key), unavailable);
  assert.equal(apiErrorMessage(new ApiError(503, 'media_storage_unavailable'), 'remove', false, key => key), unavailable);
  assert.equal(apiErrorMessage(new ApiError(413, 'request_too_large'), 'upload', false, key => key), 'The image is larger than 5 MiB.');
});

test('quota and outage failures leave the image, selected file, and file input unchanged', async () => {
  const source = await read('features/media/MediaUploader.tsx');
  for (const name of ['uploadImage', 'removeImage']) {
    const start = source.indexOf(`async function ${name}()`);
    const end = source.indexOf(name === 'uploadImage' ? 'async function removeImage()' : 'return (', start);
    assert.notEqual(start, -1);
    assert.notEqual(end, -1);
    const operation = source.slice(start, end);
    const catchBody = operation.match(/} catch \(error\) \{([\s\S]*?)\n    } finally \{/);
    assert.ok(catchBody, `${name} must handle rejected mutations`);
    assert.match(catchBody[1], /setErrorKey\(apiErrorMessage/);
    assert.doesNotMatch(catchBody[1], /setSelectedFile\(null\)|inputRef\.current\.value\s*=|onChanged\(/);
  }
  const upload = source.slice(source.indexOf('async function uploadImage()'), source.indexOf('async function removeImage()'));
  assert.match(upload, /onChanged\(result\);[\s\S]*setSelectedFile\(null\);[\s\S]*inputRef\.current\.value = ""/);
});

test('MediaUploader static render keeps the existing image controls without calling a backend fixture', async () => {
  const {MediaUploader} = await importUploader();
  const html = renderToStaticMarkup(React.createElement(MediaUploader, {
    endpoint: '/organizations/test/media',
    token: 'test-only-token',
    currentUrl: '/api/v1/media/550e8400-e29b-41d4-a716-446655440000',
    onChanged() {},
  }));

  assert.match(html, /Replace image/);
  assert.match(html, /Remove image/);
  assert.match(html, /Choose image file/);
  assert.doesNotMatch(html, /role="alert"/);
  assert.doesNotMatch(html, /media_quota_exceeded|media_storage_unavailable/);
});

test('quota and outage copy is available in English and Filipino through the shared translator', async () => {
  const source = transpile(await read('lib/auth-messages.ts'), ts.JsxEmit.Preserve);
  const {authMessages} = await import(dataUrl(source));
  const i18n = await read('lib/i18n.ts');
  const expected = [
    ['Image storage is full. Ask an administrator to review stored images and free space. Your current image and selected file were not changed.', 'Puno na ang storage ng mga larawan. Hilingin sa administrator na suriin ang mga nakaimbak na larawan at magbakante ng espasyo. Hindi binago ang kasalukuyang larawan at napiling file.'],
    ['Image storage is temporarily unavailable. Your current image and selected file were not changed; try again later.', 'Pansamantalang hindi available ang storage ng mga larawan. Hindi binago ang kasalukuyang larawan at napiling file; subukan muli mamaya.'],
  ];
  for (const [english, filipino] of expected) assert.equal(authMessages[english], filipino);
  assert.match(i18n, /\.\.\.authMessages/);
});
