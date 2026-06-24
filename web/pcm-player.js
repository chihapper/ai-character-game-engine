// AudioWorklet PCM player — robust streaming playback.
//
// A single AudioWorkletNode runs continuously and pulls mono Float32 PCM from an
// internal queue, emitting silence on underrun. Because the node never stops, the
// AudioContext doesn't "warm up" per response (no clipped first word), and there
// are no per-buffer boundaries to click at. The main thread posts Float32Array
// chunks (already at the context sample rate); "reset" clears the queue.

class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.cur = null;
    this.pos = 0;
    this.port.onmessage = (e) => {
      const d = e.data;
      if (d && d.type === "reset") {
        this.queue = [];
        this.cur = null;
        this.pos = 0;
        return;
      }
      this.queue.push(d); // Float32Array
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    if (!out) return true;
    let i = 0;
    while (i < out.length) {
      if (!this.cur || this.pos >= this.cur.length) {
        this.cur = this.queue.shift() || null;
        this.pos = 0;
        if (!this.cur) {
          // Underrun: output silence (no click, no gap artifact).
          while (i < out.length) out[i++] = 0;
          break;
        }
      }
      out[i++] = this.cur[this.pos++];
    }
    return true; // keep the processor alive
  }
}

registerProcessor("pcm-player", PCMPlayer);
