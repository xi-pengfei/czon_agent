import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
const require = createRequire(import.meta.url);
export const storage = new Map();
export const documentStub = { documentElement: { lang: '' } };
const exports = {};
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/i18n.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports, document: documentStub, localStorage: { getItem: key => storage.get(key), setItem: (key,value) => storage.set(key,value) }, require: name => name.startsWith('./locales/') ? JSON.parse(readFileSync(new URL('../src/' + name, import.meta.url), 'utf8')) : require(name) });
export const translations = exports;
