import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { OUTCOME_COLOR, OUTCOME_LABEL, type Outcome } from "../data";
import { url } from "../api";

type Row = {
  id: string; match: string; official: string; who: string; atlas: Outcome; reason: string; agree: boolean;
  abstain: boolean; partial: boolean; contradict: boolean; headline: string; quote: string; date: string; sources: string[];
  desc: string; cost: number; muni: string;
};
type Tally = { cases: number; agree: number; partial: number; abstain: number; contradict: number };
type Ev = { run: string; cases: number; agree: number; partial: number; abstain: number; contradict: number; rows: Row[];
  by_match?: { exact_or_strong: Tally; candidate: Tally } };
type Cmp = { a: string; b: string; cases: number; same_verdict: number; same_site: number; readings_compared: number;
  readings_agree: number; rows: { id: string; same_verdict: boolean; site_gap_m: number | null }[] };

const OFFICIAL: Record<string, string> = {
  ghost: "Ghost", existed_before_contract: "Existed before the contract", relocated: "Built elsewhere",
  not_built_at_site: "Not built at the approved site", not_built_when_declared: "Not built when declared complete",
};
const ease = [0.22, 1, 0.36, 1] as const;

export function EvalView({ run }: { run: string }) {
  const [ev, setEv] = useState<Ev | null>(null);
  const [cmp, setCmp] = useState<Cmp | null>(null);
  const other = new URLSearchParams(window.location.search).get("open") ?? `${run}-open`;
  useEffect(() => {
    fetch(url.evaluation(run)).then((r) => r.json()).then(setEv);
    fetch(url.compare(run, other)).then((r) => (r.ok ? r.json() : null)).then((d) => d?.cases && setCmp(d)).catch(() => {});
  }, [run, other]);
  if (!ev) return null;
  return (
    <div className="evalpage">
      <header className="case-head" style={{ position: "relative", top: 0, left: 0 }}>
        <a href="#" className="mono back">← Atlas</a>
        <span className="mono" style={{ letterSpacing: "0.32em", fontWeight: 600 }}>ATLAS</span>
        <span className="mono dim">evaluation · run {ev.run}</span>
      </header>
      <div className="eyebrow" style={{ marginTop: 48 }}>Against the official record</div>
      <h1 className="serif" style={{ fontSize: 56, lineHeight: 1.04, fontWeight: 400, margin: "12px 0 10px", maxWidth: 1100 }}>
        {ev.cases} contracts that auditors, the ICI or the President already ruled on.
      </h1>
      <p className="lede">
        Atlas audited each one without seeing the ruling. It agreed {ev.agree} times
        {ev.partial > 0 && <>, confirmed the structure without being able to date it {ev.partial} times</>}, declined to
        decide {ev.abstain} times (the evidence did not reach its two-source standard), and contradicted the official
        finding {ev.contradict} times.
      </p>
      <div className="evalstats">
        <div><span className="serif" style={{ color: "var(--exists)" }}>{ev.agree}</span><span className="eyebrow">agree</span></div>
        <div><span className="serif" style={{ color: "var(--before)" }}>{ev.partial}</span><span className="eyebrow">consistent, undated</span></div>
        <div><span className="serif" style={{ color: "var(--unverified)" }}>{ev.abstain}</span><span className="eyebrow">can't verify</span></div>
        <div><span className="serif" style={{ color: "var(--ghost)" }}>{ev.contradict}</span><span className="eyebrow">contradict</span></div>
      </div>
      {ev.by_match && (
        <p className="lede" style={{ marginTop: 18 }}>
          On the {ev.by_match.exact_or_strong.cases} contracts matched to an official finding exactly or strongly, Atlas
          {" "}agreed {ev.by_match.exact_or_strong.agree} times, was consistent {ev.by_match.exact_or_strong.partial} times, declined
          {" "}{ev.by_match.exact_or_strong.abstain} times and contradicted the finding {ev.by_match.exact_or_strong.contradict} times.
        </p>
      )}
      {cmp && (
        <motion.div className="openrow" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease }}>
          <div className="eyebrow">Open weights</div>
          <div className="openstats">
            <div><span className="serif">{cmp.same_verdict}<small>/{cmp.cases}</small></span><span className="eyebrow">same verdict</span></div>
            <div><span className="serif">{cmp.same_site}<small>/{cmp.cases}</small></span><span className="eyebrow">same site located</span></div>
            <div><span className="serif">{cmp.readings_agree}<small>/{cmp.readings_compared}</small></span><span className="eyebrow">capture readings agree</span></div>
          </div>
          <p className="dim" style={{ maxWidth: 760, margin: "10px 0 0" }}>
            The same audits run end to end on Muse Spark Open, the open-weights model an audit institution can serve on its own
            hardware. Readings are compared where both runs located the same reach.
          </p>
        </motion.div>
      )}
      <div className="evalrows">
        {ev.rows.map((r, i) => (
          <motion.a key={r.id} href={`#/case/${run}/${r.id}`} className="evalrow"
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 * i, duration: 0.6, ease }}>
            <div className="er-id">
              <span className="mono">{r.id}</span>
              <span className="dim">{r.muni} · ₱{(r.cost / 1e6).toFixed(1)}M</span>
              <span className="mono match">{r.match} match</span>
            </div>
            <div className="er-official">
              <div className="serif">{OFFICIAL[r.official] ?? r.official}</div>
              <div className="dim quote">“{r.quote}” <span className="mono">· {r.who}, {r.date}</span></div>
            </div>
            <div className="er-atlas">
              <div className="serif" style={{ color: OUTCOME_COLOR[r.atlas] }}>{OUTCOME_LABEL[r.atlas] ?? r.atlas}</div>
              <div className="dim">{r.headline}</div>
            </div>
            <div className={`er-mark mono ${r.agree ? "agree" : r.partial ? "partial" : r.abstain ? "abstain" : "contra"}`}>
              {r.agree ? "agree" : r.partial ? "consistent" : r.abstain ? "can't verify" : "contradict"}
            </div>
          </motion.a>
        ))}
      </div>
    </div>
  );
}
