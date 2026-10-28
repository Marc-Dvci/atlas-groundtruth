# R10: fresh rulings on Bulacan flood-control contracts (28 Oct 2026)

Scope: official findings (COA, ICI, DPWH, Ombudsman, DOJ, Senate, Office of the President) on Bulacan DPWH flood-control contracts, 2022-2025, matched to `atlas/data/portfolio/projects.json`. Grades as in R9: exact = contract ID quoted or cost to the centavo; strong = contractor + barangay/town + cost with no other record fitting; candidate = other records could fit, or the finding is not per project. "(fetch extract)" = quoted from a WebFetch summary of the page, not checked verbatim. "[search summary]" = seen only in search results.

Blind check: nothing under `atlas\data\runs\` or `atlas\data\answer_key\` was opened. The record file was read only for id, cost, abc, contractor, muni, province, deo, desc and dates. The `flags`, `suspicion` and `priority` fields were not used. One exception: the first schema peek printed record 24EG0058 (Palawan, not Bulacan) in full, including those fields. Nothing from it was used.

Excluded IDs (already used) were not re-graded. Where a source re-confirms one, that is noted at the end.

## Problem findings (exact/strong)

| Contract | Grade | Record (cost, contractor, place) | Official finding | Who, date | Quote | Source URL |
|---|---|---|---|---|---|---|
| 25CC0063 | strong: contractor + San Roque + cost to P74M; the only SYMS Baliuag record near that cost. Purok conflict: article says Purok 2, record says Purok 3 | ₱74,111,863.70, SYMS Construction Trading, riverbank protection, Brgy. San Roque (purok 3), Baliuag | Project does not exist ("non-existent"); DPWH also left out the supporting papers | COA, 12 Nov 2025 (fraud audit report sent to ICI) | "According to COA, the P74 million project by SYMS Construction Trading in Baliuag was non-existent..." (GMA, fetch extract); "The P74-million project in Baliuag, awarded to SYMS Construction Trading, was found to be non-existent." (Tribune, fetch extract) | https://www.gmanetwork.com/news/topstories/nation/965797/coa-finds-p344-m-bulacan-flood-control-projects-as-ghost-mismatched/story ; https://tribune.net.ph/2025/11/12/coa-flags-p344m-bulacan-flood-projects-as-fake-or-defective |
| 24CC0010 | strong on identity: Wawao + Caingin + Malolos + P77.2M, the only Wawao Caingin record. The finding is partial (55 m built), so it is listed here with that caveat | ₱77,199,942.76, Wawao Builders, riverbank protection, Brgy. Caingin, Malolos City | Built only 55 m at the approved location, against 148.8 m approved. A partial build, not a full ghost | COA, 12 Nov 2025 | "the P77 million Malolos project by Wawao Builders spanned only 55 meters at the approved location" ... "far shorter than the approved 148.8 meters" (GMA, fetch extract) | https://www.gmanetwork.com/news/topstories/nation/965797/coa-finds-p344-m-bulacan-flood-control-projects-as-ghost-mismatched/story ; https://tribune.net.ph/2025/11/12/coa-flags-p344m-bulacan-flood-projects-as-fake-or-defective (Tribune gives "P77 million", "55 meters", "148.8 meters", no barangay) |

Caveats for the rows above:
- 25CC0063: GMA prints "Purok 2"; the record says purok 3. The other SYMS San Roque record, 25CC0054 (77,199,920.13, purok 2), matches the purok but not the P74M figure, so 25CC0063 is the only cost fit.
- 24CC0010: the GMA article does not tie the sentence "a project tagged as 100% complete had no flood control structure visible at the pinpointed location" to this project. R9 said two sources disagree on whether anything stands. The primary text says 55 m stands at the approved site. The "no structure observed" source was not located.

## Negative controls (exact/strong)

None found. No project-level official inspection, validation or audit result in the sources reached says a Bulacan contract was built as declared at the approved site. See "Negative-control search" below for what was checked and why each item was rejected.

## Candidates (not scored)

| Contract | Grade | Record (cost, contractor, place) | Official finding | Who, date | Quote | Source URL |
|---|---|---|---|---|---|---|
| 24CC0297 or 24CC0298 | candidate: two records fit "P98.9 million" (article gives no centavo figure); no contract ID in article. Also resolves R9's label: the finding is pre-existing, not "relocated" | 24CC0297: ₱98,999,508.95, TopNotch / One Frame, slope protection, Brgy. Bunsuran (purok 4), Pandi, start 23 Apr 2024, completion 2 Jan 2025. 24CC0298: ₱98,999,713.40, same contractor and place, start 23 Apr 2024, completion 29 Nov 2024 | "COA found that both projects' designated sites already had an existing slope protection structure" ... "weeks before the contractor's official start date of April 23, 2024." Same article as the used Bambang pair (24CC0402/0403) | COA, 18 Sep 2025 (inspection 10 Sep 2025) | (fetch extract, GMA 959619). Place printed as "Batangay Bunsuran, Pandi"; cost printed as "P98.9 million" | https://www.gmanetwork.com/news/topstories/nation/959619/coa-dpwh-bulacan-flood-control-projects-p390-million/story |
| 25CC0155 | candidate: identity strong (SYMS + Balagtas + San Juan + purok 4 + Balagtas River). Cost conflict: record ₱74,111,867.46 vs article "P77 million" | ₱74,111,867.46, SYMS Construction Trading, riverbank protection along Balagtas River, Brgy. San Juan (purok 4), Balagtas, start 25 Feb 2025, no completion in record | "state investigators also found that the Balagtas riverbank project was supposedly a ghost project" (Tribune fetch). Ombudsman filing says the inspection found it non-existent [search summary] | Ombudsman charges (Sandiganbayan), reported 28-29 Aug 2026 | (fetch extract, Tribune 29 Aug 2026): "state investigators also found that the Balagtas riverbank project was supposedly a ghost project." | https://tribune.net.ph/2026/08/28/co-dpwh-execs-face-flood-charges ; https://mb.com.ph/2026/08/28/ombudsman-files-graft-malversation-raps-vs-co-dpwh-execs-over-77-m-bulacan-flood-control-project (MB returned 403, not read) |
| 24CC0087 | candidate: contractor + Batbatnin + Malolos match; the only Darcy Batbatnin record. Cost conflict: article "P74.1-million" vs record ₱77,199,938.27. Per-project finding, so it is the strongest candidate here | ₱77,199,938.27, Darcy & Anna Builders & Trading, riverbank protection, Brgy. Batbatnin, Malolos City, start 7 Feb 2024, completion 19 Apr 2024 | "was also flagged after CoA confirmed that no structure was built at the approved site." Satellite imagery: the structure found predates the contract by nearly a year | COA, Jan 2026 (Tribune, dated 21 Jan 2026) | (fetch extract) | https://tribune.net.ph/2026/01/20/coa-uncovers-more-questionable-bulacan-projects |
| 25CC0251 | candidate: group finding only. Identity strong (SYMS + San Roque + Baliuag + P92.7M) | ₱92,688,858.48, SYMS Construction Trading, revetment, purok 1-2, Brgy. San Roque, Baliuag, start 25 Feb 2025 | Group finding only: the four projects were "fully paid for but never built" and were "either missing, built elsewhere with substandard structures, or lacked the required documents". The article does not say which applies to which project | COA via Tribune, 3 Oct 2025 | "the P92.7-million flood control structure in Barangay San Roque, Baliuag" (fetch extract) | https://tribune.net.ph/2025/10/02/coa-uncovers-4-new-nonexistent-bulacan-infrastructure-projects |
| 24CC0030 (and 24CC0023) | candidate, defect only. Not an existence finding, so outside the problem categories. Two M3 records fit the ₱96.5M San Roque figure (24CC0030 is the one matching the un-phased "riverbank protection" name) | 24CC0030: ₱96,499,378.64, M3 Konstract (formerly Margarita), Brgy. San Roque, Baliuag, completion 2 Nov 2024. 24CC0023: ₱96,499,563.20, same contractor, "Phase II", completion 1 Nov 2024 | Defects, not existence: "the P96.5 million project by M3 Konstract Corporation already showed multiple defects and cracks" | COA, 12 Nov 2025 | (fetch extract) | https://www.gmanetwork.com/news/topstories/nation/965797/coa-finds-p344-m-bulacan-flood-control-projects-as-ghost-mismatched/story |
| 24CC0356 | candidate: group only. Identity fits (SYMS + Malibong Bata, Pandi, ₱39.6M; article says "P39 million") | ₱39,598,050.46, SYMS Construction Trading, river protection, Brgy. Malibong Bata, Pandi | Group COA finding only: "found no flood control or riverbank protection structures at the approved project sites" is article-wide, not tied to a named project | COA via GMA, 13 Feb 2026 | "the P39 million Riverbank Protection Structure at Barangay Malibong Bata" (fetch extract) | https://www.gmanetwork.com/news/topstories/nation/976487/coa-p275m-flood-control-projects-bulacan-towns/story |
| 24CC0033 | candidate: joint finding with 24CC0032 (already used). The article does NOT name Namayan; R6's Namayan attribution is not supported by this text | ₱77,115,140.90, Wawao Builders, Malolos (article "₱77.11 million"); record barangay Namayan | "No infrastructures were sighted in either of the indicated locations of the projects." Same sentence covers the Bulihan project (24CC0032) | COA via DZRH, 19 Dec 2025 | (fetch extract) | https://dzrh.com.ph/post/coa-flags-peso330m-flood-control-projects-in-bulacan-ghost-illegally-transferred |
| 24CC0592 | candidate-low: the pre-existing claim is unverified. Date and cost both point away from this record (see note) | ₱92,818,653.02, SYMS Construction Trading, Angat River package A, Brgy. Taal-Santo Cristo, Pulilan, start 17 Dec 2024 | R6 (search summary of a Tribune Jan 2026 item): "a slope-protection structure already existed at the approved location prior to the contract's Feb. 25, 2025 effectivity date" [search summary]. The Tribune page I fetched for this claim does not mention Pulilan | COA, Jan 2026 (unverified) | none verified | https://tribune.net.ph/2026/01/20/coa-spots-new-bulacan-flood-issues (returned the 21 Jan 2026 four-project article; no Pulilan) |
| No record in file: Bunsuran purok 5, Pandi (Revilla / Sandiganbayan case; R6 gives 25CC0299) | no record in projects.json: 25CC0299 and 25CC0196 are absent, and the file has no Pandi record between ₱90M and ₱95M. Cost P92.8M, SYMS, purok 5, Bunsuran per R6 (BetterGov data) | (not in file) | Ombudsman complaint: "Despite the absence of any actual construction, the respondents declared the project completed." DPWH officer-in-charge, Bulacan 1st DEO, at Sandiganbayan ocular, 15 Apr 2026: "there were no visible signs of a structure at the site." May 2026 testimony: certified complete with no materials test report | Office of the Ombudsman, 16 Jan 2026; DPWH Bulacan 1st DEO OIC, 15 Apr 2026 | (fetch extract) | https://www.philstar.com/headlines/2026/01/16/2501433/graft-raps-filed-vs-revilla-6-ex-dpwh-officials-over-bulacan-flood-control-project ; https://tribune.net.ph/2026/04/15/no-structure-found-in-p928-m-bulacan-project-dpwh ; https://tribune.net.ph/2026/05/20/dpwh-infra-project-cleared-without-required-test-report |

Notes on the candidates:
- 24CC0592 (Pulilan): the "prior to the contract's Feb. 25, 2025 effectivity date" date matches the start of 25CC0195 (₱96,493,812.80, SYMS, Pulilan, start 25 Feb 2025), not 24CC0592 (start 17 Dec 2024). The cost "P92.7-million" matches neither 24CC0592 (₱92.82M) nor 25CC0195.
- Bunsuran pair: the article's "Batangay Bunsuran" wording and "P98.9 million" cannot separate 24CC0297 from 24CC0298.
- Pandi 92.8M: the file does not contain this project. Under the rule set here it cannot be matched to a contract ID in the record file. It is reported as a candidate for the record set, not a match.

## Excluded-ID checks (no new row)

- 24CC0144 (Sipat, Wawao, already used): GMA 959619 (fetch extract) gives "Control structure on Angat River, Sipat Section, Plaridel, Bulacan by Wawao Builders, worth P92.6 million", the COA finding is "the team observed that construction was still ongoing" (10 Sep 2025) and "Historical satellite imagery as of April 7, 2025, further showed no flood control structure at the site". The record cost is ₱96,499,992.10 (completion 11 Jun 2024 matches). Cost conflicts; primary text confirms the finding.
- 24CC0402 and 24CC0403 (Bambang, used): GMA 959619 confirms "both projects' designated sites already had an existing slope protection structure" and the printed costs ₱98,999,012.87 and ₱98,999,038.556. Consistent with R9.
- 24CC0011 (Darcy & Anna, Carillo, Hagonoy, used): ICI, 13 Nov 2025, "entirely non-existent" for a ₱74M Brgy. Carillo riverbank project [search summary, MB and DZRH]. The record is ₱77,199,918.56, so the cost conflicts. Used.

## R9 candidates: outcome

| R9 item | Outcome |
|---|---|
| 24CC0297 / 24CC0298 (Bunsuran, relocated) | Still candidate. The COA finding in the fetched primary text is pre-existing structure, not relocation. Two records fit |
| 24CC0023 / 24CC0030 (San Roque, existing defective structure) | Still candidate. Defects only, not an existence finding |
| 25CC0063 / 25CC0251 (SYMS San Roque, ghost) | 25CC0063 moves to Problem (strong, COA 12 Nov 2025). 25CC0251 stays candidate (group finding only) |
| 24CC0592 (Pulilan, existed before) | Still candidate-low. Claim unverified; date and cost point to other records |
| 24CC0087 (Malolos, cost does not match) | Confirmed cost mismatch (77.2M record vs 74.1M article). Per-project finding (no structure at approved site; pre-existing) |
| 24CC0356 (Pandi, group only) | Still candidate; group finding only |
| 24CC0010 (Caingin, sources disagree) | Moves to Problem (strong on identity, partial build: 55 m of 148.8 m approved) |

## Negative-control search (nothing project-level)

Checked, not scored:
- DPWH validation (Sept 2025): "Teams checked whether reported projects physically existed, and most did" [search summary]. The Tribune 2 Sep 2025 article (fetch extract) gives only the national figure: "Of these, around 160 have undergone validation, with 15 confirmed as 'non-existent.'" No project is named. Aggregate, not scored.
- Bisnar, DPWH Undersecretary, 19 Jan 2026 (SunStar, via R6): "337 of the 416 ... exist but at a different location" is national and not Bulacan-specific. Aggregate, not scored.
- Lacson, 14 Jan 2026: alleges Bonoan gave wrong coordinates. Palace was still verifying as of 15 Jan 2026 [search summary]. An allegation, no named project. Not scored.
- DPWH completion releases (e.g. "DPWH Completes P96.5-M Riverbank Protection Project in Balagtas, Bulacan", dpwh.gov.ph/DPWH/news/37004) are the agency's own completion claim, which the brief excludes. Not fetched.
- Governor Fernando EO 16-B review (Dec 2025): no published results found.
- Sen. Lacson 2026 "flood projects were real; mapping errors" (advocatesomi): the article body did not load; only the headline was readable. Not scored.
- Paombong seawall and Hagonoy Iba floodgate (DPWH inspection, 22 Aug 2026): no contract ID, cost or contractor in the article. Not matched.

## Searched

WebSearch queries (standard mode, 29 queries): Bulacan flood control inspected/functional/validated/cleared/no-deficiency/built-as-planned; Marcos/PBBM inspections; Dizon compliance; Lacson verified/existing; ICI cleared; Ombudsman dismissed; Revilla Pandi Bunsuran 92.8M; Bunsuran purok 4 TopNotch; Balagtas 77.2M Zaldy Co; San Jose del Monte Sto. Cristo; COA verified/no-exception/2nd DEO; DPWH validation Bisnar; Senate site visit; Provincial EO 16-B review; Filipino-language "totoo, may istruktura"; ICI Hagonoy 74M contractor; Lacson "mapping errors"; DPWH "project exists" clarification.

WebFetch (primary text, pages that opened): tribune.net.ph 2025/11/12 (COA P344M); tribune.net.ph 2025/10/02 (P92.7M, Pulilan, Bagong Silang, Pagala); tribune.net.ph 2026/01/20 (21 Jan 2026 COA; two URLs returned the same article); GMA 965797 (two prompts); GMA 976487 (COA P275M, Feb 2026); GMA 959619 (COA P390M; short URL 404, full URL opened, two prompts); tribune.net.ph 2026/05/20; tribune.net.ph 2026/08/23 (Paombong/Hagonoy); tribune.net.ph 2026/08/28 (Balagtas); tribune.net.ph 2026/04/15 (Pandi); tribune.net.ph 2025/09/02 (15 validated); philstar 2026/01/16 (Revilla); dzrh.com.ph COA P330M (19 Dec 2025).

WebFetch returned HTTP 403 (not read): mb.com.ph 2025/11/13 (ICI Hagonoy P74M); mb.com.ph 2026/08/28 (Ombudsman Balagtas); mb.com.ph 2025/10/02 (COA P351M); newsinfo.inquirer.net 2139121.

Records read locally (no verdict fields): projects.json, by ID, contractor, municipality, cost (±0.3M to ±1M), ABC and completion date.

## Caveats

- Several outlets (Manila Bulletin, Inquirer) returned 403. Anything from those is `[search summary]` only.
- WebFetch quotes come from a summarizer and are marked "(fetch extract)". They should be checked verbatim before publication.
- Search summaries contain errors. A summary described the Bunsuran TopNotch / One Frame finding in terms that did not match the GMA primary text. The fetched GMA text gives a pre-existing structure at the designated site, not a relocation, so R9's "relocated" label for 24CC0297 / 24CC0298 is not supported by the fetched text.
- News costs are rounded (P74M, P77M, P98.9M). Matches by rounding are graded candidate or strong as stated above.
- Pandi (Revilla/Sandiganbayan, Bunsuran purok 5, P92.8M): no record in projects.json. It is reported, not matched.
- No category B (negative control) result at project level. The search covered inspections, validations, audits, Senate, ICI, Ombudsman and provincial reviews.
