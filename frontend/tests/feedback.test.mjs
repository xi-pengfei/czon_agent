import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url);
function load(path){const exports={};vm.runInNewContext(ts.transpileModule(readFileSync(new URL(path,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,{exports,require});return exports;}
const {ToolTimeline}=load('../src/components/ToolTimeline.tsx');
const render=props=>renderToStaticMarkup(React.createElement(ToolTimeline,{onConfirm:()=>{},...props}));
test('running work has one public phase and no technical transcript',()=>{
 const html=render({steps:[{name:'bash',args:{command:'sensitive-command'}}],runElapsedSeconds:22});
 assert.ok(html.includes('正在处理业务数据'));
 assert.ok(!html.includes("技术记录"));
 assert.ok(!html.includes("sensitive-command"));
 assert.equal((html.match(/role="status"/g)||[]).length,1);
});
test('confirmation stays open and exposes review and confirm action',()=>{
 const html=render({steps:[{name:'bash',args:{operation:'needs-review'},result:{error:{type:'ConfirmationRequired'},meta:{confirmation:{id:'confirmation-a'}}}}]});
 assert.ok(html.includes("核对操作内容"));
 assert.ok(html.includes("这项操作需要你确认"));
 assert.ok(html.includes('确认执行'));assert.ok(html.includes('needs-review'));
});
test('stopped task with missing tool result never shows a still-running step',()=>{
 const html=render({steps:[{name:'bash'}],completed:true,outcome:'stopped'});
 assert.equal(html, "");
 assert.ok(!html.includes('运行中'));
});
const {streamFade}=load('../src/components/streamFade.ts');
test('stream fade keeps Markdown structure and code intact',()=>{
 const tree={type:'root',children:[{type:'element',tagName:'strong',children:[{type:'text',value:'重点😀内容'}]},{type:'element',tagName:'code',children:[{type:'text',value:'literal_code'}]}]};
 streamFade()(tree);
 assert.equal(tree.children[0].tagName,'strong');
 assert.equal(tree.children[0].children.map(n=>n.children[0].value).join(''),'重点😀内容');
 assert.equal(tree.children[1].children[0].type,'text');
 assert.ok(tree.children[0].children.every(n=>n.properties.className[0]==='stream-fragment'));
});
