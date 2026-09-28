# kna Codebook

| | |
|---|---|
| Release | 0.7.0 |
| Data collected | Mostly on 2026-09-25, from the Open Assembly API (열린국회정보, open.assembly.go.kr). The 20th-21st member-level votes and the 18th and 20th BILLINFODETAIL records are from March 2026 (DATA_AVAILABILITY.md). |
| Coverage | 17th-22nd National Assembly. The 22nd Assembly is in session. |

This codebook describes every file in the data directory, which is
`data/processed/` in a repository checkout. Every count and coverage figure
below was computed from the 0.7.0 files. Corrections to earlier releases are
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
8. [Roll calls, 20th-22nd](#8-roll-calls-20th-22nd)
9. [Experimental 16th-19th vote rows](#9-experimental-16th-19th-vote-rows)
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
| `vote_events.parquet` | plenary tally | 8,611 | 7 |
| `roll_calls_all.parquet` | member x recorded vote, 20th-22nd | 2,557,618 | 8 |
| `roll_calls_16_19_experimental.parquet` | parsed text row, 16th-19th | 41,281 | 9 |
| `ideal_points_wnominate.csv`, `ideal_points_bridged.csv`, `ideal_points_dwnominate.csv` | legislator-term | 940 each | 10 |
| `ideal_points_bridging_params.csv`, `ideal_points_manifest.json`, `ideal_points_sessioninfo.txt`, `dwnominate_fit.rds` | build metadata | | 10 |
| `ideal_points_archive/v0.6.0_legacy/`, `ideal_points_archive/v20260312_corrected/` | earlier vintages | 936 and 939 per series | 10 |
| `members_{17..22}.parquet` | member-term | 1,948 | 11 |
| `committee_assignments.parquet` | member x assembly x committee spell | 13,616 | 12 |
| `legislator_id_mapping.parquet` | legislator | 1,156 | 13 |
| `bill_texts_linked.parquet` | bill | 60,925 | 14 |
| `hearing_meetings_summary.parquet` | meeting | 16,829 | 15 |
| `assets_wealth_panel.parquet` | member-year | 2,928 | 16 |
| `reports/` | build reports | | 17 |

`hearing_meetings_summary.parquet` and `assets_wealth_panel.parquet` are
carried over unchanged from 0.6.0. `build_all.sh` does not rebuild them.

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
in the same assembly, so joins must use MONA_CD, never the name.

**Missing values** are null, except `rgs_conf_nm` in the bill master, which
holds a single space (`" "`), not an empty string, when a bill has no plenary
session name. That is the case for 95,613 bills. Test for it with
`rgs_conf_nm.str.strip() == ""`. Other strings are kept as the API returns
them, so 26 values of `bill_nm` and 3 of `prom_law_nm` carry leading or
trailing whitespace.

**Dates** are `datetime64` in the bill master, `subcommittee_reviews`,
`committee_assignments`, `veto_events` and `vote_events`. They are strings in
the meeting tables (`YYYY-MM-DD`) and in the roll calls (`YYYYMMDD HHMMSS`).
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
| 40 | `vote_result_cd` | str | 0.0% | 0.0% | 0.0% | 13.9% | 12.2% | 8.6% | 7.5% |
| 41 | `vote_member_total` | float | 0.0% | 0.0% | 0.0% | 13.9% | 12.2% | 8.6% | 7.5% |
| 42 | `vote_total` | float | 0.0% | 0.0% | 0.0% | 13.9% | 12.2% | 8.6% | 7.5% |
| 43 | `vote_yes` | float | 0.0% | 0.0% | 0.0% | 13.9% | 12.2% | 8.6% | 7.5% |
| 44 | `vote_no` | float | 0.0% | 0.0% | 0.0% | 13.9% | 12.2% | 8.6% | 7.5% |
| 45 | `vote_abstain` | float | 0.0% | 0.0% | 0.0% | 13.9% | 12.2% | 8.6% | 7.5% |
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
| 67 | `vote_bill_id` | str | 0.0% | 0.0% | 0.0% | 13.9% | 12.2% | 8.6% | 7.5% |

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
- ALT = TVBPMBILL11, through `alternative_absorption.parquet`

When a field has several sources, the first non-null value in the order given
is used. Every bill of the 0.7.0 masters has a DETAIL row.

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
| `vote_result_cd` | Result of the tally. |
| `vote_member_total` | Members seated (재적) at the vote. |
| `vote_total` | Members voting. |
| `vote_yes`, `vote_no`, `vote_abstain` | 찬성, 반대, 기권. |
| `vote_bill_id` | BILL_ID of the tally used. |

TALLY begins with the 20th Assembly, so these columns are empty in the
17th-19th. A bill takes its own tally when one exists. Otherwise it takes a
floor-amendment tally filed under its bill_no whose name refers to the bill,
preferring the tally whose result matches the bill's first floor decision,
then the latest and the largest. `vote_bill_id` differs from `bill_id` for
40, 38 and 35 bills in the 20th, 21st and 22nd. All tallies, including
amendment votes and tallies with no bill, are in `vote_events.parquet`. For a
vetoed bill the columns hold the first passage, because the API publishes no
tally for any re-vote.

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
| Source | TALLY (ncocpgfiaoituanbr), 20th-22nd |
| Unit | one plenary tally |

| Column | Type | Definition |
|---|---|---|
| `age` | int | Assembly. |
| `vote_bill_id` | str | BILL_ID of the tally. It joins to `roll_calls_all.bill_id`. |
| `bill_no`, `bill_nm` | str | Bill number and tally name as the API gives them. |
| `proc_dt` | date | Date of the vote. |
| `vote_type` | str | `original` when the tally's BILL_ID is a master bill, `amendment` for a floor amendment (수정안) matched by bill_no and name, `reconsideration` for a re-vote after a veto, `other` for tallies matched to no bill. |
| `master_bill_id` | str | The master bill the tally belongs to. Null for `other`. |
| `member_tcnt`, `vote_tcnt`, `yes`, `no`, `abstain` | int | Members seated, votes cast, 찬성, 반대, 기권. |
| `result` | str | 원안가결, 수정가결 or 부결. |

| Assembly | original | amendment | other | All |
|---|---|---|---|---|
| 20 | 3,436 | 52 | 4 | 3,492 |
| 21 | 3,228 | 44 | 0 | 3,272 |
| 22 | 1,812 | 35 | 0 | 1,847 |
| All | 8,476 | 131 | 4 | 8,611 |

No tally is of type `reconsideration`, because the API publishes none for the
re-votes. The four `other` tallies of the 20th are petitions whose numbers
collide with bill numbers. The 20th has 3,492 tallies for 3,491 recorded
votes because bill 2000491 has two tally rows.

---

## 8. Roll calls, 20th-22nd

| | |
|---|---|
| File | `roll_calls_all.parquet` |
| Source | nojepdqqaweusdfbi (의원별 표결), 20th-22nd Assemblies |
| Unit | one member on one recorded vote. The key (term, bill_id, member_id) is unique, and rows are sorted by term, date, bill_id and member_id. |

| Column | Type | Definition |
|---|---|---|
| `term` | int | Assembly. |
| `date` | str | Vote time, `YYYYMMDD HHMMSS`. |
| `bill_id` | str | BILL_ID of the vote. It joins to `vote_events.vote_bill_id`, and usually to `master_bills.bill_id`. |
| `bill_no` | str | Bill number. |
| `member_id` | str | MONA_CD. |
| `member_name` | str | Name as the API gives it. |
| `vote` | str | 찬성, 반대, 기권 or 불참. 불참 means the member did not vote. |
| `party` | str | Party at election from `members_{term}.party`. For a successor to a proportional seat, the list the seat came from. |
| `party_api` | str | Party label of the API (POLY_NM). It is the member's party at the time of collection, written onto every past vote, and it changes between collections. The 20th and 21st were collected in March 2026 and the 22nd in September 2026. |
| `district` | str | District as the API gives it. |
| `source` | str | Always `api`. |
| `meeting_id`, `bill_context`, `vote_event`, `agg_total`, `agg_yes` | | Always null. Kept so the schema matches earlier releases. |

| Assembly | Rows | Votes | Members | First vote | Last vote | 찬성 | 반대 | 기권 | 불참 | Members with `party` ≠ `party_api` |
|---|---|---|---|---|---|---|---|---|---|---|
| 20 | 1,036,384 | 3,491 | 320 | 2016-06-09 | 2020-05-20 | 671,536 | 7,315 | 18,792 | 338,741 | 192 |
| 21 | 976,127 | 3,272 | 322 | 2020-06-08 | 2024-05-28 | 696,559 | 9,667 | 20,663 | 249,238 | 154 |
| 22 | 545,107 | 1,847 | 305 | 2024-07-04 | 2026-09-17 | 388,329 | 9,726 | 6,340 | 140,712 | 41 |

The member-level yea, nay and abstain counts equal the official tally for
every vote of the 20th and 21st, with bill 2000491 matching one of its two
tally rows. The 22nd has a gap. The live member-level API omits 16 members
seated during 2026. Votes from 2026-01-15 lack one member, votes from
2026-06-11 lack 15 and votes from 2026-09-03 lack 16, so 791 of the 1,847
22nd votes have fewer member rows than the tally's membership count. On 476
of them the yea, nay and abstain counts differ from the official tally. 475
of these differences are fully explained by the missing members. The
remaining one, bill 2215128 on 2026-01-29, also differs by one recorded vote.
These 16 members have no 22nd roll calls and no 22nd ideal point. The check
is in `reports/rollcall_tally_check.csv`.

Four pairs of legislators share a name in these assemblies, 김성태 and 최경환
in the 20th and 김병욱 and 이수진 in the 21st. The 22nd has two members named
박지원, and the one seated by a by-election is among the 16 omitted members.
Use `member_id` for every join.

---

## 9. Experimental 16th-19th vote rows

| | |
|---|---|
| File | `roll_calls_16_19_experimental.parquet` |

These rows are **not a roll-call matrix**. They were parsed from plenary
speech text and minutes appendices. The appendix parser merged every vote of
a meeting into one event, the speech-text parser merged them into a few, and
the consolidation kept one vote per member per event. A row is therefore a
member's recorded position at some vote of that meeting, not at an
identifiable vote. No row has a bill_id. `member_id` comes from a name
match that cannot be reproduced from the repository and that merges
same-name legislators. Members with two-syllable names are largely missing,
because the source spaces out the syllables. The file is shipped unchanged
from 0.6.0 with `quality_flag` = `meeting_level_pseudo_event` and is not an
input to any ideal-point series. See CORRECTIONS.md (h).

The columns are those of `roll_calls_all` without `bill_no` and `party_api`,
plus `quality_flag`. `date` is `YYYY-MM-DD`, `source` is `inline_text` or
`pdf_appendix`, and `vote` is 찬성, 반대 or 기권.

| Assembly | Rows | Meetings | Events | Members | First date | Last date | Sources |
|---|---|---|---|---|---|---|---|
| 16 | 923 | 4 | 5 | 260 | 2003-11-07 | 2004-03-02 | inline_text 923 |
| 17 | 24,901 | 79 | 108 | 316 | 2004-06-05 | 2008-05-22 | pdf_appendix 18,320, inline_text 6,581 |
| 18 | 14,210 | 62 | 62 | 320 | 2008-07-16 | 2011-05-04 | pdf_appendix 14,210 |
| 19 | 1,247 | 5 | 5 | 316 | 2013-04-29 | 2015-06-08 | pdf_appendix 1,247 |

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
legislator-term, 317, 318 and 305 in the 20th, 21st and 22nd.

**Sign.** Positive is conservative and negative is liberal in every series.

### 10.1 Estimation

- A vote counts as contested when at least 2.5% of those voting yea or nay are
  in the minority. A legislator is scaled with at least 20 contested yea or
  nay votes.
- 찬성 is yea and 반대 is nay. 기권 and 불참 are treated as missing.
- Input rows are sorted by term, date, bill_id and member_id before the vote
  matrix is built, because W-NOMINATE's output depends on row order.
- **Polarity anchor.** Every fit is oriented so that 추경호 (G152611B) has a
  positive coordinate on every dimension. He was elected for the conservative
  party in all three assemblies and has enough contested votes in each. His
  second-dimension coordinate is close to zero in the 21st and 22nd, so the
  sign of `wnom2d_dim2` in those assemblies rests on a legislator near the
  middle of that dimension.
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
| liberal | 136 | 183 | 179 | 498 |
| conservative | 124 | 115 | 108 | 347 |
| independent | 50 | 9 | 0 | 59 |
| progressive | 7 | 7 | 1 | 15 |
| rebuilding | 0 | 0 | 13 | 13 |
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
| top level of the data directory | v20260917, the default | through 2026-09-17 | 940 | 269 / 331 / 223 |
| `ideal_points_archive/v20260312_corrected/` | v20260312 | through 2026-03-12, the vote range of 0.6.0 | 939 | 269 / 331 / 139 |
| `ideal_points_archive/v0.6.0_legacy/` | none | through 2026-03-12 | 936 | 269 / 332 / 139 |

- **v20260917** is the corrected build on every vote collected by 2026-09-25.
- **v20260312** is the corrected build restricted to votes taken by
  2026-03-12, the vote range of 0.6.0. It differs from the legacy files
  through the fixes of CORRECTIONS.md (b) and (c), the explicit row order and
  the named sign anchor, so it separates those fixes from the six months of
  added 22nd votes. The refreshed data add 53 votes of 김준환 dated
  2026-03-12, and a run without them gives byte-identical ideal-point files.
  Only the manifest differs, in its record of the input and the run time.
- **v0.6.0_legacy** holds the files shipped in 0.6.0, byte for byte. They use
  the API party labels, have no `vintage` column and no manifest, and their
  `dwnominate_fit.rds` carries wrong party codes for most 21st and 22nd
  legislators. Use them only to reproduce earlier results.

| Vintage | Term | Bridging legislators | Slope | Intercept | R² |
|---|---|---|---|---|---|
| v20260917 | 21 onto 20 | 126 | 0.8985 | -0.0230 | 0.904 |
| v20260917 | 22 onto 21 | 151 | 0.7065 | -0.0307 | 0.950 |
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
| `wnom_1d` | 0.818 / 0.931 / 1.145 | 0.158 / 0.132 / 0.111 | 5.18 / 7.04 / 10.35 | +40.1% |
| `bridged_1d` | 0.818 / 0.836 / 0.809 | 0.158 / 0.119 / 0.078 | 5.18 / 7.04 / 10.35 | -1.0% |
| `dwnom_1d` | 0.781 / 0.825 / 0.846 | 0.109 / 0.115 / 0.123 | 7.14 / 7.18 / 6.90 | +8.4% |

CORRECTIONS.md (c) gives the same table for the other vintages and for the
0.6.0 labels.

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

- The series cover the 20th-22nd only, because the API has member-level votes
  from the 20th on. The 16th-19th rows of section 9 cannot be scaled.
- The 22nd is in session and its values are provisional. The 16 members
  omitted by the vote API have no 22nd ideal point.
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
| `committee_source` | str | `assignment_history` when `committee` comes from the dated spells, `allnamember` when it comes from an era-aligned ALLNAMEMBER string. Every row of 0.7.0 is `assignment_history`. |
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
both, and no member of 0.7.0 is. Across the 1,948 member-terms,
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
| `in_ideal_points` | bool | In `ideal_points_bridged.csv`. 654 legislators. |
| `in_dw_nominate` | bool | Deprecated alias of `in_ideal_points`, kept for 0.7.0 only. The old name repeated the retracted DW-NOMINATE label, and it will be removed in the next release. |
| `in_roll_calls` | bool | In `roll_calls_all.parquet`. 661. |
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
| Source | the korean-assembly-bills dataset, which scraped the 제안이유 of member bills from LIKMS |
| Unit | one bill |

| Column | Type | Definition |
|---|---|---|
| `BILL_ID` | str | Bill ID. The Python API lowercases the column names. |
| `propose_reason` | str | Text of 제안이유 및 주요내용. |
| `scrape_status` | str | `ok` for 60,546 rows, `no_csrf` 305, `empty` 73, `error` 1. Only `ok` rows have text. |

The texts cover member law bills of the 20th, 21st and 22nd only. The 22nd
stops with the bills proposed by 2026-02-27, the date of that dataset's
snapshot, so 15,675 of the 19,651 22nd member law bills have a row. One row
carries the old BILL_ID of bill 2203215, which was re-keyed upstream, and
does not join to the master.

---

## 15. Hearing meetings summary

| | |
|---|---|
| File | `hearing_meetings_summary.parquet`, carried over from 0.6.0 |
| Source | the kr-hearings-data speech corpus, version 9 |
| Unit | one committee, plenary, audit or hearing meeting |

| Column | Definition |
|---|---|
| `meeting_id` | Meeting ID of the source corpus. |
| `term` | Assembly, 16th-22nd. |
| `committee` | Committee name. |
| `hearing_type` | 상임위원회, 국정감사, 국회본회의, 예산결산특별위원회, 인사청문특별위원회 or 국정조사. |
| `date` | Meeting date. |
| `n_speeches` | Speeches in the meeting. |
| `n_legislators` | Distinct legislator codes among the speakers. |
| `parties` | Parties of the speakers, comma-joined. |

The table has 16,829 meetings dated from 2000-06-01 to 2025-07-21. Version 9
of the source corpus is known to be defective and is being rebuilt, so treat
this table as provisional. `n_legislators` counts an empty speaker code as a
legislator in 2,119 meetings, and some legislators' speeches are not linked
to a code upstream.

---

## 16. Asset disclosures

| | |
|---|---|
| File | `assets_wealth_panel.parquet`, carried over from 0.6.0 |
| Source | asset disclosure data published by OpenWatch under CC BY-SA 4.0 (see README.md, License) |
| Unit | one member in one disclosure year |

The panel has 2,928 rows for 772 members, with `wealth_year` from 2015 to 2024.
Amounts are in thousands of won.

| Assembly | Rows | `wealth_year` |
|---|---|---|
| 19 | 290 | 2015 |
| 20 | 1,164 | 2016-2019 |
| 21 | 1,175 | 2020-2023 |
| 22 | 299 | 2024 |

The columns are `mona_cd`, `wealth_year`, `member_name`, `assembly`, the totals
`total_assets`, `total_debt`, `net_worth`, `total_building`, `total_land`,
`total_deposits`, `total_stocks`, `total_realestate`, counts of properties and
apartments, indicators for real estate in Seoul and Gangnam, `political_fund`,
logged and quantile versions of the main totals, and `re_share`, which equals
`total_realestate` divided by `total_assets`.

---

## 17. Build reports

`build_all.sh` writes validation reports to `reports/` in the output
directory. The 0.7.0 `reports/` directory holds the five reports below and
nothing else.

| Report | Written by | Content |
|---|---|---|
| `master_compare.csv` | `integrate.py --compare` | Headline counts of every master, previous against new build. |
| `rollcall_tally_check.csv` | `consolidate_votes.py` | Member-level counts of every 20th-22nd vote against the official tally, with an explanation of each difference. |
| `alternative_absorption_coverage.csv` | `build_structure.py` | Alternatives queried and linked, and the share of 대안반영폐기 bills linked, per assembly. |
| `cosponsorship_mismatch.csv` | `build_structure.py` | Bills whose edges differ from their proposer text. |
| `cosponsorship_degree_change.csv` | `build_structure.py` | Degree of each 20th-22nd member-term in the earlier and the rebuilt edge file, overall and on the bills the earlier file had truncated. |
