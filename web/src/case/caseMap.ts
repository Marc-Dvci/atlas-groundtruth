import maplibregl, { type Map as MLMap } from "maplibre-gl";
import type { CaseFile } from "./types";
import { url } from "../api";

const DECLARED = "#5fd3ff";
const OBSERVED = "#fff1dc";
const WALL = "#3fe3a7";
const RELOC = "#b38bff";

export function nearestOnLine(p: [number, number], line: [number, number][]): [number, number] {
  let best: [number, number] = line[0];
  let bd = Infinity;
  const k = Math.cos((p[1] * Math.PI) / 180);
  for (let i = 0; i < line.length - 1; i++) {
    const [ax, ay] = line[i];
    const [bx, by] = line[i + 1];
    const dx = (bx - ax) * k;
    const dy = by - ay;
    const t = Math.max(0, Math.min(1, (((p[0] - ax) * k) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy || 1)));
    const q: [number, number] = [ax + t * (bx - ax), ay + t * (by - ay)];
    const d = ((q[0] - p[0]) * k) ** 2 + (q[1] - p[1]) ** 2;
    if (d < bd) {
      bd = d;
      best = q;
    }
  }
  return best;
}

export function reachCoords(c: CaseFile): [number, number][] {
  const g = c.locator.reach;
  if (!g) return [];
  if (g.type === "LineString") return g.coordinates as [number, number][];
  if (g.type === "MultiLineString") return (g.coordinates as [number, number][][]).flat();
  return [];
}

function marker(map: MLMap, lonlat: [number, number], html: string, cls: string, anchor: maplibregl.PositionAnchor) {
  const el = document.createElement("div");
  el.className = cls;
  el.innerHTML = html;
  return new maplibregl.Marker({ element: el, anchor }).setLngLat(lonlat).addTo(map);
}

export type CaseLayers = {
  showFrame: (i: number) => void;
  showMasks: (on: boolean) => void;
  showPin: (on: boolean) => void;
  showReach: (on: boolean) => void;
  showPeople: (on: boolean, cells?: [number, number, number][]) => void;
  showIllustration: (on: boolean) => void;
  showRelocation: (on: boolean) => void;
  dispose: () => void;
};

export function setupCaseLayers(map: MLMap, c: CaseFile): CaseLayers {
  const ids: string[] = [];
  const srcs: string[] = [];
  const markers: maplibregl.Marker[] = [];
  const add = (layer: maplibregl.LayerSpecification, before?: string) => {
    map.addLayer(layer, before);
    ids.push(layer.id);
  };
  const src = (id: string, s: maplibregl.SourceSpecification) => {
    map.addSource(id, s);
    srcs.push(id);
  };

  // Imagery history: one raster per capture, cross-faded by opacity.
  c.frames.forEach((f) => {
    src(`wb-${f.release}`, {
      type: "raster",
      tiles: [url.wayback(f.release)],
      tileSize: 256,
      maxzoom: 18,
      attribution: "Imagery © Esri World Imagery Wayback; Maxar / Vantor",
    });
    add({
      id: `wb-${f.release}`,
      type: "raster",
      source: `wb-${f.release}`,
      paint: { "raster-opacity": 0, "raster-opacity-transition": { duration: 900 }, "raster-fade-duration": 0 },
    });
  });

  const pin: [number, number] = [c.record.lon, c.record.lat];
  const reach = reachCoords(c);
  const foot = reach.length ? nearestOnLine(pin, reach) : pin;

  src("c-masks", {
    type: "geojson",
    data: {
      type: "FeatureCollection",
      features: c.frames.flatMap((f, i) =>
        f.masks.map((m) => ({ type: "Feature" as const, geometry: m.geometry, properties: { i, prompt: m.prompt } })),
      ),
    },
  });
  const maskColor: maplibregl.ExpressionSpecification = ["match", ["get", "prompt"], "river", "#4f8dff", WALL];
  add({ id: "c-mask-fill", type: "fill", source: "c-masks", filter: ["==", ["get", "i"], -1],
    paint: { "fill-color": maskColor, "fill-opacity": ["match", ["get", "prompt"], "river", 0.22, 0.38] } });
  add({ id: "c-mask-line", type: "line", source: "c-masks", filter: ["==", ["get", "i"], -1],
    paint: { "line-color": maskColor, "line-width": ["match", ["get", "prompt"], "river", 1, 1.8], "line-opacity": 0.95 } });

  src("c-people", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  add({ id: "c-people", type: "circle", source: "c-people",
    paint: {
      "circle-color": "#ffc46b",
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 13, ["*", 0.6, ["sqrt", ["get", "n"]]], 17, ["*", 2.6, ["sqrt", ["get", "n"]]]],
      "circle-blur": 0.6,
      "circle-opacity": 0,
      "circle-opacity-transition": { duration: 1400 },
    } });

  // Relocation search: the windows walked along the waterway, the best one, and the banks that turned hard.
  const rel = c.relocation;
  const box = (b: [number, number, number, number]) => [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]];
  src("c-reloc-win", {
    type: "geojson",
    data: {
      type: "FeatureCollection",
      features: (rel?.windows ?? []).map((w) => ({
        type: "Feature" as const,
        geometry: { type: "Polygon" as const, coordinates: [box(w.bbox)] },
        properties: { best: !!rel?.best && w.center[0] === rel.best.center[0] && w.center[1] === rel.best.center[1] ? 1 : 0, n: w.new_len_m },
      })),
    },
  });
  add({ id: "c-reloc-win", type: "line", source: "c-reloc-win",
    paint: { "line-color": ["case", ["==", ["get", "best"], 1], RELOC, OBSERVED], "line-width": ["case", ["==", ["get", "best"], 1], 2, 0.8],
      "line-dasharray": [2, 2], "line-opacity": 0, "line-opacity-transition": { duration: 900 } } });
  src("c-reloc-new", {
    type: "geojson",
    data: { type: "FeatureCollection", features: (rel?.new_hard_banks ?? []).map((g) => ({ type: "Feature" as const, geometry: g, properties: {} })) },
  });
  add({ id: "c-reloc-new", type: "fill", source: "c-reloc-new",
    paint: { "fill-color": RELOC, "fill-opacity": 0, "fill-opacity-transition": { duration: 900 } } });
  if (c.locator.waterway_geom) {
    src("c-waterway", { type: "geojson", data: { type: "Feature", geometry: c.locator.waterway_geom, properties: {} } });
    add({ id: "c-waterway", type: "line", source: "c-waterway",
      paint: { "line-color": DECLARED, "line-width": 1.2, "line-opacity": 0, "line-opacity-transition": { duration: 900 } } });
  }

  src("c-reach", { type: "geojson", data: { type: "Feature", geometry: { type: "LineString", coordinates: reach }, properties: {} } });
  add({ id: "c-reach-glow", type: "line", source: "c-reach",
    paint: { "line-color": OBSERVED, "line-width": 16, "line-blur": 12, "line-opacity": 0, "line-opacity-transition": { duration: 900 } } });
  add({ id: "c-reach", type: "line", source: "c-reach", layout: { "line-cap": "round" },
    paint: { "line-color": OBSERVED, "line-width": 3, "line-opacity": 0, "line-opacity-transition": { duration: 900 } } });
  src("c-ticks", {
    type: "geojson",
    data: { type: "FeatureCollection", features: (c.locator.ticks ?? []).map((t) => ({ type: "Feature" as const, geometry: { type: "Point" as const, coordinates: t.lonlat }, properties: { l: t.label } })) },
  });
  add({ id: "c-ticks", type: "circle", source: "c-ticks",
    paint: { "circle-radius": 2.6, "circle-color": OBSERVED, "circle-stroke-color": "#04060a", "circle-stroke-width": 1, "circle-opacity": 0, "circle-stroke-opacity": 0, "circle-opacity-transition": { duration: 900 } } });

  src("c-offset", { type: "geojson", data: { type: "Feature", geometry: { type: "LineString", coordinates: [pin, foot] }, properties: {} } });
  add({ id: "c-offset", type: "line", source: "c-offset",
    paint: { "line-color": DECLARED, "line-width": 1.6, "line-dasharray": [2, 2], "line-opacity": 0, "line-opacity-transition": { duration: 700 } } });
  src("c-pin", { type: "geojson", data: { type: "Feature", geometry: { type: "Point", coordinates: pin }, properties: {} } });
  add({ id: "c-pin-halo", type: "circle", source: "c-pin",
    paint: { "circle-radius": 22, "circle-color": DECLARED, "circle-opacity": 0, "circle-blur": 0.8, "circle-opacity-transition": { duration: 700 } } });
  add({ id: "c-pin", type: "circle", source: "c-pin",
    paint: { "circle-radius": 6, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": DECLARED, "circle-stroke-width": 2.5, "circle-stroke-opacity": 0, "circle-stroke-opacity-transition": { duration: 700 } } });

  const pinLabel = marker(map, pin, `<span>Published pin</span>`, "map-label declared", "bottom-left");
  const off = c.locator.pin_offset_m ?? 0;
  const mid: [number, number] = [(pin[0] + foot[0]) / 2, (pin[1] + foot[1]) / 2];
  const offLabel = marker(map, mid, `<span class="mono">${off >= 1000 ? (off / 1000).toFixed(1) + " km" : off + " m"}</span>`, "map-label declared small", "left");
  const rc = c.locator.center ?? pin;
  const reachLabel = marker(map, rc,
    `<span>${c.locator.waterway ?? "Located reach"}</span><span class="mono dim">${c.locator.length_m ?? ""} m</span>`, "map-label observed", "top-left");
  markers.push(pinLabel, offLabel, reachLabel);
  const vis = (m: maplibregl.Marker, on: boolean) => m.getElement().classList.toggle("on", on);
  [pinLabel, offLabel, reachLabel].forEach((m) => vis(m, false));

  let active = -1;
  let masksOn = false;
  const api: CaseLayers = {
    showFrame(i) {
      c.frames.forEach((f, k) => map.setPaintProperty(`wb-${f.release}`, "raster-opacity", k === i ? 1 : 0));
      active = i;
      const filt: maplibregl.FilterSpecification = ["==", ["get", "i"], masksOn ? active : -1];
      map.setFilter("c-mask-fill", filt);
      map.setFilter("c-mask-line", filt);
    },
    showMasks(on) {
      masksOn = on;
      api.showFrame(active);
    },
    showPin(on) {
      map.setPaintProperty("c-pin", "circle-stroke-opacity", on ? 1 : 0);
      map.setPaintProperty("c-pin-halo", "circle-opacity", on ? 0.35 : 0);
      vis(pinLabel, on);
    },
    showReach(on) {
      map.setPaintProperty("c-reach", "line-opacity", on ? 1 : 0);
      map.setPaintProperty("c-reach-glow", "line-opacity", on ? 0.45 : 0);
      map.setPaintProperty("c-ticks", "circle-opacity", on ? 1 : 0);
      map.setPaintProperty("c-ticks", "circle-stroke-opacity", on ? 1 : 0);
      map.setPaintProperty("c-offset", "line-opacity", on && off > 15 ? 0.9 : 0);
      vis(reachLabel, on);
      vis(offLabel, on && off > 15);
    },
    showPeople(on, cells) {
      if (cells) {
        (map.getSource("c-people") as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: cells.map(([x, y, n]) => ({ type: "Feature", geometry: { type: "Point", coordinates: [x, y] }, properties: { n } })),
        });
      }
      map.setPaintProperty("c-people", "circle-opacity", on ? 0.85 : 0);
    },
    showIllustration() {},
    showRelocation(on) {
      map.setPaintProperty("c-reloc-win", "line-opacity", on ? 0.9 : 0);
      map.setPaintProperty("c-reloc-new", "fill-opacity", on ? 0.55 : 0);
      if (map.getLayer("c-waterway")) map.setPaintProperty("c-waterway", "line-opacity", on ? 0.7 : 0);
    },
    dispose() {
      markers.forEach((m) => m.remove());
      ids.reverse().forEach((id) => map.getLayer(id) && map.removeLayer(id));
      srcs.forEach((id) => map.getSource(id) && map.removeSource(id));
    },
  };
  return api;
}
