import { motion } from "motion/react";

const ease = [0.22, 1, 0.36, 1] as const;

const CARDS: Record<string, { eyebrow?: string; lines: string[]; foot?: string }> = {
  open: { eyebrow: "Atlas", lines: ["What was declared,", "against what the Earth shows."] },
  close: {
    eyebrow: "Atlas · Groundtruth",
    lines: ["Every case cites its evidence.", "A human signs every one."],
    foot: "github.com/Marc-Dvci/atlas-groundtruth",
  },
};

/** Full-screen title cards (the film's first and last frames), in the app's own type. */
export function Card({ id }: { id: string }) {
  const c = CARDS[id] ?? { lines: [decodeURIComponent(id)] };
  return (
    <div className="card-page">
      <div className="pool" style={{ inset: "20% 15%" }} />
      <div style={{ position: "relative" }}>
        {c.eyebrow && (
          <motion.div className="eyebrow" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.2, ease }}
            style={{ letterSpacing: "0.32em", marginBottom: 22 }}>
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
        {c.foot && (
          <motion.div className="mono" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.2, duration: 1.2 }}
            style={{ marginTop: 34, color: "var(--declared)", fontSize: 15 }}>
            {c.foot}
          </motion.div>
        )}
      </div>
    </div>
  );
}
