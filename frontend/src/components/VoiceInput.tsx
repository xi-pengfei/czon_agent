import { useEffect, useRef, useState } from "react";
import { ArrowUp, LoaderCircle, Mic, Square, X } from "lucide-react";
import { api } from "../api";
import { SpeechSegments } from "../audio/segments";

type Props = { disabled?: boolean; onText: (text: string) => void; onNotice: (text: string) => void; onBusy: (busy: boolean) => void; onStatus: (text: string) => void; onCancel: () => void; onSubmit: (transcript: string) => void };
type Recording = {
  stream?: MediaStream; context?: AudioContext; node?: AudioWorkletNode;
  segments?: SpeechSegments; timer?: ReturnType<typeof setTimeout>;
  request?: AbortController; queue: Blob[]; draining: boolean; listening: boolean;
  closing: boolean; cancelled: boolean; received: boolean; transcript: string; submit: boolean; finished?: boolean;
};

export function VoiceInput(props: Props) {
  const [phase, setPhase] = useState<"idle" | "opening" | "recording" | "finishing">("idle");
  const current = useRef<Recording | null>(null);
  const [levels, setLevels] = useState<number[]>([]);
  const callbacks = useRef(props); callbacks.current = props;

  function release(session: Recording) {
    clearTimeout(session.timer);
    session.stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    session.node?.disconnect();
    if (session.context && session.context.state !== "closed") void session.context.close();
  }
  function cancel(session: Recording) {
    session.cancelled = true; session.listening = false; session.queue = []; session.request?.abort(); release(session);
  }
  useEffect(() => () => { if (current.current) cancel(current.current); }, []);
  useEffect(() => {
    const hidden = () => {
      const session = current.current;
      if (document.hidden && session?.listening) void stop(session);
    };
    document.addEventListener("visibilitychange", hidden);
    return () => document.removeEventListener("visibilitychange", hidden);
  }, []);

  function finish(session: Recording) {
    if (session.finished || session.cancelled || session.listening || session.closing || session.draining || session.queue.length) return;
    session.finished = true;
    setPhase("idle"); callbacks.current.onBusy(false);
    callbacks.current.onStatus(session.received ? "" : "未识别到内容，请重试或输入文字");
    if (session.submit && session.transcript.trim()) callbacks.current.onSubmit(session.transcript);
  }
  function fail(session: Recording, message: string) {
    if (session.cancelled) return;
    cancel(session); setPhase("idle"); callbacks.current.onBusy(false); callbacks.current.onStatus("");
    callbacks.current.onNotice(message);
  }
  async function drain(session: Recording) {
    if (session.draining || session.cancelled) return;
    session.draining = true;
    try {
      while (session.queue.length && !session.cancelled) {
        const body = new FormData(); body.append("file", session.queue.shift()!, "speech.wav");
        const controller = new AbortController(); session.request = controller;
        const timeout = setTimeout(() => controller.abort(), 25000);
        const progressTimer = setTimeout(() => {
          if (!session.cancelled) callbacks.current.onStatus(`识别服务响应较慢，已识别文字会保留${session.queue.length ? `，另有 ${session.queue.length} 段等待识别` : ""}`);
        }, 6000);
        try {
          const result = await api<{ text: string }>("/api/speech/asr", { method: "POST", body, signal: controller.signal });
          if (!session.cancelled && result.text.trim()) {
            session.received = true;
            session.transcript += (session.transcript ? " " : "") + result.text.trim();
            callbacks.current.onText(result.text.trim());
            callbacks.current.onStatus(session.listening ? "正在听 · 已识别文字已填入输入框" : "正在整理剩余录音…");
          }
        } finally { clearTimeout(timeout); clearTimeout(progressTimer); }
      }
    } catch (error) {
      fail(session, `语音识别未完成，已识别的文字已保留。${(error as Error).name === "AbortError" ? "服务响应超时，请重试。" : (error as Error).message}`);
    } finally { session.draining = false; finish(session); }
  }
  async function stop(session: Recording) {
    if (!session.listening || session.closing || session.cancelled) return;
    session.listening = false; session.closing = true; clearTimeout(session.timer);
    setPhase("finishing"); callbacks.current.onStatus("正在识别最后一段，请稍候…");
    // Flush the worklet's last partial block before closing the microphone.
    await new Promise<void>(resolve => {
      const timeout = setTimeout(resolve, 1000);
      const node = session.node;
      if (!node) { clearTimeout(timeout); resolve(); return; }
      node.port.addEventListener("message", function ended(event) {
        if (event.data === "stopped") { clearTimeout(timeout); node.port.removeEventListener("message", ended); resolve(); }
      });
      node.port.postMessage("stop");
    });
    release(session);
    if (session.cancelled) return;
    session.segments?.flush(); session.closing = false; finish(session);
  }
  async function toggle() {
    if (current.current?.listening) { void stop(current.current); return; }
    if (phase !== "idle") return;
    const session: Recording = { queue: [], draining: false, listening: false, closing: false, cancelled: false, received: false, transcript: "", submit: false };
    setLevels([]);
    current.current = session;
    setPhase("opening"); callbacks.current.onBusy(true); callbacks.current.onStatus("正在打开麦克风…");
    try {
      if (!window.isSecureContext) throw new Error("当前是 HTTP 局域网地址，手机浏览器不允许网页录音。请使用受信任的 HTTPS 地址；暂时可用键盘自带的听写，文字发送和播报仍可使用。");
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("此浏览器未提供麦克风权限，请在 Safari 或 Chrome 中打开，或使用键盘听写。");
      if (!window.AudioContext || !window.AudioWorkletNode) throw new Error("此浏览器不支持分段录音，请更新浏览器或使用输入法语音输入。");
      // Create/resume in the click gesture for iOS; credentials stay on the server.
      let context: AudioContext;
      try { context = new AudioContext({ sampleRate: 16000 }); }
      catch { context = new AudioContext(); }
      session.context = context;
      await context.resume();
      const capability = await api<{ asr: boolean }>("/api/speech/capabilities");
      if (session.cancelled) return;
      if (!capability.asr) throw new Error("管理员尚未配置语音识别服务，仍可使用输入法语音输入。");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      session.stream = stream;
      if (session.cancelled) { release(session); return; }
      await context.audioWorklet.addModule("/static/voice-capture.js");
      if (session.cancelled) return;
      const node = new AudioWorkletNode(context, "voice-capture"); session.node = node;
      session.segments = new SpeechSegments(context.sampleRate, file => {
        if (session.cancelled) return;
        session.queue.push(file); void drain(session);
        if (session.queue.length >= 3 && session.listening) {
          callbacks.current.onNotice("识别服务较慢，已结束录音，正在处理已录内容。"); void stop(session);
        }
      });
      node.port.onmessage = event => {
        if (!session.cancelled && event.data instanceof Float32Array) {
          session.segments?.push(event.data);
          const samples = event.data as Float32Array;
          const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / Math.max(1, samples.length));
          setLevels(previous => [...previous.slice(-47), Math.min(1, rms * 10)]);
        }
      };
      node.onprocessorerror = () => fail(session, "录音处理失败，已识别文字已保留，请重试。");
      context.createMediaStreamSource(stream).connect(node); node.connect(context.destination);
      session.listening = true; setPhase("recording");
      callbacks.current.onStatus("正在听 · 文字分段出现，点击方块结束");
      stream.getAudioTracks().forEach(track => { track.onended = () => { void stop(session); }; });
      session.timer = setTimeout(() => { void stop(session); }, 60000);
    } catch (error) { fail(session, (error as Error).message); }
  }
  const recording = phase === "recording";
  function discard() {
    if (current.current) cancel(current.current);
    setPhase("idle"); setLevels([]);
    callbacks.current.onBusy(false); callbacks.current.onStatus(""); callbacks.current.onCancel();
  }
  function submitRecording() {
    const session = current.current;
    if (!session || session.cancelled) return;
    session.submit = true;
    if (session.listening) void stop(session);
  }
  if (phase !== "idle") return <div className="voice-session" data-phase={phase}>
    <button type="button" className="voice-round secondary" onClick={discard} aria-label="取消本次录音" title="取消本次录音"><X size={19} /></button>
    <div className="voice-meter" role="status" aria-label={recording ? "正在录音" : phase === "opening" ? "正在打开麦克风" : "正在转写"}>
      {recording ? <div className="voice-wave" aria-hidden="true">{Array.from({ length: 48 }, (_, index) => <i key={index} style={{ height: `${3 + (levels[index - (48 - levels.length)] || 0) * 33}px` }} />)}</div>
        : <span>{phase === "opening" ? "正在打开麦克风" : "正在转写"}</span>}
    </div>
    {recording ? <button type="button" className="voice-round secondary" onClick={() => current.current && void stop(current.current)} aria-label="结束录音并编辑" title="结束录音并编辑"><Square size={16} fill="currentColor" /></button>
      : <LoaderCircle className="spin voice-pending" size={21} aria-hidden="true" />}
    <button type="button" className="voice-round primary" disabled={phase !== "recording"} onClick={submitRecording} aria-label="结束录音并发送" title="识别完成后发送"><ArrowUp size={22} /></button>
  </div>;
  return <button type="button" className="icon-button voice-button" disabled={props.disabled} onClick={() => void toggle()} title="语音输入（最多一分钟）" aria-label="语音输入"><Mic size={23} strokeWidth={1.8} /></button>;
}
