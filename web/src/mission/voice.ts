/** Record from the microphone and hand back a mono 16-bit 16 kHz WAV, the format Muse Voice Transcribe takes. */
export async function recordWav(): Promise<{ stop: () => Promise<Blob>; level: () => number }> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const ctx = new AudioContext();
  const src = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  src.connect(analyser);
  const rec = new MediaRecorder(stream);
  const chunks: Blob[] = [];
  rec.ondataavailable = (e) => chunks.push(e.data);
  rec.start();
  const buf = new Uint8Array(analyser.fftSize);
  return {
    level() {
      analyser.getByteTimeDomainData(buf);
      let s = 0;
      for (const v of buf) s += ((v - 128) / 128) ** 2;
      return Math.sqrt(s / buf.length);
    },
    stop: () =>
      new Promise((resolve) => {
        rec.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          const blob = new Blob(chunks, { type: rec.mimeType });
          resolve(await toWav(blob));
          ctx.close();
        };
        rec.stop();
      }),
  };
}

export async function toWav(blob: Blob, rate = 16000): Promise<Blob> {
  const arr = await blob.arrayBuffer();
  const decoded = await new AudioContext().decodeAudioData(arr);
  const off = new OfflineAudioContext(1, Math.ceil(decoded.duration * rate), rate);
  const s = off.createBufferSource();
  s.buffer = decoded;
  s.connect(off.destination);
  s.start();
  const pcm = (await off.startRendering()).getChannelData(0);
  const out = new DataView(new ArrayBuffer(44 + pcm.length * 2));
  const w = (o: number, t: string) => [...t].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF");
  out.setUint32(4, 36 + pcm.length * 2, true);
  w(8, "WAVE");
  w(12, "fmt ");
  out.setUint32(16, 16, true);
  out.setUint16(20, 1, true);
  out.setUint16(22, 1, true);
  out.setUint32(24, rate, true);
  out.setUint32(28, rate * 2, true);
  out.setUint16(32, 2, true);
  out.setUint16(34, 16, true);
  w(36, "data");
  out.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, pcm[i])) * 0x7fff, true);
  return new Blob([out], { type: "audio/wav" });
}
