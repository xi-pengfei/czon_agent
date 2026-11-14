import {useEffect, useEffectEvent, useRef, useState} from 'react';
import {AppState} from 'react-native';
import {AudioModule, RecordingPresets, setAudioModeAsync, useAudioPlayer, useAudioRecorder, useAudioRecorderState} from 'expo-audio';
import {File, Paths} from 'expo-file-system';
import type {Client} from './client';
import {translator} from './strings';

export function useVoice(client: Client, t: ReturnType<typeof translator>, onText: (text: string) => void, onError: (message: string) => void) {
  const recorder = useAudioRecorder({...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true});
  const recording = useAudioRecorderState(recorder, 150);
  const player = useAudioPlayer();
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const lock = useRef(false), generation = useRef(0), audioFile = useRef<File | null>(null);
  const signal = useRef<AbortController | null>(null);
  const recordingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const removeRecording = () => { if (recorder.uri) { const file = new File(recorder.uri); if (file.exists) file.delete(); } };
  const stopPlayback = () => {
    generation.current++; signal.current?.abort(); player.pause(); setPlaying(false);
    if (audioFile.current?.exists) audioFile.current.delete(); audioFile.current = null;
  };
  async function cancel() {
    clearTimeout(recordingTimer.current);
    generation.current++; signal.current?.abort();
    if (recorder.isRecording) await recorder.stop();
    removeRecording();
    await setAudioModeAsync({allowsRecording: false});
  }
  async function toggle() {
    if (lock.current) return;
    lock.current = true; setBusy(true);
    const own = ++generation.current;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      if (recorder.isRecording) {
        clearTimeout(recordingTimer.current);
        await recorder.stop();
        await setAudioModeAsync({allowsRecording: false, playsInSilentMode: true});
        if (!recorder.uri) throw new Error(t('error'));
        const form = new FormData(); form.append('file', new File(recorder.uri), 'recording.m4a');
        signal.current = new AbortController();
        const requestSignal = signal.current;
        timeout = setTimeout(() => requestSignal.abort(), 90_000);
        const response = await client.response('/api/speech/asr', {method: 'POST', body: form, signal: signal.current.signal});
        const data = await response.json();
        if (own === generation.current) onText(data.text);
        removeRecording();
      } else {
        const capabilities = await client.get<{asr: boolean}>('/api/speech/capabilities');
        if (!capabilities.asr) throw new Error(t('unavailable'));
        const permission = await AudioModule.requestRecordingPermissionsAsync();
        if (!permission.granted) throw new Error(t('micDenied'));
        player.pause(); setPlaying(false);
        await setAudioModeAsync({allowsRecording: true, playsInSilentMode: true});
        if (own !== generation.current) return;
        await recorder.prepareToRecordAsync();
        if (own !== generation.current) return;
        recorder.record();
        recordingTimer.current = setTimeout(() => void toggle(), 90_000);
      }
    } catch (e) { if (own === generation.current) onError((e as Error).message); }
    finally { clearTimeout(timeout); lock.current = false; setBusy(false); }
  }
  async function play(runId: string) {
    stopPlayback(); const own = generation.current;
    signal.current = new AbortController(); setPlaying(true);
    const requestSignal = signal.current;
    const timeout = setTimeout(() => requestSignal.abort(), 90_000);
    try {
      const response = await client.response(`/api/runs/${runId}/narration`, {method: 'POST', body: JSON.stringify({kind: 'answer'}), signal: signal.current.signal});
      const summary = await response.json();
      if (!summary.text || own !== generation.current) { setPlaying(false); return; }
      const audio = await client.response('/api/speech/tts', {method: 'POST', body: JSON.stringify({text: summary.text}), signal: signal.current.signal});
      const bytes = new Uint8Array(await audio.arrayBuffer());
      if (own !== generation.current) return;
      const file = new File(Paths.cache, `speech-${Date.now()}.mp3`); file.write(bytes); audioFile.current = file;
      await setAudioModeAsync({allowsRecording: false, playsInSilentMode: true});
      if (own !== generation.current) return;
      player.replace(file.uri); player.play();
    } catch (e) { if (own === generation.current) { setPlaying(false); onError((e as Error).message); } }
    finally { clearTimeout(timeout); }
  }
  const background = useEffectEvent(() => { stopPlayback(); void cancel().catch(() => {}); });
  const cleanup = useEffectEvent(() => {
    generation.current++; signal.current?.abort(); clearTimeout(recordingTimer.current);
    if (audioFile.current?.exists) audioFile.current.delete();
  });
  useEffect(() => {
    const subscription = player.addListener('playbackStatusUpdate', status => { if (status.didJustFinish) setPlaying(false); });
    const lifecycle = AppState.addEventListener('change', state => { if (state === 'background') background(); });
    return () => { cleanup(); subscription.remove(); lifecycle.remove(); };
  }, [player]);
  return {recording, busy, toggle, cancel, play, playing, stopPlayback};
}
