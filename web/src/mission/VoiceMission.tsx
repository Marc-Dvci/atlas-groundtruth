import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { recordWav } from "./voice";

export type MissionSpec = {
  province: string | null;
  scope: string;
  deadline: string | null;
  deadline_label: string | null;
  budget_usd: number | null;
  focus: string[];
};

type Props = { onMission: (m: MissionSpec, transcript: string) => void };

/** Speak the mission: Muse Voice Transcribe hears it, Muse Spark turns it into a plan. */
export function VoiceMission({ onMission }: Props) {
  const [state, setState] = useState<"idle" | "listening" | "thinking" | "done">("idle");
  const [level, setLevel] = useState(0);
  const [text, setText] = useState("");
  const [shown, setShown] = useState("");
  const [mission, setMission] = useState<MissionSpec | null>(null);
  const rec = useRef<Awaited<ReturnType<typeof recordWav>> | null>(null);
  const raf = useRef(0);

  // type the transcript out, the way it was heard
  useEffect(() => {
    if (!text) return;
    let i = 0;
    const t = setInterval(() => {
      i += 2;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(t);
    }, 22);
    return () => clearInterval(t);
  }, [text]);

  const send = async (wav: Blob) => {
    setState("thinking");
    const r = await fetch("/api/mission/voice", { method: "POST", headers: { "Content-Type": "audio/wav" }, body: wav });
    const d = await r.json();
    setText(d.transcript);
    setTimeout(() => {
      setMission(d.mission);
      setState("done");
      setTimeout(() => onMission(d.mission, d.transcript), 2200);
    }, Math.min(4000, d.transcript.length * 11 + 600));
  };

  const start = async () => {
    rec.current = await recordWav();
    setState("listening");
    const tick = () => {
      setLevel(rec.current?.level() ?? 0);
      raf.current = requestAnimationFrame(tick);
    };
    tick();
  };
  const stop = async () => {
    cancelAnimationFrame(raf.current);
    const wav = await rec.current!.stop();
    await send(wav);
  };
  // the film plays a recorded mission through the same path: listen() while it is heard, then sendUrl(wav)
  (window as unknown as { __voice: object }).__voice = {
    listen: () => {
      setState("listening");
      const t0 = performance.now();
      const tick = () => {
        const k = (performance.now() - t0) / 1000;
        setLevel(0.25 + 0.2 * Math.abs(Math.sin(k * 7.3)) * Math.abs(Math.sin(k * 2.1 + 1)));
        raf.current = requestAnimationFrame(tick);
      };
      tick();
    },
    sendUrl: async (url: string) => {
      cancelAnimationFrame(raf.current);
      return send(await (await fetch(url)).blob());
    },
  };

  return (
    <div className="voice">
      <button
        className={`mic ${state}`}
        onClick={() => (state === "idle" ? start() : state === "listening" ? stop() : undefined)}
        style={{ boxShadow: state === "listening" ? `0 0 0 ${4 + level * 120}px rgba(95,211,255,0.14)` : undefined }}
        aria-label="Speak the mission"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="9" y="3" width="6" height="12" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
        </svg>
      </button>
      <div className="voice-text">
        {state === "idle" && <span className="dim">Or say the mission</span>}
        {state === "listening" && <span style={{ color: "var(--declared)" }}>Listening… click to finish</span>}
        {state === "thinking" && !shown && <span className="dim">Muse Voice Transcribe is listening back…</span>}
        {shown && <span className="serif heard">“{shown}”</span>}
        <AnimatePresence>
          {mission && (
            <motion.div className="chips" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
              {mission.province && <span className="chip">province <b>{mission.province}</b></span>}
              {mission.deadline && <span className="chip">by <b>{mission.deadline}</b>{mission.deadline_label ? ` · ${mission.deadline_label}` : ""}</span>}
              {mission.budget_usd != null && <span className="chip">model budget <b>${mission.budget_usd}</b></span>}
              {mission.focus.map((f) => <span key={f} className="chip">first <b>{f}</b></span>)}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
