# The 22 rulings, by what officials found

Every official finding tied to a Bulacan contract ID sits in the answer keys
([`cases.json`](../../data/answer_key/cases.json), [`blind_2026-10.json`](../../data/answer_key/blind_2026-10.json),
[`blind_2026-10b.json`](../../data/answer_key/blind_2026-10b.json)), each with a `finding` field set from the
ruling's words when the key was built. This page groups the 22 by that field and sets each against the sealed
full-depth verdict (runs `eval` and `blind`, after the 29 October revision). Nothing here re-scores a case; it only
sorts them by what the ruling says went wrong.

## Not built: 10 rulings

Officials found nothing built (`ghost`), nothing built at the approved site (`not_built_at_site`), or nothing built
when it was declared complete (`not_built_when_declared`).

**Atlas let none of the 10 through, and raised the problem on 9.** It flagged 3 on its full evidence standard, and
sent 6 to an investigator with a doubt the imagery raised: the bank still bare after the declared completion in one
capture chain (24CC0032, 24CC0052), a wall another contract built at the same time also claims (24CC0195, 24CC0011),
nothing after completion in one chain (25CC0252), readers split on a capture after completion with work on both banks
more than a year after it (24CC0144). The tenth, 24CC0604, has no capture after its completion date.

| Contract | Match | Ruling | Atlas |
|---|---|---|---|
| 25CC0063 | strong | "non-existent" (COA) | **Probable ghost**: bare on 6 Mar 2025, a week into the contract; Sentinel-2 shows no change on either bank from then to Oct 2026 (rule of 29 Oct, see below) |
| 23CC0156 | candidate | "no evidence of the P77.19 million flood mitigation project was found" | **Existed before the contract**: a wall stands at the reach in January 2020, three years before the award |
| 25CC0241 | exact | "no real construction was found at the approved site" | **Existed before the contract**: the wall at the reach stands in November 2021, three years before the award |
| 24CC0032 | candidate | "No infrastructures were sighted in either of the indicated locations" | Can't verify: bank bare on 7 Apr 2025, a year after completion (0.34 m, both readers); Sentinel-2 cannot testify on a bank this bare |
| 24CC0052 | exact | "the structure was not built at the approved site" | Can't verify: bank bare on 20 Apr 2025, ten months after completion (both readers); Sentinel-2 shows a change in Dec 2024 |
| 25CC0252 | exact | "not a single thing was done" (the President) | Can't verify: no sub-metre capture after the completion date; Sentinel-2 unchanged; the one capture inside the contract was read once, as a structure |
| 24CC0604 | exact | "Ghost; no structure found" | Can't verify: no sub-metre capture after the completion date |
| 24CC0144 | candidate | "declared finished in 2024, but work only resumed in July 2025" | Can't verify: on the April 2025 capture the readers disagree; Sentinel-2 shows work-like disturbance on both banks from August 2025 |
| 24CC0195 | candidate | "no such structure found at the designated site" | Exists, not cleared: not dated to the contract, reach shared with a contract built at the same time |
| 24CC0011 | candidate | "no structure was built at the approved site" | Exists, not cleared: reach shared with a contract built at the same time |

Six of the ten say nothing was built at all, without referring to the approved plans (25CC0063, 23CC0156, 24CC0032,
25CC0252, 24CC0604, 24CC0144). On those six Atlas never reported a structure standing. It saw a structure on two
contracts whose rulings place the missing works at "the approved site" or "the designated site": the plans'
location, which is not public. Both are candidate matches.

## Already there: 6 rulings

| Contract | Match | Ruling | Atlas |
|---|---|---|---|
| 24CC0468 | candidate | "found to already exist before the contract started" | **Existed before the contract**: Sentinel-2 dates the bank's change to July 2023, before the May 2024 award |
| 24CC0403 | exact | "already had an existing slope protection structure weeks before" | Exists, not cleared (shared reach): bare in July 2023, a wall in April 2025 |
| 24CC0402 | exact | same ruling | Exists, not cleared (shared reach): bare in July 2023, a wall in April 2025 |
| 24CC0149 | exact | "a structure was already present at the approved site" (COA); "never constructed at the designated location" (ICI) | Exists, not cleared (site disputed, shared reach): bare in July 2023, a wall in April 2025, Sentinel-2 change Aug-Nov 2024 |
| 24CC0001 | strong | "pre-existing riverbank protection structure" | Exists, not cleared (site disputed): bare in November 2021, a wall in April 2025, Sentinel-2 change Jun-Nov 2024 |
| 24CC0045 | strong | "an existing flood control structure at the approved site even before the contract began" | Exists, not cleared (not dated, shared reach) |

This is where Atlas is weakest: on five of six it saw a structure and, on four, dated it to the contract window. Two
rulings put the structure "weeks before" the award; the last sub-metre capture before it is nine months older. Two
place it at the approved site (24CC0149, 24CC0045), and the second Locator disputes the reach on 24CC0149 and
24CC0001. None of the five was cleared.

## Built elsewhere: 5 rulings, and partly built: 1

These turn on where the approved plans put the works, or how long they were meant to be: neither is public.

| Contract | Match | Ruling | Atlas |
|---|---|---|---|
| 24CC0055 | strong | "was built on another portion of the river" | **Existed before the contract**: the wall at the reach stands in January 2020, four years before the award |
| 25CC0148 | exact | "never constructed at the designated location in the Approved Bid Plans" | Can't verify: no decisive capture after completion |
| 24CC0025 | strong | "constructed at a site different from that indicated in the approved bid plans" | Can't verify: Sentinel-2 unchanged; the March 2025 capture splits the readers |
| 24CC0014 | exact | "found no structure at the designated site" | Exists, not cleared (site disputed, not dated) |
| 24CC0017 | strong | "the structure was outside the approved site" | **Cleared**: a new structure at the reach the contract's words describe, dated to the contract, both Locators agree |
| 24CC0010 | strong | "spanned only 55 meters ... far shorter than the approved 148.8 meters" | Can't verify: sources disagree after completion |

## Read with

- Every ruling found a problem, so these rulings count what Atlas misses; none can show a contract wrongly flagged.
  Province-wide, Atlas flags 250 of the 1,096 contracts (23%), clears 62 (6%), has no capture after completion or no
  locatable site for 144, and sends the other 640 to an investigator unsettled. Letting none through is what Atlas does
  with any contract it cannot clear: these rulings show that known failures do not get through, not that Atlas picks
  them out of the province. Flagged: 3 of the 10 not built, 5 of all 22 (23%), against 23% of the province.
- The "bare, then unchanged" rule that settles 25CC0063 was written on 29 October 2026, after these rulings were known.
  Its one measured input, how often Sentinel-2 misses a new wall, comes from province reaches that no ruling covers
  (10 of 251, [`scripts/instruments.py`](../../scripts/instruments.py)). Without it, Atlas flags 2 of the 10 not-built
  rulings and sends 7 to an investigator with a doubt: 25CC0063 was "one source shows nothing" before.
- Match grades (exact, strong, candidate) are in the key files; 6 of the 22 are candidates, tied to a contract by
  cost, place and wording but not by ID.
