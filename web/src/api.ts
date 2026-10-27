/**
 * Where the app reads from. Live: the Atlas API (FastAPI). Static (VITE_STATIC=1): files exported by
 * scripts/export_static.py, so a recorded mission can be served by any static host with no keys and no server.
 */
export const STATIC = import.meta.env.VITE_STATIC === "1";
const BASE = import.meta.env.BASE_URL;
const S = `${BASE}static`;
const WAYBACK = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile";

export const url = {
  case: (run: string, id: string) => (STATIC ? `${S}/runs/${run}/cases/${id}.json` : `/api/runs/${run}/cases/${id}`),
  caseLedger: (run: string, id: string) => (STATIC ? `${S}/runs/${run}/ledger_${id}.json` : `/api/runs/${run}/ledger?case=${id}`),
  ledgerRaw: (run: string) => (STATIC ? `${S}/runs/${run}/ledger.jsonl` : `/api/runs/${run}/ledger.jsonl`),
  evaluation: (run: string) => (STATIC ? `${S}/runs/${run}/evaluation.json` : `/api/runs/${run}/evaluation`),
  compare: (run: string, other: string) => (STATIC ? `${S}/runs/${run}/compare_${other}.json` : `/api/runs/${run}/compare/${other}`),
  province: (name: string) => (STATIC ? `${S}/province_${name}.json` : `/api/province/${name}`),
  summary: () => (STATIC ? `${S}/summary.json` : "/api/summary"),
  evidence: (name: string) => (STATIC ? `${S}/evidence/${name}` : `/api/evidence/${name}`),
  wayback: (release: number) => (STATIC ? `${WAYBACK}/${release}/{z}/{y}/{x}` : `/api/wayback/${release}/{z}/{y}/{x}`),
  data: (path: string) => `${BASE}data/${path}`,
};

export type RawEvent = { t: number; kind: string; case: string; agent: string; data: Record<string, unknown> };

/** Stream a run's events: live from the server (or its recording, replayed in about `duration` seconds),
 * or replayed from the exported log in the static build. */
export function streamEvents(run: string, duration: number, onEvent: (e: RawEvent) => void, onEnd?: () => void): () => void {
  if (!STATIC) {
    const es = new EventSource(`/api/runs/${run}/events?duration=${duration}`);
    es.onmessage = (m) => onEvent(JSON.parse(m.data));
    es.addEventListener("end", () => {
      es.close();
      onEnd?.();
    });
    return () => es.close();
  }
  let stop = false;
  (async () => {
    const text = await (await fetch(`${S}/runs/${run}/events.jsonl`)).text();
    const evs = text.split(/\r?\n/).filter((l) => l.trim()).map((l) => JSON.parse(l) as RawEvent);
    // recorded seconds at each event, idle stretches (a stopped and resumed mission) cut to GAP_S
    const GAP_S = 4;
    const at: number[] = [];
    evs.forEach((e, i) => at.push(i ? at[i - 1] + Math.min(GAP_S, Math.max(0, e.t - evs[i - 1].t)) : 0));
    const span = at.length ? at[at.length - 1] : 0;
    const speed = duration > 0 ? Math.max(1, span / duration) : 1;
    // an absolute schedule: skipping each sub-millisecond wait must not lose the time they add up to
    const start = performance.now();
    for (let i = 0; i < evs.length; i++) {
      if (stop) return;
      const wait = start + (at[i] / speed) * 1000 - performance.now();
      if (wait > 4) await new Promise((r) => setTimeout(r, wait));
      onEvent(evs[i]);
    }
    onEnd?.();
  })();
  return () => {
    stop = true;
  };
}
