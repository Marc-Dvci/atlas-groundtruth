import { url } from "./api";

export type Outcome = "exists" | "exists_before_contract" | "built_late" | "relocated" | "probable_ghost" | "cant_verify";

export type Columns = {
  id: string[];
  lon: number[];
  lat: number[];
  cost: number[]; // PHP millions
  prov: string[];
  muni: string[];
  contractor: string[];
  year: number[];
  susp: number[];
  desc: string[];
  flags: string[][];
  src: number[]; // 0 = the President's portal list (2022-2025), 1 = later DPWH records
};

export const OUTCOME_COLOR: Record<Outcome | "pending" | "running", string> = {
  pending: "#5fd3ff",
  running: "#ffffff",
  exists: "#3fe3a7",
  exists_before_contract: "#f2c94c",
  built_late: "#ff8f3f",
  relocated: "#b38bff",
  probable_ghost: "#ff4b3a",
  cant_verify: "#8a95a6",
};

export const OUTCOME_LABEL: Record<Outcome, string> = {
  exists: "Exists",
  exists_before_contract: "Existed before the contract",
  built_late: "Declared before built",
  relocated: "Built elsewhere",
  probable_ghost: "Probable ghost",
  cant_verify: "Can't verify",
};

let cache: Promise<Columns> | null = null;
export function loadProjects(): Promise<Columns> {
  cache ??= fetch(url.data("projects.min.json")).then((r) => r.json());
  return cache;
}

export function toGeoJSON(c: Columns, filter?: (i: number) => boolean): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (let i = 0; i < c.id.length; i++) {
    if (filter && !filter(i)) continue;
    features.push({
      type: "Feature",
      id: i,
      geometry: { type: "Point", coordinates: [c.lon[i], c.lat[i]] },
      properties: { i, id: c.id[i], cost: c.cost[i], susp: c.susp[i], prov: c.prov[i] },
    });
  }
  return { type: "FeatureCollection", features };
}

export const peso = (m: number) =>
  m >= 1000 ? `₱${(m / 1000).toFixed(m >= 100000 ? 0 : 1)} billion` : `₱${m.toFixed(1)} million`;

export const fmt = new Intl.NumberFormat("en-US");
