import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const compiled = ts.transpileModule(readFileSync(new URL('../src/audio/segments.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const exports = {};
vm.runInNewContext(compiled, { exports, Blob, Float32Array, ArrayBuffer, DataView });
const { wavFile, SpeechSegments } = exports;

test('WAV header describes independent mono PCM with clipped, ordered samples', async () => {
  const file = wavFile([new Float32Array([-2, 0, 2])], 16000);
  const buffer = await file.arrayBuffer(); const view = new DataView(buffer);
  assert.equal(file.type, 'audio/wav'); assert.equal(buffer.byteLength, 50);
  assert.equal(new TextDecoder().decode(buffer.slice(0, 4)), 'RIFF');
  assert.equal(view.getUint32(24, true), 16000); assert.equal(view.getUint32(40, true), 6);
  assert.deepEqual([44,46,48].map(i => view.getInt16(i, true)), [-32768,0,32767]);
});
test('continuous speech emits before stop and preserves every sample including tail', async () => {
  const files = []; const segments = new SpeechSegments(16000, file => files.push(file));
  for (let i=0;i<123;i++) segments.push(new Float32Array(1600).fill(.1));
  assert.ok(files.length >= 2, 'must update during recording');
  segments.flush(); segments.flush();
  assert.equal(files.length, 3);
  const bytes = await Promise.all(files.map(file => file.arrayBuffer()));
  assert.equal(bytes.reduce((sum, buffer) => sum + (buffer.byteLength-44)/2, 0), 123*1600);
});
test('pause closes phrase early and digital silence is not sent to ASR', () => {
  const files = []; const segments = new SpeechSegments(16000, file => files.push(file));
  for(let i=0;i<15;i++) segments.push(new Float32Array(1600).fill(.1));
  for(let i=0;i<7;i++) segments.push(new Float32Array(1600));
  assert.equal(files.length, 1);
  for(let i=0;i<60;i++) segments.push(new Float32Array(1600));
  segments.flush(); assert.equal(files.length, 1);
});
test('worklet flushes partial frame on stop and never echoes microphone audio', () => {
  let Processor; const messages = [];
  class Base { constructor() { this.port = { postMessage: value => messages.push(value) }; } }
  vm.runInNewContext(readFileSync(new URL('../public/voice-capture.js', import.meta.url), 'utf8'), {
    AudioWorkletProcessor: Base, sampleRate:16000, Float32Array,
    registerProcessor: (_name, implementation) => { Processor = implementation; }
  });
  const processor = new Processor();
  for(let i=0;i<15;i++) processor.process([[new Float32Array(128).fill(.1)]]);
  processor.port.onmessage({data:'stop'});
  assert.equal(messages.at(-1), 'stopped');
  assert.equal(messages.filter(value => value instanceof Float32Array).reduce((n, value) => n+value.length,0), 15*128);
  assert.equal(processor.process([[new Float32Array(128)]]), false);
});
test('first continuous phrase is sent by 2.5 seconds without shortening subsequent phrases',async()=>{
 const files=[];const segments=new SpeechSegments(16000,file=>files.push(file));
 for(let i=0;i<25;i++)segments.push(new Float32Array(1600).fill(.1));
 assert.equal(files.length,1);
 assert.ok(files[0].size<=44+16000*2*2.5);
 for(let i=0;i<25;i++)segments.push(new Float32Array(1600).fill(.1));
 assert.equal(files.length,1);
 segments.flush();assert.equal(files.length,2);
});
