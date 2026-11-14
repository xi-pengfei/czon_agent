import type { Run } from '../hooks/useRuns';

export type NarrationRequest = { kind: 'progress' | 'answer'; offset: number; anchor: string; previous: string };
export type Narration = { text: string; offset: number; anchor: string; done: boolean; stage?: string; hint_id?: string; fallback: boolean };
export type PreparedSpeech = { play: (signal: AbortSignal) => Promise<void> };
type Dependencies = {
  script: (runId: string, request: NarrationRequest, signal: AbortSignal) => Promise<Narration>;
  prepare: (text: string, signal: AbortSignal) => Promise<PreparedSpeech>;
  caption: (text: string, fallback: boolean) => void;
  error: (message: string) => void;
};
const stopped = (run: Run) => ['stopped', 'failed', 'interrupted'].includes(run.status);

// One playing paragraph + one prepared paragraph. Text and audio production do not
// wait for playback, but never build an unbounded backlog of stale narration.
export class NarrationPipeline {
  private run: Run;
  private offset: number;
  private anchor: string;
  private previous = '';
  private stage = '';
  private lastProgress = 0;
  private lastRequest = 0;
  private answers = 0;
  private fallbackSaid = false;
  private preparing = false;
  private playing = false;
  private ready?: { speech: PreparedSpeech; narration: Narration; kind: string; reply: string };
  private controller = new AbortController();
  private disposed = false;
  private observed = '';
  constructor(run: Run, skipHistory: boolean, private deps: Dependencies) {
    this.run = run;
    this.offset = skipHistory ? run.reply.length : 0;
    this.anchor = run.reply.slice(Math.max(0, this.offset - 80), this.offset);
    if (skipHistory && run.status === 'completed') this.observed = `${run.status}\0${run.reply}`;
  }
  update(run: Run) {
    this.run = run;
    if (this.ready?.kind === 'progress' && (this.ready.reply !== run.reply || run.status === 'completed')) this.ready = undefined;
    if (stopped(run)) { this.stop(); return; }
    void this.pump();
  }
  tick() { void this.pump(); }
  stop() {
    this.disposed = true; this.controller.abort(); this.ready = undefined;
    this.deps.caption('', false);
  }
  private async pump() {
    if (this.disposed || this.preparing || this.ready) return;
    const run = this.run;
    const signature = `${run.status}\0${run.reply}`;
    const replaced = run.reply.slice(Math.max(0, this.offset - 80), this.offset) !== this.anchor;
    const remaining = replaced ? run.reply.length : run.reply.length - this.offset;
    const hasAnswer = (run.status === 'completed' || this.answers < 3 && remaining >= 100) && signature !== this.observed;
    const stage = run.status === 'queued' ? 'queued' : run.progress === '需要确认才能继续' ? 'confirmation' : run.steps.length ? 'working' : 'started';
    const hasProgress = run.status !== 'completed' && (!this.lastProgress || Date.now() - this.lastProgress >= 20000 || stage === 'confirmation' && this.stage !== stage);
    if (stage === 'confirmation' && this.stage === stage && !hasAnswer) return;
    if (!hasAnswer && !hasProgress) return;
    const kind = hasAnswer ? 'answer' : 'progress';
    if (kind === 'answer' && run.status !== 'completed' && Date.now() - this.lastRequest < 1500) return;
    this.lastRequest = Date.now();
    this.preparing = true;
    try {
      const narration = await this.deps.script(run.id, {kind, offset:this.offset, anchor:this.anchor, previous:this.previous}, this.controller.signal);
      if (this.disposed) return;
      if (kind === 'answer') {
        if (narration.offset !== this.offset || narration.text) this.answers++;
        if (narration.text) this.lastProgress = Date.now();
        this.observed = signature; this.offset = narration.offset; this.anchor = narration.anchor;
      } else {
        this.stage = stage; this.lastProgress = Date.now();
        // A progress message is no longer useful once the answer has arrived.
        if (this.run.reply !== run.reply || this.run.status === 'completed') return;
      }
      if (!narration.text || narration.text === this.previous || kind === 'answer' && narration.fallback && this.fallbackSaid && !narration.done) return;
      const speech = await this.deps.prepare(narration.text, this.controller.signal);
      if (this.disposed) return;
      if (kind === 'progress' && (this.run.reply !== run.reply || this.run.status === 'completed')) return;
      if (kind === 'answer' && narration.fallback) this.fallbackSaid = true;
      this.previous = narration.text;
      this.ready = {speech, narration, kind, reply: run.reply};
      void this.playNext();
    } catch (error) {
      if (!this.disposed) { this.stop(); this.deps.error((error as Error).message); }
    } finally {
      this.preparing = false;
      // If playback began while preparation was active, start look-ahead now.
      if (!this.disposed && this.playing && !this.ready && (kind === 'progress' || this.run.reply.length > this.offset)) void this.pump();
    }
  }
  private async playNext() {
    if (this.playing || !this.ready || this.disposed) return;
    const item = this.ready; this.ready = undefined;
    if (item.kind === 'progress' && (item.reply !== this.run.reply || this.run.status === 'completed')) { void this.pump(); return; }
    this.playing = true;
    this.deps.caption(item.narration.text, item.narration.fallback);
    try {
      void this.pump();
      await item.speech.play(this.controller.signal);
    } catch (error) {
      if (!this.disposed) { this.stop(); this.deps.error((error as Error).message); }
    } finally {
      this.playing = false;
      if (!this.disposed) { void this.playNext(); void this.pump(); }
    }
  }
}
