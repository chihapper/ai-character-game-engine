// AudioWorklet that captures mono mic input and posts Float32 chunks (~43ms) to
// the main thread, which downsamples to 16 kHz PCM16 and streams to the backend.
// Buffering into larger chunks keeps postMessage overhead low.

class MicCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buf = [];
    this._count = 0;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      this._buf.push(ch.slice(0));
      this._count += ch.length;
      if (this._count >= 2048) {
        const out = new Float32Array(this._count);
        let o = 0;
        for (const b of this._buf) {
          out.set(b, o);
          o += b.length;
        }
        this.port.postMessage(out, [out.buffer]);
        this._buf = [];
        this._count = 0;
      }
    }
    return true; // keep capturing
  }
}

registerProcessor("mic-capture", MicCapture);
