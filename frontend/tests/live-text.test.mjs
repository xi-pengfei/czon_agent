import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
test('pausing shows incoming text; resuming never replays old text or splits emoji',()=>{
 const slots=[],effects=[];let cursor=0,frame,clock=0;
 const react={useRef:v=>{const i=cursor++;return slots[i]??={current:v};},useState:v=>{const i=cursor++;if(!(i in slots))slots[i]=v;return[slots[i],v=>{slots[i]=v;}];},useEffect:(fn,deps)=>{const i=cursor++;const old=slots[i];if(!old||deps.some((v,j)=>v!==old.deps[j])){old?.cleanup?.();slots[i]={deps};effects.push(()=>{slots[i].cleanup=fn();});}}};
 const exports={};
 vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/hooks/useLiveText.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,require:()=>react,matchMedia:()=>({matches:false}),requestAnimationFrame:f=>{frame=f;return 1;},cancelAnimationFrame:()=>{frame=null;}});
 const render=(text,motion)=>{cursor=0;const value=exports.useLiveText(text,true,motion);effects.splice(0).forEach(f=>f());return value;};
 const step=()=>{const f=frame;frame=null;f?.(clock+=40);};
 render('开始😀处理',true);step();render('开始😀处理',false);
 assert.equal(render('开始😀处理。新的段落。',false),'开始😀处理。新的段落。');
 render('开始😀处理。新的段落。',true);step();
 assert.equal(render('开始😀处理。新的段落。',true),'开始😀处理。新的段落。');
});
