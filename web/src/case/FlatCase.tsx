import { url } from "../api";
import { reachCoords } from "./caseMap";
import type { CaseFile } from "./types";

const my = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const W = 1000;

function rings(g: GeoJSON.Geometry): [number, number][][] {
  if (g.type === "Polygon") return g.coordinates as [number, number][][];
  if (g.type === "MultiPolygon") return (g.coordinates as [number, number][][][]).flat();
  return [];
}

/** The case without WebGL: the sealed capture itself, with the located reach (and, from the History beat, the SAM 3.1
 * hard-bank masks) drawn in the capture's own Web Mercator frame. */
export function FlatCase({ c, active, beat, showMasks }: { c: CaseFile; active: number; beat: string; showMasks: boolean }) {
  const reloc = beat === "elsewhere" && c.relocation?.blob_after && c.relocation.best ? c.relocation : null;
  const f = c.frames[Math.min(active, c.frames.length - 1)];
  const blob = reloc ? reloc.blob_after : f?.blob;
  const bbox = reloc ? reloc.best!.bbox : f?.bbox;
  if (!blob || !bbox) {
    return <p className="nomap mono">This browser cannot start WebGL, so the map is off, and this case has no sub-metre capture to show instead.</p>;
  }
  const [w, s, e, n] = bbox;
  const H = (W * (my(n) - my(s))) / (((e - w) * Math.PI) / 180);
  const X = (lon: number) => ((lon - w) / (e - w)) * W;
  const Y = (lat: number) => ((my(n) - my(lat)) / (my(n) - my(s))) * H;
  const path = (pts: [number, number][]) => pts.map(([lon, lat], i) => `${i ? "L" : "M"}${X(lon).toFixed(1)},${Y(lat).toFixed(1)}`).join("");
  const reach = reachCoords(c);
  const pin: [number, number] = [c.record.lon, c.record.lat];
  const pinIn = pin[0] >= w && pin[0] <= e && pin[1] >= s && pin[1] <= n;
  const masks = showMasks && !reloc ? (f.masks ?? []).filter((m) => m.prompt !== "water") : [];
  return (
    <figure className="flatcase">
      <svg viewBox={`0 0 ${W} ${H.toFixed(1)}`} preserveAspectRatio="xMidYMid meet" role="img"
        aria-label={`Capture of ${reloc ? reloc.after : f.captured} with the located reach`}>
        <image href={url.evidence(blob)} x={0} y={0} width={W} height={H} preserveAspectRatio="none" />
        {masks.map((m, i) => rings(m.geometry).map((r, j) => (
          <path key={`${i}-${j}`} d={path(r) + "Z"} fill="rgba(63, 227, 167, 0.22)" stroke="var(--exists)" strokeWidth={1.2}
            vectorEffect="non-scaling-stroke" />
        )))}
        {reach.length > 1 && (
          <path d={path(reach)} fill="none" stroke="var(--declared)" strokeWidth={3} strokeLinecap="round"
            strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        )}
        {pinIn && <circle cx={X(pin[0])} cy={Y(pin[1])} r={7} fill="none" stroke="var(--observed)" strokeWidth={2} vectorEffect="non-scaling-stroke" />}
      </svg>
      <figcaption className="mono">
        Map off: this browser cannot start WebGL. {reloc
          ? <>Candidate {reloc.distance_m ?? "?"} m along the waterway, capture of {reloc.after}.</>
          : <>Sealed capture of {f.captured}{f.sensor ? ` · ${f.sensor}` : ""}{f.resolution_m ? ` · ${f.resolution_m} m` : ""} · {f.window.replace(/_/g, " ")}.</>}{" "}
        <span style={{ color: "var(--declared)" }}>Cyan</span>: the located reach{masks.length ? <>; <span style={{ color: "var(--exists)" }}>green</span>: SAM 3.1 hard-bank masks</> : null}.
      </figcaption>
    </figure>
  );
}
