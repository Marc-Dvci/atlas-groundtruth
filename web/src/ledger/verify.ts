/**
 * Verify an Atlas evidence ledger in the browser, without trusting the server that sent it.
 *
 * Each entry's hash is SHA-256 over the canonical JSON of {seq, ts, case, actor, kind, payload, prev}: keys sorted,
 * no spaces, UTF-8 (Python's json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)). JSON.parse would
 * lose how Python wrote a number (5.0 becomes 5), so this parser keeps every number's original text.
 */

export class Num {
  raw: string;
  constructor(raw: string) {
    this.raw = raw;
  }
}
type Val = null | boolean | string | Num | Val[] | { [k: string]: Val };

function parse(text: string): Val {
  let i = 0;
  const ws = () => {
    while (i < text.length && " \t\n\r".includes(text[i])) i++;
  };
  const val = (): Val => {
    ws();
    const ch = text[i];
    if (ch === "{") {
      i++;
      const o: { [k: string]: Val } = {};
      ws();
      if (text[i] === "}") return i++, o;
      for (;;) {
        ws();
        const k = str();
        ws();
        i++; // :
        o[k] = val();
        ws();
        if (text[i++] === "}") return o;
      }
    }
    if (ch === "[") {
      i++;
      const a: Val[] = [];
      ws();
      if (text[i] === "]") return i++, a;
      for (;;) {
        a.push(val());
        ws();
        if (text[i++] === "]") return a;
      }
    }
    if (ch === '"') return str();
    if (text.startsWith("true", i)) return (i += 4), true;
    if (text.startsWith("false", i)) return (i += 5), false;
    if (text.startsWith("null", i)) return (i += 4), null;
    const m = /^-?(?:\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(text.slice(i, i + 40));
    if (!m) throw new Error(`bad JSON at ${i}`);
    i += m[0].length;
    return new Num(m[0]);
  };
  const str = (): string => {
    const start = i;
    i++;
    while (text[i] !== '"') i += text[i] === "\\" ? 2 : 1;
    i++;
    return JSON.parse(text.slice(start, i));
  };
  return val();
}

function canonical(v: Val): string {
  if (v === null) return "null";
  if (v === true) return "true";
  if (v === false) return "false";
  if (v instanceof Num) return v.raw;
  if (typeof v === "string") return JSON.stringify(v);
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
  return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canonical(v[k])).join(",") + "}";
}

async function sha256(s: string | ArrayBuffer): Promise<string> {
  const data = typeof s === "string" ? new TextEncoder().encode(s) : s;
  const h = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(h), (b) => b.toString(16).padStart(2, "0")).join("");
}

export type Line = { seq: number; hash: string; prev: string; case: string; kind: string; raw: Record<string, Val> };
export type Result = { ok: boolean; first_bad: number | null; reason: string; entries: number; ms: number };

const GENESIS = "0".repeat(64);

export function readLines(jsonl: string): Line[] {
  return jsonl
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => {
      const o = parse(l) as Record<string, Val>;
      return { seq: Number((o.seq as Num).raw), hash: o.hash as string, prev: o.prev as string, case: o.case as string,
        kind: o.kind as string, raw: o };
    });
}

/** Recompute every link and every hash. `onProgress` gets the number of entries checked so far. */
export async function verifyLines(lines: Line[], onProgress?: (n: number) => void): Promise<Result> {
  const t0 = performance.now();
  let prev = GENESIS;
  for (let k = 0; k < lines.length; k++) {
    const e = lines[k];
    const body = { seq: e.raw.seq, ts: e.raw.ts, case: e.raw.case, actor: e.raw.actor, kind: e.raw.kind,
      payload: e.raw.payload, prev: e.raw.prev } as Record<string, Val>;
    if (e.prev !== prev) return { ok: false, first_bad: e.seq, reason: "broken link to previous entry", entries: lines.length, ms: performance.now() - t0 };
    if ((await sha256(canonical(body))) !== e.hash)
      return { ok: false, first_bad: e.seq, reason: "entry content changed after it was written", entries: lines.length, ms: performance.now() - t0 };
    prev = e.hash;
    if (onProgress && k % 50 === 0) onProgress(k);
  }
  return { ok: true, first_bad: null, reason: "chain intact", entries: lines.length, ms: performance.now() - t0 };
}

/** Evidence files are named by the SHA-256 of their bytes: fetch one and check it. */
export async function verifyBlob(url: string, name: string): Promise<boolean> {
  const buf = await (await fetch(url)).arrayBuffer();
  return (await sha256(buf)) === name.split(".")[0];
}

/** Flip one sealed claim in a copy, the way someone editing the file would: the most recent observation of the case
 * (the one a verdict rests on), and return the edited copy. */
export function tamper(lines: Line[], caseId: string | null): { lines: Line[]; changed: { seq: number; from: string; to: string; source: string } | null } {
  const out = lines.map((l) => ({ ...l, raw: { ...l.raw } }));
  const finding = (l: Line) => {
    const p = l.raw.payload as Record<string, Val> | null;
    const f = p && (p.finding as Record<string, Val> | undefined);
    return l.kind === "finding" && (!caseId || l.case === caseId) && f && (f.claim === "absent" || f.claim === "present") ? f : null;
  };
  const cands = out.filter((l) => finding(l));
  if (!cands.length) return { lines: out, changed: null };
  const target = cands.reduce((a, b) => (String(finding(b)!.observed) >= String(finding(a)!.observed) ? b : a));
  const f = finding(target)!;
  const from = f.claim as string;
  const to = from === "absent" ? "present" : "absent";
  target.raw.payload = { ...(target.raw.payload as Record<string, Val>), finding: { ...f, claim: to } };
  return { lines: out, changed: { seq: target.seq, from, to, source: String(f.source) } };
}

function toVal(x: unknown): Val {
  if (typeof x === "number") return new Num(String(x));
  if (Array.isArray(x)) return x.map(toVal);
  if (x && typeof x === "object") return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, toVal(v)]));
  return x as Val;
}

/** Seal a new entry onto the chain in this browser (the static demo has no server to append to). */
export async function sealLocal(lines: Line[], caseId: string, actor: string, kind: string, payload: Record<string, unknown>) {
  const last = lines[lines.length - 1];
  const seq = last ? last.seq + 1 : 0;
  const prev = last ? last.hash : GENESIS;
  const ts = Math.round(Date.now()) / 1000;
  const body: Val = { seq: new Num(String(seq)), ts: new Num(String(ts)), case: caseId, actor, kind, payload: toVal(payload), prev };
  return { seq, hash: await sha256(canonical(body)), prev };
}

/** The parsed value as ordinary JavaScript, for display (numbers become numbers again). */
export function plain(v: Val): unknown {
  if (v instanceof Num) return Number(v.raw);
  if (Array.isArray(v)) return v.map(plain);
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, plain(x)]));
  return v;
}

export const __test = { parse, canonical, sha256 };
