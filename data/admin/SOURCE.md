# Bulacan administrative boundaries: source and build notes

## Outputs

| File | Features | Bytes |
|---|---|---|
| `bulacan_barangays.geojson` | 572 barangays (ADM4) | 1,269,346 |
| `bulacan_municipalities.geojson` | 24 municipalities and cities (ADM3) | 336,460 |

Both are GeoJSON FeatureCollections in WGS84 lon/lat (CRS84), coordinates rounded to 6 decimals.

## Source

- Dataset: "Philippines - Subnational Administrative Boundaries" (COD-AB-PHL), OCHA, on HDX
  https://data.humdata.org/dataset/cod-ab-phl (dataset id `cod-ab-phl`)
- Resource used: `phl_admin_boundaries.geojson.zip` (1,058,477,546 bytes, country-wide), resource id `0120c30e-ba8b-487d-83f5-a664eddd3a8e`, last modified on HDX 2026-05-28.
  https://data.humdata.org/dataset/caf116df-f984-4deb-85ca-41b349d3f313/resource/0120c30e-ba8b-487d-83f5-a664eddd3a8e/download/phl_admin_boundaries.geojson.zip
- Layers read from the zip: `phl_admin4.geojson` (barangays) and `phl_admin3.geojson` (municipalities and cities).
- Dataset version: COD-AB version 03 (feature field `version` = `v03`, `valid_on` = 2025-02-13). HDX package metadata modified 2026-08-14.
- Originators per HDX: National Mapping and Resource Information Authority (NAMRIA) and Philippines Statistics Authority (PSA). Contributed by OCHA Philippines; published by OCHA FIS. Methodology: census.
- Licence: Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO) 3.0, `cc-by-igo`.
  http://creativecommons.org/licenses/by/3.0/igo/legalcode . Attribution: OCHA (COD-AB-PHL on HDX), based on NAMRIA and PSA data.

The country-wide zip (1.06 GB) was not saved, because it exceeds the 300 MB limit on kept downloads. The zip was read over HTTP range requests: the central directory, then only the bytes of the two member files, streamed in 16 MB blocks. Only the Bulacan extracts were kept.

## Counts

- Barangays: 572 features in the Bulacan layer (`adm2_pcode` PH03014). The brief expected about 569; this layer gives 572. All 572 have unique `adm4_pcode`, no `valid_to` (no expired units), no invalid or empty geometries, and no duplicate (municipality, name) pairs. The difference was not reconciled against a PSA list.
- Municipalities and cities: 24 (matches the expected 24).
- Nationally, the ADM4 layer has 42,048 features. The HDX dataset description lists "Admin 4: 11920", which does not match the file. Not investigated further.

## Properties

- Barangays: `name` = `adm4_name`; `muni` = `adm3_name` after name normalization; `psgc` = `adm4_pcode` without the "PH" prefix (10 digits).
- Municipalities/cities: `name` = `muni` = normalized `adm3_name`; `psgc` = `adm3_pcode` without "PH", plus "000" to make 10 digits.
- Normalization of municipality names: "City of " removed; " (Capital)" and " (Bigaa)" removed; the source label "Bulacan" for the town of Bulakan is written as "Bulakan" (the source uses the province name for that town).
- Barangay names are unchanged from the source (UTF-8, e.g. "Doña Remedios Trinidad" for the municipality).

## Geometry

Taken from the source polygons, then `shapely.simplify(0.00005, preserve_topology=True)` and each coordinate rounded to 6 decimals. After rounding, all output geometries are valid, and none are empty.

## Acceptance checks (run on the output files)

- Point (120.879176, 14.990567): barangay **Piel** (psgc 0301403012), municipality **Baliwag** (City of Baliwag in the source).
- Point (120.892235, 14.765788): barangay **Perez** (psgc 0301405006), municipality **Bulakan** (labelled "Bulacan" in the source).
- Municipality polygons vs. union of their barangays: all within 0.03% of area, except Doña Remedios Trinidad, where the union is 1.6% smaller than the ADM3 polygon (ratio 0.984). The ADM3 polygon was kept.

## Commands run

Python: `D:/Boulot temp/Meta global hackathon/atlas/.venv/Scripts/python` (Python 3.10.7, shapely 2.1.2, standard library only; no new packages installed).

```
curl -sL --max-time 60 "https://data.humdata.org/api/3/action/package_show?id=cod-ab-phl" -o <tmp>/hdx_pkg.json
python -I "D:/Boulot temp/Meta global hackathon/atlas/scripts/admin/rangezip.py" "<geojson.zip url>"          # lists zip members
python -I "D:/Boulot temp/Meta global hackathon/atlas/scripts/admin/fetch_bulacan.py"                          # streams ADM4 + ADM3, writes raw Bulacan extracts (about 2.5 min)
python -I "D:/Boulot temp/Meta global hackathon/atlas/scripts/admin/build_outputs.py"                          # simplify, round, write outputs, run checks
```

Raw Bulacan extracts (unsimplified, kept as build inputs): `data/raw/psa_admin/bulacan_adm4_raw.geojson` (5.4 MB) and `data/raw/psa_admin/bulacan_adm3_raw.geojson` (2.0 MB).
Scripts: `scripts/admin/rangezip.py`, `scripts/admin/fetch_bulacan.py`, `scripts/admin/build_outputs.py`.
