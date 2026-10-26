import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";

type Entry = { seq: number; ts: number; case: string; actor: string; kind: string; payload: any; prev: string; hash: string };
type Check = { ok: boolean; first_bad: number | null; reason: string };
const ease = [0.22, 1, 0.36, 1] as const;

function label(e: Entry): string {
  const p = e.payload ?? {};
  if (e.kind === "finding") return `${p.finding?.source} · ${p.finding?.claim}`;
  if (e.kind === "tool_call") return `${p.tool}(${Object.values(p.args ?? {}).slice(0, 2).join(", ")})`;
  if (e.kind === "capture") return `capture ${p.capture?.captured} · ${p.capture?.sensor ?? ""} · ${String(p.blob ?? "").slice(0, 10)}…`;
  if (e.kind === "verdict") return `${p.outcome} · ${p.reason}`;
  if (e.kind === "signature") return `signed by ${e.actor.replace("human:", "")} · ${p.decision}`;
  if (e.kind === "case_file") return `case file · ${String(p.file?.headline ?? "").slice(0, 70)}`;
  if (e.kind === "located") return `located · ${p.waterway ?? ""} · pin ${p.pin_offset_m ?? "?"} m off`;
  return e.kind.replace(/_/g, " ");
}

export function LedgerView({ run, id }: { run: string; id: string }) {
  const [rows, setRows] = useState<Entry[]>([]);
  const [check, setCheck] = useState<Check | null>(null);
  const [tamper, setTamper] = useState<{ changed: any; original: Check; tampered: Check } | null>(null);
  const [checking, setChecking] = useState(false);
  useEffect(() => {
    fetch(`/api/runs/${run}/ledger?case=${id}`)
      .then((r) => r.json())
      .then((r: Entry[]) => setRows(r.filter((e) => e.case === id)));
  }, [run, id]);
  const verify = async () => {
    setChecking(true);
    setCheck(null);
    const r = await fetch(`/api/runs/${run}/verify`).then((x) => x.json());
    setTimeout(() => {
      setCheck(r);
      setChecking(false);
    }, 900);
  };
  const doTamper = async () => {
    const r = await fetch(`/api/runs/${run}/tamper-demo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case: id }),
    }).then((x) => x.json());
    setTamper(r);
  };
  (window as any).__ledger = { verify, doTamper };
  const bad = tamper?.tampered.first_bad;
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
            Change one word or one pixel anywhere, and every seal after it breaks.
          </p>
          <div style={{ display: "flex", gap: 12, marginTop: 10 }}>
            <button className="pill" onClick={verify}>{checking ? "Verifying…" : "Verify the chain"}</button>
            <button className="pill ghost" onClick={doTamper}>Edit one sealed claim in a copy</button>
          </div>
          <AnimatePresence>
            {check && (
              <motion.div key="chk" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }} className="verify">
                <span className="serif" style={{ color: check.ok ? "var(--exists)" : "var(--ghost)", fontSize: 30 }}>
                  {check.ok ? "Chain intact" : `Broken at #${check.first_bad}`}
                </span>
                <span className="mono dim">{check.reason}</span>
              </motion.div>
            )}
            {tamper && (
              <motion.div key="tmp" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }} className="verify">
                <span className="mono dim">
                  In a copy, entry #{tamper.changed?.seq} ({tamper.changed?.source}) was edited from “{tamper.changed?.from}” to “
                  {tamper.changed?.to}”.
                </span>
                <span className="serif" style={{ color: "var(--ghost)", fontSize: 30 }}>Broken at #{tamper.tampered.first_bad}</span>
                <span className="mono dim">
                  {tamper.tampered.reason}. The original still verifies: {tamper.original.ok ? "intact" : "broken"}.
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <ol className="chain">
          {rows.map((e, i) => {
            const broken = bad != null && e.seq >= bad;
            return (
              <motion.li key={e.seq} className={broken ? "broken" : check?.ok ? "ok" : ""}
                initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}
                transition={{ delay: Math.min(1.5, 0.03 * i), duration: 0.5, ease }}>
                <span className="mono seq">#{e.seq}</span>
                <span className="who mono">{e.actor}</span>
                <span className="what">{label(e)}</span>
                <span className="mono hash">
                  {e.hash.slice(0, 12)}
                  <span className="dim"> ← {e.prev.slice(0, 6)}</span>
                </span>
              </motion.li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
