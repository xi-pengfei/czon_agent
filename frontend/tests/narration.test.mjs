import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const exports={};
let clock=Date.now();
class Clock extends Date { static now(){ return clock; } }
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/audio/narration.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports,AbortController,Date:Clock});
const {NarrationPipeline}=exports;
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const run=(changes={})=>({id:'run-a',status:'running',reply:'',steps:[],progress:'正在处理',...changes});
function harness(initial,skip=false){
 const scripts=[],prepared=[],played=[],captions=[],errors=[],ends=[];
 let current=initial;
 const pipeline=new NarrationPipeline(initial,skip,{
  script:async(id,request,signal)=>{
   scripts.push({id,request,signal});
   return {text:request.kind==='progress'?'收到，我先检查。':`这一段的重点是${current.reply.slice(-12)}`,offset:current.reply.length,anchor:current.reply.slice(-80),done:current.status==='completed',stage:'started',fallback:false};
  },
  prepare:async(text,signal)=>{
   prepared.push({text,signal});
   return {play:abort=>new Promise(resolve=>{played.push(text);ends.push(resolve);abort.addEventListener('abort',resolve,{once:true});})};
  },
  caption:text=>captions.push(text), error:message=>errors.push(message),
 });
 return {pipeline,scripts,prepared,played,captions,errors,ends,update:value=>{clock+=2000;current=value;pipeline.update(value);}};
}
test('prepare next audio during current playback; never read page text directly',async()=>{
 const h=harness(run()); h.update(run()); await flush();
 assert.equal(h.played.length,1);
 h.update(run({reply:'这是供页面显示的详细信息。'.repeat(12)})); await flush();
 assert.equal(h.prepared.length,2);assert.equal(h.played.length,1);
 assert.equal(h.scripts[1].request.kind,'answer');
 assert.ok(h.prepared[1].text.startsWith('这一段的重点'));
 h.ends[0]();await flush();assert.equal(h.played.length,2);
 h.pipeline.stop();await flush();assert.deepEqual(h.errors,[]);
});
test('mute aborts pending preparation and playback; prepared audio cannot leak into next run',async()=>{
 const h=harness(run());h.update(run());await flush();
 h.update(run({reply:'用户可见正文。'.repeat(30)}));await flush();
 h.pipeline.stop();await flush();h.pipeline.tick();await flush();
 assert.equal(h.played.length,1);assert.ok(h.scripts.every(call=>call.signal.aborted));
 assert.equal(h.captions.at(-1),'');
});
test('repeated snapshots do not repeat narration; opening history does not speak',async()=>{
 const initial=run({status:'completed',reply:'历史回答。'});
 const h=harness(initial,true);h.update(initial);await flush();
 assert.equal(h.scripts.length,0);h.pipeline.stop();
 const live=harness(run());live.update(run());await flush();
 for(let i=0;i<5;i++)live.update(run());await flush();
 assert.equal(live.scripts.length,1);live.pipeline.stop();
});
test('task failure stops speech immediately and never announces completion',async()=>{
 const h=harness(run());h.update(run());await flush();
 h.update(run({status:'failed',reply:'业务结果不确定。'}));await flush();
 assert.equal(h.played.length,1);assert.ok(h.prepared[0].signal.aborted);
 assert.equal(h.scripts.length,1);
});
test('only three interim summaries, then one final summary',async()=>{
 const h=harness(run());
 for(let i=1;i<=5;i++){
  h.update(run({reply:'正文内容。'.repeat(30*i)+`第${i}部分。`}));await flush();
  h.ends.at(-1)?.();await flush();
 }
 assert.equal(h.scripts.length,3);
 h.update(run({status:'completed',reply:'全部处理结果。'.repeat(200)}));await flush();
 assert.equal(h.scripts.length,4);
 h.ends.at(-1)?.();await flush();h.pipeline.tick();await flush();
 assert.equal(h.scripts.length,4);h.pipeline.stop();
});
test('long tool wait continues periodic narration after an existing preamble',async()=>{
 const initial=run({reply:'我先核对本月单据。',steps:[{name:'bash'}]});
 const h=harness(initial);h.update(initial);await flush();
 assert.equal(h.scripts[0].request.kind,'progress');
 h.ends[0]();await flush();
 for(let i=0;i<4;i++) { clock+=21000;h.pipeline.tick();await flush(); }
 assert.equal(h.scripts.length,5);
 h.update({...initial,status:'completed'});await flush();
 assert.equal(h.scripts.at(-1).request.kind,'answer');h.pipeline.stop();
});
test('new result discards queued waiting audio before playback',async()=>{
 let current=run({reply:'正在查询。'});let finish;
 const played=[];
 const p=new NarrationPipeline(current,false,{
  script:async(id,r)=>({text:r.kind+' '+clock,offset:current.reply.length,anchor:current.reply.slice(-80),done:current.status==='completed',fallback:false}),
  prepare:async text=>({play:()=>new Promise(resolve=>{played.push(text);finish=resolve;})}),caption:()=>{},error:()=>{},
 });
 p.update(current);await flush();clock+=21000;p.tick();await flush();
 current={...current,status:'completed',reply:'最终结果需要核实。'};p.update(current);await flush();
 finish();await flush();assert.equal(played.length,2);assert.ok(played[1].startsWith('answer'));
 finish();p.stop();
});
