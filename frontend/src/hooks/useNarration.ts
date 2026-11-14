import { useEffect, useRef, useState } from 'react';
import { api, apiResponse } from '../api';
import type { Run } from './useRuns';
import { NarrationPipeline, type Narration, type PreparedSpeech } from '../audio/narration';

// Playback is local to this device and never owns the business task.
export function useNarration(run: Run | undefined, enabled: boolean, onError: (text: string) => void, onCaption: (text: string, fallback: boolean) => void) {
  const pipeline = useRef<NarrationPipeline | null>(null);
  const context = useRef<AudioContext | null>(null);
  const [isPlaying, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const previewController = useRef<AbortController | null>(null);
  const serverTts = useRef<boolean | undefined>(undefined);
  const enabledAt = useRef(Infinity);
  const callbacks = useRef({onError, onCaption}); callbacks.current = {onError, onCaption};
  const latest = useRef(run); latest.current = run;

  // Called directly from the enable button to satisfy mobile autoplay policies.
  async function unlock() {
    enabledAt.current = Date.now();
    if (window.AudioContext) {
      if (!context.current || context.current.state === 'closed') {
        context.current = new AudioContext();
        context.current.onstatechange = () => setPaused(context.current?.state !== 'running');
      }
      await resumeAudio(context.current);
      setPaused(false);
    }
  }
  const prepare = async (text: string, signal: AbortSignal): Promise<PreparedSpeech> => {
      if (serverTts.current === undefined) serverTts.current = (await api<{tts:boolean}>('/api/speech/capabilities', {signal})).tts;
      if (!serverTts.current) {
        if (!('speechSynthesis' in window)) throw new Error('此设备没有可用的播报声音，请配置语音合成服务');
        return {play: abortSignal => new Promise<void>((resolve, reject) => {
          if (abortSignal.aborted) { resolve(); return; }
          const utterance = new SpeechSynthesisUtterance(text); utterance.lang = 'zh-CN';
          const finish = (error?: Error) => { setPlaying(false); abortSignal.removeEventListener('abort', cancel); error ? reject(error) : resolve(); };
          const cancel = () => { window.speechSynthesis.cancel(); finish(); };
          abortSignal.addEventListener('abort', cancel, {once:true});
          utterance.onend = () => finish(); utterance.onerror = () => finish(abortSignal.aborted ? undefined : new Error('设备语音播放失败'));
          setPlaying(true); window.speechSynthesis.speak(utterance);
        })};
      }
      const response = await apiResponse('/api/speech/tts', {method:'POST', body:JSON.stringify({text}), signal});
      if (!response.ok) throw new Error('语音合成暂不可用，文字和任务不受影响');
      const bytes = await response.arrayBuffer();
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const audioContext = context.current;
      if (!audioContext) throw new Error('请重新点击开启播报，以启用设备音频');
      const buffer = await audioContext.decodeAudioData(bytes);
      return {play: async abortSignal => {
        await resumeAudio(audioContext);
        return new Promise<void>((resolve, reject) => {
        if (abortSignal.aborted) { resolve(); return; }
        if (audioContext.state !== 'running') { reject(new Error('设备暂停了音频，请重新点击开启播报')); return; }
        const source = audioContext.createBufferSource(); source.buffer = buffer; source.connect(audioContext.destination);
        const finish = () => { setPlaying(false); abortSignal.removeEventListener('abort', cancel); source.disconnect(); resolve(); };
        const cancel = () => { source.stop(); finish(); };
        abortSignal.addEventListener('abort', cancel, {once:true});
        source.onended = finish; setPlaying(true); source.start();
      }); }};
    };
  async function testSound() {
    previewController.current?.abort();
    const controller = new AbortController(); previewController.current = controller;
    try {
      await unlock();
      const speech = await prepare('播报已开启，你可以在这台设备上听取任务进度和结果。', controller.signal);
      await speech.play(controller.signal);
    } catch (error) { if (!controller.signal.aborted) callbacks.current.onError((error as Error).message); }
  }
  useEffect(() => {
    if (!enabled) previewController.current?.abort();
    const current = latest.current;
    if (!enabled || !current) return;
    previewController.current?.abort();
    const player = new NarrationPipeline(current, Date.parse(current.created_at) < enabledAt.current, {
      script: (id, request, signal) => api<Narration>(`/api/runs/${id}/narration`, {method:'POST', body:JSON.stringify(request), signal}),
      prepare,
      caption: (text, fallback) => callbacks.current.onCaption(text, fallback),
      error: text => callbacks.current.onError(text),
    });
    pipeline.current = player; player.update(current);
    const timer = setInterval(() => player.tick(), 2000);
    return () => { clearInterval(timer); player.stop(); if (pipeline.current === player) pipeline.current = null; };
  }, [enabled, run?.id]);
  useEffect(() => { if (run) pipeline.current?.update(run); }, [run]);
  useEffect(() => () => { previewController.current?.abort(); if (context.current?.state !== 'closed') void context.current?.close(); }, []);
  return {unlock, testSound, paused, isPlaying};
}

// Dictation, calls and backgrounding can interrupt iOS audio after initial unlock.
async function resumeAudio(context: AudioContext) {
  if (context.state === 'running') return;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([context.resume(), new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error('声音被浏览器暂停，请点击“恢复声音”或重新开启播报；也可在 Safari 中打开此页面。')), 3000);
    })]);
    if ((context.state as string) !== 'running') throw new Error('声音尚未恢复，请再次点击开启播报');
  } finally { clearTimeout(timer); }
}
