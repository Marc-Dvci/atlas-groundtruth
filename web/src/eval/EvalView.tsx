import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { OUTCOME_COLOR, OUTCOME_LABEL, type Outcome } from "../data";
import { url } from "../api";
import { smoothScroll } from "../scroll";

type Row = {
  id: string; match: string; official: string; who: string; atlas: Outcome; reason: string; agree: boolean;
  abstain: boolean; partial: boolean; contradict: boolean; headline: string; quote: string; date: string; sources: string[];
  desc: string; cost: number; muni: string;
};
const times = (n: number) => (n === 1 ? "once" : n === 2 ? "twice" : `${n} times`);
const looseNote = (n: number, loose: number) =>
  n === 0 ? "never against a ruling"
    : loose === n ? (n === 1 ? "on a contract only loosely tied to a ruling"
      : `${n === 2 ? "both" : "all"} on contracts only loosely tied to a ruling`)
    : `${loose} of ${n} on contracts only loosely tied to a ruling`;

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
  const [focus, setFocus] = useState<number | null>(null);
  const other = new URLSearchParams(window.location.search).get("open") ?? `${run}-open`;
  useEffect(() => {
    fetch(url.evaluation(run)).then((r) => r.json()).then(setEv);
    fetch(url.compare(run, other)).then((r) => (r.ok ? r.json() : null)).then((d) => d?.cases && setCmp(d)).catch(() => {});
  }, [run, other]);
  useEffect(() => {
    (window as unknown as { __eval: object }).__eval = {
      scrollTo: (sel: string, ms = 1400) => {
        const el = document.querySelector(sel) as HTMLElement | null;
        const page = document.querySelector(".evalpage") as HTMLElement | null;
        if (el && page) smoothScroll(page, el.offsetTop - 40, ms);
      },
      top: (ms = 1400) => {
        const page = document.querySelector(".evalpage") as HTMLElement | null;
        if (page) smoothScroll(page, 0, ms);
      },
      // the film points at one tally at a time; null shows them all again
      focus: (i: number | null) => setFocus(i),
    };
  }, []);
  if (!ev) return null;
  // three plain outcomes: what Atlas found fits the ruling (the same finding, or another flag compatible with it),
  // the imagery could not settle the case, or Atlas disagrees with the ruling
  const loose = ev.by_match?.candidate.contradict ?? 0;
  const tally = [
    { n: ev.agree + ev.partial, label: "fit the ruling", color: "var(--exists)",
      note: `${ev.agree} same finding · ${ev.partial} compatible finding${ev.partial === 1 ? "" : "s"}` },
    { n: ev.abstain, label: "can't verify", color: "var(--unverified)", note: "the imagery could not settle the case" },
    { n: ev.contradict, label: "disagree", color: "var(--ghost)", note: looseNote(ev.contradict, loose) },
  ];
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
        Atlas audited each one without seeing the ruling. Where no evidence after completion reached its two-source
        standard, it said it could not verify instead of guessing.
      </p>
      <div className="evaltally">
        {tally.map((t, i) => (
          <motion.div key={t.label} animate={{ opacity: focus === null || focus === i ? 1 : 0.22 }}
            transition={{ duration: 0.5, ease }}>
            <span className="serif" style={{ color: t.color }}>{t.n}</span>
            <span className="tally-label">{t.label}</span>
            <span className="dim tally-note">{t.note}</span>
          </motion.div>
        ))}
      </div>
      {ev.by_match && (
        <p className="lede" style={{ marginTop: 18 }}>
          On the {ev.by_match.exact_or_strong.cases} contracts tied firmly to a ruling (an exact or strong match), what
          Atlas found{" "}
          {[ev.by_match.exact_or_strong.agree + ev.by_match.exact_or_strong.partial > 0 &&
              `fit the ruling ${times(ev.by_match.exact_or_strong.agree + ev.by_match.exact_or_strong.partial)}`,
            ev.by_match.exact_or_strong.abstain > 0 && `could not be verified ${times(ev.by_match.exact_or_strong.abstain)}`]
            .filter(Boolean).join(" and ")}
          {ev.by_match.exact_or_strong.contradict === 0
            ? "; it never disagreed with one."
            : `; it disagreed ${times(ev.by_match.exact_or_strong.contradict)}.`}
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
              {r.agree ? "same finding" : r.partial ? "fits" : r.abstain ? "can't verify" : "disagrees"}
            </div>
          </motion.a>
        ))}
      </div>
    </div>
  );
}
