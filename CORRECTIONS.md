# Corrections

Errata for data released by this repository. Newest first.

---

## 2026-09-26 - Release 0.7.0 corrects ten defects in the bill, vote, member and ideal-point data

Release 0.7.0 rebuilds most of its tables from raw data collected from the Open
Assembly API, with `build_all.sh` and the other scripts in this repository.
The build runs without manual steps, and its only hand-made input is
`data/raw/members/party_overrides.csv`, six documented corrections of party at
election (see (c)). A few files are not rebuilt by it. The ideal-point archive
holds a copy of the 0.6.0 files and a corrected series from a separate run
with a vote cutoff. `hearing_meetings_summary.parquet` and
`assets_wealth_panel.parquet` are carried over unchanged from 0.6.0, and the
16th-19th experimental vote rows are copied from 0.6.0 (see (h)). README.md
lists these exceptions with the commands. Most raw data were collected on
2026-09-25. The 20th-21st member-level votes and the 18th and 20th
BILLINFODETAIL records come from March 2026, because the completed assemblies
were found unchanged upstream (DATA_AVAILABILITY.md). A data audit in
September 2026 found the ten defects listed below in the files shipped up to
0.6.0. Each subsection states what was wrong, how it was detected, what
changed, and how large the change is. All figures were recomputed from the
0.6.0 files and the 0.7.0 build.

| | Correction | Severity | Files affected |
|---|---|---|---|
| (a) | Committee and judiciary meeting tables of the 17th-20th stopped at five rows per bill | High | `committee_meetings_17`-`20`, `judiciary_meetings_17`-`20` |
| (b) | Roll-call votes of same-name legislators were dropped | High | `roll_calls_all`, all ideal-point files |
| (c) | Party labels were the API's current party, applied retroactively | High | `roll_calls_all`, all ideal-point files, `members_20`, `members_21` |
| (d) | Vetoed bills were recorded as separate government bills | High | `master_bills_17`-`22` |
| (e) | The 22nd master lacked every pending non-member bill | High | `master_bills_22` |
| (f) | Member seniority and committees were anachronistic, and some districts were wrong | Medium | `members_17`-`22` |
| (g) | Cosponsorship edges stopped at 100 names per bill and did not cover the 17th-19th | Medium | `cosponsorship_edges` |
| (h) | The 16th-19th vote rows were meeting-level pseudo events, not roll calls | Medium | `roll_calls_all` |
| (i) | The collectors treated API errors as empty results | Medium | all raw collection |
| (j) | Schemas differed across assemblies, and deprecated files were still shipped | Low | masters, meeting tables, `legislator_id_mapping`, ideal points |

The default ideal-point series changes. The files that 0.6.0 shipped are kept
in `ideal_points_archive/v0.6.0_legacy/`, and a series with the bug fixes but
the same vote range as 0.6.0 is kept in `ideal_points_archive/v20260312_corrected/`.
See (c) and the "Ideal points" section of CODEBOOK.md.

### (a) Committee and judiciary meetings of the 17th-20th stopped at five rows per bill

#### What was wrong

`committee_meetings_17` to `committee_meetings_20` held at most five rows per
bill, while the 21st and 22nd held up to 209 and 220. The raw BILLJUDGECONF
files of those assemblies had been collected without an API key. Without a key
the Open Assembly API answers INFO-000 with the true `list_total_count` but
returns only a five-row sample. The collector defaulted the key to an empty
string and stopped paging as soon as a page came back short, without comparing
the rows received with `list_total_count`. The loss fell on the bills with the
longest committee reviews, so meeting counts, review intensity and
subcommittee activity were understated in four of six assemblies and could not
be compared with the 21st and 22nd. The judiciary tables had the same cap, but
few bills reach five 법제사법위원회 rows, so their loss was small.

#### How it was detected

The audit counted rows per bill in every meeting table and found a maximum of
exactly five in the 17th-20th. Keyed live calls for randomly drawn capped
bills returned more rows than were stored. For bill 031347 the API returned
58 rows with a key and, without a key, the same `list_total_count` of 58 with
only five rows.

#### What changed

- BILLJUDGECONF and BILLLWJUDGECONF were collected again, with a key, for
  every bill of the 17th-22nd.
- Every collector now goes through `kna_api.py`, which refuses to run without
  `ASSEMBLY_API_KEY` and raises unless the rows received equal
  `list_total_count`.
- The meeting tables drop exact duplicate rows, which the API itself repeats,
  and use lowercase column names in every assembly (see (j)).

#### Before and after

| Assembly | Committee rows, 0.6.0 | Committee rows, 0.7.0 | Max rows per bill, 0.6.0 | Max rows per bill, 0.7.0 | Bills at exactly 5 rows, 0.6.0 | Bills at exactly 5 rows, 0.7.0 | Judiciary rows, 0.6.0 | Judiciary rows, 0.7.0 |
|---|---|---|---|---|---|---|---|---|
| 17 | 20,044 | 24,156 | 5 | 128 | 2,119 | 408 | 1,624 | 1,628 |
| 18 | 57,003 | 105,229 | 5 | 194 | 10,647 | 2,438 | 2,797 | 2,810 |
| 19 | 78,115 | 150,192 | 5 | 206 | 14,248 | 4,562 | 3,296 | 3,304 |
| 20 | 107,933 | 202,335 | 5 | 199 | 19,811 | 8,167 | 3,323 | 3,325 |
| 21 | 200,283 | 199,384 | 209 | 181 | 9,768 | 9,769 | 3,203 | 3,217 |
| 22 | 108,749 | 137,152 | 220 | 192 | 7,013 | 9,369 | 1,082 | 1,574 |
| Total | 572,127 | 818,448 | | | | | 15,325 | 15,858 |

The 21st and 22nd change for other reasons. The 0.6.0 files held exact
duplicate rows, 973 in the 21st and 480 in the 22nd, which are now dropped.
The 21st gains 74 rows of the ten vetoed committee alternatives that 0.6.0 had
lost (see (d)), and the 22nd reflects the six-month refresh (see (e)). The
0.6.0 17th file also held 3,339 exact duplicate rows.

### (b) Roll-call votes of same-name legislators were dropped

#### What was wrong

`consolidate_votes.py` removed duplicate roll-call rows on
(term, bill_id, member_name) rather than on member_id. Four pairs of
legislators share a name in the 20th and 21st Assemblies. On every vote where
both members of a pair had a row, only one row survived, so 12,418 valid rows
disappeared, 8,292 of them yea, nay or abstain votes and 4,126 absences. Three legislator-terms
had too few votes left to be scaled and were missing from every ideal-point
file. They are 김성태 (9UW75767) and 최경환 (FJ03481D) in the 20th and 이수진
(0R68099X) in the 21st. A fourth, 김병욱 (KB04377U) in the 21st, was scaled
on 20 of his 185 contested votes.

#### How it was detected

The raw API files have no duplicate (bill_id, member_id) pairs, but they have
5,874 duplicate (bill_id, member_name) pairs in the 20th and 6,544 in the 21st.
In the shipped file the member-level yea, nay and abstain counts matched the
official tallies on only 746 of 3,491 votes in the 20th and 172 of 3,272 in
the 21st, counting a vote as matched when it equals one of its tally rows, as
for 0.7.0.

#### What changed

- `consolidate_votes.py` keys every row on member_id, and `roll_calls_all`
  is unique on (term, bill_id, member_id).
- The build compares the member-level counts of every vote with the official
  tally and stops if a 20th or 21st vote disagrees for an unexplained reason.
  The comparison is written to `reports/rollcall_tally_check.csv`.
- All ideal points were estimated again. (c) reports the combined effect on
  the party-distance tables.

#### Before and after

| Assembly | Name | MONA_CD | Rows, 0.6.0 | Rows, 0.7.0 | In the ideal points, 0.6.0 | In the ideal points, 0.7.0 |
|---|---|---|---|---|---|---|
| 20 | 김성태 | 9UW75767 | 341 | 3,491 | No | Yes |
| 20 | 김성태 | BQS2021C | 3,150 | 3,491 | Yes | Yes |
| 20 | 최경환 | FJ03481D | 902 | 2,383 | No | Yes |
| 20 | 최경환 | KA04352K | 2,589 | 3,491 | Yes | Yes |
| 21 | 김병욱 | GFF1986K | 2,765 | 3,272 | Yes | Yes |
| 21 | 김병욱 | KB04377U | 507 | 3,272 | Yes | Yes |
| 21 | 이수진 | 0R68099X | 165 | 3,272 | No | Yes |
| 21 | 이수진 | D4L60530 | 3,107 | 3,272 | Yes | Yes |

| Check | 0.6.0 | 0.7.0 |
|---|---|---|
| 20th roll-call rows | 1,030,510 | 1,036,384 |
| 21st roll-call rows | 969,583 | 976,127 |
| 20th votes whose member-level counts equal the official tally | 746 of 3,491 | 3,491 of 3,491 |
| 21st votes whose member-level counts equal the official tally | 172 of 3,272 | 3,272 of 3,272 |
| Legislator-terms in the ideal points | 936 | 939 in v20260312, 940 in v20260917 |
| `wnom_1d` of 김병욱 (KB04377U), 21st | 0.200 | 0.420 |

In the 20th, bill 2000491 has two official tally rows, and its member-level
counts equal one of them. The 940th legislator-term of the latest vintage is
김준환 (WMT66995), seated in the 22nd on 2026-03-12.

### (c) Party labels were the API's current party, applied retroactively

#### What was wrong

The member-level vote endpoint returns each member's party at the time of
collection and writes it onto every past vote. `roll_calls_all` and the
ideal-point files used this label as `party`, and the ideal-point script used
it to form the party blocs. The 20th Assembly rows therefore carried parties
founded after that Assembly ended, and 46 legislator-terms of the 20th were
labeled 국민의힘 in the 0.6.0 ideal-point files. The labels also changed
between collections. Between the March and September 2026 pulls, 조정식 and
장경태 moved from 더불어민주당 to 무소속 on all of their past votes, and 우원식
moved from 무소속 to 더불어민주당. Compared with the party at election, the
0.6.0 label differed for 190, 153 and 40 legislator-terms of the 20th, 21st
and 22nd.

#### How it was detected

No member has more than one party label within an assembly in the raw vote
files, whatever the date of the vote, and labels of parties that did not yet
exist appear on 2016 votes. A live pull in September 2026 relabeled the three
members above on votes whose other fields were unchanged.

#### What changed

- `party` in `roll_calls_all` and in every ideal-point file is now the party
  at election from `members_{term}.parquet`. For a successor to a
  proportional seat it is the list the seat came from. The API label is kept in `roll_calls_all`
  as `party_api`.
- The party at election is the party whose list or ticket the member was
  elected on. `members_{term}.party` comes from the per-era party of
  ALLNAMEMBER, which is usually that party. Six entries are not, and
  `data/raw/members/party_overrides.csv` replaces them, with the evidence for
  each. The same six labels were in the 0.6.0 member files. CODEBOOK.md
  section 11 describes the evidence.

  | Assembly | Member | ALLNAMEMBER and 0.6.0 `members` | Party at election | Evidence |
  |---|---|---|---|---|
  | 20 | 최경환 (FJ03481D) | 자유한국당 | 새누리당 | Official member record. The party took the name 자유한국당 in 2017, after his first vote on 2016-06-09. |
  | 21 | 윤상현 (MSY7784L) | 국민의힘 | 무소속 | Official member record. 국민의힘 took that name in September 2020, after his first vote on 2020-06-08. |
  | 21 | 양정숙 (PZA4062H) | 무소속 | 더불어시민당 | Elected on the 더불어시민당 proportional list and expelled afterwards. |
  | 21 | 용혜인 (GE71932C) | 기본소득당 | 더불어시민당 | Elected on the 더불어시민당 proportional list, expelled before that party merged into 더불어민주당, and returned to 기본소득당. |
  | 21 | 조정훈 (WJL30106) | 시대전환 | 더불어시민당 | Elected on the 더불어시민당 proportional list, expelled before the term began, and returned to 시대전환. |
  | 21 | 정운천 (NZF1659U) | 미래통합당 | 미래한국당 | Official member record, which lists his proportional seat under 미래한국당. |

  With the overrides, 윤상현 is in the independent bloc of the 21st ideal
  points, and 양정숙, 용혜인 and 조정훈 are in the liberal bloc. 최경환 and
  정운천 are conservative under either label.
- The conservative bloc adds 새누리당, the party's name at the 2016 election,
  and the satellite list parties 미래한국당 and 국민의미래. The liberal bloc
  adds the satellite list parties 더불어시민당 and 더불어민주연합.
- The ideal-point script also sorts its input explicitly, anchors the sign on
  a named legislator, records a vintage and a manifest, and assigns the
  correct party codes inside `dwnominate_fit.rds`. CODEBOOK.md describes these
  changes.

#### Before and after

The table gives the distance between the conservative and liberal bloc means,
the pooled within-bloc standard deviation and their ratio for the 20th, 21st
and 22nd Assemblies, and the growth of the distance from the 20th to the
22nd. "0.6.0, relabeled" applies the party at election, with the six
overrides, and the new bloc lists to the unchanged 0.6.0 estimates.

| Series | Estimates and labels | Distance | Within-bloc SD | Ratio | Growth, 20th to 22nd |
|---|---|---|---|---|---|
| Bridged | 0.6.0, API labels | 0.761 / 0.808 / 0.804 | 0.192 / 0.144 / 0.049 | 3.97 / 5.63 / 16.40 | +5.7% |
| Bridged | 0.6.0, relabeled | 0.812 / 0.832 / 0.806 | 0.157 / 0.119 / 0.075 | 5.19 / 7.00 / 10.82 | -0.7% |
| Bridged | v20260312, corrected | 0.818 / 0.836 / 0.809 | 0.158 / 0.119 / 0.075 | 5.18 / 7.04 / 10.83 | -1.1% |
| Bridged | v20260917, corrected, default | 0.818 / 0.836 / 0.809 | 0.158 / 0.119 / 0.078 | 5.18 / 7.04 / 10.35 | -1.0% |
| Per-assembly W-NOMINATE | 0.6.0, API labels | 0.761 / 0.908 / 1.236 | 0.192 / 0.161 / 0.075 | 3.97 / 5.63 / 16.40 | +62.4% |
| Per-assembly W-NOMINATE | 0.6.0, relabeled | 0.812 / 0.935 / 1.239 | 0.157 / 0.133 / 0.115 | 5.19 / 7.00 / 10.82 | +52.5% |
| Per-assembly W-NOMINATE | v20260312, corrected | 0.818 / 0.931 / 1.240 | 0.158 / 0.132 / 0.114 | 5.18 / 7.04 / 10.83 | +51.6% |
| Per-assembly W-NOMINATE | v20260917, corrected, default | 0.818 / 0.931 / 1.145 | 0.158 / 0.132 / 0.111 | 5.18 / 7.04 / 10.35 | +40.1% |
| Pooled DW-NOMINATE | 0.6.0, API labels | 0.710 / 0.772 / 0.794 | 0.133 / 0.122 / 0.102 | 5.32 / 6.32 / 7.78 | +12.0% |
| Pooled DW-NOMINATE | 0.6.0, relabeled | 0.742 / 0.788 / 0.810 | 0.107 / 0.113 / 0.126 | 6.91 / 6.99 / 6.44 | +9.1% |
| Pooled DW-NOMINATE | v20260312, corrected | 0.745 / 0.789 / 0.809 | 0.108 / 0.112 / 0.125 | 6.90 / 7.06 / 6.49 | +8.6% |
| Pooled DW-NOMINATE | v20260917, corrected, default | 0.781 / 0.825 / 0.846 | 0.109 / 0.115 / 0.123 | 7.14 / 7.18 / 6.90 | +8.4% |

The bridged growth from the 20th to the 22nd falls from +5.7% in 0.6.0 to
-1.1% in the corrected series over the same votes, and most of that change
comes from the labels. Relabeling the unchanged 0.6.0 estimates already moves
it to -0.7%, which accounts for 6.4 of the 6.8 percentage points. The
estimation fixes, mainly the restored same-name votes of (b), account for the
rest. A run that changed only the row order and the sign anchor, on the 0.6.0
input, also gives -0.7% under the new labels. The six months of 22nd votes
added in v20260917 leave the bridged growth almost unchanged and lower the
per-assembly and pooled growth. The dispersion columns move with the labels
too. Relabeling alone raises the bridged within-bloc SD of the 22nd from
0.049 to 0.075 and lowers its ratio from 16.40 to 10.82.

Party blocs changed for 67, 41 and 12 legislator-terms of the 20th, 21st and
22nd. Under the party at election, 38 members of the 20th elected for 국민의당
fall in the `independent` bloc.

### (d) Vetoed bills were recorded as separate government bills

#### What was wrong

When the President returns a bill for reconsideration (재의요구), the API
lists the bill under two BILL_IDs that share its bill_no, the original record
and a reconsideration record. The reconsideration record usually carries a
`GOV_` prefix and the proposer 대통령. The 0.6.0 builders treated these
records as separate government bills. Thirteen vetoed member bills appeared
twice. 33 vetoed committee alternatives appeared only as their reconsideration
record, mostly with proposer kind 정부 and result 부결, so their passage was
lost. `enacted` was 1 for vetoed bills that never became law, and
government-bill counts were inflated by the reconsideration records.

#### How it was detected

`bill_no` was not unique in `master_bills_17`, `master_bills_21` and
`master_bills_22`. Live queries by bill number returned both records of each
pair, for example the 위원장 original of bill 2208496 passed on 2025-03-13 and
its reconsideration record rejected on 2025-04-17. The official counts of
21st government and committee-chair law bills did not match the master.

#### What changed

- Each veto pair is folded into one row per bill. The row keeps the original
  bill's ID, proposer, proposal date and first floor result.
- `proc_rslt`, `proc_dt` and `status` follow the re-vote. A bill whose re-vote
  failed is 부결, a bill never re-voted is 임기만료폐기 at the end of a
  completed term, and a bill awaiting its re-vote in the 22nd is 계류중.
- The new columns `vetoed`, `veto_bill_id`, `veto_dt`, `revote_rslt`,
  `revote_dt` and `first_plenary_rslt` record the veto, and
  `veto_events.parquet` lists all 47 vetoes. The `rgs_*` and `vote_*` columns
  keep the first passage.
- `promulgated` marks law bills with a promulgation date, and `law_reflected`
  drops bills absorbed into a vetoed alternative that was not passed again.
  `law_reflected` uses the four result codes of the official LIKMS 법률반영
  statistic, but it keeps the bills absorbed into alternatives that the floor
  rejected without a veto, so its law-bill total equals the official one only
  in the 18th and 20th. CODEBOOK.md section 1.6 gives the gap in each
  assembly. The definitions of `passed` and `enacted` are unchanged.
- The masters are checked for unique `bill_id` and `bill_no`.

#### Before and after

| Assembly | `GOV_` rows, 0.6.0 | `GOV_` rows, 0.7.0 | Rows sharing a bill_no, 0.6.0 | Rows sharing a bill_no, 0.7.0 | 정부 bills, 0.6.0 | 정부 bills, 0.7.0 | 위원장 bills, 0.6.0 | 위원장 bills, 0.7.0 | Enacted law bills, 0.6.0 | Enacted law bills, 0.7.0 | Vetoed bills, 0.7.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 17 | 1 | 0 | 2 | 0 | 1,284 | 1,284 | 891 | 891 | 1,914 | 1,913 | 2 |
| 18 | 0 | 0 | 0 | 0 | 1,841 | 1,841 | 1,261 | 1,261 | 2,353 | 2,353 | 0 |
| 19 | 3 | 0 | 0 | 0 | 1,270 | 1,267 | 1,518 | 1,521 | 2,793 | 2,793 | 3 |
| 20 | 0 | 0 | 0 | 0 | 1,304 | 1,304 | 1,640 | 1,640 | 3,195 | 3,195 | 0 |
| 21 | 14 | 0 | 8 | 0 | 1,040 | 1,026 | 1,506 | 1,516 | 2,963 | 2,959 | 14 |
| 22 | 27 | 0 | 16 | 0 | 294 | 623 | 635 | 976 | 1,120 | 1,644 | 28 |

The 22nd columns also include the refresh of (e). The 17th and 21st masters
now equal the official LIKMS counts. The 17th has 7,489 law bills and 1,913
enacted law bills, and the 21st has 25,858 law bills, of which 1,372 were
proposed by committee chairs and 831 by the government, with 2,959 enacted.

| Final outcome of the 47 vetoes | Count |
|---|---|
| Rejected on the re-vote (부결) | 36 |
| Expired at the end of the term (임기만료폐기) | 9 |
| Passed again (수정가결), bill 2200851, promulgated 2025-04-22 | 1 |
| Awaiting the re-vote (계류중), bill 2209676 | 1 |

### (e) The 22nd master lacked every pending non-member bill

#### What was wrong

The BILLRCP pull of March 2026 held only processed bills. Government,
committee-chair and other non-member bills entered the master only through
BILLRCP, so `master_bills_22` had no non-member bill that was still pending on
2026-03-20, including pending resolutions and disciplinary motions. Its 208
government law bills included the 27 reconsideration records of (d). All 22nd
data were also six months old.

#### How it was detected

The audit compared the local files with the live API on 2026-09-24. BILLRCP
filtered to the 22nd returned 21,581 records against 4,719 local ones, and
the master's pending bills were all member bills.

#### What changed

- BILLRCP and BILLJUDGE are collected per assembly with the ERACO filter,
  which the API now applies on the server.
- The bill universe of every assembly is the union of BILLRCP, the member-bill
  list and the processed-bill list, and every BILLRCP record must end up as a
  master row or as a folded reconsideration record.
- The 22nd was collected again on 2026-09-25.

#### Before and after

| 22nd Assembly | 0.6.0 | 0.7.0 |
|---|---|---|
| Bills | 17,205 | 21,581 |
| Law bills | 16,907 | 21,022 |
| Pending non-member bills | 0 | 315 |
| 정부 law bills | 208 | 500 |
| 위원장 law bills | 557 | 871 |
| Bills proposed on or before 2026-03-20 whose 0.7.0 BILL_ID is not in 0.6.0 | | 496 |
| Of these, bills whose bill_no is not in 0.6.0 either | | 476 |
| Bills proposed after 2026-03-20 | | 3,908 |
| Latest proposal date | 2026-03-20 | 2026-09-23 |
| Plenary tallies | 1,286 | 1,847 |
| Roll-call rows | 383,739 | 545,107 |
| Members | 306 | 321 |

Of the 496 bills proposed by 2026-03-20 whose 0.7.0 BILL_ID is not in 0.6.0,
476 were absent from 0.6.0 altogether, matched by bill_no. The other 20 were
there under another ID. Nineteen are vetoed committee alternatives that 0.6.0
held only as their `GOV_` reconsideration record (see (d)). The twentieth is
law bill 2203215, which was pending in 0.6.0 and was withdrawn on 2026-05-14
and re-keyed upstream, so its 0.6.0 BILL_ID no longer exists. By proposer the
496 are 291 government bills, 139 member items and 66 committee-chair bills.
138 of the member items are resolutions, disciplinary motions and one rules
bill, and the remaining one is bill 2203215.

### (f) Member seniority and committees were anachronistic, and some districts were wrong

#### What was wrong

- `reelection` held the member's lifetime term count at the time of
  collection, so 정몽준 appeared as 7선 in the 17th Assembly, where he served
  his fifth term.
- `committee` came from a present-day committee string. For members whose
  string was not split by era, the current committees were copied into every
  past assembly. The field was empty for 172 of 322 members of the 21st.
- A positional fallback in `collect_members.py` assigned the district of
  another term to members whose district list had a different length from
  their term list.
- `members_22` lacked the 15 members seated after the March 2026 snapshot.

#### How it was detected

The audit compared `reelection` with the term list of each member and with
the official 역대 국회의원 재선 현황 table, re-parsed the committee strings
per era, and checked districts against the official per-assembly roster.

#### What changed

- `term_number` and `seniority` give the seniority at that assembly.
  `reelection` is kept, documented as the lifetime count. The seniority counts
  of the 18th-21st equal the official table exactly. For the 17th the official
  table counts two more members, 206 against 205 초선 and 43 against 42 3선.
- `committee` lists the committees of the member's dated assignment spells in
  that assembly, from the new `committee_assignments.parquet`.
  `committee_source` records where it came from.
- `district` and `election_type` come from the official per-assembly roster
  where it has the member.
- `party_current`, `is_current`, `birth_calendar` and `snapshot_date` were
  added, and the 22nd was collected again.
- `birth_calendar` comes from the field BTH_GBN_NM of the roster endpoints
  npffdutiapkzbfyvr and nwvrqwxyaytdsfvhu. ALLNAMEMBER's own code,
  BIRDY_DIV_CD, is coded the opposite way, 양 where the rosters say 음 and 음
  where they say 양, for every member, so copying it would invert every value.
  It serves only as an inverted fallback, which no 0.7.0 row uses.
- The party of six members is corrected to the party at election, see (c).

#### Before and after

| Assembly | Members, 0.6.0 | Members, 0.7.0 | 초선 by `reelection` | 초선 by `term_number` | `reelection` differs from seniority at that assembly | Committee filled, 0.6.0 | Committee filled, 0.7.0 | Members with a misaligned 0.6.0 committee string | District changed |
|---|---|---|---|---|---|---|---|---|---|
| 17 | 322 | 322 | 97 | 205 | 178 | 302 | 322 | 37 | 6 |
| 18 | 331 | 331 | 99 | 159 | 149 | 309 | 331 | 42 | 1 |
| 19 | 332 | 332 | 97 | 171 | 174 | 289 | 332 | 89 | 0 |
| 20 | 320 | 320 | 88 | 150 | 135 | 261 | 320 | 135 | 1 |
| 21 | 322 | 322 | 96 | 168 | 156 | 150 | 322 | 228 | 0 |
| 22 | 306 | 321 | 137 | 147 | 0 | 305 | 321 | 174 | 1 |

The 초선 counts by `reelection` are those of the 0.6.0 files, and the
misaligned committee counts come from the audit's re-parse of the 0.6.0
source strings. The substantive district corrections are listed below. Three
other district changes in the 17th replace short province names with the
roster's full names. The 22nd change is 박지원's district string, which the
roster now writes with the 전남광주통합특별시 prefix.

| Member | Assembly | District, 0.6.0 | District, 0.7.0 |
|---|---|---|---|
| 김한길 (1ZF7922T) | 17 | 서울 광진구갑 | 서울특별시 구로구을 |
| 김영선 (LBC8144B) | 17 | 경기 고양시일산서구 | 경기도 고양시일산구을 |
| 김영선 (LBC8144B) | 18 | 경남 창원시의창구 | 경기 고양시일산서구 |
| 박지원 (8BF5855P) | 20 | 전남 해남군완도군진도군 | 전남 목포시 |

The sixth 17th change is not a correction. 유승민 (PWU27609) entered the 17th
Assembly on the 한나라당 proportional list and won 대구 동구을 in the October
2005 by-election, which he held until 2008, and ALLNAMEMBER lists both seats.
0.6.0 gave 대구 동구을, and 0.7.0 gives the roster's seat at election,
`비례(한) 비례(한나라당)`.

### (g) Cosponsorship edges stopped at 100 names per bill and did not cover the 17th-19th

#### What was wrong

`cosponsorship_edges.parquet` was a copy of an edge list built outside this
repository. That collector never requested a second page from BILLINFOPPSR,
so every bill with more than 100 proposers and supporters kept only the first
100 names. The names kept were mostly early in 가나다 order, so the loss fell
on members whose names come late in that order and biased member-level network
measures. The file covered only the 20th-22nd, ended with the bills proposed
by 2026-02-27, and its role column did not separate co-proposers (공동발의)
from supporters (찬성).

#### How it was detected

208 bills had exactly 100 edge rows. A live BILLINFOPPSR call for one of them
reported a `list_total_count` of 128 and returned the other 28 names on page 2.
Comparing each bill's edges with the count in its proposer text found 207
truncated bills.

#### What changed

- `build_structure.py` builds the edges for every member law bill of the
  17th-22nd. Each bill takes the paginated official BILLINFOPPSR list when it
  was fetched, otherwise the old edge rows of bills that were not truncated,
  otherwise the master's proposer code lists.
- `role` is 대표발의, 공동발의 or 찬성, and `party_source` states whether
  `party` is the party at proposal or at election.
- A report compares every bill's edges with its proposer text. 97,253 of the
  97,263 bills match on both the total and the split between proposers and
  supporters. The other ten are nine 17th bills and one 21st bill whose
  official list differs from the text.

#### Before and after

| Assembly | Edges, 0.6.0 | Edges, 0.7.0 | Bills, 0.6.0 | Bills, 0.7.0 | Bills at exactly 100, 0.6.0 | Bills at exactly 100, 0.7.0 | Max per bill, 0.6.0 | Max per bill, 0.7.0 |
|---|---|---|---|---|---|---|---|---|
| 17 | 0 | 121,125 | 0 | 5,728 | 0 | 1 | | 229 |
| 18 | 0 | 222,630 | 0 | 11,191 | 0 | 5 | | 241 |
| 19 | 0 | 210,725 | 0 | 15,444 | 0 | 1 | | 172 |
| 20 | 267,962 | 269,823 | 21,594 | 21,594 | 69 | 0 | 100 | 225 |
| 21 | 297,607 | 300,045 | 23,655 | 23,655 | 54 | 1 | 100 | 261 |
| 22 | 204,204 | 255,415 | 15,676 | 19,651 | 85 | 0 | 100 | 191 |
| Total | 769,773 | 1,379,763 | 60,925 | 97,263 | 208 | 8 | 100 | 261 |

The eight bills at exactly 100 in 0.7.0 all state 100 proposers in their
proposer text. On the 208 bills capped in 0.6.0, the edges rose from 20,800 to
28,247. No member-term lost an edge. The mean gain per member-term on those
bills shows the ordering bias.

| Initial of the member's name | Member-terms | Mean edges regained |
|---|---|---|
| ㄱ to ㅆ | 468 | 1.03 |
| ㅇ to ㅎ | 495 | 14.07 |

### (h) The 16th-19th vote rows were meeting-level pseudo events, not roll calls

#### What was wrong

`roll_calls_all` included 41,281 rows for the 16th-19th Assemblies parsed from
plenary speech text and minutes appendices. The parser merged every vote of a
meeting into one event, and the consolidation then kept one arbitrary vote per
member per meeting. No row had a bill_id, member_id came from a name match
that merged same-name legislators, and members with two-syllable names were
missing because the source spaces out the syllables. The rows looked like
member-level votes but could not form a vote matrix.

#### How it was detected

The audit found exactly one event per meeting in the appendix files, 736,898
exact duplicates among their 789,193 raw rows, and member-meeting pairs with
conflicting votes, of which the consolidation silently kept one. The plenary
minutes refer to 2,062 votes with appendix name lists in the 17th and 1,706 in
the 18th, against 108 and 62 events in the file.

#### What changed

The rows moved unchanged to `roll_calls_16_19_experimental.parquet` with
`quality_flag` = `meeting_level_pseudo_event`, and `roll_calls_all` now holds
only the API votes of the 20th-22nd. No ideal-point series has ever used these
rows. A rebuild from the appendix PDFs is deferred.

#### Before and after

| Assembly | Rows | Meetings | Events in the file | Votes with appendix name lists referred to in the minutes |
|---|---|---|---|---|
| 16 | 923 | 4 | 5 | 175 |
| 17 | 24,901 | 79 | 108 | 2,062 |
| 18 | 14,210 | 62 | 62 | 1,706 |
| 19 | 1,247 | 5 | 5 | 468 |

| File | 0.6.0 | 0.7.0 |
|---|---|---|
| `roll_calls_all.parquet` | 2,425,113 rows, 16th-22nd | 2,557,618 rows, 20th-22nd |
| `roll_calls_16_19_experimental.parquet` | | 41,281 rows |

### (i) The collectors treated API errors as empty results

#### What was wrong

The Open Assembly API returns errors as HTTP 200 with a top-level `RESULT`
object, outside the endpoint envelope, so HTTP-level retries never saw them.
The collectors read such an answer as an empty page. A rate limit or server
error in the middle of a pull would end it early, and the partial result would
be saved as if complete. A per-bill request that failed was checkpointed as
done with zero rows, so resuming never retried it. A resumed run after a
finished one could also overwrite a raw file with only the newly fetched
bills.

#### How it was detected

The audit probed the error codes live and simulated failures against copies of
the collectors. One concrete loss was 17th bill 177459, an enacted law that
had no BILLINFODETAIL row and no meeting rows, so the master showed it with no
floor, transfer or promulgation dates.

#### What changed

All collectors use the shared client `kna_api.py` and append every per-bill
answer to a fetch log, so an interrupted run resumes and failed bills are
retried.

| Situation | Up to 0.6.0 | 0.7.0 |
|---|---|---|
| No API key | Requests ran with an empty key and received five-row samples | Collection stops with an error |
| ERROR-337 or a server-side error inside an HTTP 200 answer | Read as an empty page, and the partial result was saved | Retried with a delay, then raised |
| Rows received differ from `list_total_count` | Not checked | Raises |
| INFO-200, no data | Logged as an error, like real failures | Recorded as a valid empty answer |
| A per-bill request fails | Marked complete with zero rows | Recorded as failed and retried on the next run |
| Resume after a finished run | Rewrote the raw file with the new bills only | Merges, keeping the rows of every other bill |
| Bill 177459, promulgation date | Missing | 2008-03-28 |
| Bill 177459, committee meeting rows | 0 | 7 |

Every bill of the 0.7.0 masters has a BILLINFODETAIL row.

### (j) Schemas differed across assemblies, and deprecated files were still shipped

#### What was wrong

The masters had 49 columns in the 17th-19th, 55 in the 20th-21st and 54 in
the 22nd, with the undocumented columns `eraco` and `law_proc_dt_detail` in
the 17th-21st only. The meeting tables used uppercase columns in the
17th-21st and lowercase in the 22nd, so a loader call with column names failed
for the older assemblies. `legislator_id_mapping` held 121 comma-joined
composite IDs and kept the retracted name `in_dw_nominate`. The deprecated
`dw_ideal_points_20_22.csv` was still shipped although the entry of
2026-07-18 below announced its removal after one release.

#### What changed

| Item | 0.6.0 | 0.7.0 |
|---|---|---|
| Master columns | 49, 55 or 54 by assembly | 67 in every assembly, with one Arrow schema |
| `eraco`, `law_proc_dt_detail` in the 17th-21st masters | Present | Dropped. The detail dates fill the regular columns, and the lite files keep `eraco` |
| `vote_*` columns in the 17th-19th masters | Absent | Present and empty, since the API has no tallies before the 20th |
| `days_to_committee` | 22nd only | Every assembly |
| Meeting table columns, 17th-21st | Uppercase, with `_BILL_ID` | Lowercase, with `bill_id_tagged`, as in the 22nd |
| Exact duplicate meeting rows | Kept | Dropped |
| `legislator_id_mapping` rows | 1,441, including 121 composite IDs | 1,156, one per member of the 17th-22nd |
| `legislator_id_mapping` ideal-point flag | `in_dw_nominate` | `in_ideal_points`, plus `in_dw_nominate` as a deprecated alias for 0.7.0 only |
| `roll_calls_all` | Unsorted, no bill_no, retroactive party | Sorted by (term, date, bill_id, member_id), with `bill_no` and `party_api` |
| Ideal-point CSVs | No vintage | `vintage` column and `ideal_points_manifest.json` |
| `cosponsorship_edges` columns | 5 | 9, adding `age`, `bill_no`, `party_source` and `source` |
| `dw_ideal_points_20_22.csv` and `DEPRECATED_dw_ideal_points.md` | Shipped, deprecated | Removed |
| `ideal_points_17.csv`, `ideal_points_20.csv`, `ideal_points_21.csv`, `ideal_points_22.csv`, `ideal_points_all.csv` | Shipped without documentation | Not part of the 0.7.0 data |

The files in the last row were written by the superseded script
`estimate_idealpoints.R`. The 20th-22nd files keep the raw sign of each fit,
so the sign of the conservative mean differs across terms, and
`ideal_points_17.csv` has placeholder names and no member IDs.

### Action for users

- Analyses of committee meetings in the 17th-20th should be rerun on the new
  tables.
- Roll-call analyses of the 20th and 21st that involve any of the eight
  same-name legislators, or that use `party`, should be rerun.
- The default ideal points are now the corrected v20260917 series. To
  reproduce a result obtained with 0.6.0, use
  `ideal_points_archive/v0.6.0_legacy/`. To separate the bug fixes from the
  added 22nd votes, compare with `ideal_points_archive/v20260312_corrected/`.
- Enactment counts should use `bill_kind == "법률안"` together with
  `enacted`, `promulgated` or `law_reflected`, and veto analyses should use
  `veto_events.parquet`. To match the official LIKMS 법률반영 count, apply the
  rule in CODEBOOK.md section 1.6 instead of `law_reflected`.
- Cosponsorship networks should be rebuilt from the new edge file, in
  particular for mass-cosponsored bills.
- Code that reads `in_dw_nominate` should switch to `in_ideal_points` before
  the next release. Code that read `dw_ideal_points_20_22.csv` should read
  `ideal_points_bridged.csv`.

---

## 2026-07-19 - `wnom_1d` now comes from a one-dimensional fit

**Severity: low.** Affects `ideal_points_wnominate.csv` and
`ideal_points_bridged.csv` as released in 0.5.0. Values change slightly;
conclusions do not.

### What changed

In 0.5.0, `wnom_1d` held the first coordinate of a **two-dimensional**
W-NOMINATE fit. It now holds the coordinate from a **one-dimensional** fit. The
two-dimensional fit is still run and its coordinates are still distributed, as
`wnom2d_dim1` and `wnom2d_dim2`, and its eigenvalues still drive the
dimensionality diagnostics.

Both are defensible specifications. The one-dimensional fit is the better
default here because every quantity these files are used for, the distance
between party means, within-party dispersion, and their ratio, is defined on a
single dimension, and taking one coordinate from a two-dimensional solution
raises a rotation question that a one-dimensional fit does not.

### Size of the change

| Assembly | Correlation, old vs new | Mean abs. difference | Party distance, old to new |
|----------|------------------------|----------------------|----------------------------|
| 20th | 0.9993 | 0.028 | 0.753 to 0.761 |
| 21st | 0.9993 | 0.011 | 0.903 to 0.908 |
| 22nd | 0.9997 | 0.006 | 1.243 to 1.236 |

Growth in the inter-party distance from the 20th to the 22nd Assembly moves from
+65.0 to +62.4 percent. Nothing in the interpretation changes.

### Breaking change

The column `wnom_2d` is gone. Code that read it should read `wnom2d_dim2`. Code
that read `wnom_1d` continues to work but receives slightly different values.
`ideal_points_dwnominate.csv` is unaffected: the pooled estimation was already
one-dimensional.

---

## 2026-07-18 — Ideal point estimates were mislabeled as DW-NOMINATE

**Severity: high.** Affects every release up to and including `kna` 0.4.x, the
`docs/voteview.html` visualization, and any analysis that read
`data/processed/dw_ideal_points_20_22.csv`.

### What was wrong

The file `dw_ideal_points_20_22.csv` was labeled and documented as DW-NOMINATE.
It was not. It contained two columns, neither of which was DW-NOMINATE output:

- `coord1D` was **per-assembly W-NOMINATE**, estimated separately for each
  assembly, with the 21st Assembly's sign flipped to match its neighbours.
- `aligned` was an **undocumented chained bridging alignment** of `coord1D`,
  a legitimate method that had never been described or given a script.

The repository's own site text stated that each assembly was "estimated
independently" and then aligned, which contradicted the DW-NOMINATE label
everywhere else.

`estimate_dwnominate.R` was present and did call `dwnominate()`, but its output
is not what the distributed file contained. The `dwnominate` package is not on
CRAN and was not installed in the environment that produced the release.

### How the mislabeling was detected

Three checks, any of which is sufficient. They are worth running against any
redistributed ideal point file.

1. **Compare against a per-assembly fit.** A dynamic estimator pools terms and
   borrows strength through bridging legislators, so its output must differ
   from a per-assembly solution fitted to the same votes. In the released file
   the 21st Assembly's `coord1D` equaled exactly `-1` times the per-assembly
   W-NOMINATE solution, to machine precision, for all 317 legislators. Terms 20
   and 22 correlated at 0.9999. Genuine pooled estimates correlate at 0.966 to
   0.982 with mean absolute differences of 0.14 to 0.22.

2. **Check the trajectory model.** DW-NOMINATE represents each legislator's
   position as a polynomial in the term index. Under a linear model, a member
   observed in three consecutive terms must satisfy
   `theta(t2) - theta(t1) = theta(t3) - theta(t2)`. Across the 68 legislators
   serving in all three assemblies, the two differences correlated at 0.061.

3. **Check internal consistency.** The two columns implied opposite
   conclusions. The inter-party distance grew 0.720 to 1.236 under `coord1D`
   and 0.720 to 0.804 under `aligned`. A file whose two columns disagree about
   the direction of the headline trend needs its provenance established before
   use.

### What changed

`dw_ideal_points_20_22.csv` is retained for one release cycle so existing code
does not break, but it is deprecated and will be removed. It is superseded by
three files with explicit names, all produced by `build_ideal_points.R`:

| File | Column | Method |
|------|--------|--------|
| `ideal_points_wnominate.csv` | `wnom_1d` | per-assembly W-NOMINATE |
| `ideal_points_bridged.csv` | `bridged_1d` | chained bridging alignment |
| `ideal_points_dwnominate.csv` | `dwnom_1d` | pooled DW-NOMINATE |

`ideal_points_bridged.csv` is now the default series used by the CLI, the
Python API, and the visualization. It is the same method the old `aligned`
column implemented, now documented, scripted, and reproducible, with the
fitted alignment parameters written to `ideal_points_bridging_params.csv`.

Genuine pooled DW-NOMINATE is now distributed for the first time. Note its
limitation: with only three assemblies the estimator admits only constant
trajectories, so each legislator receives a single position for all terms.
See CODEBOOK.md.

### What this changes substantively

Anything reported from `coord1D` as a cross-assembly comparison is affected.
Most consequentially, the growth in the distance between the two major party
means from the 20th to the 22nd Assembly:

| Series | 20th | 21st | 22nd | Growth |
|--------|------|------|------|--------|
| Per-assembly W-NOMINATE | 0.753 | 0.903 | 1.243 | +65.0% |
| Chained bridging | 0.753 | 0.806 | 0.801 | +6.3% |
| Pooled DW-NOMINATE | 0.710 | 0.772 | 0.794 | +12.0% |

Per-assembly estimates fix their scale from the recovered configuration rather
than from any external unit, so what they identify is the ratio of between-party
distance to within-party dispersion rather than the distance itself. Over this
period Korean parties became more internally cohesive: party unity on contested
votes rose from 0.911 to 0.943, a measure that uses no scaling model at all.
Rising cohesion raises that ratio, and per-assembly estimation reports it as
parties moving apart.

Two practical consequences follow for anyone using these files.

**Report dispersion alongside distance.** A polarization trend that moves while
within-party dispersion is flat means something different from one that moves
while dispersion collapses. Both are computable from any of the three series.

**Bridging does not fix this.** The alignment in `ideal_points_bridged.csv` is
an affine map, and an affine map rescales distance and dispersion together, so
it leaves their ratio exactly where it found it. In these data the
distance-to-dispersion ratio is identical under `wnom_1d` and `bridged_1d` in
every assembly (4.05, 5.31, 15.49). Bridging solves comparability, which is a
real and separate problem. Only the pooled estimation in
`ideal_points_dwnominate.csv` anchors the metric outside a single chamber, and
its ratios differ accordingly (5.33, 6.26, 8.04).

Within-assembly rankings and comparisons were never affected: all three series
correlate above 0.96 within any single term.

### Action for users

If you compared scores **across** assemblies using `coord1D`, re-run with
`ideal_points_bridged.csv` or `ideal_points_dwnominate.csv`. If you worked
**within** a single assembly, or used ranks, your results are unaffected.
