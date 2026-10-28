import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { OUTCOME_COLOR, OUTCOME_LABEL, type Outcome } from "../data";

const ease = [0.22, 1, 0.36, 1] as const;
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- event and ledger payloads are free-form JSON
type Ev = { t: number; kind: string; case: string; agent: string; data: Record<string, any> };
type Status = { enabled: boolean; open: boolean; running: { run: string; id: string; started: number } | null; spent_usd: number;
  budget_usd: number; today: number; per_day: number; recent: { run: string; id: string; outcome: Outcome | null; seconds: number | null; done: boolean }[] };

/** One line per agent step: what it did, in its own words where it has them. */
function brief(e: Ev): string | null {
  const d = e.data ?? {};
  const k = `${e.agent}:${e.kind}`;
  if (e.kind === "ledger") return null;
  if (k === "fleet:case_start") return `Contract ${d.record?.id}: ${d.record?.desc}`;
  if (k === "locator:tool") return `${d.tool}(${Object.values(d.args ?? {}).slice(0, 3).map((x) => JSON.stringify(x)).join(", ")})${d.refused ? ` refused: ${d.refused}` : ""}`;
  if (k === "locator:answer") return `reads the contract: ${d.river ?? "no river named"} · ${(d.barangays ?? []).join(", ")} · ${d.confidence} confidence`;
  if (k === "locator:located") return `located ${d.length_m} m of ${d.waterway}, ${d.pin_offset_m} m from the published pin`;
  if (k === "locator:traced") return `SAM 3.1 traced the channel on ${d.captured} imagery`;
  if (k === "existence:captures") return `${(d.captures ?? []).length} distinct sub-metre captures since 2010`;
  if (k === "existence:frame") return `capture ${d.captured}: SAM 3.1 hard banks on ${Math.round((d.coverage ?? 0) * 100)}% of the reach`;
  if (k === "existence:reading") return `Muse Spark reads the captures: ${d.summary ?? d.change ?? ""}`;
  if (k === "existence:s2") return `Sentinel-2: ${d.first_change ? `bank changed from ${d.first_change.date}` : d.disturbance ? `work-like disturbance from ${d.disturbance.date}` : "no lasting change on either bank"}`;
  if (k === "ground:photos") return `Mapillary: ${d.found ?? 0} street photos near the reach, ${d.after_completion ?? 0} after completion`;
  if (k === "ground:photo") return `street photo ${d.date}: ${d.reading?.structure ?? ""}`;
  if (e.kind === "finding") return `finding · ${d.finding?.source} · ${d.finding?.claim} (quality ${d.finding?.quality})`;
  if (k === "timeline:timeline") return `timeline: ${(d.flags ?? []).join("; ") || "no date flag"}`;
  if (k === "valuation:valuation") return `money: ${(d.flags ?? []).map((f: { text: string }) => f.text).join("; ") || "no money flag"}`;
  if (k === "impact:impact") return `${d.people_low_ground?.toLocaleString("en-US")} people on low ground behind the reach`;
  if (k === "verdict:verdict") return `VERDICT (rules): ${d.headline}`;
  if (k === "casebuilder:case_file") return `Muse Wonder wrote the case file: ${d.headline}`;
  if (k === "fleet:error") return `error: ${d.error}`;
  if (d.text) return String(d.text);
  return null;
}

export function LiveView() {
  const [st, setSt] = useState<Status | null>(null);
  const [run, setRun] = useState<{ run: string; id: string } | null>(null);
  const [evs, setEvs] = useState<Ev[]>([]);
  const [seals, setSeals] = useState(0);
  const [verdict, setVerdict] = useState<{ outcome: Outcome; headline: string } | null>(null);
  const [done, setDone] = useState(false);
  const [id, setId] = useState("");
  const [err, setErr] = useState("");
  const feed = useRef<HTMLOListElement>(null);
  const status = () => fetch("/api/live/status").then((r) => r.json()).then((s: Status) => {
    setSt(s);
    return s;
  });
  useEffect(() => {
    status().then((s) => s.running && setRun({ run: s.running.run, id: s.running.id }));
  }, []);
  useEffect(() => {
    if (!run) return;
    setEvs([]);
    setSeals(0);
    setVerdict(null);
    setDone(false);
    const es = new EventSource(`/api/runs/${run.run}/events`);
    es.onmessage = (m) => {
      const e = JSON.parse(m.data) as Ev;
      if (e.kind === "ledger") return setSeals((n) => n + 1);
      if (e.agent === "verdict" && e.kind === "verdict") setVerdict({ outcome: e.data.outcome, headline: e.data.headline });
      if (e.agent === "fleet" && e.kind === "case_end") {
        setDone(true);
        es.close();
        status();
      }
      setEvs((xs) => [...xs, e]);
    };
    return () => es.close();
  }, [run]);
  useEffect(() => {
    feed.current?.lastElementChild?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [evs.length]);

  const start = async (pick?: string) => {
    setErr("");
    const token = new URLSearchParams(window.location.search).get("token") ?? "";
    const r = await fetch("/api/live/audit", { method: "POST", headers: { "Content-Type": "application/json", "X-Live-Token": token },
      body: JSON.stringify(pick ? { id: pick } : {}) });
    if (r.status === 409) {
      const d = JSON.parse((await r.json()).detail);
      return setRun(d);
    }
    if (!r.ok) return setErr((await r.json()).detail ?? r.statusText);
    const d = await r.json();
    setRun({ run: d.run, id: d.id });
    status();
  };
  const t0 = evs[0]?.t ?? 0;
  const busy = !!run && !done;

  return (
    <div className="evalpage livepage">
      <header className="case-head" style={{ position: "relative", top: 0, left: 0 }}>
        <a href="https://marc-dvci.github.io/atlas-groundtruth/" className="mono back">← recorded demo</a>
        <span className="mono" style={{ letterSpacing: "0.32em", fontWeight: 600 }}>ATLAS</span>
        <span className="mono dim">live audit</span>
      </header>
      <div className="eyebrow" style={{ marginTop: 44 }}>Live</div>
      <h1 className="serif" style={{ fontSize: 52, lineHeight: 1.04, fontWeight: 400, margin: "12px 0 12px", maxWidth: 1000 }}>
        Pick a contract, or let Atlas pick one. It audits it now, from scratch.
      </h1>
      <p className="lede" style={{ maxWidth: 820 }}>
        Full depth, on the Meta Model API: the Locator reads the contract and works through the map, SAM 3.1 and Muse Spark
        read every sub-metre capture since 2010, Muse Spark Open re-reads the decisive ones, Sentinel-2 dates the banks,
        fixed rules decide. The run starts with an empty model cache, so every answer below is a call made now, and every
        step is sealed on a new ledger as it happens.
      </p>
      {st && !st.enabled && <p className="note">Live audits are off on this server.</p>}
      {st?.enabled && !st.open && <p className="note">Live audits on this server are not open to the public yet.</p>}
      {st?.enabled && (
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
          <button className="pill" onClick={() => start()} disabled={busy}>Audit a random Bulacan contract</button>
          <input className="name mono" style={{ width: 150 }} value={id} onChange={(e) => setId(e.target.value)} placeholder="or a contract id" />
          <button className="pill ghost" onClick={() => start(id)} disabled={busy || !id.trim()}>Audit this one</button>
          <span className="mono dim" style={{ fontSize: 12 }}>
            ${st.spent_usd.toFixed(2)} of the ${st.budget_usd.toFixed(0)} live budget spent · {st.today} of {st.per_day} audits today
          </span>
        </div>
      )}
      {err && <p className="note" style={{ color: "var(--ghost)" }}>{err}</p>}
      {run && (
        <div className="live-grid">
          <div>
            <div className="eyebrow" style={{ marginTop: 26 }}>Contract {run.id} · run {run.run}</div>
            <div className="mono dim" style={{ marginTop: 6 }}>{seals} ledger entries sealed{busy ? " · auditing…" : ""}</div>
            {verdict && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease }}>
                <div className="serif" style={{ fontSize: 46, lineHeight: 1, color: OUTCOME_COLOR[verdict.outcome], margin: "18px 0 10px" }}>
                  {OUTCOME_LABEL[verdict.outcome]}
                </div>
                <p className="prose">{verdict.headline}</p>
              </motion.div>
            )}
            {done && (
              <p style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <a className="pill" href={`#/case/${run.run}/${run.id}`}>Open the case</a>
                <a className="pill ghost" href={`#/ledger/${run.run}/${run.id}`}>Verify its ledger</a>
              </p>
            )}
          </div>
          <ol ref={feed} className="live-feed">
            {evs.map((e, i) => {
              const b = brief(e);
              return b ? (
                <li key={i} className={e.agent === "verdict" ? "v" : ""}>
                  <span className="mono dim">{(e.t - t0).toFixed(1)} s</span>
                  <span className="mono who">{e.agent}</span>
                  <span>{b}</span>
                </li>
              ) : null;
            })}
          </ol>
        </div>
      )}
      {st && st.recent.length > 0 && (
        <div style={{ marginTop: 34 }}>
          <div className="eyebrow">Earlier live audits</div>
          <ul className="live-recent">
            {st.recent.map((r) => (
              <li key={r.run}>
                <a href={`#/case/${r.run}/${r.id}`} className="mono">{r.id}</a>
                <span style={{ color: r.outcome ? OUTCOME_COLOR[r.outcome] : "var(--muted)" }}>
                  {r.outcome ? OUTCOME_LABEL[r.outcome] : r.done ? "error" : "running"}
                </span>
                <span className="mono dim">{r.run.slice(5, 20)}{r.seconds ? ` · ${Math.round(r.seconds)} s` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
