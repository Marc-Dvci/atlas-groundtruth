import maplibregl, { type Map as MLMap } from "maplibre-gl";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BaseMap } from "../map/BaseMap";
import { fmt, loadProjects, OUTCOME_COLOR, OUTCOME_LABEL, toGeoJSON, type Columns, type Outcome } from "../data";
import { AGENTS, empty, laneModel, reduce, type Ev, type FleetState } from "./fleetState";
import { VoiceMission, type MissionSpec } from "./VoiceMission";
import { STATIC, streamEvents, url } from "../api";

type Stage = "globe" | "province" | "fleet";
type Proj = { id: string; desc: string; muni: string; contractor: string; cost: number; lon: number; lat: number;
  flags: { code: string; text: string }[]; priority: number };

const BULACAN: [number, number, number, number] = [120.62, 14.68, 121.26, 15.2];
const ease = [0.22, 1, 0.36, 1] as const;
const STATUS_CODE: Record<string, number> = { running: 1, exists: 2, exists_before_contract: 3, relocated: 4, probable_ghost: 5, cant_verify: 6, built_late: 7 };

const params = new URLSearchParams(window.location.search);
const DEFAULT_RUN = "bulacan"; // the province mission; ?run=eval replays the evaluation instead

export function Mission() {
  const [map, setMap] = useState<MLMap | null>(null);
  const [cols, setCols] = useState<Columns | null>(null);
  const [prov, setProv] = useState<Proj[] | null>(null);
  const [summary, setSummary] = useState<any>(null);
  const [stage, setStage] = useState<Stage>("globe");
  const [fleet, setFleet] = useState<FleetState>(empty);
  const [spec, setSpec] = useState<MissionSpec | null>(null);
  const spin = useRef(true);

  const [hotspots, setHotspots] = useState<{ name: string; muni: string; n: number; php: number; c: [number, number] }[]>([]);
  const pulse = useRef<number>(0);

  useEffect(() => {
    loadProjects().then(setCols);
    fetch(url.province("bulacan")).then((r) => r.json()).then(setProv);
    fetch(url.summary()).then((r) => r.json()).then(setSummary);
  }, []);

  const onReady = useCallback((m: MLMap) => {
    setMap(m);
    const step = () => {
      if (!spin.current) return;
      const c = m.getCenter();
      m.easeTo({ center: [c.lng + 2.2, c.lat], duration: 1000, easing: (t) => t });
    };
    m.on("moveend", step);
    step();
    m.once("mousedown", () => (spin.current = false));
  }, []);

  // national layer + Bulacan layers
  useEffect(() => {
    if (!map || !cols || !prov || map.getSource("projects")) return;
    map.addSource("projects", { type: "geojson", data: toGeoJSON(cols) });
    map.addLayer({ id: "proj-halo", type: "circle", source: "projects", paint: {
      "circle-color": "#5fd3ff", "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 2.5, 6, 6, 10, 14],
      "circle-blur": 1, "circle-opacity": 0.28, "circle-opacity-transition": { duration: 1500 } } });
    map.addLayer({ id: "proj-core", type: "circle", source: "projects", paint: {
      "circle-color": "#dff6ff", "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 0.7, 6, 1.6, 10, 3.5],
      "circle-opacity": 0.9, "circle-opacity-transition": { duration: 1500 } } });

    map.addSource("bul-water", { type: "geojson", data: url.data("bulacan/waterways.geojson") });
    map.addLayer({ id: "bul-water", type: "line", source: "bul-water", paint: {
      "line-color": "#5fd3ff", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.6, 13, 1.6], "line-opacity": 0,
      "line-opacity-transition": { duration: 2000 } } });
    map.addSource("bul-brgy", { type: "geojson", data: url.data("bulacan/barangays.geojson") });
    // money per barangay, from the words of the contracts (scripts/hotspots.py), never from the pins
    map.addLayer({ id: "bul-hot", type: "fill", source: "bul-brgy", paint: {
      "fill-color": "#ffb45a",
      "fill-opacity": 0, "fill-opacity-transition": { duration: 2200 } } });
    map.addLayer({ id: "bul-brgy", type: "line", source: "bul-brgy", paint: {
      "line-color": "#d6e4ff", "line-width": 0.4, "line-opacity": 0, "line-opacity-transition": { duration: 2000 } } });
    map.addSource("bul-outline", { type: "geojson", data: url.data("bulacan/province.geojson") });
    map.addLayer({ id: "bul-outline-glow", type: "line", source: "bul-outline", paint: {
      "line-color": "#5fd3ff", "line-width": 8, "line-blur": 8, "line-opacity": 0, "line-opacity-transition": { duration: 2000 } } });
    map.addLayer({ id: "bul-outline", type: "line", source: "bul-outline", paint: {
      "line-color": "#5fd3ff", "line-width": 1.4, "line-dasharray": [3, 2], "line-opacity": 0, "line-opacity-transition": { duration: 2000 } } });

    map.addSource("bul", { type: "geojson", promoteId: "id", data: { type: "FeatureCollection", features: prov.map((p) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] }, properties: { id: p.id, cost: p.cost / 1e6 } })) } });
    const st: maplibregl.ExpressionSpecification = ["coalesce", ["feature-state", "st"], 0];
    const color: maplibregl.ExpressionSpecification = ["match", st,
      1, "#ffffff", 2, OUTCOME_COLOR.exists, 3, OUTCOME_COLOR.exists_before_contract, 4, OUTCOME_COLOR.relocated,
      5, OUTCOME_COLOR.probable_ghost, 6, OUTCOME_COLOR.cant_verify, 7, OUTCOME_COLOR.built_late, "#5fd3ff"];
    map.addLayer({ id: "bul-halo", type: "circle", source: "bul", paint: {
      "circle-color": color, "circle-blur": 1,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, ["+", 3, ["*", 0.05, ["get", "cost"]]], 12, ["+", 8, ["*", 0.12, ["get", "cost"]]]],
      "circle-opacity": 0, "circle-opacity-transition": { duration: 1200 } } });
    map.addLayer({ id: "bul-core", type: "circle", source: "bul", paint: {
      "circle-color": color,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, ["+", 1.2, ["*", 0.012, ["get", "cost"]]], 12, ["+", 2.5, ["*", 0.04, ["get", "cost"]]]],
      "circle-stroke-color": "#04060a", "circle-stroke-width": 0.6,
      "circle-opacity": 0, "circle-opacity-transition": { duration: 1200 } } });
    map.addSource("running", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({ id: "running", type: "circle", source: "running", paint: {
      "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.4, "circle-radius": 10, "circle-stroke-opacity": 0.8 } });
    map.on("click", "bul-core", (e) => {
      const id = e.features?.[0]?.properties?.id;
      const run = params.get("run") ?? DEFAULT_RUN;
      if (id && fleetRef.current.status[id] && fleetRef.current.status[id] !== "running") window.location.hash = `#/case/${run}/${id}`;
    });
    map.on("mouseenter", "bul-core", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "bul-core", () => (map.getCanvas().style.cursor = ""));
  }, [map, cols, prov]);

  // the five barangays where the most money was contracted, labelled on the province view
  useEffect(() => {
    if (!map) return;
    fetch(url.data("bulacan/barangays.geojson")).then((r) => r.json()).then((fc: GeoJSON.FeatureCollection) => {
      const rows = fc.features
        .map((f) => {
          const p = f.properties as { name: string; muni: string; n?: number; php?: number };
          const ring = (f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : f.geometry.type === "MultiPolygon" ? f.geometry.coordinates[0][0] : []) as [number, number][];
          const c: [number, number] = ring.length ? [ring.reduce((a, q) => a + q[0], 0) / ring.length, ring.reduce((a, q) => a + q[1], 0) / ring.length] : [0, 0];
          return { name: p.name, muni: p.muni, n: p.n ?? 0, php: p.php ?? 0, c };
        })
        .sort((a, b) => b.php - a.php)
        .slice(0, 5);
      setHotspots(rows);
    });
  }, [map]);

  const fleetRef = useRef(fleet);
  fleetRef.current = fleet;

  // project status -> feature state; running ring pulses
  useEffect(() => {
    if (!map || !map.getSource("bul")) return;
    for (const [id, s] of Object.entries(fleet.status)) map.setFeatureState({ source: "bul", id }, { st: STATUS_CODE[s] ?? 0 });
    const run = Object.entries(fleet.status).filter(([, s]) => s === "running").map(([id]) => id);
    const byId = new Map(prov?.map((p) => [p.id, p]));
    (map.getSource("running") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: run.flatMap((id) => {
      const p = byId.get(id);
      return p ? [{ type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] }, properties: {} }] : [];
    }) });
  }, [fleet.status, map, prov]);

  useEffect(() => {
    if (!map) return;
    const tick = () => {
      const k = (performance.now() % 1400) / 1400;
      if (map.getLayer("running")) {
        map.setPaintProperty("running", "circle-radius", 6 + 16 * k);
        map.setPaintProperty("running", "circle-stroke-opacity", 0.9 * (1 - k));
      }
      pulse.current = requestAnimationFrame(tick);
    };
    pulse.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(pulse.current);
  }, [map]);

  const goProvince = () => {
    if (!map) return;
    spin.current = false;
    map.stop();
    map.setPaintProperty("proj-core", "circle-opacity", 0.12);
    map.setPaintProperty("proj-halo", "circle-opacity", 0.05);
    ["bul-water"].forEach((l) => map.setPaintProperty(l, "line-opacity", 0.32));
    map.setPaintProperty("bul-brgy", "line-opacity", 0.07);
    map.setPaintProperty("bul-hot", "fill-opacity", ["interpolate", ["linear"], ["coalesce", ["get", "php"], 0], 0, 0, 2e8, 0.06, 1e9, 0.22, 2.2e9, 0.42]);

    map.setPaintProperty("bul-outline", "line-opacity", 0.9);
    map.setPaintProperty("bul-outline-glow", "line-opacity", 0.35);
    map.setPaintProperty("bul-core", "circle-opacity", 0.95);
    map.setPaintProperty("bul-halo", "circle-opacity", 0.35);
    map.fitBounds(BULACAN, { padding: { top: 90, bottom: 150, left: 60, right: 600 }, duration: 5200 });
    setStage("province");
  };

  const launch = async () => {
    setStage("fleet");

    map?.setPaintProperty("bul-hot", "fill-opacity", ["interpolate", ["linear"], ["coalesce", ["get", "php"], 0], 0, 0, 1e9, 0.08, 2.2e9, 0.16]);
    const run = params.get("run") ?? DEFAULT_RUN;
    const duration = Number(params.get("dur") ?? "80");
    let s = empty();
    let raf = 0;
    streamEvents(run, duration, (e) => {
      s = reduce(s, e as Ev);
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; setFleet(s); });
    });
  };

  useEffect(() => {
    (window as any).__mission = { goProvince, launch, setStage };
  });

  // the headline counts the President's portal list only; later DPWH records are drawn but not counted
  const listed = cols ? cols.src.filter((x) => x === 0).length : 0;
  const total = cols ? cols.cost.reduce((a, b, i) => a + (cols.src[i] === 0 ? b : 0), 0) : 0;
  const bulTotal = prov ? prov.reduce((a, p) => a + p.cost, 0) : 0;
  const flags = useMemo(() => {
    if (!prov) return null;
    const c = (code: string) => prov.filter((p) => p.flags.some((f) => f.code === code)).length;
    return { ceiling: c("BID_AT_CEILING") + c("ABOVE_ABC"), above: c("ABOVE_ABC"), withBudget: prov.filter((p: any) => p.abc).length,
      repeated: c("REPEATED_AMOUNT"), shared: c("SHARED_PIN"), copied: c("PIN_COPIED_DECIMALS") };
  }, [prov]);
  const overlaps = summary?.overlaps?.filter((o: any) => o.province === "Bulacan").length ?? 0;
  const deadline = spec?.deadline ?? fleet.plan?.deadline ?? params.get("deadline") ?? "2026-11-06";
  const deadlineLabel = new Date(deadline + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <BaseMap onReady={onReady} />
      <div className="vignette" />
      <header style={{ position: "absolute", top: 26, left: 32, display: "flex", alignItems: "baseline", gap: 14 }}>
        <span className="mono" style={{ letterSpacing: "0.32em", fontSize: 13, fontWeight: 600 }}>ATLAS</span>
        <span className="eyebrow" style={{ color: "var(--faint)" }}>
          declared <span style={{ color: "var(--declared)" }}>━</span> observed <span style={{ color: "var(--observed)" }}>━</span>
        </span>
      </header>

      <AnimatePresence mode="wait">
        {stage === "globe" && cols && (
          <motion.section key="globe" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 1.1, ease }} style={{ position: "absolute", left: 64, bottom: 96, maxWidth: 760 }}>
            <div className="pool" style={{ inset: "-120px -160px -80px -140px" }} />
            <div style={{ position: "relative" }}>
              <div className="eyebrow">Philippines · flood control · 2022 to 2025</div>
              <h1 className="serif" style={{ fontSize: 64, lineHeight: 1.02, margin: "14px 0 18px", fontWeight: 400 }}>
                {fmt.format(listed)} projects marked complete.
                <br />
                <span style={{ color: "var(--text-2)" }}>₱{(total / 1000).toFixed(1)} billion paid.</span>
              </h1>
              <p style={{ color: "var(--text-2)", fontSize: 18, maxWidth: 580, margin: 0 }}>
                Inspectors flagged 421 of them as ghosts. By January 2026, 14 had been confirmed. Atlas checks each one
                against what the Earth shows.
              </p>
              <button onClick={goProvince} className="cta">
                <span className="cta-dot">→</span>
                <span>Audit Bulacan</span>
                <span className="mono dim" style={{ fontSize: 12 }}>{prov ? fmt.format(prov.length) : "…"} contracts</span>
              </button>
              {!STATIC && <VoiceMission onMission={(m) => { setSpec(m); goProvince(); }} />}
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {stage !== "globe" && prov && (
          <motion.aside key="mission" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 1, delay: stage === "province" ? 2.6 : 0, ease }} className="mission">
            <div className="eyebrow">Mission</div>
            <h2 className="serif">Every flood-control contract in Bulacan, before the deadline.</h2>
            {spec && (
              <div className="chips" style={{ marginBottom: 14 }}>
                {spec.deadline && <span className="chip">by <b>{spec.deadline}</b></span>}
                {spec.budget_usd != null && <span className="chip">model budget <b>${spec.budget_usd}</b></span>}
                {spec.focus.map((f) => <span key={f} className="chip">first <b>{f}</b></span>)}
              </div>
            )}
            <div className="mission-facts">
              <div><span className="serif big">{fmt.format(prov.length)}</span><span className="eyebrow">contracts</span></div>
              <div><span className="serif big">₱{(bulTotal / 1e9).toFixed(1)}B</span><span className="eyebrow">paid</span></div>
              <div><span className="serif big">{deadlineLabel}</span><span className="eyebrow">{spec?.deadline_label ?? "deadline"}</span></div>
            </div>
            {flags && (
              <ul className="redflags">
                <li><b className="mono">{fmt.format(flags.ceiling)}</b> of {fmt.format(flags.withBudget)} were awarded at 99.9% or more of the approved budget</li>
                <li><b className="mono">{fmt.format(flags.above)}</b> have a recorded cost above the approved budget</li>
                <li><b className="mono">{fmt.format(flags.repeated)}</b> share an identical amount with others in the same office</li>
                <li><b className="mono">{overlaps}</b> pairs pay twice for overlapping stations of the same bank</li>
                {summary?.pins && (
                  <li><b className="mono">{summary.pins.over_1km}</b> pins sit more than 1 km from the barangay their own contract names{flags.copied > 0 && <>; <b className="mono">{flags.copied}</b> repeat the longitude's decimals in the latitude</>}</li>
                )}
              </ul>
            )}
            {stage === "province" && (
              <button onClick={launch} className="cta" style={{ marginTop: 22 }}>
                <span className="cta-dot">▸</span><span>Launch the fleet</span>
                <span className="mono dim" style={{ fontSize: 12 }}>{AGENTS.length} agents</span>
              </button>
            )}
            {stage === "fleet" && fleet.plan && (
              <p className="planline mono">
                plan · {fmt.format(fleet.plan.full_depth)} at full depth · {fmt.format(fleet.plan.screening_depth ?? 0)} screened ·
                ${fleet.plan.budget_usd} budget{fleet.plan.deadline ? ` · by ${fleet.plan.deadline}` : ""}
              </p>
            )}
            {stage === "fleet" && <Lanes fleet={fleet} />}
          </motion.aside>
        )}
      </AnimatePresence>

      {stage === "province" && map && hotspots.length > 0 && <Callouts map={map} spots={hotspots} />}
      {stage === "fleet" && <Counters fleet={fleet} />}
    </div>
  );
}

function Lanes({ fleet }: { fleet: FleetState }) {
  const now = Math.max(0, ...Object.values(fleet.lanes).map((l) => l.t));
  return (
    <div className="lanes">
      {AGENTS.map((a) => {
        const l = fleet.lanes[a.key];
        const live = l && now - l.t < 20;
        return (
          <div key={a.key} className={`lane ${live ? "live" : ""}`}>
            <div className="lane-head">
              <span className="lane-dot" />
              <span className="lane-name">{a.label}</span>
              <span className="mono lane-model">{laneModel(a.model, fleet.plan?.lm)}</span>
              {l && <span className="mono lane-case">{l.case}</span>}
            </div>
            <AnimatePresence mode="popLayout">
              {l && (
                <motion.div key={l.n} className="mono lane-text" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.35 }}>
                  {l.text}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

function Counters({ fleet }: { fleet: FleetState }) {
  const order: Outcome[] = ["probable_ghost", "built_late", "relocated", "exists_before_contract", "exists", "cant_verify"];
  return (
    <motion.div className="counters" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease }}>
      <div className="count-main">
        <span className="serif">{fmt.format(fleet.done)}</span>
        <span className="dim"> / {fmt.format(fleet.total || 0)} checked</span>
        <span className="mono dim" style={{ marginLeft: 18 }}>₱{(fleet.php / 1e9).toFixed(2)}B examined</span>
        {fleet.plan && (
          <span className="mono dim" style={{ marginLeft: 18 }}>
            ${fleet.spent.toFixed(2)} of ${fleet.plan.budget_usd} model budget{fleet.plan.lm === "open" ? " · open weights" : ""}
          </span>
        )}
      </div>
      <div className="outcomes">
        {order.map((o) => (
          <span key={o} className="outcome">
            <i style={{ background: OUTCOME_COLOR[o] }} />
            <span className="mono">{fleet.outcomes[o] ?? 0}</span> {OUTCOME_LABEL[o]}
          </span>
        ))}
      </div>
    </motion.div>
  );
}

/** Where the money went, as callouts in the empty west of the map, each with a leader line to its barangay. */
function Callouts({ map, spots }: { map: MLMap; spots: { name: string; muni: string; n: number; php: number; c: [number, number] }[] }) {
  const [pts, setPts] = useState<{ x: number; y: number }[]>([]);
  useEffect(() => {
    let raf = 0;
    const upd = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setPts(spots.map((h) => map.project(h.c))));
    };
    upd();
    map.on("move", upd);
    return () => {
      map.off("move", upd);
      cancelAnimationFrame(raf);
    };
  }, [map, spots]);
  const x0 = 64;
  const y0 = window.innerHeight * 0.42;
  return (
    <motion.svg className="callouts" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 4.6, duration: 1.4 }}
      width="100%" height="100%">
      {spots.map((h, i) => {
        const p = pts[i];
        const y = y0 + i * 62;
        if (!p) return null;
        const xe = x0 + 230;
        return (
          <g key={h.name + h.muni}>
            <path d={`M${xe},${y - 6} C${xe + 80},${y - 6} ${p.x - 80},${p.y} ${p.x},${p.y}`} fill="none" stroke="#ffc98a"
              strokeOpacity={0.45} strokeWidth={1} />
            <circle cx={p.x} cy={p.y} r={3.2} fill="#ffc98a" />
            <circle cx={p.x} cy={p.y} r={9} fill="none" stroke="#ffc98a" strokeOpacity={0.5} />
            <text x={x0} y={y - 12} className="co-name">{h.name}<tspan className="co-muni" dx={8}>{h.muni}</tspan></text>
            <text x={x0} y={y + 6} className="co-num">₱{(h.php / 1e9).toFixed(2)} billion · {h.n} contracts</text>
          </g>
        );
      })}
    </motion.svg>
  );
}
