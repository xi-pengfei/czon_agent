// Each segment is a complete WAV file; MediaRecorder timeslices are not guaranteed
// to be independently decodable (notably MP4 on iOS).
export function wavFile(blocks: Float32Array[], sampleRate: number): Blob {
  const count = blocks.reduce((sum, block) => sum + block.length, 0);
  const buffer = new ArrayBuffer(44 + count * 2);
  const view = new DataView(buffer);
  const label = (offset: number, text: string) => [...text].forEach((letter, i) => view.setUint8(offset + i, letter.charCodeAt(0)));
  label(0, "RIFF"); view.setUint32(4, 36 + count * 2, true); label(8, "WAVE");
  label(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  label(36, "data"); view.setUint32(40, count * 2, true);
  let offset = 44;
  for (const block of blocks) for (const value of block) {
    const clipped = Math.max(-1, Math.min(1, value));
    view.setInt16(offset, clipped < 0 ? clipped * 32768 : clipped * 32767, true); offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export class SpeechSegments {
  private blocks: Float32Array[] = [];
  private duration = 0;
  private silence = 0;
  private audible = false;
  private first = true;
  constructor(private sampleRate: number, private emit: (file: Blob) => void) {}
  push(samples: Float32Array) {
    const seconds = samples.length / this.sampleRate;
    const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
    this.blocks.push(samples); this.duration += seconds;
    this.silence = rms < .008 ? this.silence + seconds : 0;
    this.audible ||= rms > .001;
    // Prefer pauses after a short phrase; continuous speech still appears in chunks.
    if ((this.duration >= 2 && this.silence >= .6) || this.duration >= (this.first ? 2.5 : 5)) this.flush();
  }
  flush() {
    if (this.audible && this.blocks.length) {
      this.emit(wavFile(this.blocks, this.sampleRate)); this.first = false;
    }
    this.blocks = []; this.duration = 0; this.silence = 0; this.audible = false;
  }
}
