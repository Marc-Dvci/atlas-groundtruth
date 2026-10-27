# Atlas

**Atlas checks what a government declared against what the Earth shows.**

Its first mission, Groundtruth, audits whether the flood-control works the Philippines paid for were built. Between
2022 and 2025 the government recorded 9,855 flood-control projects as complete, worth ₱547.6 billion. Inspectors later
called hundreds of them ghosts, and the President stood on a riverbank in Bulacan where ₱55.7 million had bought
nothing. Finding suspects was never the hard part. Proving each one took a team, a site visit and months.

Atlas takes a province and a deadline, and sends a fleet of agents through every contract, most money and most red
flags first. Each agent tests one audit assertion against independent evidence: sub-metre satellite history, the
Sentinel-2 archive, street-level photos and the public record. Fixed rules, not a model, decide each outcome. Every
reading, mask and verdict is sealed in a hash-chained ledger, and a human investigator signs every case.

<!-- screenshot: docs/case.png -->

## What a case looks like

1. **Declared.** The contract's own words: "Construction of Riverbank Protection Structure at Barangay Bulihan, Malolos
   City", ₱77.2 million, declared complete on 19 April 2024.
2. **Located.** Published pins are unreliable: in Bulacan, 46 of the 918 contracts that name a barangay have a pin more
   than 1 km outside it, and four pins repeat their longitude's six decimals in the latitude. The Locator reads the
   description and works through map tools (official barangay boundaries, every mapped waterway, the other contracts
   that name the same barangay, and SAM 3.1 tracing a channel the map lacks) until it can cut the reach the text
   describes.
3. **History.** Every distinct sub-metre capture of the site since 2010 (Esri World Imagery Wayback). SAM 3.1 segments
   the hard banks and the water in each one; Muse Spark reads every capture along the reach, oldest first; Muse Spark
   Open re-reads each capture that decides the case beside the last capture before the award, and a reading counts
   only when both models agree. Wayback can list one image under several dates; identical pixels count once.
4. **Elsewhere.** When the declared reach is bare after completion, Atlas walks the same waterway 1.5 km each way,
   compares SAM 3.1 hard-bank masks before the award and after completion window by window, and asks Muse Spark to
   confirm the strongest candidate.
5. **Sentinel-2.** Every clear 10 m scene since four years before the award, bank by bank, compared season against
   season, to date when the bank changed.
6. **Money and people.** Bids at the ceiling, contracts paid twice for the same stations, every contract that names the
   same barangay, and the number of people who live within 1.5 km of the reach on ground no more than 3 m above its
   bank (Meta and CIESIN High Resolution Settlement Layer, Copernicus DEM).
7. **Verdict.** Computed by the rules below. Each source is listed as counted or refused, with the reason.
8. **Case file.** Muse Wonder writes the file an investigator signs. Every paragraph must cite ledger entries; code
   removes any paragraph whose citations do not resolve. For a missing structure, Muse Image draws what the contract
   paid for onto the real capture, labelled as an illustration and never counted as evidence.

## How Atlas decides

Agents file typed findings; [`atlas/verdict.py`](atlas/verdict.py) counts them. The rules are plain code, so an
investigator or a court can read them, and [`tests/test_verdict.py`](tests/test_verdict.py) pins each one down.

| Outcome | What it takes |
|---|---|
| Probable ghost | Absent after the declared completion in **two independent capture chains** |
| Declared before built | Bare after the declared completion in sub-metre imagery, and a 10 m series unchanged until then dates a lasting change only afterwards |
| Built elsewhere | Absent at the declared reach in two chains, and a new structure on the same waterway during the contract window |
| Existed before the contract | The structure is visible before the award, or a 10 m series dates the bank's change to before it |
| Exists | Visible after completion |
| Can't verify | Anything less, with the reason: one source only, sources that disagree, no usable capture after completion |

- Two captures are independent only if their pixels come from different capture chains. Every DigitalGlobe, Maxar and
  Vantor capture is one constellation, so five of them count as one source. A street photo is its own chain.
- 10 m pixels can date a change and testify to absence, but they cannot establish that a wall is there, and they
  cannot testify about a structure shorter than about 150 m.
- A Sentinel-2 bank that dips and then regrows (cleared ground, equipment, fresh concrete) makes that source
  inconclusive; it never counts as absence.
- A reading below the quality floor (haze, cloud, blur) is refused, and so is a decisive reading the second model
  contradicts.
- A 10 m change is dated to its season; it predates the award only if the whole season ended before it.

## Meta models in Atlas

| Model | Role |
|---|---|
| **Muse Spark 1.3** | Locator (function calling over six spatial tools), multi-image reading of every capture along the reach, street-photo reading, relocation confirmation, mission parsing |
| **Muse Spark Open** | The independent second reader of every decisive capture; and the whole audit end to end on open weights (served by Baseten here), for audit institutions that must keep national data on their own hardware |
| **SAM 3.1** | Concept segmentation of hard banks ("riverbank") and water ("river") in every capture; channel tracing where the map has no waterway; before/after change detection along the river |
| **Muse Wonder** | The case file: four to six cited paragraphs, limits, open questions, documents to request |
| **Muse Image** | The declared structure drawn onto the real capture, as a labelled illustration |
| **Muse Voice Transcribe** | The investigator states the mission aloud; Muse Spark turns it into province, deadline and budget |
| **Mapillary** | Dated street-level photos near the reach, an independent capture chain |
| **High Resolution Settlement Layer** | People living behind each reach (Meta and CIESIN) |

SAM 3.1 surprised me on concepts: "riverbank" isolates engineered hard banks (dikes, revetments, paved edges) and
leaves vegetated banks alone, while "levee", "dike", "flood wall" and "revetment" return nothing. Its masks arrive in a
compact one-bit format; [`atlas/sam_codec.py`](atlas/sam_codec.py) decodes it (base85, then a binary range coder with a
12-pixel causal context), pixel-exact in under half a second per mask.

## Evaluation against the official record

Twelve Bulacan contracts carry an official finding (Commission on Audit, the Independent Commission for
Infrastructure, the President's own inspection) that can be tied to a contract ID: six exactly or strongly, six only as
candidates. They sit in [`data/answer_key/cases.json`](data/answer_key/cases.json). No audit reads that file;
[`scripts/evaluate.py`](scripts/evaluate.py) compares only after every verdict is sealed.

| On the 12 contracts | Muse Spark 1.3 | Muse Spark Open |
|---|---|---|
| Agree (same finding) | 1 | 1 |
| Consistent (flags the contract on other grounds) | 4 | 5 |
| Can't verify | 5 | 4 |
| Contradict | 2 | 2 |

- *Consistent* means Atlas flags the contract another way: officials found phase III of a Malis riverbank wall (24CC0055)
  "built on another portion of the river", and Atlas finds the wall at the located reach standing since January 2020,
  four years before the award.
- On the six exact or strong matches, neither host contradicts the official finding. Muse Spark 1.3 abstains on three:
  one has no sub-metre capture after completion, one has a single source showing nothing (the standard needs two), and
  one has only a 10 m change after completion.
- Both contradictions are candidate matches, where Atlas sees a structure after completion and the report quoted
  found a ghost. On 24CC0011 the April 2025 capture shows a new wall along the west bank of the located reach that the
  2020 capture does not.
- The two hosts reached the same verdict on 11 of 12 contracts, located the same site on 10, and agreed on 33 of 34
  capture readings where they looked at the same site.

Reproduce: `ATLAS_AS_OF=2026-10-27 sh scripts/eval_both.sh` (runs `eval` and `eval-open`, then compares them).

## The first mission: Bulacan

All 1,096 flood-control contracts in Bulacan (₱72.5 billion), most money and most red flags first, within a $45 model
budget. The 40 highest-priority contracts ran at full depth; the rest at screening depth (the last sub-metre capture
before the award and every one after it) on Muse Spark's contributor tier, which costs a twelfth as much because
Meta may train on what it is sent: it carries only public contract records and public imagery.

| Outcome | Contracts | ₱ billion |
|---|---|---|
| Existed before the contract | 177 | 12.02 |
| Probable ghost | 36 | 2.08 |
| Built elsewhere | 6 | 0.46 |
| Declared before built | 5 | 0.27 |
| Exists | 266 | 18.23 |
| Can't verify | 606 | 39.42 |

224 contracts worth ₱14.83 billion go to the investigator's worklist. Of the 606 Atlas cannot verify,
242 have a single source showing nothing, 205 have no decisive observation after completion,
118 have no capture after completion, 25 could not be located and 16 have sources that disagree. These
are leads, not findings of fact: each case names its sources and the reason for its outcome, and a human signs it
before it leaves the system.

## The evidence ledger

[`atlas/ledger.py`](atlas/ledger.py) appends one entry per tool call, capture, mask, reading, finding, verdict, case
file and signature. Each entry carries the SHA-256 of the previous one; image chips and masks are stored under the
hash of their own bytes. The web app re-verifies the whole chain and the case's evidence files in the browser
([`web/src/ledger/verify.ts`](web/src/ledger/verify.ts)), reproducing the Python canonical JSON byte for byte, so the
check trusts nothing the server says. Editing one sealed claim in a copy breaks every seal from that entry on.

## Cost and budget

Every Meta call is cached on disk by the hash of its request, so a recorded mission replays byte for byte without
spending credit, and every call is metered against a hard cap before it is sent. A full-depth audit with a case file
costs about $0.15; screening depth about $0.03.

## Run it

```
python -m venv --system-site-packages .venv
.venv/Scripts/python -m pip install rasterio shapely pyproj mercantile httpx fastapi uvicorn scipy pillow numpy
cp .env.example .env            # MODEL_API_KEY; optional MAPILLARY_TOKEN, BASETEN_API_KEY
.venv/Scripts/python scripts/build_portfolio.py && .venv/Scripts/python scripts/overlaps.py
.venv/Scripts/python -m uvicorn atlas.server:app --port 8787
cd web && npm install && npm run dev    # http://localhost:5317
```

- One contract: `.venv/Scripts/python -m atlas.audit 24CC0032 --run dev` (add `--lm open` for Muse Spark Open)
- A province: `.venv/Scripts/python scripts/fleet_run.py --run bulacan --budget 40 --full-top 40`
- The evaluation: `.venv/Scripts/python scripts/evaluate.py --run eval` then `--compare eval eval-open`
- Tests: `.venv/Scripts/python -m pytest tests`

## Layout

- `atlas/agents/` Locator, Existence (optical history, Sentinel-2), Ground, Relocation, Timeline, Valuation, Impact,
  Case builder
- `atlas/verdict.py` the evidence calculus; `atlas/ledger.py` the hash chain; `atlas/fleet.py` mission planning
  against budget and deadline; `atlas/meta.py` the model client (cache, meter, default-deny tool gateway, open-weights
  host); `atlas/server.py` the HTTP API
- `web/` the investigator's interface (React, MapLibre)
- `data/answer_key/` official findings, read only by the evaluation, never by an audit

## Data

DPWH flood-control projects (the President's portal list, 9,855 rows, and later records from the BetterGov DPWH API);
Esri World Imagery Wayback; Sentinel-2 L2A (ESA Copernicus, via Element 84 Earth Search); Copernicus DEM GLO-30;
High Resolution Settlement Layer (Meta and CIESIN, CC BY 4.0); Mapillary (CC BY-SA 4.0); OpenStreetMap waterways
(ODbL); PSA/NAMRIA barangay boundaries via OCHA COD-AB (CC BY-IGO). Imagery attribution is shown on every map.

## Limits

Atlas reports observations and exceptions, never intent. Sub-metre history depends on when Wayback captured a site:
for contracts completed in 2025 the newest capture often predates completion, and Atlas then says it cannot verify.
Contract descriptions rarely give stations with a known origin, so the located reach can differ from the approved
site; the Locator states its confidence and the published pin's offset in every case. A human signs every outcome
before it leaves the system.
