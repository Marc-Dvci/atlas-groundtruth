import type { Map as MLMap } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { OUTCOME_COLOR, OUTCOME_LABEL } from "../data";
import { BaseMap } from "../map/BaseMap";
import { reachCoords, setupCaseLayers, type CaseLayers } from "./caseMap";
import { Dossier } from "./Dossier";
import { Scrubber } from "./Scrubber";
import type { CaseFile } from "./types";

type Beat = { key: string; label: string };

/** The beats a case is told in. A relocation search, when one ran, gets a beat of its own. */
export function beatsFor(c: CaseFile | null): Beat[] {
  return [
    { key: "head", label: "Declared" },
    { key: "locate", label: "Located" },
    { key: "history", label: "History" },
    ...(c?.relocation ? [{ key: "elsewhere", label: "Elsewhere" }] : []),
    { key: "series", label: "Sentinel-2" },
    { key: "money", label: "Money" },
    { key: "impact", label: "People" },
    { key: "verdict", label: "Verdict" },
    { key: "file", label: "Case file" },
  ];
}

function bounds(pts: [number, number][]): [[number, number], [number, number]] {
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]];
}

export function CaseView({ run, id, onBack }: { run: string; id: string; onBack: () => void }) {
  const [c, setC] = useState<CaseFile | null>(null);
  const [map, setMap] = useState<MLMap | null>(null);
  const layers = useRef<CaseLayers | null>(null);
  const [beat, setBeat] = useState(0);
  const [active, setActive] = useState(0);
  const [tools, setTools] = useState<{ tool: string; args: Record<string, unknown>; refused?: string | null }[]>([]);
  const [w, setW] = useState(window.innerWidth);
  const beats = useMemo(() => beatsFor(c), [c]);
  const key = beats[Math.min(beat, beats.length - 1)].key;
  const at = useCallback((k: string) => beats.findIndex((b) => b.key === k), [beats]);
  const reached = useCallback((k: string) => at(k) >= 0 && beat >= at(k), [at, beat]);

  useEffect(() => {
    fetch(`/api/runs/${run}/cases/${id}`).then((r) => r.json()).then(setC);
    fetch(`/api/runs/${run}/ledger?case=${id}`)
      .then((r) => r.json())
      .then((rows: { kind: string; actor: string; payload: { tool: string; args: Record<string, unknown>; refused?: string } }[]) =>
        setTools(rows.filter((e) => e.kind === "tool_call" && e.actor === "locator").map((e) => e.payload)),
      );
    const on = () => setW(window.innerWidth);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, [run, id]);

  const onReady = useCallback((m: MLMap) => setMap(m), []);

  // layers
  useEffect(() => {
    if (!map || !c) return;
    layers.current = setupCaseLayers(map, c);
    const last = c.frames.length - 1;
    setActive(last);
    layers.current.showFrame(last);
    layers.current.showPin(true);
    map.jumpTo({ center: [c.record.lon, c.record.lat], zoom: 16.4, pitch: 0, bearing: 0 });
    return () => layers.current?.dispose();
  }, [map, c]);

  useEffect(() => {
    layers.current?.showFrame(active);
  }, [active]);

  // beats drive the camera and the layers
  useEffect(() => {
    const L = layers.current;
    if (!map || !c || !L) return;
    const reach = reachCoords(c);
    const pin: [number, number] = [c.record.lon, c.record.lat];
    const pad = { top: 120, bottom: 230, left: 80, right: 640 };
    L.showReach(reached("locate"));
    L.showMasks(reached("history"));
    L.showRelocation(key === "elsewhere");
    if (key === "locate" && reach.length) map.fitBounds(bounds([...reach, pin]), { padding: pad, duration: 2600, maxZoom: 17.6 });
    if (key === "history" && reach.length) map.fitBounds(bounds(reach), { padding: pad, duration: 2000, maxZoom: 17.8, pitch: 38 });
    if (key === "elsewhere" && c.relocation) {
      const pts = c.relocation.windows.flatMap((x) => [[x.bbox[0], x.bbox[1]], [x.bbox[2], x.bbox[3]]] as [number, number][]);
      const after = c.frames.findIndex((f) => f.captured === c.relocation!.after);
      setActive(after >= 0 ? after : c.frames.length - 1);
      map.fitBounds(bounds([...pts, ...reach]), { padding: pad, duration: 2600, pitch: 0, maxZoom: 16.5 });
    }
    if (key === "impact") {
      fetch(`/api/evidence/${c.impact.cells_blob}`).then((r) => r.json()).then((cells) => L.showPeople(true, cells));
      map.easeTo({ zoom: 14.2, pitch: 30, duration: 2600 });
    } else L.showPeople(false);
    if (reached("verdict") && reach.length) map.fitBounds(bounds(reach), { padding: pad, duration: 1800, maxZoom: 17.6, pitch: 20 });
  }, [key, map, c, reached]);

  // history beat: walk through the captures once
  useEffect(() => {
    if (key !== "history" || !c) return;
    let i = 0;
    setActive(0);
    const t = setInterval(() => {
      i += 1;
      if (i >= c.frames.length) return clearInterval(t);
      setActive(i);
    }, 1700);
    return () => clearInterval(t);
  }, [key, c]);

  // keyboard + director hooks (the film drives these)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowRight") setBeat((b) => Math.min(beats.length - 1, b + 1));
      if (e.key === "ArrowLeft") setBeat((b) => Math.max(0, b - 1));
    };
    window.addEventListener("keydown", onKey);
    (window as unknown as { __atlas: object }).__atlas = {
      setBeat, setActive, beats: beats.map((b) => b.key), go: (k: string) => setBeat(Math.max(0, at(k))),
    };
    return () => window.removeEventListener("keydown", onKey);
  }, [beats, at]);

  const v = c?.verdict;
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <BaseMap onReady={onReady} initial={{ center: [120.88, 14.9], zoom: 12 }} />
      <div className="vignette case" />
      <div className="topshade" />
      <header className="case-head">
        <button onClick={onBack} className="mono back">← Bulacan</button>
        <span className="mono" style={{ letterSpacing: "0.32em", fontWeight: 600 }}>ATLAS</span>
        {c && <span className="mono dim">{c.id}</span>}
        {c?.models?.lm === "open" && <span className="mono pill-open">open weights · {c.models.spark}</span>}
        {v && reached("verdict") && (
          <span className="pill-outcome" style={{ color: OUTCOME_COLOR[v.outcome], borderColor: OUTCOME_COLOR[v.outcome] }}>
            {OUTCOME_LABEL[v.outcome]}
          </span>
        )}
      </header>
      <nav className="beats">
        {beats.map((b, i) => (
          <button key={b.key} className={i === beat ? "on" : i < beat ? "done" : ""} onClick={() => setBeat(i)}>
            <span className="mono">{String(i + 1).padStart(2, "0")}</span> {b.label}
          </button>
        ))}
      </nav>
      {c && (
        <>
          <div className="scrub">
            <Scrubber c={c} active={active} onPick={setActive} width={Math.max(600, w - 640 - 80)} showSeries={reached("series")} />
          </div>
          <div className="dossier-pool" />
          <Dossier c={c} beat={key} reached={reached} active={active} onPickFrame={setActive} tools={tools} run={run} />
        </>
      )}
    </div>
  );
}
