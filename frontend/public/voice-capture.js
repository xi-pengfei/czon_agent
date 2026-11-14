// Runs off the UI thread. Keep one microphone stream open between ASR segments.
class VoiceCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(Math.round(sampleRate / 10));
    this.offset = 0;
    this.stopped = false;
    this.port.onmessage = event => {
      if (event.data === 'stop') {
        this.flush();
        this.stopped = true;
        this.port.postMessage('stopped');
      }
    };
  }
  flush() {
    if (this.offset) this.port.postMessage(this.buffer.slice(0, this.offset));
    this.offset = 0;
  }
  process(inputs) {
    if (this.stopped) return false;
    const samples = inputs[0]?.[0];
    if (samples) {
      for (const sample of samples) {
        this.buffer[this.offset++] = sample;
        if (this.offset === this.buffer.length) this.flush();
      }
    }
    return true;
  }
}
registerProcessor('voice-capture', VoiceCapture);
