import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { OUTCOME_COLOR, OUTCOME_LABEL, type Outcome } from "../data";
import { url } from "../api";
import { smoothScroll } from "../scroll";

/** Every ruling in the three answer keys, grouped by what officials found (the key's `finding`, set from the ruling's
 * words when the key was built), against the sealed full-depth verdict. Nothing is re-scored here. */
type Row = { id: string; match: string; official: string; who: string; atlas: Outcome; reason: string; headline: string;
  quote: string; date: string; cost: number; muni: string; cleared?: boolean; not_cleared?: string[] };
type Ev = { rows: Row[] };
type TriageRow = { id: string; outcome: Outcome; tier: string; cost: number };

const KEYS: [string, string][] = [["eval", "cases"], ["blind", "blind_2026-10"], ["blind", "blind_2026-10b"]];
const FLAGS: Outcome[] = ["probable_ghost", "relocated", "built_late", "exists_before_contract"];
const GROUPS: { key: string; label: string; findings: string[] }[] = [
  { key: "not_built", label: "Not built", findings: ["ghost", "not_built_at_site", "not_built_when_declared"] },
  { key: "already", label: "A structure already there", findings: ["existed_before_contract"] },
  { key: "elsewhere", label: "Built elsewhere", findings: ["relocated"] },
  { key: "partly", label: "Partly built", findings: ["partly_built"] },
];
const OFFICIAL: Record<string, string> = {
  ghost: "Ghost", existed_before_contract: "Existed before the contract", relocated: "Built elsewhere",
  not_built_at_site: "Not built at the approved site", not_built_when_declared: "Not built when declared complete",
  partly_built: "Partly built",
};
const NOT_CLEARED: Record<string, string> = {
  NOT_DATED_TO_CONTRACT: "not dated to it", SHARED_REACH: "reach claimed by another contract", SITE_DISPUTED: "site disputed",
  SITE_UNCHECKED: "site unchecked",
};
type Kind = "flagged" | "review" | "none" | "cleared";
const kind = (r: Row): Kind =>
  FLAGS.includes(r.atlas) ? "flagged" : r.cleared ? "cleared"
    : ["NO_POST_COMPLETION_IMAGERY", "SITE_NOT_LOCATABLE"].includes(r.reason) ? "none" : "review";
const ease = [0.22, 1, 0.36, 1] as const;

export function RulingsView() {
  const [rows, setRows] = useState<(Row & { run: string })[] | null>(null);
  const [leads, setLeads] = useState<{ n: number; php: number; people?: number } | null>(null);
  const [focus, setFocus] = useState<number | null>(null);
  useEffect(() => {
    Promise.all(KEYS.map(([run, key]) => fetch(url.evaluation(run, key)).then((r) => r.json() as Promise<Ev>)
      .then((ev) => ev.rows.map((r) => ({ ...r, run })))))
      .then((all) => {
        const flat = all.flat();
        setRows(flat);
        const ruled = new Set(flat.map((r) => r.id));
        fetch(url.triage("bulacan")).then((r) => (r.ok ? r.json() : null)).then((t: { rows: TriageRow[] } | null) => {
          const g = (t?.rows ?? []).filter((x) => x.outcome === "probable_ghost" && x.tier === "lead" && !ruled.has(x.id));
          setLeads({ n: g.length, php: g.reduce((s, x) => s + x.cost, 0) });
          // people on low ground around them, each settlement cell counted once (scripts/instruments.py)
          fetch(url.instruments("bulacan")).then((r) => (r.ok ? r.json() : null))
            .then((m: { ghost_leads_no_ruling?: { contracts: number; people_low_ground: number } } | null) => {
              const x = m?.ghost_leads_no_ruling;
              if (x && x.contracts === g.length) setLeads((l) => (l ? { ...l, people: x.people_low_ground } : l));
            }).catch(() => {});
        }).catch(() => {});
      });
  }, []);
  useEffect(() => {
    (window as unknown as { __rulings: object }).__rulings = {
      // the film points at one number at a time; null shows them all again
      focus: (i: number | null) => setFocus(i),
      scrollTo: (sel: string, ms = 1400) => {
        const el = document.querySelector(sel) as HTMLElement | null;
        const page = document.querySelector(".evalpage") as HTMLElement | null;
        if (el && page) smoothScroll(page, el.offsetTop - 40, ms);
      },
    };
  }, []);
  if (!rows) return null;
  const of = (g: (typeof GROUPS)[number]) => rows.filter((r) => g.findings.includes(r.official));
  const count = (rs: Row[], k: Kind) => rs.filter((r) => kind(r) === k).length;
  const nb = of(GROUPS[0]);
  const tally = [
    { n: count(nb, "flagged"), label: "flagged", color: "var(--exists)",
      note: "on Atlas's full evidence standard: a probable ghost, or a wall at the reach older than the contract" },
    { n: count(nb, "review"), label: "sent with a doubt", color: "var(--unverified)",
      note: "to an investigator, with what the imagery raised: nothing at the reach after completion in one capture chain, a wall another contract built at the same time also claims, or readers split" },
    { n: count(nb, "none"), label: "no image after completion", color: "var(--muted)",
      note: "no capture of the reach after its completion date: sent to an investigator unseen" },
    { n: count(nb, "cleared"), label: "cleared", color: "var(--ghost)", note: "let through as built" },
  ];
  return (
    <div className="evalpage">
      <header className="case-head" style={{ position: "relative", top: 0, left: 0 }}>
        <a href="#" className="mono back">← Atlas</a>
        <span className="mono" style={{ letterSpacing: "0.32em", fontWeight: 600 }}>ATLAS</span>
        <span className="mono dim">the official rulings · by what officials found</span>
      </header>
      <div className="eyebrow" style={{ marginTop: 48 }}>Against the official record</div>
      <h1 className="serif" style={{ fontSize: 56, lineHeight: 1.04, fontWeight: 400, margin: "12px 0 10px", maxWidth: 1100 }}>
        {rows.length} contracts officials had already ruled on.
      </h1>
      <p className="lede">
        Atlas audited each one without seeing the ruling. Officials found {nb.length} of them not built.
      </p>
      <div className="eyebrow" id="notbuilt" style={{ marginTop: 34 }}>Officials found it not built · {nb.length}</div>
      <div className="evaltally" style={{ marginTop: 14 }}>
        {tally.map((t, i) => (
          <motion.div key={t.label} animate={{ opacity: focus === null || focus === i ? 1 : 0.22 }}
            transition={{ duration: 0.5, ease }}>
            <span className="serif" style={{ color: t.color }}>{t.n}</span>
            <span className="tally-label">{t.label}</span>
            <span className="dim tally-note">{t.note}</span>
          </motion.div>
        ))}
      </div>
      {leads && (
        <motion.div className="openrow" id="unnamed" animate={{ opacity: focus === null || focus === 4 ? 1 : 0.22 }}
          transition={{ duration: 0.5, ease }}>
          <div className="eyebrow">Not in any ruling</div>
          <div className="openstats">
            <div>
              <span className="serif">{leads.n}</span>
              <span className="eyebrow">probable ghosts in Bulacan that no published ruling names</span>
            </div>
            <div>
              <span className="serif">₱{(leads.php / 1e9).toFixed(2)}<small> bn</small></span>
              <span className="eyebrow">paid for them</span>
            </div>
            {leads.people !== undefined && (
              <div>
                <span className="serif">{Math.round(leads.people / 1000).toLocaleString("en-US")},000</span>
                <span className="eyebrow">people on low ground around them</span>
              </div>
            )}
          </div>
          <p className="dim" style={{ maxWidth: 820, margin: "10px 0 0" }}>
            Absent in two independent capture chains (or bare, then unchanged), on a reach a second Locator confirmed from
            the contract text alone. Leads for an investigator, never a verdict on their own. People: Meta and CIESIN High
            Resolution Settlement Layer, within 1.5 km of a reach and at most 3 m above its bank, each counted once.
          </p>
        </motion.div>
      )}
      <div className="byatlas">
        <div className="eyebrow">Every ruling, by what officials found</div>
        <table>
          <thead><tr><th>officials found</th><th>rulings</th><th>flagged</th><th>sent with a doubt</th><th>no image after completion</th><th>cleared</th></tr></thead>
          <tbody>
            {GROUPS.map((g) => {
              const rs = of(g);
              return (
                <tr key={g.key}>
                  <td>{g.label}</td><td className="mono">{rs.length}</td><td className="mono">{count(rs, "flagged")}</td>
                  <td className="mono">{count(rs, "review")}</td><td className="mono">{count(rs, "none")}</td>
                  <td className="mono">{count(rs, "cleared")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="dim" style={{ maxWidth: 820 }}>
          Grouped by the finding recorded in the answer keys, from each ruling's own words. Every ruling found a problem, so
          they count what Atlas misses; none can show a contract wrongly flagged. 25CC0063 is flagged under the "bare, then
          unchanged" rule, added on 29 October 2026 after these rulings were known. A structure already there, built
          elsewhere or too short turns on the approved plans or on weeks between captures, which free imagery cannot see.{" "}
          <a href="#/eval/eval" className="mono">the evaluation by answer key →</a>
        </p>
      </div>
      {GROUPS.map((g) => (
        <div key={g.key} className="evalrows" style={{ marginTop: 26 }}>
          <div className="eyebrow">{g.label} · {of(g).length}</div>
          {of(g).map((r) => (
            <a key={r.id} href={`#/case/${r.run}/${r.id}`} className="evalrow">
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
              <div className={`er-mark mono ${kind(r) === "flagged" ? "partial" : kind(r) === "cleared" ? "contra" : "abstain"}`}>
                {kind(r) === "flagged" ? "flagged" : kind(r) === "cleared" ? "cleared" : kind(r) === "none" ? "no image after completion" : "sent with a doubt"}
                {r.atlas === "exists" && !r.cleared && r.not_cleared?.length ? (
                  <span className="dim" style={{ display: "block" }}>{r.not_cleared.map((c) => NOT_CLEARED[c] ?? c).join(" · ")}</span>
                ) : null}
              </div>
            </a>
          ))}
        </div>
      ))}
    </div>
  );
}
