import type { Outcome } from "../data";

export type Finding = {
  agent: string;
  source: string;
  family: string;
  capture_root: string;
  observed: string;
  claim: "present" | "absent" | "inconclusive";
  quality: number;
  note: string;
  entry: string;
  site: string;
};

export type Frame = {
  release: number;
  captured: string;
  release_date: string;
  sensor: string | null;
  resolution_m: number | null;
  provider: string | null;
  window: "before_award" | "during_contract" | "after_completion";
  bbox: [number, number, number, number];
  blob: string;
  masks: { prompt: string; object: number; confidence: number | null; geometry: GeoJSON.Geometry }[];
  coverage: number | null;
  sides?: { left: number; right: number };
  reading?: { date: string; bank: string; structure_visible: string; extent_fraction: number; quality: string; what_i_see: string } | null;
  entry: string;
};

export type Photo = {
  id: string; date: string; distance_m: number; blob: string; creator: string; window: string;
  reading: { river_visible: boolean; bank_visible: boolean; structure: string; what_i_see: string } | null;
};

export type Decision = { finding: Finding; counted: boolean; why: string };

export type Verdict = {
  outcome: Outcome;
  reason: string;
  headline: string;
  explanation: string[];
  counted_roots: string[];
  decisions: Decision[];
};

export type CaseFile = {
  id: string;
  record: {
    id: string;
    desc: string;
    muni: string;
    province: string;
    contractor: string;
    cost: number;
    abc: number | null;
    start: string | null;
    completion: string | null;
    lon: number;
    lat: number;
    flags: { code: string; text: string }[];
    status?: string;
    length_m?: number | null;
    cost_per_m?: number;
    cost_per_m_pct?: number;
  };
  award: string;
  completion: string;
  completion_basis: string;
  locator: {
    located: boolean;
    answer: {
      structure?: string;
      river?: string | null;
      barangays?: string[];
      purok_or_sitio?: string | null;
      section?: string | null;
      stations?: string[];
      declared_length_m?: number | null;
      confidence?: string;
      pin?: string;
      reasoning?: string;
    };
    reach?: GeoJSON.Geometry;
    center?: [number, number];
    length_m?: number;
    declared_length_m?: number | null;
    pin_offset_m?: number;
    pin_to_center_m?: number;
    waterway?: string;
    waterway_source?: string;
    ticks?: { lonlat: [number, number]; label: string; m: number }[];
    mode?: string;
    model?: string | null;
    note?: string;
    waterway_geom?: GeoJSON.Geometry | null;
  };
  frames: Frame[];
  photos?: Photo[];
  s2: {
    before: { n: number; ndvi: number; bright: number; from: string; to: string } | null;
    after: { n: number; ndvi: number; bright: number; from: string; to: string } | null;
    first_change: { date: string; ndvi_before: number; ndvi_after: number; shift: number; bank?: string } | null;
    disturbance?: { date: string; ndvi_before: number; ndvi_after: number; bank: string } | null;
    rows: { date: string; ndvi: number; bright: number }[];
  };
  timeline: { events: { date: string; kind: string; label: string; source: string }[]; first_seen: string | null; flags: string[] };
  valuation: {
    cost_php: number;
    abc_php: number | null;
    length_m: number | null;
    cost_per_m: number | null;
    cost_per_m_pct: number | null;
    flags: { code: string; text: string }[];
    overlaps: { other: string; overlap_m: number; other_desc: string; other_year: number; other_cost: number }[];
    same_amount: number;
    prior?: { id: string; distance_m: number; completion: string; cost: number; contractor: string; desc: string }[];
    barangay_total?: { barangay: string; n: number; php: number; years: [number, number] | null; contractors: number; ids: string[] } | null;
  };
  impact: {
    people_low_ground: number;
    people_in_radius: number;
    radius_m: number;
    rise_m: number;
    bank_elevation_m: number;
    method: string;
    cells_blob: string;
    n_cells: number;
  };
  verdict: Verdict;
  findings: Finding[];
  case_file?: {
    headline: string;
    paragraphs: { text: string; cites: number[] }[];
    limits: string[];
    open_questions: string[];
    requests: string[];
    dropped_uncited: number;
  };
  illustration?: { blob: string; base_capture: string; label: string };
  models?: { lm: string | null; depth: string; spark?: string; writer?: string };
  relocation?: {
    windows: { center: [number, number]; bbox: [number, number, number, number]; new_len_m: number; d_m: number }[];
    best: { center: [number, number]; bbox: [number, number, number, number]; new_len_m: number; d_m: number } | null;
    before: string;
    after: string;
    new_hard_banks: GeoJSON.Geometry[];
    found: boolean;
    confirm?: { new_structure: string; where: string; what_i_see: string };
    distance_m?: number;
    blob_before?: string;
    blob_after?: string;
  } | null;
  seconds: number;
  ledger_head: string;
  error?: string;
};
