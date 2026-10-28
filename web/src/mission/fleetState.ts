import type { Outcome } from "../data";

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- event and ledger payloads are free-form JSON
export type Ev = { t: number; kind: string; case: string; agent: string; data: Record<string, any> };

export const AGENTS: { key: string; label: string; model: string }[] = [
  { key: "locator", label: "Locator", model: "Muse Spark" },
  { key: "existence", label: "Existence", model: "SAM 3.1 · Muse Spark" },
  { key: "ground", label: "Ground", model: "Mapillary · Muse Spark" },
  { key: "relocation", label: "Relocation", model: "SAM 3.1 · Muse Spark" },
  { key: "timeline", label: "Timeline", model: "code" },
  { key: "valuation", label: "Valuation", model: "code" },
  { key: "impact", label: "Impact", model: "Meta HRSL" },
  { key: "verdict", label: "Verdict", model: "rules" },
  { key: "casebuilder", label: "Case builder", model: "Muse Wonder" },
];

export type Lane = { case: string; text: string; t: number; n: number };

export type FleetState = {
  status: Record<string, "running" | Outcome>;
  lanes: Record<string, Lane>;
  done: number;
  total: number;
  php: number;
  outcomes: Partial<Record<Outcome, number>>;
  spent: number;
  plan: { projects: number; full_depth: number; budget_usd: number; deadline: string | null; php_total: number; mission: string;
    lm?: string; screening_depth?: number } | null;
  log: { t: number; agent: string; case: string; text: string }[];
  costById: Record<string, number>;
  headline: Record<string, string>;
  verdictById: Record<string, Outcome>;
  finished: boolean;
};

export const empty = (): FleetState => ({
  status: {}, lanes: {}, done: 0, total: 0, php: 0, outcomes: {}, spent: 0, plan: null, log: [], costById: {}, headline: {},
  verdictById: {},
  finished: false,
});

const short = (s: unknown, n = 64) => {
  const t = typeof s === "string" ? s : JSON.stringify(s);
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
};

/** The model behind a lane, as the run actually used it. */
export const laneModel = (model: string, lm?: string) => (lm === "open" ? model.replace("Muse Spark", "Muse Spark Open") : model);

export function describe(e: Ev): string | null {
  const d = e.data;
  switch (`${e.agent}:${e.kind}`) {
    case "locator:start": return "reading the contract";
    case "locator:tool": {
      const a = d.args ?? {};
      const arg = a.name ?? a.waterway_id ?? a.barangay_id ?? (a.lon ? `${(+a.lon).toFixed(4)}, ${(+a.lat).toFixed(4)}` : "");
      return `${d.refused ? "✕ " : ""}${d.tool}(${short(arg, 34)})`;
    }
    case "locator:traced": return `river traced from ${d.captured} imagery`;
    case "locator:located": return `${d.waterway} · ${d.length_m} m · pin ${d.pin_offset_m} m off`;
    case "existence:captures": return `${(d.captures ?? []).length} sub-metre captures`;
    case "existence:frame": return `${d.captured} · hard bank on ${Math.round((d.coverage ?? 0) * 100)}% of reach`;
    case "existence:reading": return short(d.change ?? d.summary, 60);
    case "existence:s2": return d.first_change ? `Sentinel-2: bank changed ${String(d.first_change.date).slice(0, 7)}` : "Sentinel-2: no lasting change";
    case "ground:photos": return `${d.found} street photos, ${d.after_completion} after completion`;
    case "ground:photo": return `${d.date} · ${d.reading?.structure ?? "photo"}`;
    case "timeline:timeline": return d.flags?.[0] ? short(d.flags[0], 60) : `${(d.events ?? []).length} dated events`;
    case "valuation:valuation": return d.overlaps?.length ? `${d.overlaps[0].overlap_m} m also paid under ${d.overlaps[0].other}` : d.flags?.[0]?.text ? short(d.flags[0].text, 60) : "within norms";
    case "impact:impact": return `${Number(d.people_low_ground).toLocaleString("en-US")} people on low ground`;
    case "verdict:verdict": return short(d.headline, 64);
    case "casebuilder:case_file": return short(d.headline, 64);
    case "casebuilder:illustration": return "illustration of the declared wall";
    case "relocation:start": return `walking the waterway · ${d.before} vs ${d.after}`;
    case "relocation:window": return `${d.offset_m > 0 ? "+" : ""}${d.offset_m} m · ${d.new_len_m} m of new hard bank`;
    case "relocation:candidate": return d.found ? `new wall ${d.distance_m} m away` : `candidate ${d.distance_m} m away: nothing new`;
    case "relocation:none": return "nothing built elsewhere on this waterway";
    default: return null;
  }
}

export function reduce(s: FleetState, e: Ev): FleetState {
  const d = e.data;
  if (e.kind === "plan") {
    return { ...s, plan: d as FleetState["plan"], total: d.projects };
  }
  if (e.kind === "finished") {
    return { ...s, finished: true };
  }
  if (e.kind === "progress") {
    return { ...s, spent: d.spent_usd ?? s.spent, total: d.total ?? s.total };
  }
  const status = { ...s.status };
  let { done, php, outcomes, costById, total } = s;
  if (e.kind === "case_start") {
    status[e.case] = "running";
    costById = { ...costById, [e.case]: d.record?.cost ?? 0 };
  }
  if (e.kind === "verdict") {
    status[e.case] = d.outcome;
    s = { ...s, headline: { ...s.headline, [e.case]: d.headline } };
    // a resumed mission re-audits a contract whose run was cut short: its new verdict replaces the old one
    const before = s.verdictById[e.case];
    if (before) {
      outcomes = { ...outcomes, [before]: (outcomes[before] ?? 1) - 1 };
    } else {
      done += 1;
      php += costById[e.case] ?? 0;
    }
    s = { ...s, verdictById: { ...s.verdictById, [e.case]: d.outcome } };
    outcomes = { ...outcomes, [d.outcome]: (outcomes[d.outcome as Outcome] ?? 0) + 1 };
    total = Math.max(total, done);
  }
  s = { ...s, done, php, outcomes, costById, total };
  const text = describe(e);
  if (!text) return status === s.status ? s : { ...s, status };
  const prev = s.lanes[e.agent];
  const lanes = { ...s.lanes, [e.agent]: { case: e.case, text, t: e.t, n: (prev?.n ?? 0) + 1 } };
  const log = [{ t: e.t, agent: e.agent, case: e.case, text }, ...s.log].slice(0, 9);
  return { ...s, status, lanes, log };
}
