import { motion } from "motion/react";
import { useEffect, useState } from "react";

const ease = [0.22, 1, 0.36, 1] as const;

// `then` is a second, smaller group of lines: shown after the first, or on window.__card.next() when the URL has ?cue
// (the film reveals it on the spoken sentence)
const CARDS: Record<string, { eyebrow?: string; lines: string[]; then?: string[]; foot?: string }> = {
  open: { eyebrow: "Atlas", lines: ["What was declared,", "against what the Earth shows."] },
  close: {
    eyebrow: "Atlas · Groundtruth",
    lines: ["1,096 contracts. Two hours. $13."],
    then: ["Wherever a government publishes what it paid for,", "Atlas can now check it from orbit, anywhere on Earth."],
    foot: "github.com/Marc-Dvci/atlas-groundtruth",
  },
};

/** Full-screen title cards (the film's first and last frames), in the app's own type. */
export function Card({ id }: { id: string }) {
  const c = CARDS[id] ?? { lines: [decodeURIComponent(id)] };
  const cued = new URLSearchParams(window.location.search).has("cue");
  const [next, setNext] = useState(!cued);
  useEffect(() => {
    (window as unknown as { __card: object }).__card = { next: () => setNext(true) };
  }, []);
  const at = (i: number) => (cued ? 0.15 * i : 1.7 + 0.4 * i);
  return (
    <div className="card-page">
      <div className="pool" style={{ inset: "20% 15%" }} />
      <div style={{ position: "relative" }}>
        {c.eyebrow && (
          <motion.div className="eyebrow" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.2, ease }}
            style={{ letterSpacing: "0.42em", marginBottom: 26, fontSize: 15, color: "var(--declared)" }}>
            {c.eyebrow}
          </motion.div>
        )}
        {c.lines.map((l, i) => (
          <motion.h1 key={i} className="serif" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 + 0.7 * i, duration: 1.4, ease }}
            style={{ fontSize: 76, lineHeight: 1.05, margin: 0, fontWeight: 400, color: i ? "var(--text-2)" : "var(--text)" }}>
            {l}
          </motion.h1>
        ))}
        {c.then && next && (
          <div style={{ marginTop: 30 }}>
            {c.then.map((l, i) => (
              <motion.p key={i} className="serif" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: at(i), duration: 1.3, ease }}
                style={{ fontSize: 42, lineHeight: 1.18, margin: 0, color: "var(--text-2)" }}>
                {l}
              </motion.p>
            ))}
          </div>
        )}
        {c.foot && next && (
          <motion.div className="mono" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            transition={{ delay: c.then ? at(c.then.length) + 0.4 : 2.2, duration: 1.2 }}
            style={{ marginTop: 34, color: "var(--declared)", fontSize: 15 }}>
            {c.foot}
          </motion.div>
        )}
      </div>
    </div>
  );
}
