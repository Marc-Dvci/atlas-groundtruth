import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { plain, readLines, tamper, verifyBlob, verifyLines, type Line, type Result } from "./verify";
import { url } from "../api";

const ease = [0.22, 1, 0.36, 1] as const;

type P = Record<string, any>;
const MODEL: Record<string, string> = { "muse-spark-1.3": "Muse Spark 1.3", "muse-spark-1.3-contributor": "Muse Spark 1.3",
  "meta-models/muse-spark-open-1026": "Muse Spark Open", "muse-wonder-1.0": "Muse Wonder" };

function label(kind: string, actor: string, p: P): string {
  if (kind === "finding") return `${p.finding?.source} · ${p.finding?.claim}`;
  if (kind === "tool_call") return `${p.tool}(${Object.values(p.args ?? {}).slice(0, 2).join(", ")})`;
  if (kind === "capture") return `capture ${p.capture?.captured} · ${p.capture?.sensor ?? ""} · ${String(p.blob ?? "").slice(0, 10)}…`;
  if (kind === "verdict") return `${p.outcome} · ${p.reason}`;
  if (kind === "signature") return `signed by ${actor.replace("human:", "")} · ${p.decision}`;
  if (kind === "case_file") return `case file · ${String(p.file?.headline ?? "").slice(0, 70)}`;
  if (kind === "located") return `located · ${p.waterway ?? ""} · pin ${p.pin_offset_m ?? "?"} m off`;
  if (kind === "imagery_reading") return `${MODEL[p.model] ?? p.model ?? "model"} reads the captures · ${String(p.answer?.change ?? "")}`;
  if (kind === "relocation_search") return `relocation search · ${p.found ? `new wall ${p.distance_m} m away` : "nothing built elsewhere"}`;
  return kind.replace(/_/g, " ");
}

function blobs(p: unknown, out: string[] = []): string[] {
  if (Array.isArray(p)) p.forEach((x) => blobs(x, out));
  else if (p && typeof p === "object")
    for (const [k, v] of Object.entries(p as P)) {
      if ((k === "blob" || k.endsWith("_blob")) && typeof v === "string") out.push(v);
      else blobs(v, out);
    }
  return out;
}

export function LedgerView({ run, id }: { run: string; id: string }) {
  const [lines, setLines] = useState<Line[] | null>(null);
  const [check, setCheck] = useState<(Result & { blobs?: [number, number] }) | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [tam, setTam] = useState<{ changed: { seq: number; from: string; to: string; source: string } | null; tampered: Result;
    original: Result; lines: Line[] } | null>(null);

  useEffect(() => {
    fetch(url.ledgerRaw(run)).then((r) => r.text()).then((t) => setLines(readLines(t)));
  }, [run]);
  const mine = useMemo(() => (tam?.lines ?? lines ?? []).filter((l) => l.case === id), [lines, tam, id]);

  const verify = async () => {
    if (!lines) return;
    setCheck(null);
    setTam(null);
    setProgress(0);
    const r = await verifyLines(lines, (n) => setProgress(n));
    const names = [...new Set(mine.flatMap((l) => blobs(plain(l.raw.payload))))];
    let good = 0;
    for (const n of names) if (await verifyBlob(url.evidence(n), n)) good++;
    setProgress(null);
    setCheck({ ...r, blobs: [good, names.length] });
  };
  const doTamper = async () => {
    if (!lines) return;
    setCheck(null);
    const t = tamper(lines, id);
    const [tampered, original] = await Promise.all([verifyLines(t.lines), verifyLines(lines)]);
    setTam({ changed: t.changed, tampered, original, lines: t.lines });
  };
  (window as unknown as { __ledger: object }).__ledger = { verify, doTamper };
  const bad = tam?.tampered.first_bad;

  return (
    <div className="evalpage ledgerpage">
      <header className="case-head" style={{ position: "relative", top: 0, left: 0 }}>
        <a href={`#/case/${run}/${id}`} className="mono back">← case {id}</a>
        <span className="mono" style={{ letterSpacing: "0.32em", fontWeight: 600 }}>ATLAS</span>
        <span className="mono dim">evidence ledger · run {run}</span>
      </header>
      <div className="ledger-grid">
        <div>
          <div className="eyebrow" style={{ marginTop: 44 }}>Evidence ledger</div>
          <h1 className="serif" style={{ fontSize: 50, lineHeight: 1.05, fontWeight: 400, margin: "12px 0 14px" }}>
            Every reading, mask and verdict is sealed to the one before it.
          </h1>
          <p className="lede" style={{ fontSize: 16 }}>
            Each entry carries the SHA-256 of the previous entry. Images are stored under the hash of their own bytes.
            Change one word or one pixel anywhere, and every seal after it breaks. The check below runs in this browser:
            it trusts nothing the server says.
          </p>
          <div style={{ display: "flex", gap: 12, marginTop: 10 }}>
            <button className="pill" onClick={verify} disabled={!lines}>
              {progress != null ? `Checking ${progress} of ${lines?.length}…` : "Verify the chain"}
            </button>
            <button className="pill ghost" onClick={doTamper} disabled={!lines}>Edit one sealed claim in a copy</button>
          </div>
          <AnimatePresence>
            {check && (
              <motion.div key="chk" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }} className="verify">
                <span className="serif" style={{ color: check.ok ? "var(--exists)" : "var(--ghost)", fontSize: 30 }}>
                  {check.ok ? "Chain intact" : `Broken at #${check.first_bad}`}
                </span>
                <span className="mono dim">
                  {check.entries.toLocaleString("en-US")} entries re-hashed in {Math.round(check.ms)} ms
                  {check.blobs ? ` · ${check.blobs[0]} of ${check.blobs[1]} evidence files match their seal` : ""}
                </span>
              </motion.div>
            )}
            {tam && (
              <motion.div key="tmp" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }} className="verify">
                <span className="mono dim">
                  In a copy, entry #{tam.changed?.seq} ({tam.changed?.source}) was edited from “{tam.changed?.from}” to “{tam.changed?.to}”.
                </span>
                <span className="serif" style={{ color: "var(--ghost)", fontSize: 30 }}>Broken at #{tam.tampered.first_bad}</span>
                <span className="mono dim">
                  {tam.tampered.reason}. The original still verifies: {tam.original.ok ? "intact" : "broken"}.
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <ol className="chain">
          {mine.map((l, i) => {
            const broken = bad != null && l.seq >= bad;
            const edited = tam?.changed?.seq === l.seq;
            return (
              <motion.li key={l.seq} className={`${broken ? "broken" : check?.ok ? "ok" : ""} ${edited ? "edited" : ""}`}
                initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}
                transition={{ delay: Math.min(1.5, 0.03 * i), duration: 0.5, ease }}>
                <span className="mono seq">#{l.seq}</span>
                <span className="who mono">{String(l.raw.actor)}</span>
                <span className="what">{label(l.kind, String(l.raw.actor), (plain(l.raw.payload) ?? {}) as P)}</span>
                <span className="mono hash">
                  {l.hash.slice(0, 12)}
                  <span className="dim"> ← {l.prev.slice(0, 6)}</span>
                </span>
              </motion.li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
