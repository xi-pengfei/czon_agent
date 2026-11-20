const {test} = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
function load(name) {
  const code = ts.transpileModule(fs.readFileSync(`${__dirname}/../src/${name}.ts`, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
  const exports = {}; vm.runInNewContext(code, {exports, URL, Error}); return exports;
}
const {serverOrigin, apiUrl, sseParser} = load('protocol');
const {reduceRun} = load('runs');
test('LAN builds permit login and session restore even in Release mode', async () => {
  const code = ts.transpileModule(fs.readFileSync(`${__dirname}/../src/client.ts`, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
  for (const enabled of [true, false]) {
    const exports = {};
    let requests = 0;
    const credentials = {origin: 'http://192.168.0.35:8000', token: 'test-token', identity: {csrf_token: 'test-csrf'}};
    vm.runInNewContext(code, {exports, __DEV__: false, URL, Error, AbortSignal, require(name) {
      if (name === 'expo-constants') return {__esModule: true, default: {expoConfig: {extra: {allowLocalHttp: enabled}}}};
      if (name === './protocol') return {serverOrigin, apiUrl};
      if (name === 'expo-secure-store') return {getItemAsync: async () => JSON.stringify(credentials), deleteItemAsync: async () => {}};
      if (name === 'expo/fetch') return {fetch: async () => {requests++; return {ok: true, json: async () => ({session_token: 'test-token', csrf_token: 'test-csrf'})};}};
      throw new Error(`Unexpected module: ${name}`);
    }});
    if (enabled) {
      assert.equal((await exports.login(credentials.origin, 'test', 'test')).origin, credentials.origin);
      assert.equal((await exports.restoreCredentials()).origin, credentials.origin);
      assert.equal(requests, 1);
    } else {
      await assert.rejects(exports.login(credentials.origin, 'test', 'test'));
      assert.equal(await exports.restoreCredentials(), null);
      assert.equal(requests, 0);
    }
  }
});
test('credentials are restricted to one validated server origin', () => {
  assert.equal(serverOrigin('https://agent.example.com/'), 'https://agent.example.com');
  assert.equal(serverOrigin('http://192.168.0.35:8000', true), 'http://192.168.0.35:8000');
  for (const input of ['http://example.com', 'https://user:secret@example.com', 'https://example.com/path', 'https://example.com?token=x', 'http://192.168.0.35:8000']) assert.throws(() => serverOrigin(input));
  for (const path of ['https://evil.test/api/upload', '//evil.test/api/upload', '/api/../../outside', '/api/\\evil.test']) assert.throws(() => apiUrl('https://agent.example.com', path));
});
test('SSE handles chunk boundaries, comments, CRLF and multiline payloads', () => {
  const events = []; const feed = sseParser((event, data) => events.push([event, data]));
  for (const chunk of [':heartbeat\r', '\n\r\neve', 'nt: run_event\r\ndata: 第一行\r\n', 'data: 第二行\r\n\r', '\nevent: keepalive\ndata: {}\n\n']) feed(chunk);
  assert.deepEqual(events, [['run_event', '第一行\n第二行'], ['keepalive', '{}']]);
});
test('streamed reply and final authoritative reply converge', () => {
  let run = {id:'x',reply:'',steps:[],status:'queued'};
  for (const text of ['你好', '，世界']) run = reduceRun(run, {event:'assistant_delta',data:{text}});
  assert.equal(run.reply, '你好，世界');
  run = reduceRun(run, {event:'agent_done',data:{reply:'最终结果'}});
  assert.equal(run.reply, '最终结果'); assert.equal(run.status,'completed');
});
test('confirmation and stop events retain review data and terminal state', () => {
  let run = {id:'x',reply:'',steps:[],status:'running'};
  run = reduceRun(run,{event:'confirmation_required',data:{id:'c',name:'write',args:{bill:1},result:{meta:{confirmation:{id:'confirm'}}}}});
  assert.equal(run.steps[0].result.meta.confirmation.id, 'confirm');
  run = reduceRun(run,{event:'agent_stopped',data:{}}); assert.equal(run.status,'stopped');
});
test('patched Markdown parser preserves tables, emphasis and safe links', () => {
  const MarkdownIt = require('markdown-it');
  const md = new MarkdownIt({html: false, typographer: true});
  const tokens = md.parse('## 经营数据\n\n**销售额**\n\n| 城市 | 金额 |\n| --- | --- |\n| 北京 | 7700 |\n\n1. 第一项\n\n[unsafe](javascript:alert(1))\n<script>alert(1)</script>', {});
  assert.ok(tokens.some(t => t.type === 'heading_open'));
  assert.ok(tokens.some(t => t.type === 'table_open'));
  assert.ok(tokens.some(t => t.type === 'ordered_list_open'));
  assert.ok(tokens.some(t => t.children?.some(c => c.type === 'strong_open')));
  assert.ok(!tokens.some(t => t.type === 'html_block'));
  assert.ok(!tokens.some(t => t.children?.some(c => c.type === 'link_open' && /javascript/.test(String(c.attrs)))));
});
