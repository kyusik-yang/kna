# Data Availability by Assembly

| | |
|---|---|
| Release | 0.7.0 |
| Raw data collected | Mostly on 2026-09-25, from the Open Assembly API (열린국회정보). See below for the exceptions. |

This document lists what each assembly's data contain and what they cannot
support. The 22nd Assembly is in session, so its figures describe the state
of the API on the collection date. The latest bill in the data was proposed on
2026-09-23 and the latest recorded vote was taken on 2026-09-17. Column
definitions are in [CODEBOOK.md](CODEBOOK.md), and corrections to earlier
releases in [CORRECTIONS.md](CORRECTIONS.md).

Most raw files were collected on 2026-09-25. The exceptions are listed below.

| Raw data | Collected |
|---|---|
| Member-level votes of the 20th and 21st (`roll_calls_20`, `roll_calls_21`) | March 2026 |
| BILLINFODETAIL records of the 18th and 20th | March 2026 |
| TVBPMBILL11 links of the vetoed alternative 2209676, awaiting its re-vote | 2026-09-26 |
| Official member records used as evidence for the party overrides (`data/raw/members/nprlapfmaufmqytet_17_21.parquet`) | 2026-09-26 |

The March files were not collected again because the completed assemblies
were found unchanged upstream. In September the official totals of their
member-bill and processed-bill lists and the 20th and 21st plenary tallies
matched the March files, and the member-level counts of every 20th and 21st
vote equal the official tallies collected in September.

---

## Overview

Rows per assembly in each table. A dash means the source has no data for that
assembly.

| | 17th | 18th | 19th | 20th | 21st | 22nd |
|---|---|---|---|---|---|---|
| Term | 2004-2008 | 2008-2012 | 2012-2016 | 2016-2020 | 2020-2024 | 2024- |
| Bills in the master, all kinds | 8,368 | 14,762 | 18,735 | 24,996 | 26,707 | 21,581 |
| Law bills (법률안) | 7,489 | 13,913 | 17,822 | 24,141 | 25,858 | 21,022 |
| Enacted law bills | 1,913 | 2,353 | 2,793 | 3,195 | 2,959 | 1,644 |
| Promulgated laws | 1,913 | 2,353 | 2,793 | 3,195 | 2,959 | 1,555 |
| Pending bills (계류중) | 0 | 0 | 0 | 0 | 0 | 15,105 |
| BILLRCP records (접수목록) | 8,368 | 14,762 | 18,735 | 24,996 | 26,707 | 21,581 |
| Member law bills (의원발의법률안) | 5,728 | 11,191 | 15,444 | 21,594 | 23,655 | 19,651 |
| Processed law bills (처리의안) | 7,489 | 13,913 | 17,822 | 24,141 | 25,858 | 6,088 |
| BILLJUDGE records (심사정보) | 1,128 | 6,707 | 6,844 | 8,101 | 8,526 | 5,241 |
| Master bills with a BILLINFODETAIL row | all | all | all | all | all | all |
| Committee meeting rows | 24,156 | 105,229 | 150,192 | 202,335 | 199,384 | 137,152 |
| Judiciary meeting rows | 1,628 | 2,810 | 3,304 | 3,325 | 3,217 | 1,574 |
| Subcommittee review rows | 2,966 | 10,880 | 15,765 | 22,206 | 23,840 | 18,324 |
| Alternative absorption links | 1,106 | 3,831 | 4,663 | 5,563 | 5,996 | 4,280 |
| 대안반영폐기 bills linked to their alternative | 57.5% | 99.5% | 99.6% | 99.9% | 99.3% | 99.9% |
| Cosponsorship edges | 121,125 | 222,630 | 210,725 | 269,823 | 300,045 | 255,415 |
| Vetoed bills | 2 | 0 | 3 | 0 | 14 | 28 |
| Plenary tallies | - | - | - | 3,492 | 3,272 | 1,847 |
| Member-level roll-call rows | - | - | - | 1,036,384 | 976,127 | 545,107 |
| Experimental 16th-19th vote rows | 24,901 | 14,210 | 1,247 | - | - | - |
| Ideal points, legislator-terms | - | - | - | 317 | 318 | 305 |
| Members | 322 | 331 | 332 | 320 | 322 | 321 |
| Committee assignment spells | 2,402 | 2,466 | 2,506 | 2,367 | 2,016 | 1,763 |
| Bill texts | - | - | - | 21,594 | 23,655 | 15,675 |
| Hearing meetings | 3,244 | 2,839 | 2,708 | 2,334 | 2,315 | 573 |
| Asset disclosure rows | - | - | 290 | 1,164 | 1,175 | 299 |

The experimental vote file also has 923 rows for the 16th Assembly, and the
hearing summary 2,816 meetings of the 16th. Committee assignment spells also
exist for the 14th-16th, from the careers of members who served later.

## What each assembly supports

| Analysis | 17th | 18th | 19th | 20th | 21st | 22nd |
|---|---|---|---|---|---|---|
| Bill outcomes and processing time | Yes | Yes | Yes | Yes | Yes | Yes, in session |
| Stage timing: committee, 법사위, floor, promulgation | Yes | Yes | Yes | Yes | Yes | Yes, in session |
| Presidential vetoes and re-votes | Yes | Yes | Yes | Yes | Yes | Yes, one re-vote pending |
| Committee meetings per bill | Yes | Yes | Yes | Yes | Yes | Yes |
| Subcommittee stages | Partial, 33.5% of bills | Yes | Yes | Yes | Yes | Yes |
| Alternative absorption | Partial, 57.5% | Yes | Yes | Yes | Yes | Yes |
| Cosponsorship networks, law bills | Yes | Yes | Yes | Yes | Yes | Yes |
| Party at proposal in the edges | No | No | Partial | Yes | Yes | Yes |
| Plenary tallies | No | No | No | Yes | Yes | Yes |
| Member-level roll calls | No | No | No | Yes | Yes | Partial, 16 members missing |
| Ideal points | No | No | No | Yes | Yes | Partial, 16 members missing |
| Committee assignment histories | Yes | Yes | Yes | Yes | Yes | Yes |
| Propose-reason texts | No | No | No | Yes | Yes | Partial, through 2026-02-27 |
| Asset disclosures | No | No | Partial, 2015 only | Yes | Yes | Partial, 2024 only |
| Hearing summaries | Yes | Yes | Yes | Yes | Yes | Partial, through 2025-07-21 |

The API has no member-level votes before the 20th Assembly. The 16th-19th
rows in `roll_calls_16_19_experimental.parquet` were parsed from minutes and
are not a roll-call matrix (CODEBOOK.md section 9).

---

## Known limitations

1. **22nd roll calls miss 16 members.** The live member-level vote API omits
   16 members seated during 2026. They are 이소희, 김태규, 유의동, 윤용근,
   이진숙, 김남국, 김남준, 김성범, 김의겸, 박지원 (H7X3372O), 송영길, 이광재,
   임문영, 전은수, 한동훈 and 김형연. Votes from 2026-01-15 lack one member,
   votes from 2026-06-11 lack 15 and votes from 2026-09-03 lack 16.

   | Votes | Members missing | 22nd votes |
   |---|---|---|
   | 2024-07-04 to 2025-12-30 | 0 | 1,056 |
   | 2026-01-15 to 2026-05-07 | 1 | 539 |
   | 2026-06-11 to 2026-08-26 | 15 | 165 |
   | 2026-09-03 to 2026-09-17 | 16 | 87 |

   As a result 791 of the 1,847 22nd votes have fewer member rows than the
   tally's membership count, and on 476 of them the yea, nay and abstain
   counts differ from the official tally. 475 of these differences are fully
   explained by the missing members. The remaining one, bill 2215128 on
   2026-01-29, also differs from the tally by one recorded vote. The 16
   members have no 22nd roll calls and no 22nd ideal point.
   `reports/rollcall_tally_check.csv` lists every vote.
2. **17th alternative absorption covers 57.5%.** TVBPMBILL11 returns nothing
   for most 17th alternatives with a numeric BILL_ID, so 1,099 of the 1,911
   17th 대안반영폐기 bills are linked. The 18th-22nd link 99.3% to 99.9%.
3. **Member-sponsored non-law items have no cosponsorship edges.** Resolutions,
   disciplinary motions and other non-law member items, 263 to 396 per
   assembly, have no proposer list in any API source.
4. **Bill texts come from another dataset.** `bill_texts_linked.parquet` is
   taken from the korean-assembly-bills dataset. It covers member law bills of
   the 20th-22nd and none proposed after its snapshot, the latest being
   2026-02-27, so 3,976 of the 22nd member law bills have no text.
5. **Hearing data are provisional.** `hearing_meetings_summary.parquet` and the
   speech links in `link_external.py` depend on version 9 of the
   kr-hearings-data corpus, which is known to be defective and is being
   rebuilt. The summary ends on 2025-07-21.
6. **The funnel is cumulative.** `kna stats funnel` counts the bills that
   reached a stage or any later stage, so that bills skipping a stage, such as
   committee alternatives and the 법제사법위원회's own bills, still count.
   Raw per-stage counts are not monotone.
7. **Party is fixed per term.** `party` is the party at election, the party
   whose list or ticket the member was elected on, or for a successor to a
   proportional seat the list the seat came from. It comes from ALLNAMEMBER,
   whose per-era party is usually the party at election, and six documented
   exceptions are overridden (CODEBOOK.md section 11). Party switches within a
   term are not observed. `party_api` in the roll calls is the API's current
   label and changes between collections.
8. **`rgs_rsln_dt` and `rgs_conf_rslt` are not floor-vote fields.** The API
   fills them with the final disposition of every processed bill. Use
   `plenary_decided` for floor decisions.
9. **Some fields are missing or wrong upstream.** Three withdrawn 18th bills
   have no processing date in any source. Per-bill dates are kept as the API
   returns them, so the master holds a few that are impossible or fall outside
   the bill's assembly. The only date set to null is 1006-11-30, the 소관위
   처리일 of 17th bill 175025 in BILLINFODETAIL and the processed-bill list,
   which the date type cannot hold. The meeting tables keep dates as the
   strings the API returns.

   | Bill | Proposed | Column | Date |
   |---|---|---|---|
   | 170993 | 2004-11-29 | `committee_dt`, `jrcmit_cmmt_dt` | 2000-11-30 |
   | 171318 | 2005-02-01 | `committee_dt`, `jrcmit_cmmt_dt` | 2002-02-02 |
   | 171320 | 2005-02-01 | `committee_dt`, `jrcmit_cmmt_dt` | 2002-02-02 |
   | 177527 | 2007-10-02 | `cmt_proc_dt`, `jrcmit_proc_dt` | 2207-12-27 |
   | 171175 | 2004-12-17 | `gvrn_trsf_dt` | 2004-04-30 |
   | 1803593 | 2009-01-19 | `cmt_present_dt`, `jrcmit_prsnt_dt` | 2008-01-21 |
   | 2207382 | 2025-01-09 | `jrcmit_cmmt_dt` | 2024-01-10 |

   These are the dates before the start of the bill's assembly or after the
   collection date. The first five bills are of the 17th Assembly.
10. **Agenda items outside the bill lists are excluded.** 인사청문요청안 and
    similar items that appear only in BILLJUDGE are not master bills. Their
    committee meeting rows are the 42 and 24 rows of the 17th and 18th that
    do not join to the master.
11. **District strings are not normalized.** See CODEBOOK.md section 11.
12. **`law_reflected` is not the official 법률반영 count.** It uses the four
    result codes of the LIKMS statistic but keeps the 69 law bills absorbed
    into six committee alternatives that the floor rejected without a veto.
    It therefore exceeds the official figure by 44, 16, 7 and 2 bills in the
    17th, 19th, 21st and 22nd, and equals it in the 18th and 20th. CODEBOOK.md
    section 1.6 gives a rule that reproduces the official count.

---

## API behavior

As observed in the September 2026 collection and audit.

| Endpoint | Content | Filter | Notes |
|---|---|---|---|
| nzmimeepazxkubdpn | 의원발의법률안, member law bills | `AGE` | Required parameter. |
| BILLRCP | 접수목록, every received bill | `ERACO`, such as `제22대` | `AGE` is ignored. `ERACO` filters on the server. Pending bills are included. |
| BILLJUDGE | 심사정보, committee review records | `ERACO` | Same as BILLRCP. |
| ncocpgfiaoituanbr | 의안별표결현황, plenary tallies | `AGE` | No data before the 20th. |
| nzpltgfqabtcpsmai | 처리의안, processed law bills | `AGE` | |
| BILLINFODETAIL | 의안상세정보 | `BILL_ID` | One call per bill. |
| BILLJUDGECONF | 위원회 회의정보 | `BILL_ID` | One call per bill. |
| BILLLWJUDGECONF | 법제사법위원회 회의정보 | `BILL_ID` | One call per bill. |
| nojepdqqaweusdfbi | 의원별 표결, member-level votes | `AGE` and `BILL_ID` | Both parameters are required. No data before the 20th. Omits some members seated during the term and fills in past votes later, so an ongoing assembly must be re-pulled in full. Its party label is the member's party at the time of the call. |
| BILLINFOPPSR | proposers and supporters of a bill | `BILL_ID` | Paginates beyond 100 names. Party at proposal is empty for the 17th and 18th. |
| TVBPMCONFINFO | 소위 심사정보, subcommittee stages | `AGE` | Opened in July 2026. |
| TVBPMBILL11 | bills linked to an alternative | `AGE` and `BILL_ID_REF` | Returns nothing for most 17th alternatives with a numeric BILL_ID. A vetoed alternative awaiting its re-vote must be queried by its original `PRC_` ID, which no bill list returns. |
| ALLNAMEMBER | all members ever | none | Party, district and committee as `/`-separated lists by era, which are sometimes misaligned. The per-era party is usually the party at election, with six known exceptions. The calendar code BIRDY_DIV_CD is the reverse of BTH_GBN_NM in the two endpoints below. |
| npffdutiapkzbfyvr | 역대 국회의원 현황 | `UNIT_CD` `1000{age}` | District, election type and birth calendar of the term. Serving 22nd members are not in it. |
| nwvrqwxyaytdsfvhu | current members | none | Current party, district and birth calendar. |
| nqbeopthavwwfbekw | committee careers of former members | `PROFILE_UNIT_CD` | Dated spells. |
| nyzrglyvagmrypezq | committee careers of current members | none | Dated spells, all assemblies. |

Two more endpoints are used only for checks. `collect_members.py` compares
its seniority counts with ngdeoqgoablceakpp (역대 국회의원 재선 현황) after a
collection, and not during a build. The per-assembly member records of
nprlapfmaufmqytet are the evidence for three of the six party overrides, and
a snapshot of the 17th-21st is kept in `data/raw/members/`. For the other
three, members elected on the 더불어시민당 list, those records give
더불어민주당, which absorbed 더불어시민당 in May 2020, and
`party_overrides.csv` cites Korean Wikipedia instead.

**17th-Assembly bill IDs.** The 17th master has 2,633 `PRC_` IDs, 13 `ARC_`
IDs and 5,722 six-digit numeric IDs. All three formats work on the per-bill
endpoints BILLINFODETAIL, BILLJUDGECONF and BILLLWJUDGECONF.

| 17th ID format | Bills | With committee meeting rows | With judiciary meeting rows | With subcommittee rows |
|---|---|---|---|---|
| `PRC_` | 2,633 | 1,736 | 319 | 1,360 |
| `ARC_` | 13 | 4 | 1 | 4 |
| numeric | 5,722 | 3,163 | 992 | 1,438 |

**General behavior.**

- The page size is at most 1,000 rows.
- Errors come back as HTTP 200 with a top-level `RESULT` object, outside the
  endpoint envelope. INFO-200 means no data, and ERROR-337 is the traffic
  limit.
- Without a valid key the API answers INFO-000 with the true
  `list_total_count` but returns only a five-row sample. The collectors
  therefore refuse to run without `ASSEMBLY_API_KEY` and check that the rows
  received equal `list_total_count`.
- The portal rejects some default User-Agents. The collectors send a
  browser-like one.
- BILL_IDs are not permanently stable. Bill 2203215 was re-keyed when it was
  withdrawn on 2026-05-14, and its old ID no longer resolves.

---

## Committee names

Committees are renamed and reorganized between and within assemblies, so
time-series analysis by committee needs a harmonization table, which kna does
not provide. In the 22nd master both the earlier and the later names appear.

| Later name | Bills, 22nd | Earlier name | Bills, 22nd |
|---|---|---|---|
| 기후에너지환경노동위원회 | 1,892 | 환경노동위원회 | 170 |
| 재정경제기획위원회 | 1,494 | 기획재정위원회 | 491 |
| 성평등가족위원회 | 249 | 여성가족위원회 | 51 |
