import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { OUTCOME_COLOR, OUTCOME_LABEL, fmt } from "../data";
import type { CaseFile } from "./types";
import { STATIC, url } from "../api";
import { readLines, sealLocal, type Line } from "../ledger/verify";
import { CHALLENGES, myKey, signStatement, verifyDecision, type MyKey, type Statement } from "../ledger/sign";
import { smoothScroll } from "../scroll";

const ease = [0.22, 1, 0.36, 1] as const;
const php = (v: number | null | undefined) =>
  v == null ? "—" : v >= 1e9 ? `₱${(v / 1e9).toFixed(2)} billion` : `₱${(v / 1e6).toFixed(1)} million`;

function Section({ id, eyebrow, children }: { id: string; eyebrow: string; children: React.ReactNode }) {
  return (
    <motion.section
      id={`sec-${id}`}
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.9, ease }}
      style={{ padding: "26px 0 4px" }}
    >
      <div className="eyebrow" style={{ marginBottom: 12 }}>
        {eyebrow}
      </div>
      {children}
      <div className="thread" style={{ marginTop: 26 }} />
    </motion.section>
  );
}

/** The contract text, with what the Locator read underlined in the "declared" voice. */
function Declared({ c }: { c: CaseFile }) {
  const a = c.locator.answer ?? {};
  const terms = [a.river, ...(a.barangays ?? []), a.purok_or_sitio, a.section, ...(a.stations ?? [])]
    .filter((x): x is string => !!x && x.length > 2)
    .map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const desc = c.record.desc;
  if (!terms.length) return <span>{desc}</span>;
  const re = new RegExp(`(${terms.join("|")})`, "gi");
  const parts = desc.split(re);
  return (
    <span>
      {parts.map((p, i) =>
        re.test(p) || terms.some((t) => new RegExp(`^${t}$`, "i").test(p)) ? (
          <mark key={i} className="hl-declared">{p}</mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </span>
  );
}

function Stat({ value, label, color }: { value: string; label: string; color?: string }) {
  return (
    <div>
      <div className="serif" style={{ fontSize: 44, lineHeight: 1, color: color ?? "var(--text)" }}>{value}</div>
      <div className="eyebrow" style={{ marginTop: 8 }}>{label}</div>
    </div>
  );
}

type Props = {
  c: CaseFile;
  beat: string; // key of the current beat
  reached: (key: string) => boolean;
  active: number;
  onPickFrame: (i: number) => void;
  tools: { tool: string; args: Record<string, unknown>; refused?: string | null }[];
  run: string;
};

export function Dossier({ c, beat, reached, active, onPickFrame, tools, run }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const spark = c.models?.spark ?? "Muse Spark";
  useEffect(() => {
    const el = document.getElementById(`sec-${beat}`);
    if (el && scroller.current) {
      smoothScroll(scroller.current, el.offsetTop - 90, 1000); // where the first section starts, clear of the top fade
    }
  }, [beat]);
  const v = c.verdict;
  const loc = c.locator;
  const r = c.record;

  return (
    <div ref={scroller} className="dossier">
      <Section id="head" eyebrow={`Contract ${r.id} · ${r.muni}, ${r.province}`}>
        <h1 className="serif" style={{ fontSize: 34, lineHeight: 1.08, margin: "0 0 18px", fontWeight: 400 }}>
          <Declared c={c} />
        </h1>
        <div className="facts">
          <span className="mono">{php(r.cost)}</span>
          <span>{r.contractor}</span>
          <span className="mono">start {c.award}</span>
          <span className="mono" title={c.completion_basis}>declared complete {c.completion}</span>
        </div>
        {c.revision && (
          <p className="note revision">
            Revised after a signed challenge (ledger #{c.revision.challenge_seq}). Before it:{" "}
            {c.revision.previous.map((p, i) => (
              <span key={i}>{i ? "; " : ""}{OUTCOME_LABEL[p.outcome as keyof typeof OUTCOME_LABEL] ?? p.outcome} ({p.reason}), kept as {p.file}</span>
            ))}. Every earlier entry stays on the ledger.
          </p>
        )}
        {c.completion_basis && !c.completion_basis.startsWith("DPWH") && (
          <p className="note">Completion date: {c.completion_basis}.</p>
        )}
      </Section>

      {reached("locate") && (
        <Section id="locate" eyebrow={`Locator · ${loc.mode ?? ""}`}>
          {loc.located ? (
            <>
              <div style={{ display: "flex", gap: 40, marginBottom: 18 }}>
                <Stat value={(loc.pin_offset_m ?? 0) >= 1000 ? `${((loc.pin_offset_m ?? 0) / 1000).toFixed(1)} km` : `${loc.pin_offset_m} m`}
                  label="published pin to the site" color="var(--declared)" />
                <Stat value={`${loc.length_m} m`} label={`reach on ${loc.waterway}`} color="var(--observed)" />
              </div>
              <p className="prose">{loc.answer?.reasoning}</p>
              {tools.length > 0 && (
                <ol className="tooltrace">
                  {tools.map((t, i) => (
                    <li key={i} className={t.refused ? "refused" : ""}>
                      <span className="mono">{t.tool}</span>
                      <span className="mono dim">{JSON.stringify(t.args).slice(0, 80)}</span>
                      {t.refused && <span className="mono refused-tag">refused: {t.refused}</span>}
                    </li>
                  ))}
                </ol>
              )}
              <p className="note">Waterway geometry: {loc.waterway_source}.</p>
            </>
          ) : (
            <p className="prose">Not locatable: {loc.note}</p>
          )}
        </Section>
      )}

      {reached("history") && c.frames.length > 0 && (
        <Section id="history" eyebrow={`Sub-metre history · ${c.frames.length} captures since ${c.frames[0].captured.slice(0, 4)}`}>
          <div className="filmstrip">
            {c.frames.map((f, i) => (
              <button key={f.release} onClick={() => onPickFrame(i)} className={i === active ? "on" : ""}>
                <img src={url.evidence(f.blob)} alt={f.captured} />
                <span className="mono">{f.captured.slice(0, 7)}</span>
                {f.coverage != null && <span className={`mono cov ${f.coverage >= 0.3 ? "yes" : ""}`}>{Math.round(f.coverage * 100)}%</span>}
              </button>
            ))}
          </div>
          {c.frames[active]?.reading && (
            <motion.div key={active} className="reading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5 }}>
              <div className="eyebrow">{spark} reads {c.frames[active].captured}</div>
              {c.frames[active].reading!.banks && (
                <div className="mono dim banks">
                  {c.frames[active].reading!.banks!.map((b) => `${b.side}: ${b.edge}${b.structure === "no" ? "" : `, structure ${b.structure}`}`).join("  ·  ")}
                </div>
              )}
              <p className="prose">{c.frames[active].reading!.what_i_see}</p>
              {c.frames[active].cross && (
                <>
                  <div className="eyebrow" style={{ marginTop: 10 }}>
                    Second reader · {c.frames[active].cross!.model}{c.frames[active].cross!.reference && <> · beside {c.frames[active].cross!.reference}</>} · structure: {c.frames[active].cross!.structure}
                  </div>
                  <p className="prose">{c.frames[active].cross!.what_i_see}</p>
                </>
              )}
            </motion.div>
          )}
          <p className="note">
            Mint: SAM 3.1 "riverbank" masks (hard banks). Blue: SAM 3.1 "river". Percentages: share of the located reach
            with a hard-bank mask beside it.
          </p>
          <ul className="findings">
            {c.findings.filter((f) => f.family === "optical_vhr").map((f) => (
              <li key={f.entry}>
                <span className={`claim ${f.claim}`}>{f.claim}</span>
                <span>{f.source}</span>
                <span className="dim">{f.note}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {reached("elsewhere") && c.relocation && <Elsewhere c={c} spark={spark} />}

      {reached("series") && (
        <Section id="series" eyebrow="Sentinel-2 · the bank, every month">
          {c.s2.before && c.s2.after ? (
            <div style={{ display: "flex", gap: 40 }}>
              <Stat value={c.s2.before.ndvi.toFixed(2)} label={`bank NDVI before the award (${c.s2.before.n} scenes)`} />
              <Stat value={c.s2.after.ndvi.toFixed(2)} label={`after completion (${c.s2.after.n} scenes)`} />
            </div>
          ) : (
            <p className="prose">Too few clear scenes along the bank.</p>
          )}
          <ul className="findings">
            {c.findings.filter((f) => f.family === "optical_hr").map((f) => (
              <li key={f.entry}>
                <span className={`claim ${f.claim}`}>{f.claim}</span>
                <span className="dim">{f.note}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {reached("series") && (c.photos?.length ?? 0) > 0 && (
        <Section id="ground" eyebrow="Street level · Mapillary">
          {c.photos!.map((p) => (
            <figure key={p.id} className="photo">
              <img src={url.evidence(p.blob)} alt={`Mapillary ${p.date}`} />
              <figcaption>
                <span className="mono">{p.date} · {p.distance_m} m from the reach · CC BY-SA, {p.creator}</span>
                {p.reading && <span className="prose">{p.reading.what_i_see}</span>}
              </figcaption>
            </figure>
          ))}
        </Section>
      )}

      {reached("money") && (
        <Section id="money" eyebrow="Timeline and money · computed from the record">
          {c.valuation.barangay_total && c.valuation.barangay_total.n > 1 && (
            <div style={{ display: "flex", gap: 40, marginBottom: 18 }}>
              <Stat value={php(c.valuation.barangay_total.php).replace(" billion", "B").replace(" million", "M")}
                label={`${c.valuation.barangay_total.n} contracts name ${c.valuation.barangay_total.barangay}`} color="#ffc98a" />
              <Stat value={String(c.valuation.barangay_total.contractors)}
                label={`contractors${c.valuation.barangay_total.years ? `, ${c.valuation.barangay_total.years[0]} to ${c.valuation.barangay_total.years[1]}` : ""}`} />
            </div>
          )}
          <ul className="flags">
            {[...c.timeline.flags, ...c.valuation.flags.map((f) => f.text)].map((t, i) => (
              <li key={i}>{t}</li>
            ))}
            {(c.valuation.prior ?? []).length > 0 && (
              <li className="strong">
                {c.valuation.prior!.length} earlier contract{c.valuation.prior!.length > 1 ? "s" : ""} already paid for works within 200 m of
                this reach, completed before it started: {c.valuation.prior!.slice(0, 4).map((p) => `${p.id} (${php(p.cost)}, ${p.completion})`).join(", ")}
              </li>
            )}
            {c.valuation.overlaps.map((o) => (
              <li key={o.other} className="strong">
                {o.overlap_m} m of this reach were also contracted under {o.other} ({o.other_year}, {php(o.other_cost)})
              </li>
            ))}
          </ul>
        </Section>
      )}

      {reached("impact") && c.impact?.people_low_ground != null && (
        <Section id="impact" eyebrow="Who lives behind this reach">
          <Stat value={fmt.format(c.impact.people_low_ground)} label={`people within ${c.impact.radius_m / 1000} km, at most ${c.impact.rise_m} m above the bank`} color="#ffc46b" />
          <p className="note" style={{ marginTop: 14 }}>{c.impact.method} Population: Meta & CIESIN High Resolution Settlement Layer.</p>
        </Section>
      )}

      {reached("verdict") && (
        <Section id="verdict" eyebrow="Verdict · computed by rules, not by a model">
          <div className="serif" style={{ fontSize: 54, lineHeight: 1, color: OUTCOME_COLOR[v.outcome], marginBottom: 14 }}>
            {OUTCOME_LABEL[v.outcome]}
          </div>
          <p className="prose" style={{ fontSize: 17 }}>{v.headline}</p>
          {v.explanation.slice(1).map((t, i) => <p key={i} className="prose" style={{ fontSize: 14 }}>{t}</p>)}
          {c.illustration && (
            <Compare
              observed={url.evidence(c.frames.find((f) => f.captured === c.illustration!.base_capture)?.blob ?? c.frames[c.frames.length - 1].blob)}
              declared={url.evidence(c.illustration.blob)}
              when={c.illustration.base_capture}
            />
          )}
          <Chains c={c} />
          <ul className="decisions">
            {v.decisions.map((d, i) => (
              <li key={i} className={d.counted ? "counted" : "refused"}>
                <span className="mark">{d.counted ? "✓" : "✕"}</span>
                <span>{d.finding.source} <span className="dim">· {d.finding.claim}</span></span>
                <span className="why">{d.why}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {reached("next") && (c.triage?.tier || c.triage?.exists_dated != null) && <Next c={c} run={run} />}

      {reached("file") && (
        <Section id="file" eyebrow={`Case file · ${c.models?.writer ?? "Muse Wonder"}, every paragraph cited`}>
          {c.case_file ? (
            <>
              <h3 className="serif" style={{ fontSize: 26, margin: "0 0 12px", fontWeight: 400 }}>{c.case_file.headline}</h3>
              {c.case_file.paragraphs.map((p, i) => (
                <p key={i} className="prose">
                  {p.text}{" "}
                  {p.cites.map((n) => (
                    <a key={n} className="cite mono" href={`#/ledger/${run}/${c.id}`} title="open the evidence ledger">#{n}</a>
                  ))}
                </p>
              ))}
              {c.case_file.requests.length > 0 && (
                <>
                  <div className="eyebrow" style={{ margin: "18px 0 8px" }}>Request from the agency</div>
                  <ul className="flags">{c.case_file.requests.map((q, i) => <li key={i}>{q}</li>)}</ul>
                </>
              )}
            </>
          ) : (
            <p className="note">No case file: this outcome does not need one, or the run had no model access.</p>
          )}
          <a className="mono ledger-link" href={`#/ledger/${run}/${c.id}`}>Evidence ledger · verify every seal →</a>
          <Sign c={c} run={run} />
        </Section>
      )}
      <div style={{ height: "45vh" }} />
    </div>
  );
}


/** Relocation search: the same waterway walked 1.5 km each way, hard banks before vs after, one candidate read by the model. */
function Elsewhere({ c, spark }: { c: CaseFile; spark: string }) {
  const r = c.relocation!;
  const best = r.best;
  return (
    <Section id="elsewhere" eyebrow={`Relocation search · SAM 3.1 · ${spark}`}>
      <p className="prose">
        The declared reach is bare after completion, so Atlas walked the same waterway: {r.windows.length} windows, the last capture
        before the award ({r.before}) against the first after completion ({r.after}), SAM 3.1 hard-bank masks compared window by
        window.
      </p>
      <div className="walk">
        {r.windows.map((w, i) => (
          <span key={i} className={`walk-w ${w === best || (best && w.center[0] === best.center[0] && w.center[1] === best.center[1]) ? "best" : ""}`}
            style={{ height: 6 + Math.min(54, w.new_len_m / 6) }} title={`${w.d_m} m: ${w.new_len_m} m of new hard bank`} />
        ))}
      </div>
      <div className="note" style={{ marginTop: 6 }}>New hard bank per window, along the waterway.</div>
      {r.blob_before && r.blob_after && (
        <div className="pair">
          <figure><img src={url.evidence(r.blob_before)} alt="before" /><figcaption className="mono">{r.before}</figcaption></figure>
          <figure><img src={url.evidence(r.blob_after)} alt="after" /><figcaption className="mono">{r.after}</figcaption></figure>
        </div>
      )}
      {r.confirm ? (
        <div className="reading">
          <div className="eyebrow">{spark} reads the best candidate, {r.distance_m} m away</div>
          <p className="prose">{r.confirm.what_i_see}</p>
          <p className="prose" style={{ color: r.found ? "var(--relocated)" : "var(--text-2)" }}>
            {r.found ? "A new structure was built here during the contract window." : "No new structure: nothing was built elsewhere either."}
          </p>
        </div>
      ) : (
        <p className="prose">No window gained a hard bank as long as the declared works: nothing was built elsewhere on this waterway.</p>
      )}
    </Section>
  );
}

const centerOf = (g: GeoJSON.Geometry): [number, number] | null => {
  const cs = g.type === "LineString" ? g.coordinates : g.type === "MultiLineString" ? g.coordinates.flat() : [];
  const m = cs[Math.floor(cs.length / 2)];
  return m ? [m[0], m[1]] : null;
};

/** An investigator's decision, signed with this browser's Ed25519 key. A challenge names its reason; a challenge
 * that the works are elsewhere names the reach, and the live server audits the case again there. */
function Sign({ c, run }: { c: CaseFile; run: string }) {
  const [name, setName] = useState(() => {
    try { return localStorage.getItem("atlas-investigator") ?? ""; } catch { return ""; }
  });
  const [key, setKey] = useState<MyKey | null>(null);
  const [open, setOpen] = useState(false);
  const [why, setWhy] = useState("WRONG_SITE");
  const [note, setNote] = useState("");
  const second = c.triage?.second_reach ? centerOf(c.triage.second_reach) : null;
  const [site, setSite] = useState("");
  const [seal, setSeal] = useState<{ hash: string; seq: number; decision: string; verified: boolean; where: string; reaudit: boolean } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    myKey().then(setKey).catch(() => setErr("This browser cannot create an Ed25519 key, so it cannot sign."));
  }, []);

  const go = async (decision: string) => {
    if (!key) return;
    setErr("");
    try { localStorage.setItem("atlas-investigator", name); } catch { /* a remembered name is a convenience only */ }
    let base: { verdict: string; verdict_reason: string; verdict_entry: string; ledger_head: string };
    let lines: Line[] = [];
    if (STATIC) {
      lines = readLines(await (await fetch(url.ledgerRaw(run))).text());
      const v = [...lines].reverse().find((l) => l.case === c.id && l.kind === "verdict");
      base = { verdict: c.verdict.outcome, verdict_reason: c.verdict.reason, verdict_entry: v?.hash ?? "",
        ledger_head: lines[lines.length - 1].hash };
    } else {
      const reg = await (await fetch("/api/investigators")).json();
      if (!reg.investigators.some((r: { key_id: string }) => r.key_id === key.keyId)) {
        const e = await fetch("/api/investigators/enrol", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ public_key: key.publicKey, name }) });
        if (!e.ok) return setErr(await e.text());
      }
      base = await (await fetch(`/api/runs/${run}/cases/${c.id}/to-sign`)).json();
    }
    const challenge = decision === "challenge";
    const st: Statement = {
      run, case: c.id, decision, challenge: challenge ? why : "", note: challenge ? note : "",
      verdict: base.verdict, verdict_reason: base.verdict_reason, verdict_entry: base.verdict_entry,
      ledger_head: base.ledger_head, key_id: key.keyId, signed_at: new Date().toISOString().slice(0, 19) + "Z",
      site: challenge && why === "WRONG_SITE" ? site.replace(/\s+/g, "") : "",
    };
    const payload = { statement: st, public_key: key.publicKey, signature: await signStatement(key, st), investigator: name };
    const verified = await verifyDecision(payload);
    if (STATIC) {
      const e = await sealLocal(lines, c.id, `human:${key.keyId}`, challenge ? "challenge" : "signature", payload);
      return setSeal({ hash: e.hash, seq: e.seq, decision, verified, reaudit: false,
        where: "sealed in this browser with a key made here; no audit office has enrolled it" });
    }
    const r = await fetch(`/api/runs/${run}/cases/${c.id}/sign`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload) });
    if (!r.ok) return setErr(await r.text());
    const e = await r.json();
    setSeal({ hash: e.hash, seq: e.seq, decision, verified, reaudit: !!e.reaudit, where: "sealed on the run's ledger by the server, which checked it against the registry" });
  };
  const DONE: Record<string, string> = { concur: "Concurs", refer_for_site_visit: "Refers for a site visit", dissent: "Dissents",
    challenge: "Challenges the finding" };
  return (
    <div className="sign">
      <div className="eyebrow" style={{ marginBottom: 10 }}>
        Investigator{key ? ` · Ed25519 key ${key.keyId}` : ""}
      </div>
      <AnimatePresence mode="wait">
        {seal ? (
          <motion.div key="seal" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.7, ease }}>
            <div className="serif" style={{ fontSize: 26 }}>{DONE[seal.decision]} · signed by {name}</div>
            <div className="mono seal">ledger #{seal.seq} · {seal.hash.slice(0, 16)}…{seal.hash.slice(-6)}</div>
            <p className="note">
              Signature {seal.verified ? "verifies" : "does NOT verify"} against key {key?.keyId}; {seal.where}.
              {seal.reaudit && " Atlas is auditing the case again at the reach you named: the earlier case file and every earlier entry stay on the record."}
              {seal.decision === "challenge" && why === "WRONG_SITE" && STATIC &&
                " On the live server, a challenge that names a reach starts a new audit there; this static copy has no server."}
            </p>
          </motion.div>
        ) : (
          <motion.div key="form" exit={{ opacity: 0 }}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="name" />
            <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
              <button className="pill" onClick={() => go("concur")} disabled={!name || !key}>Concur and sign</button>
              <button className="pill ghost" onClick={() => go("refer_for_site_visit")} disabled={!name || !key}>Refer for a site visit</button>
              <button className="pill ghost" onClick={() => go("dissent")} disabled={!name || !key}>Dissent</button>
              <button className="pill ghost" onClick={() => setOpen(!open)} disabled={!name || !key}>Challenge…</button>
            </div>
            {open && (
              <div className="challenge">
                {Object.entries(CHALLENGES).map(([k, t]) => (
                  <label key={k} className={why === k ? "on" : ""}>
                    <input type="radio" name="why" checked={why === k} onChange={() => setWhy(k)} />
                    <span>{t}</span>
                  </label>
                ))}
                {why === "WRONG_SITE" && (
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <input className="name mono" style={{ width: 250 }} value={site} onChange={(e) => setSite(e.target.value)}
                      placeholder="lon, lat of the works" />
                    {second && (
                      <button className="pill ghost" onClick={() => setSite(`${second[0].toFixed(6)},${second[1].toFixed(6)}`)}>
                        Use the second Locator's reach
                      </button>
                    )}
                  </div>
                )}
                <textarea className="name" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What the record shows" />
                <button className="pill" onClick={() => go("challenge")}
                  disabled={!name || !key || (why === "WRONG_SITE" && !/^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$/.test(site.trim()))}>
                  Sign the challenge
                </button>
              </div>
            )}
            {err && <div className="note" style={{ color: "var(--ghost)" }}>{err}</div>}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}


const TIER: Record<string, { label: string; color: string; text: string }> = {
  lead: { label: "Lead", color: "var(--ghost)", text: "Nothing on the record explains it: ready for an investigator." },
  needs_plans: { label: "Needs the plans", color: "var(--before)",
    text: "Not a lead yet. The as-built plans must say what this contract added, and where." },
  site_disputed: { label: "Site disputed", color: "var(--relocated)",
    text: "Not a lead yet. A second Locator placed the works elsewhere: confirm which reach the contract paid for." },
  site_unchecked: { label: "Site not re-checked", color: "var(--unverified)", text: "No second Locator has re-located this contract yet." },
  dated: { label: "Dated to this contract", color: "var(--exists)",
    text: "The structure appears in the contract window: the record supports that this contract built what stands here." },
  undated: { label: "Not dated to this contract", color: "var(--before)",
    text: "A structure stands, but nothing ties it to this contract's window: it may be older, or another contract's. Not a clearance." },
};

/** What an investigator does next: the triage rules (atlas/triage.py), over the sealed evidence. */
function Next({ c, run }: { c: CaseFile; run: string }) {
  const t = c.triage!;
  const tier = TIER[t.tier ?? (t.exists_dated ? "dated" : "undated")];
  return (
    <Section id="next" eyebrow="Triage · what happens next, decided by rules">
      <div className="serif" style={{ fontSize: 44, lineHeight: 1, color: tier.color, marginBottom: 12 }}>{tier.label}</div>
      <p className="prose" style={{ fontSize: 16 }}>{tier.text}</p>
      <ul className="decisions">
        {t.reasons.map((r) => (
          <li key={r.code} className={["SITE_CONFIRMED", "BILLED_AS_NEW_NOTHING_ADDED", "DATED_TO_CONTRACT"].includes(r.code) ? "counted" : "refused"}>
            <span className="mark">{["SITE_CONFIRMED", "BILLED_AS_NEW_NOTHING_ADDED", "DATED_TO_CONTRACT"].includes(r.code) ? "✓" : "•"}</span>
            <span>{r.text}</span>
            <span className="why mono">{r.code.toLowerCase().replace(/_/g, " ")}</span>
          </li>
        ))}
      </ul>
      {(t.earlier_contracts?.length ?? 0) > 0 && t.earlier_contracts && (
        <p className="note">
          Earlier contracts near this reach:{" "}
          {t.earlier_contracts.slice(0, 6).map((id, i) => <span key={id} className="mono">{i ? ", " : ""}{id}</span>)}
          {t.earlier_contracts.length > 6 ? "…" : ""}. Pins are unreliable, so they are listed, not counted.
        </p>
      )}
      {t.entry && <a className="mono ledger-link" href={`#/ledger/${run}/${c.id}`}>Sealed as {t.entry.slice(0, 12)}… →</a>}
    </Section>
  );
}

/** Declared vs observed: Muse Image's drawing of what the contract describes, against the real capture. */
function Compare({ observed, declared, when }: { observed: string; declared: string; when: string }) {
  const [x, setX] = useState(50);
  // the film sweeps the divider from the observed capture to the declared illustration and back
  useEffect(() => {
    (window as unknown as { __compare: object }).__compare = {
      sweep: (ms = 3200) => {
        const t0 = performance.now();
        const step = () => {
          const k = Math.min(1, (performance.now() - t0) / ms);
          const e = 0.5 - 0.5 * Math.cos(Math.PI * 2 * k); // 0 -> 1 -> 0
          setX(100 - 100 * e * 0.92);
          if (k < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      },
    };
  }, []);
  return (
    <figure className="compare">
      <div className="compare-box" onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setX(Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)));
      }}>
        <img src={observed} alt="observed" />
        <img src={declared} alt="declared" style={{ clipPath: `inset(0 ${100 - x}% 0 0)` }} />
        <div className="compare-bar" style={{ left: `${x}%` }} />
        <span className="compare-tag l mono">declared · illustration</span>
        <span className="compare-tag r mono">observed · {when}</span>
      </div>
      <figcaption className="note">Left: Muse Image draws what the contract describes onto the real capture. It is an illustration, never evidence.</figcaption>
    </figure>
  );
}

const CHAIN: Record<string, string> = {
  maxar: "Maxar constellation · WorldView, GeoEye, Legion",
  airbus: "Airbus · Pléiades, SPOT",
  s2: "Sentinel-2 · ESA, 10 m",
};

/** One row per physical capture chain: however many captures it holds, it is one source. */
function Chains({ c }: { c: CaseFile }) {
  const rows = new Map<string, { n: number; counted: boolean; claims: Set<string> }>();
  for (const d of c.verdict.decisions) {
    const k = d.finding.capture_root;
    const r = rows.get(k) ?? { n: 0, counted: false, claims: new Set<string>() };
    r.n += 1;
    r.counted ||= d.counted;
    if (d.counted) r.claims.add(d.finding.claim);
    rows.set(k, r);
  }
  if (!rows.size) return null;
  const name = (k: string) => CHAIN[k] ?? (k.startsWith("mapillary:") ? `Mapillary · street photos by ${k.slice(10)}` : k.replace(/^vhr:/, ""));
  return (
    <div className="chains">
      <div className="eyebrow" style={{ marginBottom: 8 }}>Independent sources: {[...rows.values()].filter((r) => r.counted).length} counted</div>
      {[...rows.entries()].map(([k, r]) => (
        <div key={k} className={`chain-row ${r.counted ? "on" : ""}`}>
          <span className="chain-dots">{Array.from({ length: Math.min(r.n, 8) }, (_, i) => <i key={i} />)}</span>
          <span className="chain-name">{name(k)}</span>
          <span className="mono chain-n">{r.n} {r.n === 1 ? "finding" : "findings"} = 1 source{r.counted ? ` · ${[...r.claims].join(", ")}` : ""}</span>
        </div>
      ))}
    </div>
  );
}
