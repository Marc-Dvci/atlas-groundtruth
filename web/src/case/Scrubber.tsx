import { motion } from "motion/react";
import type { CaseFile } from "./types";

const TODAY = "2026-10-26";
const t = (d: string) => new Date(d + "T00:00:00Z").getTime();

type Props = {
  c: CaseFile;
  active: number;
  onPick: (i: number) => void;
  width: number;
  showSeries: boolean;
};

export function Scrubber({ c, active, onPick, width, showSeries }: Props) {
  const dates = c.frames.map((f) => f.captured);
  const lo = Math.min(t(dates[0] ?? c.award), t(c.award) - 3 * 365 * 864e5);
  const hi = t(TODAY);
  const W = width;
  const x = (d: string) => 24 + ((t(d) - lo) / (hi - lo)) * (W - 48);
  const H = 132;
  const base = 96;
  const rows = c.s2.rows ?? [];
  const nd = rows.map((r) => r.ndvi);
  const nmin = Math.min(...nd, 0);
  const nmax = Math.max(...nd, 0.6);
  const y = (v: number) => base - 14 - ((v - nmin) / (nmax - nmin || 1)) * 46;
  const path = rows.map((r, i) => `${i ? "L" : "M"}${x(r.date).toFixed(1)},${y(r.ndvi).toFixed(1)}`).join("");
  const years: number[] = [];
  for (let yy = new Date(lo).getUTCFullYear() + 1; yy <= 2026; yy++) years.push(yy);
  const fc = c.s2.first_change;

  return (
    <svg width={W} height={H} style={{ overflow: "visible", display: "block" }}>
      <defs>
        <linearGradient id="spark" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#3fe3a7" stopOpacity="0.9" />
          <stop offset="1" stopColor="#3fe3a7" stopOpacity="0.2" />
        </linearGradient>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" />
        </filter>
      </defs>
      {/* contract window */}
      <rect x={x(c.award)} y={18} width={Math.max(2, x(c.completion) - x(c.award))} height={base - 18}
        fill="rgba(95,211,255,0.07)" />
      <line x1={x(c.award)} x2={x(c.award)} y1={12} y2={base} stroke="#5fd3ff" strokeDasharray="3 3" />
      <line x1={x(c.completion)} x2={x(c.completion)} y1={12} y2={base} stroke="#5fd3ff" strokeDasharray="3 3" />
      <text x={x(c.award) - 6} y={10} fill="#5fd3ff" fontSize={10.5} textAnchor="end" className="mono">
        award {c.award}
      </text>
      <text x={x(c.completion) + 6} y={10} fill="#5fd3ff" fontSize={10.5} className="mono">
        declared complete {c.completion}
      </text>
      {/* Sentinel-2 bank NDVI */}
      {showSeries && rows.length > 1 && (
        <motion.path d={path} fill="none" stroke="url(#spark)" strokeWidth={1.4}
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 2.2, ease: "easeInOut" }} />
      )}
      {showSeries && rows.map((r) => <circle key={r.date} cx={x(r.date)} cy={y(r.ndvi)} r={1.3} fill="#3fe3a7" opacity={0.7} />)}
      {showSeries && fc && (
        <g>
          <line x1={x(fc.date)} x2={x(fc.date)} y1={30} y2={base} stroke="#ffc46b" strokeWidth={1} />
          <text x={x(fc.date) + 5} y={34} fill="#ffc46b" fontSize={10.5} className="mono">bank change {fc.date.slice(0, 7)}</text>
        </g>
      )}
      {showSeries && (
        <text x={24} y={30} fill="#7c8899" fontSize={10} className="mono">SENTINEL-2 · BANK NDVI</text>
      )}
      {/* axis */}
      <line x1={24} x2={W - 24} y1={base} y2={base} stroke="rgba(214,228,255,0.25)" />
      {years.map((yy) => (
        <g key={yy}>
          <line x1={x(`${yy}-01-01`)} x2={x(`${yy}-01-01`)} y1={base - 3} y2={base + 3} stroke="rgba(214,228,255,0.35)" />
          <text x={x(`${yy}-01-01`)} y={base + 18} fill="#7c8899" fontSize={10.5} textAnchor="middle" className="mono">{yy}</text>
        </g>
      ))}
      {/* captures */}
      {c.frames.map((f, i) => {
        const on = i === active;
        const col = f.window === "before_award" ? "#b7c1cf" : f.window === "after_completion" ? "#fff1dc" : "#5fd3ff";
        return (
          <g key={f.release} onClick={() => onPick(i)} style={{ cursor: "pointer" }}>
            {on && <circle cx={x(f.captured)} cy={base} r={11} fill={col} opacity={0.5} filter="url(#glow)" />}
            <rect x={x(f.captured) - (on ? 6 : 4.5)} y={base - (on ? 6 : 4.5)} width={on ? 12 : 9} height={on ? 12 : 9}
              transform={`rotate(45 ${x(f.captured)} ${base})`} fill={on ? col : "#04060a"} stroke={col} strokeWidth={1.5} />
            {on && (
              <text x={x(f.captured)} y={base + 34} fill={col} fontSize={11.5} textAnchor="middle" className="mono">
                {f.captured} · {f.sensor ?? ""} {f.resolution_m ? `${f.resolution_m} m` : ""}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
