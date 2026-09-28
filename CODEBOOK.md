# kna Codebook

| | |
|---|---|
| Release | 0.8.0 |
| Data collected | Mostly on 2026-09-25, from the Open Assembly API (열린국회정보, open.assembly.go.kr). The 20th-21st member-level votes and the 18th and 20th BILLINFODETAIL records are from March 2026. The BPMBILLSUMMARY texts, the LIKMS vote pages and the 17th-19th plenary minutes were collected on 2026-09-28 (DATA_AVAILABILITY.md). |
| Coverage | 17th-22nd National Assembly. The 22nd Assembly is in session. |

This codebook describes every file in the data directory, which is
`data/processed/` in a repository checkout. Every count and coverage figure
below was computed from the 0.8.0 files. Corrections to earlier releases are
listed in [CORRECTIONS.md](CORRECTIONS.md), and per-assembly coverage and
known limitations in [DATA_AVAILABILITY.md](DATA_AVAILABILITY.md).

---

## Contents

1. [Bill master](#1-bill-master-master_bills_age)
2. [Committee and judiciary meetings](#2-committee-and-judiciary-meetings)
3. [Subcommittee reviews](#3-subcommittee-reviews)
4. [Alternative absorption](#4-alternative-absorption)
5. [Cosponsorship edges](#5-cosponsorship-edges)
6. [Veto events](#6-veto-events)
7. [Vote events](#7-vote-events)
8. [Roll calls, 17th-22nd](#8-roll-calls-17th-22nd)
9. [Experimental 16th vote rows](#9-experimental-16th-vote-rows)
10. [Ideal points](#10-ideal-points)
11. [Members](#11-members)
12. [Committee assignments](#12-committee-assignments)
13. [Legislator ID mapping](#13-legislator-id-mapping)
14. [Bill texts](#14-bill-texts)
15. [Hearing meetings summary](#15-hearing-meetings-summary)
16. [Asset disclosures](#16-asset-disclosures)
17. [Build reports](#17-build-reports)

## Files

| File | One row per | Rows | Section |
|---|---|---|---|
| `master_bills_{17..22}.parquet` | bill | 115,149 | 1 |
| `master_bills_{17..21}_lite.parquet` | bill, 36 legacy columns | 93,568 | 1 |
| `master_bills_22.sqlite` | tables `bills`, `committee_meetings`, `judiciary_meetings` of the 22nd | | 1 |
| `committee_meetings_{17..22}.parquet` | bill x committee meeting x agenda step | 818,448 | 2 |
| `judiciary_meetings_{17..22}.parquet` | bill x 법제사법위원회 meeting | 15,858 | 2 |
| `subcommittee_reviews.parquet` | bill x subcommittee stage | 93,981 | 3 |
| `alternative_absorption.parquet` | committee alternative x linked bill | 25,439 | 4 |
| `cosponsorship_edges.parquet` | bill x member | 1,379,763 | 5 |
| `veto_events.parquet` | vetoed bill | 47 | 6 |
| `vote_events.parquet` | plenary tally (20th-22nd) or recorded vote of the minutes (17th-19th) | 16,465 | 7 |
| `roll_calls_all.parquet` | member x recorded vote, 17th-22nd | 4,147,402 | 8 |
| `roll_calls_16_19_experimental.parquet` | parsed text row, 16th only | 923 | 9 |
| `ideal_points_wnominate.csv`, `ideal_points_bridged.csv`, `ideal_points_dwnominate.csv` | legislator-term | 955 each | 10 |
| `ideal_points_bridging_params.csv`, `ideal_points_manifest.json`, `ideal_points_sessioninfo.txt`, `dwnominate_fit.rds` | build metadata | | 10 |
| `ideal_points_archive/v0.6.0_legacy/`, `ideal_points_archive/v20260312_corrected/` | earlier vintages | 936 and 939 per series | 10 |
| `members_{17..22}.parquet` | member-term | 1,948 | 11 |
| `committee_assignments.parquet` | member x assembly x committee spell | 13,616 | 12 |
| `legislator_id_mapping.parquet` | legislator | 1,156 | 13 |
| `bill_texts_linked.parquet` | bill | 109,829 | 14 |
| `hearing_meetings_summary.parquet` | meeting | 26,261 | 15 |
| `assets_wealth_panel.parquet` | member-year | 3,215 | 16 |
| `reports/` | build reports | | 17 |

`build_all.sh` rebuilds `hearing_meetings_summary.parquet` only when the
kr-hearings-data v10 files are available (section 15), and
`assets_wealth_panel.parquet` only when its source files are available
(section 16). Otherwise it carries the shipped files over. Section 17
describes the build.

## Conventions

**Assembly number.** The column is `age` in the bill tables, `term` in the
roll calls and ideal points, and `assembly` in `committee_assignments` and the
asset panel.

**Bill identifiers.** `bill_id` is the Open Assembly BILL_ID. It is `PRC_` or
`ARC_` followed by 30 characters, or a six-digit number for most 17th-Assembly
bills. All three formats work on the per-bill endpoints. `GOV_` IDs belong to
presidential reconsideration records. They are folded into the vetoed bill's
row and survive only as `veto_bill_id` (section 1.4). `bill_no` has six digits
in the 17th and seven digits from the 18th on, and its first two digits give
the assembly. Both keys are unique within an assembly.

| Format of `bill_id` | 17 | 18 | 19 | 20 | 21 | 22 |
|---|---|---|---|---|---|---|
| `PRC_` | 2,633 | 13,268 | 17,660 | 23,902 | 25,912 | 21,088 |
| `ARC_` | 13 | 1,494 | 1,075 | 1,094 | 795 | 493 |
| six-digit numeric | 5,722 | 0 | 0 | 0 | 0 | 0 |

**Legislator identifiers.** MONA_CD is an eight-character code of digits and
capital letters. It is called `mona_cd` in the member tables and `member_id`
in the roll calls, ideal points and edges. Several legislators share a name
in the same assembly, so joins must use MONA_CD, never the name. In the
17th-19th roll calls `member_id` is null where the minutes print a name that
two members share and do not say which of them voted (section 8).

**Missing values** are null, except `rgs_conf_nm` in the bill master, which
holds a single space (`" "`), not an empty string, when a bill has no plenary
session name. That is the case for 95,613 bills. Test for it with
`rgs_conf_nm.str.strip() == ""`. Other strings are kept as the API returns
them, so 26 values of `bill_nm` and 3 of `prom_law_nm` carry leading or
trailing whitespace.

**Dates** are `datetime64` in the bill master, `subcommittee_reviews`,
`committee_assignments`, `veto_events` and `vote_events`. They are strings in
the meeting tables (`YYYY-MM-DD`) and in the roll calls (`YYYYMMDD HHMMSS` in
the 20th-22nd, `YYYYMMDD` in the 17th-19th).
The 17th committee meeting dates contain a few impossible upstream values,
such as 1905-06-28 and 6006-03-03, which are kept as the API returns them.
The bill master keeps a few impossible or out-of-term dates too, listed in
DATA_AVAILABILITY.md, limitation 9.

**Korean categories**, such as result codes and bill kinds, are kept as the
API returns them.

---

## 1. Bill master (`master_bills_{age}`)

| | |
|---|---|
| Unit | one row per bill (의안), including law bills and every other bill kind. |
| Files | one per assembly. All six share the same 67 columns and the same Arrow schema. |

The bill universe of an assembly is the union of three official lists:

- BILLRCP (접수목록), filtered to the assembly with ERACO
- nzmimeepazxkubdpn (의원발의법률안), the member law bills
- nzpltgfqabtcpsmai (처리의안), the processed law bills

A vetoed bill appears upstream under two BILL_IDs that share its bill_no, the
original record and the reconsideration (재의요구) record. Each pair is folded
into one row (section 1.4). The build checks that `bill_id` and `bill_no` are
unique and that every BILLRCP record is a master row or a folded
reconsideration record. Agenda items that appear only in BILLJUDGE, mostly
인사청문요청안, are not bills and are left out. Their meeting rows are the only
meeting rows without a master bill (section 2).

`master_bills_{17..21}_lite.parquet` keep the 36 columns of the earlier lite
files, including `eraco`, for code written against them. `master_bills_22.sqlite`
holds the 22nd master and its two meeting tables with indexes on `bill_id`,
`bill_no`, `ppsr_kind` and `committee_nm`.

### 1.1 Headline counts

| Assembly | Bills | Law bills | `passed` | `enacted` | `enacted`, law bills | `promulgated` | `law_reflected` | `law_reflected`, law bills | `plenary_decided` | `expired_at_term_end` | `vetoed` | `alt_vetoed` | 계류중 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 17 | 8,368 | 7,489 | 4,457 | 2,546 | 1,913 | 1,913 | 4,455 | 3,810 | 2,557 | 3,353 | 2 | 2 | 0 |
| 18 | 14,762 | 13,913 | 6,775 | 2,930 | 2,353 | 2,353 | 6,775 | 6,178 | 2,938 | 6,489 | 0 | 0 | 0 |
| 19 | 18,735 | 17,822 | 8,095 | 3,414 | 2,793 | 2,793 | 8,084 | 7,445 | 3,424 | 10,052 | 3 | 11 | 0 |
| 20 | 24,996 | 24,141 | 9,362 | 3,794 | 3,195 | 3,195 | 9,403 | 8,799 | 3,800 | 15,216 | 0 | 0 | 0 |
| 21 | 26,707 | 25,858 | 9,537 | 3,550 | 2,959 | 2,959 | 9,701 | 9,070 | 3,575 | 16,579 | 14 | 57 | 0 |
| 22 | 21,581 | 21,022 | 6,223 | 2,012 | 1,644 | 1,555 | 6,138 | 5,765 | 2,046 | 0 | 28 | 124 | 15,105 |
| All | 115,149 | 110,245 | 44,449 | 18,246 | 14,857 | 14,768 | 44,556 | 41,067 | 18,340 | 51,689 | 47 | 194 | 15,105 |

`enacted` counts every bill kind. For enacted laws, filter on
`bill_kind == "법률안"`. In the 22nd, 89 enacted law bills have no
promulgation date yet, and 86 of them passed in September 2026. Section 1.6
compares these counts with the official LIKMS statistics.

### 1.2 Variable index and coverage

Coverage is the share of rows with a non-null value that is not blank.

| # | Variable | Type | 17 | 18 | 19 | 20 | 21 | 22 | All |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `bill_id` | str | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 2 | `bill_no` | str | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 3 | `age` | int | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 4 | `bill_kind` | str | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 5 | `bill_nm` | str | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 6 | `ppsr_kind` | str | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 7 | `proposer_text` | str | 68.5% | 75.8% | 82.4% | 86.4% | 88.6% | 91.1% | 84.5% |
| 8 | `rst_proposer` | str | 68.5% | 75.8% | 82.4% | 86.4% | 88.6% | 91.1% | 84.5% |
| 9 | `rst_mona_cd` | str | 68.5% | 75.8% | 82.4% | 86.4% | 88.6% | 91.1% | 84.5% |
| 10 | `publ_proposer` | str | 66.3% | 72.7% | 82.0% | 86.4% | 88.5% | 91.0% | 83.8% |
| 11 | `publ_mona_cd` | str | 66.3% | 72.7% | 82.0% | 86.4% | 88.5% | 91.0% | 83.8% |
| 12 | `ppsl_dt` | date | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 13 | `committee_dt` | date | 88.1% | 87.5% | 90.5% | 92.4% | 93.2% | 94.2% | 91.7% |
| 14 | `bdg_cmmt_dt` | date | 12.8% | 45.2% | 36.5% | 32.4% | 31.9% | 24.3% | 31.7% |
| 15 | `cmt_present_dt` | date | 72.6% | 81.7% | 87.0% | 89.1% | 88.9% | 83.0% | 85.4% |
| 16 | `jrcmit_prsnt_dt` | date | 12.7% | 44.3% | 35.7% | 31.6% | 31.3% | 23.8% | 31.0% |
| 17 | `jrcmit_cmmt_dt` | date | 88.1% | 87.5% | 90.5% | 92.4% | 93.2% | 94.2% | 91.7% |
| 18 | `cmt_proc_dt` | date | 47.9% | 52.2% | 42.5% | 38.2% | 37.1% | 30.4% | 39.7% |
| 19 | `jrcmit_proc_dt` | date | 12.7% | 44.3% | 35.2% | 31.7% | 31.3% | 23.8% | 30.9% |
| 20 | `law_submit_dt` | date | 21.0% | 14.9% | 14.1% | 12.2% | 10.8% | 7.3% | 12.2% |
| 21 | `law_cmmt_dt` | date | 21.0% | 15.0% | 14.1% | 12.2% | 10.8% | 7.3% | 12.3% |
| 22 | `law_present_dt` | date | 18.4% | 14.2% | 14.0% | 12.0% | 10.5% | 7.1% | 11.8% |
| 23 | `law_prsnt_dt` | date | 18.5% | 14.2% | 14.0% | 12.0% | 10.6% | 7.1% | 11.9% |
| 24 | `law_proc_dt` | date | 18.2% | 14.0% | 13.9% | 11.9% | 10.4% | 7.1% | 11.7% |
| 25 | `rgs_prsnt_dt` | date | 30.4% | 20.5% | 18.3% | 15.2% | 13.4% | 9.4% | 16.0% |
| 26 | `rgs_rsln_dt` | date | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 30.0% | 86.9% |
| 27 | `gvrn_trsf_dt` | date | 24.4% | 16.9% | 15.3% | 13.2% | 11.5% | 7.9% | 13.5% |
| 28 | `prom_dt` | date | 22.9% | 15.9% | 14.9% | 12.8% | 11.1% | 7.2% | 12.8% |
| 29 | `proc_dt` | date | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 30.0% | 86.9% |
| 30 | `jrcmit_proc_rslt` | str | 12.9% | 45.2% | 36.5% | 32.4% | 31.9% | 24.3% | 31.7% |
| 31 | `cmt_proc_result_cd` | str | 47.0% | 51.1% | 42.5% | 37.5% | 36.5% | 29.9% | 39.1% |
| 32 | `law_proc_rslt` | str | 19.3% | 14.0% | 13.9% | 11.9% | 10.4% | 7.1% | 11.8% |
| 33 | `law_proc_result_cd` | str | 19.2% | 13.9% | 13.8% | 11.8% | 10.3% | 7.1% | 11.7% |
| 34 | `rgs_conf_nm` | str | 44.6% | 19.9% | 18.3% | 15.2% | 13.5% | 9.4% | 17.0% |
| 35 | `rgs_conf_rslt` | str | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 30.0% | 86.9% |
| 36 | `proc_rslt` | str | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 30.0% | 86.9% |
| 37 | `status` | str | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 38 | `passed` | int (0/1) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 39 | `enacted` | int (0/1) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 40 | `vote_result_cd` | str | 25.9% | 17.2% | 16.5% | 13.9% | 12.2% | 8.6% | 14.2% |
| 41 | `vote_member_total` | float | 0.0% | 0.0% | 0.0% | 13.9% | 12.2% | 8.6% | 7.5% |
| 42 | `vote_total` | float | 25.9% | 17.2% | 16.5% | 13.9% | 12.2% | 8.6% | 14.2% |
| 43 | `vote_yes` | float | 25.9% | 17.2% | 16.5% | 13.9% | 12.2% | 8.6% | 14.2% |
| 44 | `vote_no` | float | 25.9% | 17.2% | 16.5% | 13.9% | 12.2% | 8.6% | 14.2% |
| 45 | `vote_abstain` | float | 25.9% | 17.2% | 16.5% | 13.9% | 12.2% | 8.6% | 14.2% |
| 46 | `prom_no` | str | 22.9% | 15.9% | 14.9% | 12.8% | 11.1% | 7.2% | 12.8% |
| 47 | `prom_law_nm` | str | 22.4% | 14.4% | 14.1% | 12.2% | 10.4% | 6.8% | 12.1% |
| 48 | `committee_nm` | str | 97.3% | 96.0% | 98.6% | 98.9% | 98.9% | 98.7% | 98.3% |
| 49 | `committee_id` | str | 89.4% | 91.7% | 95.1% | 96.6% | 96.7% | 95.8% | 95.1% |
| 50 | `jrcmit_nm` | str | 12.9% | 45.2% | 36.5% | 32.3% | 31.9% | 24.3% | 31.6% |
| 51 | `link_url` | str | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 52 | `member_list` | str | 68.5% | 75.8% | 82.4% | 86.4% | 88.6% | 91.1% | 84.5% |
| 53 | `days_to_proc` | float | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 30.0% | 86.9% |
| 54 | `days_to_committee` | float | 12.8% | 45.2% | 36.5% | 32.4% | 31.9% | 24.3% | 31.7% |
| 55 | `vetoed` | int (0/1) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 56 | `veto_bill_id` | str | 0.0% | 0.0% | 0.0% | 0.0% | 0.1% | 0.1% | 0.0% |
| 57 | `veto_dt` | date | 0.0% | 0.0% | 0.0% | 0.0% | 0.1% | 0.1% | 0.0% |
| 58 | `revote_rslt` | str | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.1% | 0.0% |
| 59 | `revote_dt` | date | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.1% | 0.0% |
| 60 | `first_plenary_rslt` | str | 0.0% | 0.0% | 0.0% | 0.0% | 0.1% | 0.1% | 0.0% |
| 61 | `promulgated` | int (0/1) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 62 | `law_reflected` | int (0/1) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 63 | `alt_bill_id` | str | 13.2% | 26.0% | 24.9% | 22.3% | 22.5% | 19.8% | 22.1% |
| 64 | `alt_vetoed` | int (0/1) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 65 | `expired_at_term_end` | int (0/1) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 66 | `plenary_decided` | int (0/1) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 67 | `vote_bill_id` | str | 25.9% | 17.2% | 16.5% | 13.9% | 12.2% | 8.6% | 14.2% |

The veto columns look empty at one decimal. They are filled for the 47 vetoed
bills, and `revote_rslt` and `revote_dt` for the 37 of them that had a re-vote.

### 1.3 Variable definitions

Source abbreviations used below:

- RCP = BILLRCP (접수목록)
- NZM = nzmimeepazxkubdpn (의원발의법률안)
- NZP = nzpltgfqabtcpsmai (처리의안)
- JUDGE = BILLJUDGE (심사정보)
- DETAIL = BILLINFODETAIL (의안상세정보), one call per bill
- TALLY = ncocpgfiaoituanbr (의안별표결현황), 20th Assembly on
- MINUTES = the recorded votes of the plenary minutes, 17th-19th, through `vote_events.parquet` (section 7)
- ALT = TVBPMBILL11, through `alternative_absorption.parquet`

When a field has several sources, the first non-null value in the order given
is used. Every bill of the 0.8.0 masters has a DETAIL row.

#### Identifiers and proposer

| Variable | Source | Definition |
|---|---|---|
| `bill_id` | RCP, NZM, NZP | Open Assembly BILL_ID, the primary key. See Conventions. |
| `bill_no` | RCP, NZM, NZP | 의안번호. Six digits in the 17th, seven from the 18th. |
| `age` | | Assembly number. |
| `bill_kind` | RCP | 의안 종류. Bills that appear only in NZM or NZP are 법률안. |
| `bill_nm` | RCP, NZM, NZP | 의안명. Committee alternatives end with `(대안)`. |
| `ppsr_kind` | RCP, then 의원 for NZM bills, then NZP | Proposer kind: 의원, 위원장, 정부, 의장 or 기타. |
| `proposer_text` | NZM | Proposer text, such as `홍길동의원 등 10인` or `A의원 등 6인 외 94인`. `등 N인` counts the proposers and `외 M인` the supporters (찬성). |
| `rst_proposer` | NZM | Lead proposer name, comma-joined for joint leads. |
| `rst_mona_cd` | NZM | Lead proposer MONA_CD, comma-joined for joint leads. 217 bills have joint leads, 214 of them in the 22nd. |
| `publ_proposer` | NZM | Co-proposer names, comma-separated, in the order of `publ_mona_cd`. Supporters are not listed. |
| `publ_mona_cd` | NZM | Co-proposer MONA_CDs. Use `cosponsorship_edges.parquet` for a complete edge list with roles. |
| `member_list` | NZM | LIKMS URL of the proposer list. |
| `link_url` | NZM, RCP, NZP | LIKMS URL of the bill page. |

The proposer fields are filled only for member law bills. The member items of
other kinds, mostly resolutions and disciplinary motions, have no proposer data
in any list. There are 336, 355, 352, 330, 396 and 263 such items in the
17th-22nd.

#### Lifecycle dates

| Variable | Source | Definition |
|---|---|---|
| `ppsl_dt` | NZM, RCP, NZP | 제안일. For a vetoed bill, the original bill's proposal date. |
| `committee_dt` | NZM, NZP, then DETAIL `jrcmit_cmmt_dt` | 소관위 회부일. |
| `bdg_cmmt_dt` | JUDGE | 소관위 회부일 as recorded in BILLJUDGE. Filled only for bills in BILLJUDGE. |
| `cmt_present_dt` | NZM, NZP, then DETAIL `jrcmit_prsnt_dt` | 소관위 상정일. |
| `jrcmit_prsnt_dt` | JUDGE | 소관위 상정일 as recorded in BILLJUDGE. |
| `jrcmit_cmmt_dt` | DETAIL | 소관위 회부일 as recorded in BILLINFODETAIL. |
| `cmt_proc_dt` | NZM, NZP, then DETAIL `jrcmit_proc_dt` | 소관위 처리일. |
| `jrcmit_proc_dt` | JUDGE | 소관위 처리일 as recorded in BILLJUDGE. |
| `law_submit_dt` | NZM, NZP | 법사위 회부일. |
| `law_cmmt_dt` | DETAIL | 법사위 회부일 as recorded in BILLINFODETAIL. |
| `law_present_dt` | NZM, NZP | 법사위 상정일. |
| `law_prsnt_dt` | DETAIL | 법사위 상정일 as recorded in BILLINFODETAIL. |
| `law_proc_dt` | NZM, NZP, then DETAIL | 법사위 처리일. |
| `rgs_prsnt_dt` | DETAIL | 본회의 상정일. |
| `rgs_rsln_dt` | DETAIL | Labeled 본회의 의결일 upstream, but the API fills it for every processed bill with its final disposition date, including 대안반영폐기, 철회 and the term-end date of expired bills. It is not a floor-vote indicator. Use `plenary_decided`. For a vetoed bill it is the date of the first floor passage. |
| `gvrn_trsf_dt` | DETAIL | 정부이송일. |
| `prom_dt` | DETAIL | 공포일. |
| `proc_dt` | NZM, NZP, then DETAIL `rgs_rsln_dt` | Final processing date. It is set for every processed bill. For a bill that expired in a completed assembly it is the last day of the term. For a vetoed bill it is the re-vote date, or the last day of the term when no re-vote took place. Null for the 15,105 pending 22nd bills and for three 18th bills withdrawn with no date in any source. |

Where two sources give the same stage, as `committee_dt`, `bdg_cmmt_dt` and
`jrcmit_cmmt_dt` do, the NZM, NZP and DETAIL based columns cover almost every
referred bill, while the JUDGE columns cover only the bills in BILLJUDGE, which
are mostly bills already disposed of in committee.

#### Results and derived flags

| Variable | Definition |
|---|---|
| `jrcmit_proc_rslt` | Committee result from JUDGE. |
| `cmt_proc_result_cd` | Committee result from NZM or NZP. |
| `law_proc_rslt` | 법사위 result from DETAIL. |
| `law_proc_result_cd` | 법사위 result from NZM or NZP. |
| `rgs_conf_nm` | 본회의 session name from DETAIL, such as `제374회 국회(임시회) 제2차 본회의`. A single space (`" "`) when there is none, never null or an empty string. |
| `rgs_conf_rslt` | Labeled 본회의 결과 upstream. Like `rgs_rsln_dt` it holds the final disposition of every processed bill, including 대안반영폐기, 철회 and 임기만료폐기. For a vetoed bill it is the first floor result. |
| `proc_rslt` | Final result from NZM, RCP or NZP. For a vetoed bill it follows the re-vote (section 1.4). Null for pending 22nd bills. |
| `status` | `proc_rslt`, or 계류중 when it is null. |
| `passed` | 1 if `proc_rslt` is 원안가결, 수정가결 or 대안반영폐기. All bill kinds. |
| `enacted` | 1 if `proc_rslt` is 원안가결 or 수정가결. All bill kinds, so it includes resolutions, budgets and consent motions, and law bills not yet promulgated. Because `proc_rslt` is the final result, a vetoed bill counts only if it was passed again. |
| `promulgated` | 1 if `bill_kind` is 법률안 and `prom_dt` is set, that is, the law was promulgated. |
| `law_reflected` | 1 if `proc_rslt` is 원안가결, 수정가결, 대안반영폐기 or 수정안반영폐기 and `alt_vetoed` is 0. The four results are the result codes of the official LIKMS 법률반영 statistic. The second condition removes bills absorbed into a committee alternative that was vetoed and not passed again, whose content never became law. Computed for all bill kinds. Restricted to 법률안, it equals the official 법률반영 count in the 18th and 20th only, because it keeps the bills absorbed into alternatives rejected on the floor without a veto. Section 1.6 gives the gap in each assembly and a rule that reproduces the official count. |
| `alt_bill_id` | The committee alternative (대안) that TVBPMBILL11 links to this bill (section 4). It means "linked alternative", not "absorbed". It is also set for 74 pending 22nd bills linked to alternatives that are themselves pending, and for 62 bills of the 17th, 18th and 21st that expired together with their alternative. Coverage of 대안반영폐기 bills is 57.5% in the 17th and 99.3% to 99.9% in the 18th-22nd. |
| `alt_vetoed` | 1 if `alt_bill_id` is a vetoed bill whose final result is not a pass. This includes the two bills absorbed into 2209676, a 22nd alternative still awaiting its re-vote. |
| `expired_at_term_end` | 1 if `proc_rslt` is 임기만료폐기. |
| `plenary_decided` | 1 if the bill received a floor decision, that is, `rgs_conf_rslt` is 원안가결, 수정가결 or 부결. When `rgs_conf_rslt` is null the first floor result and then `proc_rslt` are used. For a vetoed bill it records the first floor decision. |
| `days_to_proc` | `proc_dt` minus `ppsl_dt`, in days. For an expired bill it is the time to the end of the term, a censored duration, so filter or censor on `expired_at_term_end`. |
| `days_to_committee` | `bdg_cmmt_dt` minus `ppsl_dt`, in days. It inherits the BILLJUDGE coverage of `bdg_cmmt_dt`. `committee_dt` minus `ppsl_dt` covers far more bills. |

Median `days_to_proc` with and without expired bills:

| Assembly | All bills with `proc_dt` | Excluding `expired_at_term_end` |
|---|---|---|
| 17 | 260 | 127 |
| 18 | 364 | 171 |
| 19 | 409 | 176 |
| 20 | 461 | 168 |
| 21 | 464 | 171 |
| 22 | 146.5 | 146.5 |

#### Committee

| Variable | Definition |
|---|---|
| `committee_nm` | 소관위원회 from NZM or NZP, then DETAIL `jrcmit_nm`. It is never 본회의. It is filled for 95.8% of non-member bills. Names change over time, and both the earlier and the later names appear in the 22nd, for example 환경노동위원회 and 기후에너지환경노동위원회. |
| `committee_id` | Seven-digit committee code from NZM or NZP. |
| `jrcmit_nm` | Committee name as recorded in BILLJUDGE. |

#### Plenary tally

| Variable | Definition |
|---|---|
| `vote_result_cd` | Result of the tally. 원안가결, 수정가결 or 부결 in the 20th-22nd. 가결 or 부결 as the chair announced it in the 17th-19th. Null for one 18th bill whose vote, 18_34089_006, has no readable announcement (section 7). |
| `vote_member_total` | Members seated (재적) at the vote. Null in the 17th-19th, whose minutes print no such count. |
| `vote_total` | Members voting. |
| `vote_yes`, `vote_no`, `vote_abstain` | 찬성, 반대, 기권. |
| `vote_bill_id` | BILL_ID of the tally used in the 20th-22nd. In the 17th-19th the `vote_event_id` of the vote used. It joins to `vote_events.vote_event_id` in every assembly. |

TALLY begins with the 20th Assembly. For the 17th-19th the columns come from
the recorded votes of the plenary minutes (section 7). A bill takes the
latest recorded vote on the bill itself, a repeated vote or a vote to reverse
a decision (번안) included, and otherwise the latest vote on a floor amendment
to it. `vote_total`, `vote_yes`, `vote_no` and `vote_abstain` count the names
the minutes print. Latest is by date and then by order in the minutes. 2,167
bills of the 17th, 2,539 of the 18th and 3,095 of the 19th have these
columns. Of these, 25, 29 and 29 take them from a vote on a floor amendment,
and in the 18th one of the 29 is the repeated vote on the 방송법 amendment of
2009-07-22. Two bills of the 17th take them from a vote to reverse a
decision. Every one of these bills has `plenary_decided` = 1. A bill decided
without a recorded vote, by voice or without objection, keeps the columns
null.

In the 20th-22nd a bill takes its own tally when one exists. Otherwise it
takes a floor-amendment tally filed under its bill_no whose name refers to the
bill, preferring the tally whose result matches the bill's first floor
decision, then the latest and the largest. `vote_bill_id` differs from
`bill_id` for 40, 38 and 35 bills in the 20th, 21st and 22nd. All tallies and
recorded votes, including amendment votes and votes with no bill, are in
`vote_events.parquet`. For a vetoed bill the columns hold the first passage,
because the API publishes no tally for any re-vote.

### 1.4 Vetoed bills

When the President requests reconsideration (재의요구), the API lists the bill
under two BILL_IDs that share its bill_no. The reconsideration record usually
has a `GOV_` prefix and the proposer 대통령. In the 17th, bill 171640's
reconsideration record is `PRC_G0K8A0Q2M1H4L1O1Q2V5H4P2C5K1E9`. Each pair is
one master row:

- `bill_id`, `ppsr_kind`, `ppsl_dt` and the proposer fields describe the
  original bill.
- `rgs_*`, `first_plenary_rslt` and the `vote_*` columns keep the first floor
  passage.
- `proc_rslt`, `proc_dt` and `status` follow the re-vote. A failed re-vote is
  부결, a bill never re-voted is 임기만료폐기 at the end of a completed term,
  and a bill awaiting its re-vote in the 22nd is 계류중.

| Variable | Definition |
|---|---|
| `vetoed` | 1 if reconsideration was requested. |
| `veto_bill_id` | BILL_ID of the reconsideration record. `kna show` accepts it. |
| `veto_dt` | Date of the request, the proposal date of the reconsideration record. |
| `revote_rslt` | Result of the re-vote, when one took place. |
| `revote_dt` | Date of the re-vote, when one took place. |
| `first_plenary_rslt` | First floor result, before the veto. |

`veto_events.parquet` has one row per vetoed bill (section 6).

### 1.5 Value tables

`bill_kind`:

| Value | 17 | 18 | 19 | 20 | 21 | 22 | All |
|---|---|---|---|---|---|---|---|
| 법률안 | 7,489 | 13,913 | 17,822 | 24,141 | 25,858 | 21,022 | 110,245 |
| 결의안 | 389 | 419 | 459 | 377 | 346 | 227 | 2,217 |
| 동의안 | 166 | 137 | 163 | 143 | 133 | 81 | 823 |
| 중요동의 | 71 | 75 | 89 | 77 | 88 | 42 | 442 |
| 승인안 | 83 | 73 | 50 | 53 | 61 | 46 | 366 |
| 예산안 | 25 | 33 | 33 | 85 | 102 | 62 | 340 |
| 의원징계 | 37 | 57 | 39 | 47 | 51 | 56 | 287 |
| 선출안 | 46 | 30 | 52 | 45 | 47 | 35 | 255 |
| 규칙안 | 17 | 12 | 17 | 16 | 14 | 5 | 81 |
| 건의안 | 18 | 5 | 5 | 6 | 3 | 1 | 38 |
| 결산 | 8 | 6 | 4 | 4 | 4 | 3 | 29 |
| 윤리심사 | 19 | 2 | 0 | 0 | 0 | 0 | 21 |
| 헌법개정 | 0 | 0 | 0 | 2 | 0 | 1 | 3 |
| 의원자격심사 | 0 | 0 | 2 | 0 | 0 | 0 | 2 |

`ppsr_kind`:

| Value | 17 | 18 | 19 | 20 | 21 | 22 | All |
|---|---|---|---|---|---|---|---|
| 의원 | 6,064 | 11,546 | 15,796 | 21,924 | 24,051 | 19,914 | 99,295 |
| 위원장 | 891 | 1,261 | 1,521 | 1,640 | 1,516 | 976 | 7,805 |
| 정부 | 1,284 | 1,841 | 1,267 | 1,304 | 1,026 | 623 | 7,345 |
| 의장 | 118 | 103 | 141 | 119 | 104 | 62 | 647 |
| 기타 | 11 | 11 | 10 | 9 | 10 | 6 | 57 |

`status`:

| Value | 17 | 18 | 19 | 20 | 21 | 22 | All |
|---|---|---|---|---|---|---|---|
| 임기만료폐기 | 3,353 | 6,489 | 10,052 | 15,216 | 16,579 | 0 | 51,689 |
| 대안반영폐기 | 1,911 | 3,845 | 4,681 | 5,568 | 5,987 | 4,211 | 26,203 |
| 계류중 | 0 | 0 | 0 | 0 | 0 | 15,105 | 15,105 |
| 원안가결 | 1,553 | 2,170 | 2,354 | 2,671 | 2,304 | 1,403 | 12,455 |
| 수정가결 | 993 | 760 | 1,060 | 1,123 | 1,246 | 609 | 5,791 |
| 폐기 | 447 | 944 | 393 | 144 | 111 | 10 | 2,049 |
| 철회 | 101 | 545 | 188 | 225 | 239 | 171 | 1,469 |
| 수정안반영폐기 | 0 | 0 | 0 | 41 | 221 | 39 | 301 |
| 부결 | 10 | 8 | 7 | 6 | 20 | 33 | 84 |
| 심사대상제외 | 0 | 0 | 0 | 2 | 0 | 0 | 2 |
| 가결 | 0 | 1 | 0 | 0 | 0 | 0 | 1 |

The single 가결 is an 18th 의원징계 item, and the two 심사대상제외 are 20th
의원징계 items. None of the three is in `passed`, `enacted` or
`law_reflected`.

### 1.6 Comparison with the official LIKMS statistics

LIKMS, the bill information system of the National Assembly, publishes counts
of law bills by result for each assembly on its statistics page,
`https://likms.assembly.go.kr/bill/bi/stats/gnStatsPage.do`. The figures below
are the 총계 row of its law-bill statistics, the `searchGnStats` query with
`gnStatsDiv=prpsBill`, accessed on 2026-09-26. The page defines 법률반영 as
the sum of 원안가결, 수정가결, 대안반영 and 수정안반영. Its glossary defines
기타, a result not counted as 법률반영, as the law bills that were not sent to
the floor because a committee alternative absorbed them, when that
alternative was rejected (부결) or was left undecided after a presidential
reconsideration request.

| Assembly | Law bills, LIKMS | Law bills, kna | 원안가결 and 수정가결, LIKMS | `enacted`, law bills | 법률반영, LIKMS | `law_reflected`, law bills | Gap | 기타, LIKMS | `alt_vetoed`, law bills |
|---|---|---|---|---|---|---|---|---|---|
| 17 | 7,489 | 7,489 | 1,913 | 1,913 | 3,766 | 3,810 | +44 | 46 | 2 |
| 18 | 13,913 | 13,913 | 2,353 | 2,353 | 6,178 | 6,178 | 0 | 0 | 0 |
| 19 | 17,822 | 17,822 | 2,793 | 2,793 | 7,429 | 7,445 | +16 | 27 | 11 |
| 20 | 24,141 | 24,141 | 3,195 | 3,195 | 8,799 | 8,799 | 0 | 0 | 0 |
| 21 | 25,858 | 25,858 | 2,959 | 2,959 | 9,063 | 9,070 | +7 | 64 | 57 |
| 22 | 21,022 | 21,022 | 1,644 | 1,644 | 5,763 | 5,765 | +2 | 126 | 124 |

The law bill and enacted law bill counts equal the official ones in every
assembly. `law_reflected` uses the four result codes of the official 법률반영
count but equals it only in the 18th and 20th. In every assembly the official
기타 count equals the number of 대안반영폐기 law bills whose linked alternative
did not become law, either because the floor rejected it or because it was
vetoed and has not been passed again. `alt_vetoed` removes only the second
group, so `law_reflected` keeps the bills absorbed into the six alternatives
below, which the floor rejected without a veto. They account for the whole
gap.

| Assembly | Alternative | Rejected on | Absorbed bills |
|---|---|---|---|
| 17 | 175838 조세특례제한법 일부개정법률안(대안) | 2006-12-22 | 22 |
| 17 | 176321 국민연금법 일부개정법률안(대안) | 2007-04-02 | 22 |
| 19 | 1914136 영유아보육법 일부개정법률안(대안) | 2015-03-03 | 16 |
| 21 | 2112201 법원조직법 일부개정법률안(대안) | 2021-08-31 | 4 |
| 21 | 2118783 한국전력공사법 일부개정법률안(대안) | 2022-12-08 | 3 |
| 22 | 2214062 항공보안법 일부개정법률안(대안) | 2025-11-13 | 2 |

To reproduce the official 법률반영 count, count the law bills whose
`proc_rslt` is one of the four results, leaving out every 대안반영폐기 bill
whose `alt_bill_id` has a `status` other than 원안가결 or 수정가결. This gives
the official total in all six assemblies. The 22nd is in session, so its
official figures change as bills are processed.

---

## 2. Committee and judiciary meetings

| | |
|---|---|
| Files | `committee_meetings_{age}.parquet` (BILLJUDGECONF, 위원회 회의정보) and `judiciary_meetings_{age}.parquet` (BILLLWJUDGECONF, 법제사법위원회 회의정보). |

A committee row is one agenda step of one bill at one meeting, such as 상정,
제안설명, 검토보고, 대체토론, 소위회부, 축조심사 or 의결. A bill discussed at
one meeting therefore has several rows, and the row counts are not counts of
meetings. A judiciary row is one bill at one meeting, with the steps joined by
`/`, for example `상정/제안설명/검토보고/대체토론/의결`. Exact duplicate rows,
which the API repeats, are dropped. Columns are lowercase in every assembly.

| Column | Definition |
|---|---|
| `eraco` | Assembly label, such as `제21대`. |
| `bill_id`, `bill_no`, `bill_nm`, `ppsr`, `ppsl_dt` | Bill fields as returned with the meeting. |
| `jrcmit_conf_nm` / `lwcmit_conf_nm` | Meeting name, such as `제388회 국회(임시회) 제3차 전체회의`. |
| `jrcmit_conf_dt` / `lwcmit_conf_dt` | Meeting date, a `YYYY-MM-DD` string. |
| `jrcmit_conf_rslt` / `lwcmit_conf_rslt` | Agenda step, or the joined steps in the judiciary table. |
| `bill_id_tagged` | The BILL_ID that was requested, which joins to `master_bills.bill_id`. |

| Assembly | Committee rows | Bills | Max rows per bill | Master bills with rows | Judiciary rows | Bills | Max rows per bill |
|---|---|---|---|---|---|---|---|
| 17 | 24,156 | 4,918 | 128 | 58.6% | 1,628 | 1,312 | 5 |
| 18 | 105,229 | 12,077 | 194 | 81.7% | 2,810 | 2,083 | 8 |
| 19 | 150,192 | 16,431 | 206 | 87.7% | 3,304 | 2,627 | 7 |
| 20 | 202,335 | 22,767 | 199 | 91.1% | 3,325 | 2,931 | 6 |
| 21 | 199,384 | 24,101 | 181 | 90.2% | 3,217 | 2,828 | 6 |
| 22 | 137,152 | 18,186 | 192 | 84.3% | 1,574 | 1,541 | 3 |

The 17th and 18th committee tables hold 42 and 24 rows whose bill is not in
the master. They belong to BILLJUDGE-only agenda items, mostly 인사청문요청안.

---

## 3. Subcommittee reviews

| | |
|---|---|
| File | `subcommittee_reviews.parquet` |
| Source | TVBPMCONFINFO (소위 심사정보, 법률안), an endpoint opened in July 2026 |
| Unit | one bill at one subcommittee stage, as the API returns it |

| Column | Type | Definition |
|---|---|---|
| `age` | int | Assembly. |
| `bill_no`, `bill_id` | str | Bill keys. Every row joins to the master. |
| `committee_id`, `committee_name` | str | Standing committee. |
| `sub_committee_name` | str | Subcommittee, such as 법안심사제1소위원회, or 안건조정위원회. Null when the row records only the committee referral and no subcommittee stage. |
| `present_session`, `present_cha` | int | Session (회) and sitting (차) of the subcommittee presentation. |
| `proc_session`, `proc_cha` | int | Session and sitting of the subcommittee decision. |
| `submit_dt` | date | Referral date. |
| `present_dt` | date | Subcommittee presentation date. |
| `proc_dt` | date | Subcommittee decision date. |
| `proc_result_cd` | str | Subcommittee result, such as 대안반영폐기, 수정가결 or 본회의에 부의하지 아니하기로 의결. |
| `enroll_type` | str | `Y` for a direct referral to the subcommittee (소위 직접회부), otherwise `N`. |
| `conf_bigo` | str | Remarks, such as the legal basis and date of a direct referral. |
| `is_direct_referral` | int | 1 when `enroll_type` is `Y`. |

| Assembly | Rows | Bills | Rows without a subcommittee | Direct referrals | 안건조정위원회 rows | Exact duplicate rows | Master bills with any row | Master bills with a named stage |
|---|---|---|---|---|---|---|---|---|
| 17 | 2,966 | 2,802 | 317 | 0 | 0 | 0 | 33.5% | 30.1% |
| 18 | 10,880 | 10,540 | 2,488 | 180 | 0 | 0 | 71.4% | 55.4% |
| 19 | 15,765 | 14,918 | 5,677 | 55 | 0 | 0 | 79.6% | 51.3% |
| 20 | 22,206 | 20,932 | 9,492 | 335 | 36 | 0 | 83.7% | 47.7% |
| 21 | 23,840 | 23,016 | 11,028 | 2,044 | 258 | 0 | 86.2% | 46.2% |
| 22 | 18,324 | 17,727 | 10,120 | 2,294 | 125 | 5 | 82.1% | 36.4% |

The table equals the raw API rows. The five exact duplicate 22nd 안건조정위원회
rows are kept as returned. The API returns far fewer rows for the 17th than
for later assemblies.

---

## 4. Alternative absorption

| | |
|---|---|
| File | `alternative_absorption.parquet` |
| Source | TVBPMBILL11 called with `BILL_ID_REF` set to each committee alternative, one call per alternative |
| Unit | one committee alternative (대안) and one bill linked to it |

| Column | Type | Definition |
|---|---|---|
| `age` | int | Assembly. |
| `alt_bill_id`, `alt_bill_no` | str | The committee alternative. Never null. |
| `absorbed_bill_id`, `absorbed_bill_no` | str | The linked bill. |
| `absorbed_proc_rslt` | str | The linked bill's result as TVBPMBILL11 reports it. |

Alternatives are the bills of BILLRCP and NZP whose name ends with `(대안)`.
BILLRCP lists a vetoed alternative under its reconsideration record, and one
that is still awaiting its re-vote is in neither list under its own ID, so the
collector also queries the ID formed from the `GOV_` record's suffix with the
`PRC_` prefix. That adds 2209676 in the 22nd, whose `alt_bill_no` is taken
from the reconsideration record with the same bill_no. In the 17th the ID
derived this way does not exist, because the original record of bill 176979
has another suffix and is in NZP, and the extra query returned nothing. The
table counts that query, so 604 of the 605 17th alternatives queried are
master bills. Every master bill whose name ends with `(대안)` was queried.
Self links and duplicate pairs are dropped, and no bill is linked to more than
one alternative. Coverage is the share of 대안반영폐기 bills with a link.

| Assembly | Alternatives queried | Alternatives with rows | Links | 대안반영폐기 bills | Linked | Coverage | Links to 임기만료폐기 bills | Links with no result yet |
|---|---|---|---|---|---|---|---|---|
| 17 | 605 | 321 | 1,106 | 1,911 | 1,099 | 57.5% | 7 | 0 |
| 18 | 963 | 953 | 3,831 | 3,845 | 3,825 | 99.5% | 6 | 0 |
| 19 | 1,228 | 1,217 | 4,663 | 4,681 | 4,663 | 99.6% | 0 | 0 |
| 20 | 1,402 | 1,400 | 5,563 | 5,568 | 5,563 | 99.9% | 0 | 0 |
| 21 | 1,373 | 1,356 | 5,996 | 5,987 | 5,947 | 99.3% | 49 | 0 |
| 22 | 864 | 860 | 4,280 | 4,211 | 4,206 | 99.9% | 0 | 74 |

The 17th coverage is low because TVBPMBILL11 returns nothing for most 17th
alternatives with a numeric BILL_ID. The links to 임기만료폐기 bills come from
alternatives that themselves expired, and the 74 links with no result come
from 22nd alternatives that are still pending. These rows are real API links,
which is why `alt_bill_id` in the master means "linked", not "absorbed".

For 0.8.0 the missing 17th links were searched for in other official sources,
without result. TVBPMBILL11 called with other parameters and the other bill
services of the Open Assembly catalog give no further links, and the 대안정보
tab of LIKMS lists the same bills as the API. The texts of the alternatives
support an inference that reaches a precision of 99.8% and a recall of 47.7%
on the linked alternatives and would raise the 17th coverage to 66.7%. Those
links are not official, and the table does not include them. CORRECTIONS.md,
entry of 2026-09-28, describes the search and the inference.

---

## 5. Cosponsorship edges

| | |
|---|---|
| File | `cosponsorship_edges.parquet` |
| Unit | one member on one member law bill, 17th-22nd |

| Column | Type | Definition |
|---|---|---|
| `bill_id`, `bill_no`, `age` | | Bill keys and assembly. |
| `member_id` | str | MONA_CD. Never null, and always in `members_{age}`. |
| `member_name` | str | Name. |
| `party` | str | Party at proposal or at election, see `party_source`. |
| `role` | str | 대표발의 for a lead proposer, 공동발의 for a co-proposer, 찬성 for a supporter, the `외 M인` of the proposer text. |
| `party_source` | str | `proposal` when `party` is the party at proposal from BILLINFOPPSR, `elected` when it is the party at election from `members_{age}`. |
| `source` | str | `BILLINFOPPSR`, `legacy_edges` or `master_codes`, see below. |

Each bill takes the first available source:

1. `BILLINFOPPSR`, the official proposer list, fetched with pagination for the
   bills whose master code lists disagree with the proposer text, for bills the
   earlier edge file had truncated, and for bills newer than that file.
2. `legacy_edges`, the rows of the earlier edge file for bills it had not
   truncated. That file was built from BILLINFOPPSR outside this repository.
3. `master_codes`, the lead and co-proposer code lists of the bill master,
   with names and the party at election from `members_{age}`.

BILLINFOPPSR gives no party for 17th and 18th bills, so those parties come
from `members_{age}` and are marked `elected`. The master code lists carry no
supporters, but every bill with supporters in its proposer text was fetched
from BILLINFOPPSR. There is one row per bill and member, with the strongest
role kept.

| Assembly | Edges | Bills | Max per bill | 대표발의 | 공동발의 | 찬성 | BILLINFOPPSR | legacy_edges | master_codes | `proposal` | `elected` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 17 | 121,125 | 5,728 | 229 | 5,728 | 95,888 | 19,509 | 20,609 | 0 | 100,516 | 0 | 121,125 |
| 18 | 222,630 | 11,191 | 241 | 11,191 | 139,894 | 71,545 | 72,066 | 0 | 150,564 | 0 | 222,630 |
| 19 | 210,725 | 15,444 | 172 | 15,444 | 186,370 | 8,911 | 8,997 | 0 | 201,728 | 8,997 | 201,728 |
| 20 | 269,823 | 21,594 | 225 | 21,594 | 247,638 | 591 | 8,848 | 260,975 | 0 | 269,823 | 0 |
| 21 | 300,045 | 23,655 | 261 | 23,660 | 273,495 | 2,890 | 7,991 | 292,054 | 0 | 300,045 | 0 |
| 22 | 255,415 | 19,651 | 191 | 19,905 | 231,827 | 3,683 | 59,988 | 195,427 | 0 | 255,210 | 205 |
| All | 1,379,763 | 97,263 | 261 | 97,522 | 1,175,112 | 107,129 | 178,499 | 748,456 | 452,808 | 834,075 | 545,688 |

Every member law bill of the 17th-22nd has edges. 97,253 of the 97,263 bills
match their proposer text on both the total and the split between proposers
and supporters, and `reports/cosponsorship_mismatch.csv` lists the other ten,
nine 17th bills and one 21st bill whose official list differs from the text.
Member-sponsored items that are not law bills, such as resolutions and
disciplinary motions, have no edges, because no list in the API gives their
proposers.

---

## 6. Veto events

| | |
|---|---|
| File | `veto_events.parquet` |
| Unit | one vetoed bill (재의요구) |

| Column | Type | Definition |
|---|---|---|
| `age`, `bill_no`, `bill_id` | | The vetoed bill, as in the master. |
| `veto_bill_id` | str | BILL_ID of the reconsideration record. |
| `bill_nm`, `ppsr_kind` | str | Bill name and proposer kind of the original bill. |
| `first_plenary_rslt`, `first_plenary_dt` | str, date | First floor passage. |
| `veto_dt` | date | Date of the reconsideration request. |
| `revote_rslt`, `revote_dt` | str, date | Re-vote, when one took place. |
| `final_status` | str | Final result: 부결, 수정가결, 임기만료폐기 or 계류중. |

| Assembly | 부결 | 수정가결 | 임기만료폐기 | 계류중 | All | 위원장 bills | 의원 bills |
|---|---|---|---|---|---|---|---|
| 17 | 1 | 0 | 1 | 0 | 2 | 1 | 1 |
| 19 | 0 | 0 | 3 | 0 | 3 | 3 | 0 |
| 21 | 9 | 0 | 5 | 0 | 14 | 10 | 4 |
| 22 | 26 | 1 | 0 | 1 | 28 | 20 | 8 |
| All | 36 | 1 | 9 | 1 | 47 | 34 | 13 |

The one bill passed again is 2200851 (방송법 일부개정법률안), promulgated on
2025-04-22. The pending one is 2209676 (헌법재판소법 일부개정법률안(대안)).
Until its re-vote, the two bills absorbed into it, 2209471 and 2207212, have
`alt_vetoed` 1 and `law_reflected` 0.

---

## 7. Vote events

| | |
|---|---|
| File | `vote_events.parquet` |
| Source | TALLY (ncocpgfiaoituanbr) for the 20th-22nd. The recorded votes of the plenary minutes appendices for the 17th-19th (`collect_minutes_votes.py`). |
| Unit | one plenary tally, or one recorded vote of the minutes |

| Column | Type | Definition |
|---|---|---|
| `age` | int | Assembly. |
| `vote_bill_id` | str | BILL_ID of the tally. In the 17th-19th, the bill voted on, which for an amendment vote is the amended bill. Null for 18 votes of the 17th-19th that concern no bill of the master. It joins to `roll_calls_all.bill_id`. |
| `bill_no`, `bill_nm` | str | Bill number and tally name as the API gives them. In the 17th-19th, the bill number of `vote_bill_id` and the title printed in the appendix. |
| `proc_dt` | date | Date of the vote. For the 18 votes of meeting 40341 of the 19th, a sitting that ran from 2016-02-23 to 2016-03-02, it is later than the meeting date. |
| `vote_type` | str | `original` when the tally's BILL_ID is a master bill, or in the 17th-19th a vote on the bill itself. `amendment` for a floor amendment (수정안), matched by bill_no and name in the 20th-22nd. `reversal` for a vote to reverse a decision (번안) and `revote` for a vote repeated under the same title, both 17th-19th only. `reconsideration` for a re-vote after a veto. `other` for votes linked to no bill. |
| `master_bill_id` | str | The master bill the vote belongs to. Null for `other`. |
| `member_tcnt` | int | Members seated. Null in the 17th-19th. |
| `vote_tcnt`, `yes`, `no`, `abstain` | int | Votes cast, 찬성, 반대, 기권. In the 17th-19th, the names printed in the appendix. |
| `result` | str | 원안가결, 수정가결 or 부결 in the 20th-22nd. 가결 or 부결 as announced by the chair in the 17th-19th. Null for the 2 votes of the 18th that also lack the chair's counts, 18_33387_002 and 18_34089_006. |
| `source` | str | `api` for the 20th-22nd, `minutes_pdf` for the 17th-19th. |
| `vote_event_id` | str | ID of the vote. For `api` rows it equals `vote_bill_id`. For `minutes_pdf` rows it is `{age}_{CONFER_NUM}_{seq}`, the seq-th recorded vote in the appendix of that meeting's minutes. It joins to `roll_calls_all.vote_event_id` and to `master_bills.vote_bill_id`. |
| `chair_present`, `chair_yes`, `chair_no`, `chair_abstain` | int | The counts the chair announced in the 17th-19th, 재석, 찬성, 반대 and 기권. Null for 2 votes of the 18th, a vote the chair declared void (18_33387_002) and an announcement that names 반대 twice (18_34089_006). Null in the 20th-22nd. |
| `chair_counts_differ` | bool | True when a count the chair announced differs from the names printed in the appendix. Null where the chair's counts are null, and in the 20th-22nd. |
| `correction_note` | bool | True when the appendix prints a note with the actual counts, as in '(OOO 의원 표결기 조작 지체. 실제 찬성 의원 214인, 기권 의원 3인임)'. Null in the 20th-22nd. |

| Assembly | original | amendment | reversal | revote | other | All |
|---|---|---|---|---|---|---|
| 17 | 2,141 | 40 | 2 | 0 | 6 | 2,189 |
| 18 | 2,510 | 38 | 0 | 1 | 10 | 2,559 |
| 19 | 3,066 | 38 | 0 | 0 | 2 | 3,106 |
| 20 | 3,436 | 52 | 0 | 0 | 4 | 3,492 |
| 21 | 3,228 | 44 | 0 | 0 | 0 | 3,272 |
| 22 | 1,812 | 35 | 0 | 0 | 0 | 1,847 |
| All | 16,193 | 247 | 2 | 1 | 22 | 16,465 |

No tally is of type `reconsideration`, because the API publishes none for the
re-votes. The four `other` tallies of the 20th are petitions whose numbers
collide with bill numbers. The 20th has 3,492 tallies for 3,491 recorded
votes because bill 2000491 has two tally rows.

In the 17th-19th the names printed in the appendix are the record, and the
chair's counts stand beside them. The two agree in 1,999 of the 2,189 votes of
the 17th, in 2,133 of the 2,557 votes of the 18th with a readable announcement
and in 2,532 of the 3,106 votes of the 19th. Where they differ, the appendix
usually prints a correction note whose counts equal the names. This holds for
189 of the 190 differing votes of the 17th, 409 of 424 in the 18th and 570 of
574 in the 19th. The 18th repeated vote is the second vote on the 방송법 floor
amendment of 2009-07-22 (18_33387_003). The chair declared the first vote of
that pair void for lack of members present (표결 불성립) and announced no
counts.

---

## 8. Roll calls, 17th-22nd

| | |
|---|---|
| File | `roll_calls_all.parquet` |
| Source | The name lists of the plenary minutes appendices (【전자투표 찬반 의원 성명】) for the 17th-19th, read by `collect_minutes_votes.py`. nojepdqqaweusdfbi (의원별 표결) for the 20th-22nd, with the LIKMS vote pages for the 22nd members the API omits, read by `collect_votes_likms.py`. |
| Unit | one member on one recorded vote. The key (term, vote_event_id, member_id) is unique over the rows with a member_id, and in the 20th-22nd (term, bill_id, member_id) is unique as well. Rows are sorted by term, date, bill_id, member_id and vote_event_id. |

| Column | Type | Definition |
|---|---|---|
| `term` | int | Assembly. |
| `date` | str | Vote time, `YYYYMMDD HHMMSS`, in the 20th-22nd. `YYYYMMDD` in the 17th-19th, whose minutes print no vote time. |
| `bill_id` | str | The bill voted on. It joins to `vote_events.vote_bill_id`, and usually to `master_bills.bill_id`. In the 17th-19th an amendment vote carries the bill it amends, so several votes can share a bill_id, and 18 votes, which are petitions, procedural motions and four repeal bills the master cannot tell apart, have none. Use `vote_event_id` to identify a vote. |
| `bill_no` | str | Bill number. |
| `vote_event_id` | str | ID of the vote. It equals `bill_id` in the 20th-22nd and is `{term}_{CONFER_NUM}_{seq}` in the 17th-19th. It joins to `vote_events.vote_event_id`. |
| `member_id` | str | MONA_CD. Null for 1,694 rows of the 18th and 19th whose printed name two members share when the minutes do not say which of them voted. |
| `member_name` | str | Name as the API gives it, or for `likms` and `likms_absent` rows the name in `members_22`. In the 17th-19th, the name in `members_{term}`, which is the Hangul form for a name printed in Hanja, and the printed name where member_id is null. |
| `member_match` | str | How the printed name of a 17th-19th row was matched (see below). Null in the 20th-22nd. |
| `vote` | str | 찬성, 반대, 기권 or 불참. 불참 means the member did not vote. The minutes list only the members who voted, so the 17th-19th have no 불참 rows. |
| `party` | str | Party at election from `members_{term}.party` in every assembly. For a successor to a proportional seat, the list the seat came from. Null where member_id is null. |
| `party_api` | str | Party label of the API (POLY_NM). It is the member's party at the time of collection, written onto every past vote, and it changes between collections. The 20th and 21st were collected in March 2026 and the 22nd in September 2026. For `likms` and `likms_absent` rows it is `members_22.party_current`. Null in the 17th-19th. |
| `district` | str | District as the API gives it in the 20th-22nd, `members_{term}.district` in the 17th-19th. Null where member_id is null. |
| `source` | str | `minutes_pdf` in the 17th-19th. `api` in the 20th-22nd, and in the 22nd also `likms` for a member on a LIKMS vote list and `likms_absent` for a seated member on no list. |
| `meeting_id`, `bill_context`, `vote_event` | | The CONFER_NUM of the minutes, the vote title printed in the appendix and the seq of the vote, in the 17th-19th. Null in the 20th-22nd. |
| `agg_total`, `agg_yes` | | Always null. Kept so the schema matches earlier releases. |

| Assembly | Rows | Votes | Members | First vote | Last vote | 찬성 | 반대 | 기권 | 불참 | Rows without member_id | Members with `party` ≠ `party_api` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 17 | 440,473 | 2,189 | 322 | 2004-06-05 | 2008-05-22 | 422,408 | 11,471 | 6,594 | 0 | 0 | - |
| 18 | 500,535 | 2,559 | 328 | 2008-07-16 | 2012-05-02 | 485,355 | 7,541 | 7,639 | 0 | 361 | - |
| 19 | 644,370 | 3,106 | 331 | 2012-07-09 | 2016-05-19 | 619,568 | 9,312 | 15,490 | 0 | 1,333 | - |
| 20 | 1,036,384 | 3,491 | 320 | 2016-06-09 | 2020-05-20 | 671,536 | 7,315 | 18,792 | 338,741 | 0 | 192 |
| 21 | 976,127 | 3,272 | 322 | 2020-06-08 | 2024-05-28 | 696,559 | 9,667 | 20,663 | 249,238 | 0 | 154 |
| 22 | 549,513 | 1,847 | 321 | 2024-07-04 | 2026-09-17 | 391,339 | 9,919 | 6,432 | 141,823 | 0 | 41 |

Members counts the distinct member_ids. `party_api` is null in the 17th-19th.
No ideal-point series uses the 17th-19th rows. `build_ideal_points.R` reads
only the `api`, `likms` and `likms_absent` rows of the 20th-22nd.

### 8.1 The 20th-22nd

The member-level yea, nay and abstain counts equal the official tally for
every vote of the 20th and 21st, with bill 2000491 matching one of its two
tally rows. The member-level API omits 16 members seated during 2026 in the
22nd. They are 이소희, seated on 2026-01-15, the 14 winners of the
by-elections of 2026-06-11, and 김형연, seated on 2026-09-03. Their rows come
from the vote page of LIKMS (의안 상세, 표결정보), read by
`collect_votes_likms.py` on 2026-09-28 for the 791 votes whose API rows fall
short of the tally's membership count. The page lists the members who voted
찬성, 반대 and 기권 by name. The names left over after removing the API's
rows are matched to the one member of `members_22` with that name who has no
API row on that vote, and become `likms` rows. A seated member on no list
becomes a `likms_absent` row with vote 불참. The seat dates come from the
steps in the tally's membership count and from the first list on which each
member appears. The raw rows are in `data/raw/roll_calls_22_supplement.parquet`,
3,295 `likms` and 1,111 `likms_absent`.

With these rows every 22nd vote has as many member rows as the tally's
membership count. One vote still differs from the official tally, bill
2215128 of 2026-01-29, whose member rows give 196 찬성, no 반대 and 1 기권
against 195, 0 and 2 in the tally. The name lists of its LIKMS page give the
member-level counts, and the counts in the header of the same page give the
tally's. The check is in `reports/rollcall_tally_check.csv`.

Four pairs of legislators share a name in the 20th and 21st, 김성태 and
최경환 in the 20th and 김병욱 and 이수진 in the 21st. The 22nd has two members
named 박지원. 8BF5855P has an API row on every vote, and H7X3372O, seated by
a by-election, has `likms` and `likms_absent` rows. Use `member_id` for
every join.

### 8.2 The 17th-19th

The 17th-19th rows come from the minutes PDFs of all 188, 179 and 182
plenary meetings listed by nzbyfwhwaoanttzje, of which 81, 82 and 78 print a
roll-call appendix. The names equal the group counts the appendix prints
(투표/찬성/반대/기권 의원(N인)) in every vote but two. 17_27974_047 prints 207
찬성 over 206 names, and the chair also announced 206. 18_34052_012 prints the
176 찬성 of its correction note over the 175 names of the vote record. One
17th vote, 17_27710_059, prints 원혜영 twice on its 찬성 list, and the repeat
is dropped. The member-level lists were compared with an independent parse of
the same minutes prepared for version 10 of kr-hearings-data before its
release. They are identical for 1,850 of the 1,861 17th votes both hold,
all 2,510 18th votes and 3,104 of 3,105 19th votes. Eleven of the twelve
differences are parse errors on the other side. In seven votes two names are
read as one, in three a page header, a note or stray text is read as a name,
and in one a list is cut short by 56 names. The twelfth is the misprinted
원혜영, which the other parse keeps twice.

`member_match` records how each 17th-19th row was matched:

| Value | Meaning | 17 | 18 | 19 |
|---|---|---|---|---|
| `name` | the one member of `members_{term}` with the printed name | 440,467 | 496,235 | 634,476 |
| `name_spelling` | 유근찬, printed for 류근찬 | 6 | 0 | 0 |
| `hanja` | a name printed in Hanja, matched on `member_name_hanja` | 0 | 734 | 2,027 |
| `same_name_seated_alone` | a shared name on a date when only one of the two held the seat | 0 | 2,651 | 4,720 |
| `same_name_event_hanja` | a shared name in Hangul in a vote that prints the other member in Hanja | 0 | 540 | 1,814 |
| `same_name_pair_same_vote` | a shared name printed twice in one vote with the same vote | 0 | 14 | 0 |
| `unresolved_same_name` | a shared name the minutes do not resolve (member_id null) | 0 | 361 | 1,333 |

Two pairs of members share a name in the 18th (김선동, 이영애) and three pairs in the
19th (권은희, 김영주, 이재영). The minutes print one member of a pair in Hanja
in some meetings, but not always the same one. For 김선동 it is the member
seated later (金先東), for 이영애 the one seated first (李玲愛), and the choice
also varies within a meeting. The seat dates come from the minutes (oath,
vacancy and succession notices) and are listed in `minutes_votes.py`. Nothing
else is inferred, so 284 rows of 김선동 and 77 of 이영애 in the 18th and 732 of
권은희, 474 of 김영주 and 127 of 이재영 in the 19th keep member_id null. They
count toward the vote totals. For a member-level analysis, treat them as
missing.

`bill_id` is set for 2,183 of the 2,189 17th votes, 2,549 of the 2,559 18th
votes and 3,104 of the 3,106 19th votes. The others are 9 petitions (청원), 5
procedural motions of the 18th (의사일정 상정, 토론종결, 회의 비공개) and 4
repeal bills that share their title with a second bill in the master, two
긴급금융조치법 폐지법률안 in the 17th and two 세입보전국채발행에관한건
폐지법률안 in the 18th. Among the votes on a bill itself, the chair's 가결 or
부결 agrees with the master's `rgs_conf_rslt` in all 2,141, 2,509 and 3,066
votes with a result.

---

## 9. Experimental 16th vote rows

| | |
|---|---|
| File | `roll_calls_16_19_experimental.parquet` |

The file keeps its name, but it now holds only the 16th Assembly, 923 rows
from 4 meetings merged into 5 events and parsed from plenary speech text.
These rows are **not a roll-call matrix**. The parser merged the votes of a
meeting into a few events, and the consolidation kept one vote per member per
event, so a row is a member's recorded position at some vote of that meeting,
not at an identifiable vote. No row has a bill_id. `member_id` comes from a
name match that cannot be reproduced from the repository and that merges
same-name legislators. The rows keep `quality_flag` =
`meeting_level_pseudo_event` and are copied unchanged from the previous
release. The 40,358 pseudo-event rows of the 17th-19th were dropped when the
roll calls of section 8 replaced them. See CORRECTIONS.md, entries of
2026-09-26 (h) and 2026-09-28.

The columns are those of `roll_calls_all` without `bill_no`, `party_api`,
`vote_event_id` and `member_match`, plus `quality_flag`. `date` is
`YYYY-MM-DD`, `source` is `inline_text` and `vote` is 찬성, 반대 or 기권.

| Assembly | Rows | Meetings | Events | Members | First date | Last date | Sources |
|---|---|---|---|---|---|---|---|
| 16 | 923 | 4 | 5 | 260 | 2003-11-07 | 2004-03-02 | inline_text 923 |

The API has no member-level votes before the 20th Assembly.

---

## 10. Ideal points

The repository distributes **three ideal-point series**. They answer
different questions and are **not interchangeable**. All are built by
`build_ideal_points.R` from `roll_calls_all.parquet`.

| File | Column | Method | Within an assembly | Across assemblies | Movement of a legislator |
|---|---|---|---|---|---|
| `ideal_points_wnominate.csv` | `wnom_1d` | W-NOMINATE, one-dimensional, per assembly | Yes | No | No |
| `ideal_points_bridged.csv` | `bridged_1d` | Chained bridging alignment of `wnom_1d` | Yes | Yes | Partly |
| `ideal_points_dwnominate.csv` | `dwnom_1d` | Pooled DW-NOMINATE | Yes | Yes | No, constant |

`ideal_points_bridged.csv` is the default series of the CLI and the Python API.

The three files share the columns `member_id` (MONA_CD), `member_name`,
`party`, `party_bloc`, `term` and `vintage`. `ideal_points_wnominate.csv` adds
`wnom2d_dim1` and `wnom2d_dim2` from a two-dimensional fit, and
`ideal_points_bridged.csv` keeps `wnom_1d`. There is one row per
legislator-term, 317, 318 and 320 in the 20th, 21st and 22nd.

**Sign.** Positive is conservative and negative is liberal in every series.

### 10.1 Estimation

- A vote counts as contested when at least 2.5% of those voting yea or nay are
  in the minority. A legislator is scaled with at least 20 contested yea or
  nay votes.
- The input is the rows of `roll_calls_all` with source `api`, `likms` or
  `likms_absent`, which are the 20th-22nd. The 17th-19th rows from the
  minutes are not used.
- 찬성 is yea and 반대 is nay. 기권 and 불참 are treated as missing.
- Input rows are sorted by term, date, bill_id and member_id before the vote
  matrix is built, because W-NOMINATE's output depends on row order.
- **Polarity anchor.** Every fit is oriented so that 추경호 (G152611B) has a
  positive coordinate on every dimension. He was elected for the conservative
  party in all three assemblies and has enough contested votes in each. His
  second-dimension coordinate is close to zero in the 21st, so the sign of
  `wnom2d_dim2` there rests on a legislator near the middle of that
  dimension. In the 22nd that dimension is unstable (section 10.5).
- **Bridging.** `bridged_1d` equals `wnom_1d` in the 20th. The 21st is mapped
  onto the 20th and the 22nd onto the aligned 21st by a least-squares line
  fitted on the legislators serving in both assemblies,
  `bridged_1d[t] = intercept_t + slope_t * wnom_1d[t]`. The parameters are in
  `ideal_points_bridging_params.csv`. The mapping assumes that the bridging
  legislators do not move on average, and any real movement they made is
  absorbed into it.
- **Pooled DW-NOMINATE.** The three assemblies are estimated together, with
  bridging legislators tying the scale. Its trajectory model needs at least
  five terms for a linear trajectory, so with three terms it admits only a
  constant, and each legislator has one position for all terms
  (`model = 0`). Changes in party means across assemblies are then entirely
  compositional. The fit is started from a pooled two-dimensional W-NOMINATE
  solution anchored on the same legislator, with seed 20260718.
  `dwnominate_fit.rds` is the fitted object. The `dwnominate` package is not
  on CRAN. The build used version 1.2 from GitHub, commit
  `fd39e6a85ada1ba491030ac14a1b0f3c1fefb736`, which the manifest records.

### 10.2 Party labels and blocs

`party` is the party at election from `members_{term}.parquet`, the party
whose list or ticket the member was elected on (for a successor to a
proportional seat, the list the seat came from). It includes the six documented overrides
of section 11. Earlier releases used the roll-call API's label, which is the
member's party at collection time applied to every term (CORRECTIONS.md (c)).
`party_bloc` groups the parties:

| `party_bloc` | Parties |
|---|---|
| `conservative` | 국민의힘, 미래통합당, 자유한국당, 새누리당, and the satellite list parties 미래한국당 and 국민의미래 |
| `liberal` | 더불어민주당, and the satellite list parties 더불어시민당 and 더불어민주연합 |
| `progressive` | 정의당, 진보당, 기본소득당, 사회민주당 |
| `rebuilding` | 조국혁신당 |
| `centrist` | 개혁신당, 새로운미래 |
| `liberal_minor` | 민생당, 열린민주당 |
| `independent` | 무소속 and every other party, including 국민의당 and 바른미래당 |

The `conservative` and `liberal` blocs define the party means in the build
log and in the tables below. Under the party at election, 38 members of the
20th elected for 국민의당 fall in `independent`. The counts below are for the
default (v20260917) files.

| `party_bloc` | 20th | 21st | 22nd | All |
|---|---|---|---|---|
| liberal | 136 | 183 | 188 | 507 |
| conservative | 124 | 115 | 113 | 352 |
| independent | 50 | 9 | 0 | 59 |
| progressive | 7 | 7 | 1 | 15 |
| rebuilding | 0 | 0 | 14 | 14 |
| liberal_minor | 0 | 4 | 0 | 4 |
| centrist | 0 | 0 | 4 | 4 |

### 10.3 Vintages, manifest and archive

Every row carries `vintage`, which is `v` followed by the date of the last
vote used. `ideal_points_manifest.json` records the vintage and vote cutoff,
the input path and SHA-256, the number of rows scaled, the settings, the
polarity anchors, the first and last vote date, recorded votes, legislators,
contested votes and APRE of each term, the bridging parameters, the R and
package versions and the SHA-256 of every output. The script, input and member paths
are relative to the repository root, and outputs are listed by file name in
the manifest's own directory. `ideal_points_sessioninfo.txt` is the R
session information.

| Series location | Vintage | Votes used | Legislator-terms | Contested votes, 20th / 21st / 22nd |
|---|---|---|---|---|
| top level of the data directory | v20260917, the default | through 2026-09-17 | 955 | 269 / 331 / 226 |
| `ideal_points_archive/v20260312_corrected/` | v20260312 | through 2026-03-12, the vote range of 0.6.0 | 939 | 269 / 331 / 139 |
| `ideal_points_archive/v0.6.0_legacy/` | none | through 2026-03-12 | 936 | 269 / 332 / 139 |

- **v20260917** is the corrected build on every vote collected by 2026-09-25,
  with the LIKMS rows of the 22nd collected on 2026-09-28. The vintage names
  the date of the last vote, so the 0.7.x files, built without the LIKMS
  rows, carry the same label. The input SHA-256 in the manifest tells them
  apart, and CORRECTIONS.md, entry of 2026-09-28, compares them. The
  per-assembly W-NOMINATE values and `bridged_1d` of the 20th and 21st are
  identical in the two, while the pooled `dwnom_1d` moves slightly in every
  assembly, because it is estimated on the three assemblies at once.
- **v20260312** is the corrected build restricted to votes taken by
  2026-03-12, the vote range of 0.6.0. It differs from the legacy files
  through the fixes of CORRECTIONS.md (b) and (c), the explicit row order and
  the named sign anchor, so it separates those fixes from the six months of
  added 22nd votes. The refreshed data add 53 votes of 김준환 dated
  2026-03-12, and a run without them gives byte-identical ideal-point files.
  Only the manifest differs, in its record of the input and the run time. A
  run on the 0.8.0 roll calls with the same cutoff also gives byte-identical
  ideal-point files.
- **v0.6.0_legacy** holds the files shipped in 0.6.0, byte for byte. They use
  the API party labels, have no `vintage` column and no manifest, and their
  `dwnominate_fit.rds` carries wrong party codes for most 21st and 22nd
  legislators. Use them only to reproduce earlier results.

| Vintage | Term | Bridging legislators | Slope | Intercept | R² |
|---|---|---|---|---|---|
| v20260917 | 21 onto 20 | 126 | 0.8985 | -0.0230 | 0.904 |
| v20260917 | 22 onto 21 | 156 | 0.7661 | -0.0525 | 0.951 |
| v20260312 | 21 onto 20 | 126 | 0.8985 | -0.0230 | 0.904 |
| v20260312 | 22 onto 21 | 151 | 0.6523 | -0.0396 | 0.947 |
| v0.6.0 legacy | 21 onto 20 | 126 | 0.8901 | -0.0178 | 0.904 |
| v0.6.0 legacy | 22 onto 21 | 150 | 0.6508 | -0.0385 | 0.947 |

### 10.4 Comparing the series

Distance between the conservative and liberal bloc means, the pooled
within-bloc standard deviation, and their ratio, for the 20th, 21st and 22nd
Assemblies in the default vintage:

| Series | Distance | Within-bloc SD | Ratio | Growth of the distance, 20th to 22nd |
|---|---|---|---|---|
| `wnom_1d` | 0.818 / 0.931 / 1.068 | 0.158 / 0.132 / 0.107 | 5.18 / 7.04 / 10.01 | +30.6% |
| `bridged_1d` | 0.818 / 0.836 / 0.818 | 0.158 / 0.119 / 0.082 | 5.18 / 7.04 / 10.01 | +0.1% |
| `dwnom_1d` | 0.762 / 0.809 / 0.834 | 0.109 / 0.114 / 0.123 | 7.00 / 7.11 / 6.80 | +9.5% |

CORRECTIONS.md gives the same table for the 0.7.x files of this vintage in
the entry of 2026-09-28, and for the other vintages and the 0.6.0 labels in
the entry of 2026-09-26, (c).

A scaling model fixes its unit from the recovered configuration, so what a
per-assembly fit identifies is the ratio of the distance between parties to
the dispersion within them, not the distance itself. When parties become more
cohesive, per-assembly estimation reports that as parties moving apart even if
positions are unchanged. Bridging does not remove this. An affine map rescales
distance and dispersion by the same factor and leaves their ratio exactly
where it was, which is why the ratios of `wnom_1d` and `bridged_1d` are equal
in every assembly. Only the pooled estimation anchors the unit outside a
single chamber, and its ratios differ. When comparing polarization across
assemblies, report within-party dispersion together with the distance, and
treat the growth in the per-assembly series as an upper bound.

### 10.5 Limits

- The series cover the 20th-22nd only. The 17th-19th roll calls of section 8
  are not scaled, and the 16th rows of section 9 cannot be.
- The 22nd is in session and its values are provisional. 한동훈 (5DC8083A),
  seated on 2026-06-11, has 12 contested yea or nay votes and no 22nd ideal
  point. The other 15 members that the vote API omits are scaled from their
  LIKMS rows.
- The second dimension of the 22nd two-dimensional fit, `wnom2d_dim2`, is
  unstable. Adding the LIKMS rows in 0.8.0 changed it so much that it
  correlates at -0.354 with the 0.7.x values over the 305 legislators in both,
  and the mean of the 개혁신당 members moved from 0.92 to -0.94. The first
  dimension correlates at 0.9997. Do not use the 22nd `wnom2d_dim2`.
- The LIKMS rows also move the 22nd `bridged_1d`. The line that maps the
  22nd onto the 21st now rests on 156 bridging legislators instead of 151,
  and its slope rose from 0.7065 to 0.7661, so the 305 legislators in both
  releases shift by up to 0.081. Their values correlate at 0.99978 with
  0.7.x. The pooled `dwnom_1d` shifts by up to 0.045, 0.055 and 0.031 in the
  20th, 21st and 22nd.
- Party switches within a term are not observed. `party` is fixed per term.

`dw_ideal_points_20_22.csv`, which earlier releases labeled DW-NOMINATE, is
no longer distributed. Its `aligned` column is the 0.6.0 `bridged_1d` with
the opposite sign. See CORRECTIONS.md, entries of 2026-07-18 and 2026-09-26.

---

## 11. Members

| | |
|---|---|
| Files | `members_{age}.parquet` |
| Sources | ALLNAMEMBER (all members, per-era fields), npffdutiapkzbfyvr (역대 국회의원 현황, per assembly), nwvrqwxyaytdsfvhu (current members), nqbeopthavwwfbekw and nyzrglyvagmrypezq (committee careers), and `data/raw/members/party_overrides.csv` (documented party corrections) |
| Unit | one member in one assembly, including members who entered during the term. `mona_cd` is unique within each file. |

| Column | Type | Definition |
|---|---|---|
| `mona_cd` | str | MONA_CD. |
| `member_name`, `member_name_hanja`, `member_name_eng` | str | Name in Hangul, Hanja and English. |
| `sex` | str | 남 or 여. |
| `birth_date` | str | `YYYY-MM-DD`. |
| `birth_calendar` | str | 양 (solar) or 음 (lunar) calendar of `birth_date`, from the field BTH_GBN_NM of the per-assembly roster npffdutiapkzbfyvr or, for the 299 serving 22nd members, of the current-member endpoint nwvrqwxyaytdsfvhu. See the note below the table. |
| `reelection` | str | Lifetime seniority at the time of collection, such as 초선, 재선 or 3선. It does not describe seniority at this assembly. |
| `term_number` | int | This assembly's position among the member's assemblies, 1 for a first term. |
| `seniority` | str | `term_number` as a label, 초선, 재선 or N선. |
| `email`, `homepage`, `photo_url` | str | Contact and photo URLs at the time of collection. |
| `age` | int | Assembly. |
| `party` | str | Party at election in this assembly, the party whose list or ticket the member was elected on, and 무소속 for an independent. For a successor to a proportional seat it is the list the seat came from, and for a by-election winner the party of that ticket. It is the per-era party of ALLNAMEMBER, except for six members whose ALLNAMEMBER party is not the party at election, which are overridden (see below the table). Satellite list parties are kept, for example 미래한국당 and 더불어시민당 in the 21st and 국민의미래 and 더불어민주연합 in the 22nd. |
| `party_current` | str | Current party of members serving at the snapshot, 22nd only. It differs from `party` for 35 of the 299 serving members. Null for everyone else. |
| `district` | str | Electoral district from the official per-assembly roster when it has the member, otherwise from ALLNAMEMBER or, for serving 22nd members, from the current-member endpoint. 비례대표 for proportional seats. |
| `election_type` | str | 지역구 or 비례대표. |
| `committee` | str | Committees of the member's dated assignment spells in this assembly, comma-joined in order of first appearance (section 12). |
| `committee_source` | str | `assignment_history` when `committee` comes from the dated spells, `allnamember` when it comes from an era-aligned ALLNAMEMBER string. Every row of 0.8.0 is `assignment_history`. |
| `is_current` | bool | True for members serving at the snapshot, 22nd only. |
| `snapshot_date` | str | Collection date, 2026-09-25. |

| Assembly | Members | 지역구 | 비례대표 | 초선 by `term_number` | `reelection` ≠ `seniority` | `is_current` | `party_current` filled |
|---|---|---|---|---|---|---|---|
| 17 | 322 | 260 | 62 | 205 | 178 | 0 | 0 |
| 18 | 331 | 266 | 65 | 159 | 149 | 0 | 0 |
| 19 | 332 | 270 | 62 | 171 | 174 | 0 | 0 |
| 20 | 320 | 270 | 50 | 150 | 135 | 0 | 0 |
| 21 | 322 | 266 | 56 | 168 | 156 | 0 | 0 |
| 22 | 321 | 268 | 53 | 147 | 0 | 299 | 299 |

The seniority counts of the 18th-21st equal the official 역대 국회의원 재선
현황 table exactly. That table ends with the 21st, and for the 17th it counts
two more members, 206 against 205 초선 and 43 against 42 3선.

**Party at election.** `party` is the party whose list or ticket the member
was elected on. A successor to a proportional seat takes the party of the
list the seat came from, and a by-election winner the party of that ticket.
ALLNAMEMBER gives each member's party as a `/`-separated list with one entry
per era of service, and the entry is usually that party. Six entries are not,
and `data/raw/members/party_overrides.csv` replaces them. The build stops if
ALLNAMEMBER changes one of these entries, so each override is checked again at
every rebuild. The file gives the evidence for each override. For three
members it is the official member record of endpoint nprlapfmaufmqytet. For
the three members elected on the 더불어시민당 list, that record gives
더불어민주당, the party that absorbed 더불어시민당 in May 2020, and the
evidence is the member's Korean Wikipedia article, accessed on 2026-09-26.

| Assembly | Member | MONA_CD | ALLNAMEMBER | `party` | Evidence |
|---|---|---|---|---|---|
| 20 | 최경환 | FJ03481D | 자유한국당 | 새누리당 | The official member record of the 20th Assembly lists 경북 경산시 under 새누리당. The party took the name 자유한국당 in 2017, after his first recorded vote on 2016-06-09. |
| 21 | 윤상현 | MSY7784L | 국민의힘 | 무소속 | The official member record of the 21st Assembly lists 인천 동구미추홀구을 as 무소속. 국민의힘 took that name in September 2020, after his first recorded vote on 2020-06-08. |
| 21 | 양정숙 | PZA4062H | 무소속 | 더불어시민당 | Elected in 2020 on the 더불어시민당 proportional list. ALLNAMEMBER records 무소속, the status she held after the party expelled her. |
| 21 | 용혜인 | GE71932C | 기본소득당 | 더불어시민당 | Elected in 2020 on the 더불어시민당 proportional list, expelled before that party merged into 더불어민주당, and returned to 기본소득당, which ALLNAMEMBER records. |
| 21 | 조정훈 | WJL30106 | 시대전환 | 더불어시민당 | Elected in 2020 as candidate 6 on the 더불어시민당 proportional list, expelled before the term began, and returned to 시대전환, which ALLNAMEMBER records. |
| 21 | 정운천 | NZF1659U | 미래통합당 | 미래한국당 | The official member record of the 21st Assembly lists his proportional seat under 미래한국당. |

The other 20th and 21st labels with a party name that postdates the election
belong to members who entered during the term. The 14 rows of `members_21`
labeled 국민의힘 are members whose first recorded vote was in 2022 or later,
and the four 20th members labeled 자유한국당 or 바른미래당 cast their first
recorded vote in 2017-2019, after the party took that name. Two 22nd members
who succeeded to proportional seats of the 더불어민주연합 list, 손솔 and
최혁진, cast their first recorded vote on 2025-06-26. They carry the
더불어민주연합 label of that list, as the rule requires, although the party
merged into 더불어민주당 in May 2024. ALLNAMEMBER records some other list
successors under the merged party's name instead, for example 더불어민주당 for
22nd successors on the same list and 국민의힘 for 21st successors on the
미래한국당 list. Both names map to the same bloc, so no bloc assignment depends
on which name is recorded. Their current parties are in `party_current`.

**Birth calendar.** ALLNAMEMBER has its own calendar code, BIRDY_DIV_CD, but
it is coded the opposite way from BTH_GBN_NM of the roster endpoints. For
every member in npffdutiapkzbfyvr and nwvrqwxyaytdsfvhu, BIRDY_DIV_CD says 양
where they say 음 and 음 where they say 양. `birth_calendar` therefore comes
from the roster endpoints, which cover every member of the 17th-22nd. The
build falls back to the inverted BIRDY_DIV_CD only for a member missing from
both, and no member of 0.8.0 is. Across the 1,948 member-terms,
`birth_calendar` is 양 for 1,380 and 음 for 568.

District strings are not normalized. The 17th uses full province names, such
as 서울특별시, for 162 members and short names for the others. Three 17th
proportional members have strings like `비례(한) 비례(한나라당)`. Since 0.7.1
three consistency rules apply after parsing. A district recorded as 비례대표 is
a proportional seat, so 신용현 and 권미혁 in the 20th, whom the official roster
lists as 지역구, have election type 비례대표. A proportional member with no
district string, 손솔 and 최혁진 in the 22nd, has district 비례대표. A 22nd
district that the serving-member endpoint renamed with the 2026
전남광주통합특별시 prefix is mapped back to the name used at election, taken
from the rosters of earlier assemblies, so 박지원 (8BF5855P) has 전남
해남군완도군진도군.

Names shared by two members of the same assembly are 김선동 and 이영애 in the
18th, 김영주, 권은희 and 이재영 in the 19th, 김성태 and 최경환 in the 20th,
김병욱 and 이수진 in the 21st, and 박지원 in the 22nd.

---

## 12. Committee assignments

| | |
|---|---|
| File | `committee_assignments.parquet` |
| Sources | nqbeopthavwwfbekw (committee careers of former members, per assembly) and nyzrglyvagmrypezq (committee careers of current members, all assemblies) |
| Unit | one committee spell of one member in one assembly |

| Column | Type | Definition |
|---|---|---|
| `mona_cd`, `member_name` | str | Member. |
| `assembly` | int | Assembly of the spell. |
| `committee` | str | Committee name, with the `제N대` prefix removed. Special committees are included. |
| `start_date`, `end_date` | date | Spell dates. `end_date` is null for an open spell. |
| `is_current` | bool | True when the spell has no end date. |
| `frto_date` | str | The date range as the API gives it, such as `2017.05.30 ~ 2018.05.29`. |

| Assembly | Spells | Members | Committee names | Open spells |
|---|---|---|---|---|
| 14 | 3 | 1 | 2 | 0 |
| 15 | 18 | 2 | 11 | 0 |
| 16 | 75 | 5 | 25 | 0 |
| 17 | 2,402 | 322 | 73 | 0 |
| 18 | 2,466 | 331 | 67 | 0 |
| 19 | 2,506 | 332 | 73 | 0 |
| 20 | 2,367 | 320 | 61 | 0 |
| 21 | 2,016 | 322 | 48 | 3 |
| 22 | 1,763 | 321 | 42 | 490 |

Every member of the 17th-22nd has at least one spell in that assembly. The
14th-16th rows are earlier spells of members who also served in the
17th-22nd. The sources give committee names only, so chairs and ranking
members (위원장, 간사) are not identified.

---

## 13. Legislator ID mapping

| | |
|---|---|
| File | `legislator_id_mapping.parquet` |
| Unit | one legislator of the 17th-22nd Assemblies, 1,156 rows |

| Column | Type | Definition |
|---|---|---|
| `mona_cd`, `member_name` | str | MONA_CD and name. Every `mona_cd` matches `^[0-9A-Z]{8}$`. |
| `terms` | str | Assemblies served among the 17th-22nd, comma-joined. |
| `in_ideal_points` | bool | In `ideal_points_bridged.csv`. 664 legislators. |
| `in_dw_nominate` | bool | Deprecated alias of `in_ideal_points`, still present in 0.8.0. The old name repeated the retracted DW-NOMINATE label, and it will be removed in a later release. |
| `in_roll_calls` | bool | With a member_id in `roll_calls_all.parquet`, 17th-22nd. 1,152. |
| `in_bill_masters` | bool | Lead proposer of at least one bill in the masters. 1,140. |
| `in_mp_metadata` | bool | In the external legislator metadata table that `link_external.py` reads from the directory in `KNA_WITNESSES_DIR`. 1,145. Null when that variable is not set at build time. |
| `in_assembly_bills` | bool | In the proposer table of the korean-assembly-bills dataset. 661. |

The universe is the members of `members_{17..22}`. A flag is null when its
source was skipped at build time. Legislators who served only in the 16th
Assembly are not in the map.

---

## 14. Bill texts

| | |
|---|---|
| File | `bill_texts_linked.parquet` |
| Sources | the korean-assembly-bills dataset, which scraped the 제안이유 of 20th-22nd member law bills from LIKMS, and BPMBILLSUMMARY (법률안 제안이유 및 주요내용), collected on 2026-09-28 by `collect_structure.py summaries` for every law bill without a scraped text |
| Unit | one bill, law bills of the 17th-22nd |

| Column | Type | Definition |
|---|---|---|
| `BILL_ID` | str | Bill ID. The Python API lowercases the column names. |
| `propose_reason` | str | Text of 제안이유 및 주요내용. Null in the 72 scraped rows whose scrape failed and that the API does not fill. |
| `scrape_status` | str | Result of the LIKMS scrape. `ok` for 60,546 rows, `no_csrf` 305, `empty` 73 and `error` 1. It keeps the scrape's own result also in the 307 rows whose text now comes from BPMBILLSUMMARY, 304 `no_csrf`, 2 `empty` and 1 `error`. Null for the 48,904 rows the scrape never covered. |
| `age` | int | Assembly, from the master. Null for one row, see below. |
| `bill_no` | str | Bill number, from the master. Null for the same row. |
| `source` | str | `likms_scrape` for the 60,618 rows whose text, or missing text, comes from the scrape. `BPMBILLSUMMARY` for the 49,211 rows whose text comes from the API. |

`link_external.py texts` keeps every scraped row and its text unchanged,
fills the scraped rows without a text from the API where it can, and adds a
row for every other law bill with an API text. A BPMBILLSUMMARY answer lists
every record that shares the bill number, so the texts are matched on
BILL_ID. The API texts keep the heading the document starts with, such as
제안이유 및 주요내용 or ■ 대안의 제안경위, which the scraped texts lack. On 300
scraped bills drawn at random, 100 from each of the 20th-22nd, the two texts
are identical once that heading and all whitespace are removed.

| Assembly | Law bills | With a text | Share | Scraped text | BPMBILLSUMMARY text | Without a text |
|---|---|---|---|---|---|---|
| 17 | 7,489 | 7,486 | 99.96% | 0 | 7,486 | 3 |
| 18 | 13,913 | 13,584 | 97.64% | 0 | 13,584 | 329 |
| 19 | 17,822 | 17,822 | 100.00% | 0 | 17,822 | 0 |
| 20 | 24,141 | 24,109 | 99.87% | 21,592 | 2,517 | 32 |
| 21 | 25,858 | 25,787 | 99.73% | 23,314 | 2,473 | 71 |
| 22 | 21,022 | 20,968 | 99.74% | 15,639 | 5,329 | 54 |
| All | 110,245 | 109,756 | 99.56% | 60,545 | 49,211 | 489 |

For the 489 law bills without a text the API returns a record whose text is
empty. 328 of them are government bills of the 18th.
`reports/bill_texts_missing.csv` lists them, and
`reports/bill_texts_coverage.csv` gives the table by proposer kind as well.
Every row but one joins to a law bill of the masters. That row carries the old
BILL_ID of bill 2203215, which was re-keyed upstream, and keeps `age` and
`bill_no` null.

---

## 15. Hearing meetings summary

| | |
|---|---|
| File | `hearing_meetings_summary.parquet`, built by `build_hearings_summary.py` |
| Source | kr-hearings-data release v10.2 (run 20260928T175652_175976) |
| Unit | one committee, plenary, audit or hearing meeting |

| Column | Definition |
|---|---|
| `meeting_id` | The Open API CONF_ID of the meeting, verbatim. Null for the 187 meetings that no Open API list returns, which kr-hearings-data found by scanning record-viewer IDs. |
| `term` | Assembly, 16th-22nd. |
| `committee` | `committee_raw` of kr-hearings-data. A 국정감사 meeting with an audit team carries the team after a hyphen, as in the earlier table. A subcommittee meeting carries its parent committee. |
| `hearing_type` | 상임위원회, 국정감사, 국회본회의, 예산결산특별위원회, 인사청문특별위원회, 국정조사, 특별위원회 or 전원위원회. |
| `date` | Meeting date, `YYYY-MM-DD`. |
| `n_speeches` | Speaker turns in the meeting, after kr-hearings-data merges the fragments of one turn. |
| `n_legislators` | Distinct legislator codes (`naas_cd`) among the turns spoken in the legislator role (`role_group` = legislator). A minister who holds a seat does not count in a meeting where they speak as minister. |
| `parties` | Distinct party labels of the legislator-role turns, sorted and comma-joined. A label is the speaker's party on the speech date. |
| `conf_num` | Record-viewer ID of the meeting. It is set and unique for every meeting and joins to `conf_num` in kr-hearings-data. |
| `is_subcommittee` | True for a subcommittee meeting, as in kr-hearings-data. |

The table has 26,261 meetings dated from 2000-06-05 to 2026-09-22, 7,268 of
them subcommittee meetings, with 15,114,183 turns. kr-hearings-data v10.2 has
26,264 meetings. The three it holds without turns are left out, which are two
identical duplicate copies (`duplicate_of`) and one meeting without turns.
Use `conf_num` to join the table to kr-hearings-data, because `meeting_id` is
null for 187 meetings.

| Assembly | 16 | 17 | 18 | 19 | 20 | 21 | 22 |
|---|---|---|---|---|---|---|---|
| Meetings | 3,408 | 4,635 | 4,308 | 4,191 | 3,761 | 3,644 | 2,314 |
| Meetings in the table of 0.6.0-0.8.0 | 2,816 | 3,244 | 2,839 | 2,708 | 2,334 | 2,315 | 573 |

**Change from 0.8.0.** Releases 0.6.0 to 0.8.0 shipped a table of 16,829
meetings built from version 9 of kr-hearings-data, whose defects D1 to D12
are listed in docs/CHANGELOG.md of kr-hearings-data. That table counted an
empty speaker code as a legislator in 2,119 meetings and showed an empty
party label as a leading comma. Its `meeting_id` is the v9 ID, which drops
the leading zero of five-digit CONF_IDs. Of the 16,829 v9 meetings, 16,793
are matched through the `v9_meeting_id` of kr-hearings-data. CORRECTIONS.md,
entry of Release 0.8.1, lists how the matched meetings differ.

**Rebuilding.** `python3 build_hearings_summary.py --source v10 --out DIR`
reads the v10 files in one of three forms:

- a build directory with `meetings.parquet` and `turns/tNN/part-*.parquet`,
  given by `--v10-dir` or `KNA_HEARINGS_V10_DIR` (default
  `../kr-hearings-data/v10/build/release`);
- a directory of release assets, `meetings_v10.2.parquet` and
  `turns_t16_v10.2.parquet` to `turns_t22_v10.2.parquet`, such as the cache
  of the kr-hearings-data package, given the same way (with `--v10-version`
  when it holds more than one version);
- the kr-hearings-data package, `--v10-package v10.2`, which downloads what
  it needs.

`link_external.py speeches` writes the same table. `build_all.sh` rebuilds
it when `KNA_HEARINGS_V10_DIR` is set and otherwise carries the shipped file
over. `tests/test_hearings_summary.py` rebuilds the table when the v10 files
are present and checks that it equals the shipped file.
`--source v9` still reproduces the table of 0.6.0 to 0.8.0 from
`all_speeches_16_22_v9.parquet` in `KNA_HEARINGS_DIR`.

---

## 16. Asset disclosures

| | |
|---|---|
| File | `assets_wealth_panel.parquet`, built by `build_assets.py` |
| Sources | wealth_year 2015-2024: the item-level asset disclosure data of the March regular disclosures 2016-2025 published by OpenWatch under CC BY-SA 4.0. wealth_year 2025: the official 국회공보 제2026-54호 of 2026-03-26, which prints the March 2026 regular disclosure (국회공직자윤리위원회공고 제2026-3호). See README.md, License. |
| Unit | one member in one disclosure year |

The panel has 3,215 rows for 776 members, with `wealth_year` from 2015 to
2025. `wealth_year` is the year the wealth refers to, so the disclosure of
March 2026 gives wealth_year 2025. `assembly` is the assembly in session at
that disclosure. Amounts are in thousands of won, as printed.

| Assembly | Rows | `wealth_year` |
|---|---|---|
| 19 | 290 | 2015 |
| 20 | 1,164 | 2016-2019 |
| 21 | 1,175 | 2020-2023 |
| 22 | 586 | 2024-2025 |

The columns are `mona_cd`, `wealth_year`, `member_name`, `assembly`, the totals
`total_assets`, `total_debt`, `net_worth`, `total_building`, `total_land`,
`total_deposits`, `total_stocks`, `total_realestate`, counts of properties and
apartments, indicators for real estate in Seoul and Gangnam, `political_fund`,
logged and quantile versions of the main totals, and `re_share`, which equals
`total_realestate` divided by `total_assets`.

The 2015-2024 rows are built from the OpenWatch item files and equal the
panel shipped up to 0.7.1 in every row and column. The 2025 rows are parsed
from the 국회공보 PDF, whose members are matched to their MONA_CD by name
through `members_22`. The parsed items add up to all 2,323 printed category
subtotals and the subtotals to all 330 printed totals, and the build stops
otherwise. The same parser, applied to the March 2025 issue, reproduces all
299 member-years of wealth_year 2024 that the OpenWatch files give. The
quantile columns `total_realestate_q`, `total_assets_q` and `net_worth_q`
use the cut points of the pooled 2015-2024 rows, and later years are binned
with the same cut points.

The 2026 notice lists 287 members, 275 of whom were serving at the member
snapshot of 2026-09-25. Seven serving members with a 2024 row are not in
it. They are 정동영, 김윤덕, 윤호중, 김민석, 안규백, 정성호 and 김성환, and the
reason has not been verified. The members seated in 2026 have no 2025 row
either.
`reports/assets_member_check.csv` lists every 22nd member with the 2024 and
2025 totals.

---

## 17. Build reports

`build_all.sh` rebuilds every table from `data/raw/` without API calls and
writes validation reports to `reports/` in the output directory. It runs
`collect_members.py --build-only`, `integrate.py`, `consolidate_votes.py`,
`build_ideal_points.R`, `build_structure.py`, `link_external.py texts` and
`link_external.py idmap`, and `build_assets.py build` when `KNA_ASSETS_DIR`
is set. The 17th-19th roll calls enter through the tables that
`collect_minutes_votes.py` writes to `data/raw/`, so the build itself needs
neither the minutes PDFs nor a PDF library. README.md lists the inputs that
come from outside `data/raw/`.

`refresh_22.sh` refreshes the ongoing 22nd Assembly. It collects the 22nd
again from the API, including the LIKMS vote pages and the BPMBILLSUMMARY
texts, runs `build_all.sh` into a staging directory, `data/_build` by default,
runs the test suite against it and writes a comparison with
`data/processed/` to `logs/`. It promotes nothing to `data/processed/`.

The 0.8.0 `reports/` directory holds the nine reports below and nothing else.

| Report | Written by | Content |
|---|---|---|
| `master_compare.csv` | `integrate.py --compare` | Headline counts of every master, previous against new build. |
| `rollcall_tally_check.csv` | `consolidate_votes.py` | Member-level counts of every 20th-22nd vote against the official tally, with an explanation of each difference. |
| `alternative_absorption_coverage.csv` | `build_structure.py` | Alternatives queried and linked, and the share of 대안반영폐기 bills linked, per assembly. |
| `cosponsorship_mismatch.csv` | `build_structure.py` | Bills whose edges differ from their proposer text. |
| `cosponsorship_degree_change.csv` | `build_structure.py` | Degree of each 20th-22nd member-term in the earlier and the rebuilt edge file, overall and on the bills the earlier file had truncated. It is written only when the earlier edge file is available, so the file is the one of the 0.7.0 build. The edges have not changed since. |
| `bill_texts_coverage.csv` | `link_external.py texts` | Law bills with a text by assembly and proposer kind, split by source. |
| `bill_texts_missing.csv` | `link_external.py texts` | Every law bill without a text, with the reason. |
| `assets_compare.csv` | `build_assets.py build --compare` | Rows and cells of the asset panel, previous against new build. |
| `assets_member_check.csv` | `build_assets.py build` | Every 22nd member with the 2024 and 2025 totals and whether the prior-year total printed in the 2026 notice equals the 2024 net worth. |
