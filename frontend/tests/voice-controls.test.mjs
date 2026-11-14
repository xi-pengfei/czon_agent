import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
const require=createRequire(import.meta.url);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness() {
 const slots=[];let cursor=0,node,stops=0,resolveAsr;
 const events={text:[],sent:[],cancel:0,busy:[]};
 const hooks={useRef:value=>{const i=cursor++;return slots[i]??=( {current:value});},useState:value=>{const i=cursor++;if(!(i in slots))slots[i]=value;return [slots[i],value=>{slots[i]=typeof value==='function'?value(slots[i]):value;}];},useEffect:()=>{}};
 class Context {state='running';sampleRate=16000;audioWorklet={addModule:async()=>{}};resume=async()=>{};close=async()=>{this.state='closed'};createMediaStreamSource=()=>({connect(){}});}
 class Node {constructor(){node=this;} disconnect(){} connect(){} port={addEventListener:(_name,fn)=>{this.end=fn;},removeEventListener(){},postMessage:()=>queueMicrotask(()=>this.end?.({data:'stopped'}))};}
 class Segments {constructor(_rate,emit){this.emit=emit;}push(){this.emit(new Blob(['sample']));}flush(){}}
 const api=async(path)=>path.endsWith('capabilities')?{asr:true}:await new Promise(resolve=>{resolveAsr=resolve;});
 const exports={};
 const source=ts.transpileModule(readFileSync(new URL('../src/components/VoiceInput.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(source,{exports,require:name=>name==='react'?hooks:name==='../api'?{api}:name==='../audio/segments'?{SpeechSegments:Segments}:require(name),window:{isSecureContext:true,AudioContext:Context,AudioWorkletNode:Node},AudioContext:Context,AudioWorkletNode:Node,navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){stops++;}}],getAudioTracks:()=>[]})}},setTimeout,clearTimeout,AbortController,FormData,Float32Array,queueMicrotask});
 const props={onText:t=>events.text.push(t),onSubmit:t=>events.sent.push(t),onCancel:()=>events.cancel++,onBusy:b=>events.busy.push(b),onStatus(){},onNotice(){}};
 const render=()=>{cursor=0;return exports.VoiceInput(props);};
 const find=(tree,label)=>{if(!tree)return null;if(Array.isArray(tree))return tree.map(t=>find(t,label)).find(Boolean);if(tree.props?.['aria-label']===label)return tree;return find(tree.props?.children,label);};
 return {events,click:label=>{const el=find(render(),label);assert.ok(el,`missing ${label}`);el.props.onClick();},phase:()=>render().props['data-phase'],samples:()=>node.port.onmessage({data:new Float32Array([.3,.2])}),reply:t=>resolveAsr({text:t}),get stops(){return stops;}};
}
test('cancel ignores late ASR response and never sends it',async()=>{
 const h=harness();h.click('语音输入');await tick();assert.equal(h.phase(),'recording');h.samples();await tick();
 h.click('取消本次录音');h.reply('迟到文字');await tick();
 assert.deepEqual(h.events.text,[]);assert.deepEqual(h.events.sent,[]);assert.equal(h.events.cancel,1);assert.ok(h.stops>0);assert.equal(h.events.busy.at(-1),false);
});
test('recording send waits for final transcription and submits exactly once',async()=>{
 const h=harness();h.click('语音输入');await tick();h.samples();await tick();h.click('结束录音并发送');await tick();
 assert.equal(h.phase(),'finishing');assert.deepEqual(h.events.sent,[]);
 h.reply('完整识别文本');await tick();assert.deepEqual(h.events.sent,['完整识别文本']);assert.equal(h.events.busy.at(-1),false);assert.ok(h.stops>0);
});
test('stop returns recognized text for editing without sending',async()=>{
 const h=harness();h.click('语音输入');await tick();h.samples();await tick();h.click('结束录音并编辑');await tick();h.reply('可以修改的草稿');await tick();
 assert.deepEqual(h.events.text,['可以修改的草稿']);assert.deepEqual(h.events.sent,[]);assert.equal(h.phase(),undefined);
});
