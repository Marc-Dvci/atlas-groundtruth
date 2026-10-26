"""Normalise the 9,855 flood-control projects and compute portfolio red flags.

Input: the public mirror of the President's portal (sumbongsapangulo.ph) GeoJSON.
Output:
  data/portfolio/projects.json        full normalised records + flags
  web/public/data/projects.min.json   columnar, compact, for the map
  data/portfolio/summary.json         national and Bulacan statistics

Every flag here is computed by code from the published record; nothing is
inferred by a model. The flags only order the work; they are never a verdict.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.geo.geom import parse_stations  # noqa: E402

SRC = ROOT / "data/raw/github_rukku_sumbongsapangulo_mirror/flood_control_projects.geojson"
BG = ROOT / "data/raw/bettergov_api_flood_control/projects.jsonl"
BULACAN_MUNIS = ["Angat", "Balagtas", "Baliuag", "Baliwag", "Bocaue", "Bulakan", "Bustos", "Calumpit", "Doña Remedios Trinidad",
                 "Guiguinto", "Hagonoy", "Malolos", "Marilao", "Meycauayan", "Norzagaray", "Obando", "Pandi", "Paombong",
                 "Plaridel", "Pulilan", "San Ildefonso", "San Jose del Monte", "San Miguel", "San Rafael", "Santa Maria"]
OUT = ROOT / "data/portfolio"
WEB = ROOT / "web/public/data"

RIVER = re.compile(r"\b(?:along|at)?\s*(?:the\s+)?([A-Z][A-Za-z\-ñÑ]+(?:\s+[A-Z][A-Za-z\-ñÑ]+){0,2})\s+(River|Creek|Channel)\b")
BRGY = re.compile(r"\b(?:Barangay|Brgy\.?)\s+([A-Z][\w\.\-ñÑ]+(?:\s+[A-Z0-9][\w\.\-ñÑ]+){0,3})")
KSTA = re.compile(r"\bK\s*0*(\d+)\s*\+\s*(\d{3})", re.I)
LEN = re.compile(r"(\d{2,5}(?:\.\d+)?)\s*(?:l\.?m\.?|lin(?:ear)?\.?\s*m|meters?|m)\b(?:\s*long)?", re.I)


def iso_date(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc).date().isoformat()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return None


def stations(desc: str) -> list[float]:
    st = parse_stations(desc)
    if not st:
        st = [int(a) * 1000 + float(b) for a, b in KSTA.findall(desc or "")]
    return st


def clean_muni(m: str | None) -> str:
    if not m:
        return ""
    m = re.sub(r"\s*\((?:BULACAN|CAPITAL)\)", "", m, flags=re.I)
    m = re.sub(r"\s*\([^)]*\)\s*$", "", m)
    return m.strip().title().replace("City Of ", "")


def main() -> None:
    gj = json.loads(SRC.read_text(encoding="utf-8"))
    recs = []
    for f in gj["features"]:
        p = f["properties"]
        lon, lat = (f.get("geometry") or {}).get("coordinates") or [p.get("Longitude"), p.get("Latitude")]
        desc = (p.get("ProjectDescription") or "").strip()
        st = stations(desc)
        length = abs(st[-1] - st[0]) if len(st) >= 2 else None
        m = LEN.search(desc) if length is None else None
        if m and 20 <= float(m.group(1)) <= 20000:
            length = float(m.group(1))
        cost = float(p.get("ContractCost") or 0) or None
        abc = float(p.get("ABC") or 0) or None
        river = RIVER.search(desc)
        brgy = BRGY.search(desc)
        recs.append({
            "id": p.get("ContractID") or p.get("ProjectID"),
            "project_id": p.get("ProjectID"),
            "desc": desc,
            "type": p.get("TypeofWork"),
            "region": p.get("Region"),
            "province": (p.get("Province") or "").title(),
            "muni": clean_muni(p.get("Municipality")),
            "deo": p.get("DistrictEngineeringOffice") or p.get("ImplementingOffice"),
            "district": p.get("LegislativeDistrict"),
            "contractor": (p.get("Contractor") or "").strip(),
            "cost": cost,
            "abc": abc,
            "start": iso_date(p.get("StartDate")),
            "completion": iso_date(p.get("CompletionDateActual")) or iso_date(p.get("CompletionDateOriginal")),
            "year": p.get("InfraYear"),
            "lon": round(float(lon), 6) if lon is not None else None,
            "lat": round(float(lat), 6) if lat is not None else None,
            "stations_m": st,
            "length_m": length,
            "river_text": " ".join(river.groups()) if river else None,
            "brgy_text": brgy.group(1) if brgy else None,
        })

    # ---- BetterGov (DPWH API mirror): status, progress, and later Bulacan contracts ----
    bg = {}
    for line in BG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            bg[d["contractId"]] = d
    have = {r["id"] for r in recs}
    for r in recs:
        b = bg.get(r["id"])
        r["source"] = "sumbong"
        if b:
            r["status"], r["progress"] = b.get("status"), b.get("progress")
    for cid, b in bg.items():
        prov = ((b.get("location") or {}).get("province") or "")
        if cid in have or "Bulacan" not in prov or str(b.get("infraYear")) not in ("2022", "2023", "2024", "2025"):
            continue
        if b.get("latitude") is None or b.get("longitude") is None:
            continue
        if b.get("status") in ("For Procurement", "Not Yet Started", "Terminated"):
            continue  # nothing was declared built yet
        desc = (b.get("description") or "").strip()
        dl = desc.lower()
        muni = next((m for m in BULACAN_MUNIS if m.lower() in dl), "")
        muni = "Baliuag" if muni == "Baliwag" else muni
        st = stations(desc)
        length = abs(st[-1] - st[0]) if len(st) >= 2 else None
        river = RIVER.search(desc.title())
        brgy = BRGY.search(desc.title())
        recs.append({
            "id": cid, "project_id": None, "desc": desc.capitalize() if desc.isupper() else desc,
            "type": b.get("category"), "region": (b.get("location") or {}).get("region"), "province": "Bulacan",
            "muni": muni, "deo": prov, "district": None,
            "contractor": re.sub(r"\s*\((?:\[[A-Z]+\]\s*)?\d+\)", "", b.get("contractor") or "").strip(),
            "cost": float(b.get("budget") or 0) or None, "abc": None,
            "start": b.get("startDate"), "completion": b.get("completionDate"), "year": int(b.get("infraYear")),
            "lon": round(float(b["longitude"]), 6), "lat": round(float(b["latitude"]), 6),
            "stations_m": st, "length_m": length,
            "river_text": " ".join(river.groups()) if river else None, "brgy_text": brgy.group(1) if brgy else None,
            "source": "bettergov", "status": b.get("status"), "progress": b.get("progress"),
        })

    # ---- portfolio flags (code only) ----
    pin_groups = collections.defaultdict(list)
    for r in recs:
        if r["lon"] is not None:
            pin_groups[(round(r["lon"], 5), round(r["lat"], 5))].append(r["id"])
    amt_groups = collections.Counter((r["deo"], round(r["cost"] or 0, -3)) for r in recs if r["cost"])
    deo_total = collections.Counter()
    deo_contractor = collections.Counter()
    for r in recs:
        if r["cost"]:
            deo_total[r["deo"]] += r["cost"]
            deo_contractor[(r["deo"], r["contractor"])] += r["cost"]

    cpm = sorted(r["cost"] / r["length_m"] for r in recs if r["cost"] and r["length_m"] and r["length_m"] >= 30)

    def pct(v: float) -> float:
        import bisect
        return bisect.bisect_left(cpm, v) / max(1, len(cpm))

    def _decimals(x: float) -> str:
        t = repr(float(x))
        return t.split(".")[1] if "." in t else ""

    for r in recs:
        flags = []
        shared = len(pin_groups.get((round(r["lon"] or 0, 5), round(r["lat"] or 0, 5)), [])) - 1 if r["lon"] else 0
        r["shared_pin"] = max(0, shared)
        if shared > 0:
            flags.append({"code": "SHARED_PIN", "text": f"Same map pin as {shared} other project(s)"})
        if r["lon"] is not None and (abs(r["lon"] * 1e3 - round(r["lon"] * 1e3)) < 1e-6 and abs(r["lat"] * 1e3 - round(r["lat"] * 1e3)) < 1e-6):
            flags.append({"code": "COARSE_PIN", "text": "Pin rounded to 3 decimals (~100 m)"})
        if r["lon"] is not None and _decimals(r["lon"]) == _decimals(r["lat"]) and len(_decimals(r["lon"])) >= 4:
            flags.append({"code": "PIN_COPIED_DECIMALS", "text": f"Pin latitude repeats the longitude's decimals "
                                                                 f"({r['lon']}, {r['lat']}): typed, not measured"})
        same_amt = amt_groups.get((r["deo"], round(r["cost"] or 0, -3)), 0) - 1 if r["cost"] else 0
        r["same_amount"] = max(0, same_amt)
        if same_amt >= 2:
            flags.append({"code": "REPEATED_AMOUNT", "text": f"Identical contract amount to {same_amt} other contracts in the same office"})
        if r["cost"] and r["abc"] and r["cost"] > r["abc"] + 0.5:
            flags.append({"code": "ABOVE_ABC", "text": f"Recorded cost exceeds the approved budget by ₱{r['cost'] - r['abc']:,.0f}; "
                                                       "bids above the approved budget are disqualified unless a variation order explains it"})
        elif r["cost"] and r["abc"] and r["cost"] / r["abc"] >= 0.999:
            flags.append({"code": "BID_AT_CEILING", "text": f"Awarded at {100 * r['cost'] / r['abc']:.2f}% of the approved budget"})
        if r["cost"] and r["length_m"] and r["length_m"] >= 30:
            v = r["cost"] / r["length_m"]
            r["cost_per_m"] = round(v)
            r["cost_per_m_pct"] = round(pct(v), 3)
            if r["cost_per_m_pct"] >= 0.9:
                flags.append({"code": "COST_PER_M_HIGH", "text": f"₱{v:,.0f} per metre, top {100 - 100 * r['cost_per_m_pct']:.0f}% nationally"})
        share = deo_contractor[(r["deo"], r["contractor"])] / deo_total[r["deo"]] if r["cost"] and deo_total[r["deo"]] else 0
        r["contractor_share"] = round(share, 3)
        if share >= 0.15:
            flags.append({"code": "CONTRACTOR_CONCENTRATION", "text": f"Contractor holds {100 * share:.0f}% of this office's flood-control spend"})
        if r["start"] and r["completion"]:
            days = (date.fromisoformat(r["completion"]) - date.fromisoformat(r["start"])).days
            r["days"] = days
            if days < 0:
                flags.append({"code": "COMPLETED_BEFORE_START", "text": f"Completion dated {-days} days before the start date"})
            elif r["cost"] and days < 120 and r["cost"] > 50e6:
                flags.append({"code": "FAST_COMPLETION", "text": f"₱{r['cost'] / 1e6:.0f}M completed in {days} days"})
        r["flags"] = flags
        weights = {"ABOVE_ABC": 0.8, "SHARED_PIN": 1.0, "COARSE_PIN": 0.3, "PIN_COPIED_DECIMALS": 1.0, "REPEATED_AMOUNT": 0.6,
                   "BID_AT_CEILING": 0.4,
                   "COST_PER_M_HIGH": 0.8, "CONTRACTOR_CONCENTRATION": 0.5, "COMPLETED_BEFORE_START": 1.0,
                   "FAST_COMPLETION": 0.6}
        r["suspicion"] = round(sum(weights[f["code"]] for f in flags), 2)
        r["priority"] = round((r["cost"] or 0) / 1e6 * (1 + r["suspicion"]), 1)

    OUT.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)
    (OUT / "projects.json").write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")

    keep = [r for r in recs if r["lon"] is not None and r["lat"] is not None]
    cols = {
        "id": [r["id"] for r in keep],
        "lon": [r["lon"] for r in keep],
        "lat": [r["lat"] for r in keep],
        "cost": [round((r["cost"] or 0) / 1e6, 2) for r in keep],
        "prov": [r["province"] for r in keep],
        "muni": [r["muni"] for r in keep],
        "contractor": [r["contractor"] for r in keep],
        "year": [r["year"] for r in keep],
        "susp": [r["suspicion"] for r in keep],
        "desc": [r["desc"] for r in keep],
        "flags": [[f["code"] for f in r["flags"]] for r in keep],
        "src": [0 if r["source"] == "sumbong" else 1 for r in keep],
    }
    (WEB / "projects.min.json").write_text(json.dumps(cols, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def stats(rs):
        fl = collections.Counter(f["code"] for r in rs for f in r["flags"])
        return {
            "projects": len(rs),
            "total_php": round(sum(r["cost"] or 0 for r in rs)),
            "with_stations": sum(1 for r in rs if r["stations_m"]),
            "with_length": sum(1 for r in rs if r["length_m"]),
            "shared_pin_projects": sum(1 for r in rs if r["shared_pin"] > 0),
            "flags": dict(fl.most_common()),
            "top_contractors": collections.Counter(r["contractor"] for r in rs).most_common(10),
        }

    bul = [r for r in recs if r["province"] == "Bulacan"]
    summary = {"national": stats([r for r in recs if r["source"] == "sumbong"]),
               "bulacan_sumbong": stats([r for r in bul if r["source"] == "sumbong"]), "bulacan": stats(bul), "cost_per_m_n": len(cpm),
               "cost_per_m_median": cpm[len(cpm) // 2] if cpm else None}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:3000])


if __name__ == "__main__":
    main()
