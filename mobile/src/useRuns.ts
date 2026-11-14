import {useEffect, useState} from 'react';
import {AppState} from 'react-native';
import {Client} from './client';
import {sseParser} from './protocol';
import {reduceRun, type Run, type RunEvent} from './runs';

export function useRuns(client: Client) {
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [connected, setConnected] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let disposed = false, generation = 0;
    let controller: AbortController | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let flush: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    const start = async () => {
      if (disposed || AppState.currentState === 'background') return;
      const own = ++generation;
      controller?.abort(); clearTimeout(retry); clearTimeout(flush);
      controller = new AbortController();
      const connection = controller;
      const signal = connection.signal;
      let watchdog = setTimeout(() => connection.abort(), 30_000);
      let pending: RunEvent[] = [];
      const apply = () => {
        flush = undefined;
        if (disposed || own !== generation) return;
        const batch = pending; pending = [];
        setRuns(previous => {
          const next = {...previous};
          for (const e of batch) {
            if (e.event === 'run_created') next[e.run_id] = e.data as unknown as Run;
            else if (e.event === 'session_deleted') {
              for (const [id, run] of Object.entries(next)) if (run.session_id === e.data.session_id) delete next[id];
            } else if (next[e.run_id]) next[e.run_id] = reduceRun(next[e.run_id], e);
          }
          return next;
        });
        if (batch.some(e => e.event === 'run_created' || e.event === 'session_deleted' || e.event.startsWith('agent_') && e.event !== 'agent_start')) setRevision(n => n + 1);
      };
      try {
        // A fresh authoritative snapshot also recovers gaps after long suspension or server restart.
        const snapshot = await client.get<{runs: Run[]; cursor: number}>('/api/runs', signal);
        if (disposed || own !== generation) return;
        setRuns(Object.fromEntries(snapshot.runs.map(run => [run.id, run])));
        setRevision(n => n + 1);
        let cursor = snapshot.cursor;
        const response = await client.response(`/api/events?after=${cursor}`, {signal, headers: {Accept: 'text/event-stream'}});
        if (disposed || own !== generation) return;
        setConnected(true); failures = 0;
        const reader = response.body?.getReader();
        if (!reader) throw new Error('无法连接事件流');
        const decoder = new TextDecoder();
        const parse = sseParser((name, data) => {
          if (name === 'auth_expired') { client.expired(); controller?.abort(); return; }
          if (name !== 'run_event') return;
          const event = JSON.parse(data) as RunEvent;
          if (event.seq <= cursor) return;
          cursor = event.seq; pending.push(event);
          if (!flush) flush = setTimeout(apply, 60);
        });
        try {
          while (!signal.aborted) {
            const {done, value} = await reader.read();
            if (done) break;
            clearTimeout(watchdog);
            watchdog = setTimeout(() => connection.abort(), 30_000);
            parse(decoder.decode(value, {stream: true}));
          }
        } finally { reader.releaseLock(); }
        apply();
      } catch { /* Retry with a snapshot; never cancel server-side jobs. */ }
      finally { clearTimeout(watchdog); }
      if (!disposed && own === generation) {
        setConnected(false);
        retry = setTimeout(start, Math.min(15_000, 1000 * 2 ** failures++));
      }
    };
    const listener = AppState.addEventListener('change', state => {
      if (state === 'active') void start();
      else { generation++; controller?.abort(); clearTimeout(retry); clearTimeout(flush); setConnected(false); }
    });
    void start();
    return () => { disposed = true; generation++; controller?.abort(); clearTimeout(retry); clearTimeout(flush); listener.remove(); };
  }, [client]);
  return {runs, connected, revision};
}
