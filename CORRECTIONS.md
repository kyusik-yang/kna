# Corrections

Errata for data released by this repository. Newest first.

---

## 2026-09-28 - Release 0.8.1

Release 0.8.1 rebuilds `hearing_meetings_summary.parquet` from
kr-hearings-data release v10.2 (run 20260928T175652_175976). Releases 0.6.0
to 0.8.0 shipped a table built from version 9, whose defects D1 to D12 are
listed in docs/CHANGELOG.md of kr-hearings-data. Every other file is
identical to 0.8.0. The figures were computed from the 0.8.0 table and the
0.8.1 build.

| File | 0.8.0 | 0.8.1 |
|---|---|---|
| `hearing_meetings_summary.parquet` | 16,829 meetings, 2000-06-01 to 2025-07-21, eight columns | 26,261 meetings, 2000-06-05 to 2026-09-22, columns `conf_num` and `is_subcommittee` added |

The build reads the v10.2 build directory, the v10.2 release assets or the
kr-hearings-data package, and the three give the same table.

### What changed

- **Key.** `meeting_id` is now the Open API CONF_ID, verbatim. The v9 ID
  dropped the leading zero of five-digit CONF_IDs, so `meeting_id` differs in
  14,321 of the matched meetings. 187 meetings have no CONF_ID, because no
  Open API list returns them, and keep a null `meeting_id`. `conf_num`, the
  record-viewer ID, is set and unique for every meeting and joins to
  kr-hearings-data.
- **Coverage.** 16,793 of the 16,829 v9 meetings are matched through the
  `v9_meeting_id` of kr-hearings-data. 9,468 meetings are new, 6,873 of them
  subcommittee meetings. The 36 v9 meetings without a match are 35
  인사청문특별위원회 meetings and one 국정감사 meeting.
  `crosswalk_meetings` of kr-hearings-data records where each v9 meeting
  went.
- **n_legislators** counts the distinct codes of legislator-role turns only.
  The v9 table counted every code, including an empty one, which it counted
  as a legislator in 2,119 meetings.
- **parties** lists the labels of the legislator-role turns, each the
  speaker's party on the speech date. No meeting has an empty label any more.

Among the 16,793 matched meetings the other columns differ as follows.

| Column | Matched meetings that differ |
|---|---|
| `term`, `date` | 0 |
| `committee` | 202, all 국정감사. In 164 (16th 2, 17th 162) the v9 name carries an audit team (for example 통일외교통상위원회-구주반) and v10 has none. kr-hearings-data finds no team in the 17th source. In 34 of the 22nd v10 carries a team and v9 has none. In 4 the team is spelled with a different separator. |
| `hearing_type` | 3. conf_num 45567, 45569 and 52770 were 인사청문특별위원회 in v9 and are 상임위원회 in v10. |
| `n_speeches` | 3,058 |
| `n_legislators` | 2,967 |
| `parties` | 12,350 |

### Action for users

- Join the table to kr-hearings-data on `conf_num`, not on `meeting_id`.
- Code that joined on the v9 `meeting_id` should use the `v9_meeting_id` of
  kr-hearings-data `meetings` to find the new rows.
- Counts of meetings per assembly are higher, mainly because subcommittee
  meetings are now included. Filter on `is_subcommittee` to leave them out.

---

## 2026-09-28 - Release 0.8.0

Release 0.8.0 extends the bill texts to every law bill of the 17th-22nd
Assemblies, completes the 22nd roll calls for 16 members that the
member-level vote API omits, adds the member-level roll calls of the
17th-19th from the plenary minutes, rebuilds the asset panel with a script in
this repository and extends it to wealth_year 2025, and reports a search for
the missing 17th alternative links. The added 22nd votes change the default
ideal points of the 22nd and move the pooled DW-NOMINATE series slightly in
every assembly. The files below change, and every other file is
identical to 0.7.1. All figures were computed from the 0.7.1 files and the
0.8.0 build.

| File | 0.7.1 | 0.8.0 |
|---|---|---|
| `bill_texts_linked.parquet` | 60,925 rows, 20th-22nd member law bills | 109,829 rows, 17th-22nd law bills, columns `age`, `bill_no` and `source` added |
| `roll_calls_all.parquet` | 2,557,618 rows, 20th-22nd | 4,147,402 rows, 17th-22nd, columns `vote_event_id` and `member_match` added |
| `vote_events.parquet` | 8,611 tallies, 20th-22nd | 16,465 rows, with 7,854 recorded votes of the 17th-19th and the columns `vote_event_id`, `chair_present`, `chair_yes`, `chair_no`, `chair_abstain`, `chair_counts_differ` and `correction_note` added |
| `master_bills_17`-`19` | `vote_*` columns empty | `vote_*` columns filled for the bills with a recorded vote |
| `roll_calls_16_19_experimental.parquet` | 41,281 rows, 16th-19th | 923 rows, 16th only |
| `ideal_points_*.csv`, `ideal_points_manifest.json`, `dwnominate_fit.rds` | 940 legislator-terms | 955 legislator-terms |
| `legislator_id_mapping.parquet` | `in_roll_calls` 661, `in_ideal_points` 654 | `in_roll_calls` 1,152, `in_ideal_points` 664 |
| `assets_wealth_panel.parquet` | 2,928 rows, wealth_year 2015-2024 | 3,215 rows, wealth_year 2015-2025 |
| `reports/` | five reports | nine reports. `bill_texts_coverage.csv`, `bill_texts_missing.csv`, `assets_compare.csv` and `assets_member_check.csv` are added, and `master_compare.csv` and `rollcall_tally_check.csv` are rewritten |

### Bill texts extended to every 17th-22nd law bill

#### What changed

`bill_texts_linked.parquet` held the texts that the korean-assembly-bills
dataset had scraped from LIKMS, which cover the member law bills of the
20th-22nd proposed by 2026-02-27. The texts of the 17th-19th, of government
and committee bills and of recent 22nd bills were missing, 49,700 law bills
in all. `collect_structure.py summaries` collected them on 2026-09-28 from
BPMBILLSUMMARY (법률안 제안이유 및 주요내용), one call per bill number, and
no call failed. The answers are in `data/raw/BPMBILLSUMMARY_{17..22}.parquet`.

`link_external.py texts` keeps every scraped row and its text unchanged. It
fills the 307 scraped rows that have no text from the API, which keep the
`scrape_status` of the scrape, and adds a row for every other law bill with an
API text. The new column `source` is
`likms_scrape` or `BPMBILLSUMMARY`, and the new columns `age` and `bill_no`
come from the masters. The one row with the old BILL_ID of bill 2203215 keeps
them null.

#### How it was checked

On 300 scraped bills drawn at random, 100 from each of the 20th, 21st and
22nd, the API text equals the scraped text once the leading heading and all
whitespace are removed. The API texts keep the heading the document starts
with, such as 제안이유 및 주요내용 or ■ 대안의 제안경위. For 489 law bills
the API returns a record whose text is empty, and 328 of them are government
bills of the 18th. `reports/bill_texts_missing.csv` lists them, and
`reports/bill_texts_coverage.csv` gives the coverage by assembly and
proposer kind.

#### Before and after

| Assembly | Law bills | With a text, 0.7.1 | With a text, 0.8.0 | Scraped text | BPMBILLSUMMARY text |
|---|---|---|---|---|---|
| 17 | 7,489 | 0 | 7,486 | 0 | 7,486 |
| 18 | 13,913 | 0 | 13,584 | 0 | 13,584 |
| 19 | 17,822 | 0 | 17,822 | 0 | 17,822 |
| 20 | 24,141 | 21,592 | 24,109 | 21,592 | 2,517 |
| 21 | 25,858 | 23,314 | 25,787 | 23,314 | 2,473 |
| 22 | 21,022 | 15,639 | 20,968 | 15,639 | 5,329 |
| All | 110,245 | 60,545 | 109,756 | 60,545 | 49,211 |

| Check | 0.7.1 | 0.8.0 |
|---|---|---|
| Rows | 60,925 | 109,829 |
| Rows with a text | 60,546 | 109,757 |
| Share of law bills with a text | 54.9% | 99.6% |
| Latest proposal date of a bill with a text | 2026-02-27 | 2026-09-23 |

The rows with a text exceed the law bills with a text by one, the old-ID row
of bill 2203215.

### 22nd roll calls completed for 16 members from LIKMS

#### What was wrong

The member-level vote API, nojepdqqaweusdfbi, omits 16 members seated
during 2026. They are 이소희, seated on 2026-01-15, the 14 winners of the
by-elections of 2026-06-11, and 김형연, seated on 2026-09-03. The per-member
views of LIKMS and of www.assembly.go.kr return nothing for them either. In
0.7.1 they had no 22nd roll calls and no 22nd ideal point, 791 of the 1,847
22nd votes had fewer member rows than the tally's membership count, and on
476 of them the 찬성, 반대 and 기권 counts differed from the official tally.

#### What changed

`collect_votes_likms.py` reads the vote page of LIKMS (의안 상세, 표결정보)
for each of the 791 votes. It made at most one request per second on
2026-09-28, and every request succeeded. The page lists the members who voted
찬성, 반대 and 기권 by name, with no member ID and no list of absentees. The
script removes the API's rows from each list and matches the names left over
to the one member of `members_22` with that name who has no API row on that
vote. They become rows with source `likms`. The roster has two members named
박지원, and 8BF5855P has an API row on every vote, so a left-over 박지원 is
H7X3372O. A member who was seated but is on no list gets a 불참 row with
source `likms_absent`. The seat dates come from the steps in the tally's
membership count and from the first list on which each member appears. The
rows are written to `data/raw/roll_calls_22_supplement.parquet`, and the build
stops if a name cannot be matched or if the rows do not add up to the page's
lists and to the membership count. `party` is the party at election, as for
every row, and `party_api` is the member's current party,
`members_22.party_current`.

#### Before and after

| 22nd Assembly | 0.7.1 | 0.8.0 |
|---|---|---|
| Roll-call rows | 545,107 | 549,513 |
| Rows with source `api` / `likms` / `likms_absent` | 545,107 / 0 / 0 | 545,107 / 3,295 / 1,111 |
| Members with roll calls | 305 | 321 |
| Votes with fewer member rows than the tally's membership count | 791 | 0 |
| Votes whose 찬성, 반대 and 기권 counts differ from the tally | 476 | 1 |

The one remaining difference is bill 2215128 of 2026-01-29. Its member rows
give 196 찬성, no 반대 and 1 기권, against 195, 0 and 2 in the tally. The
name lists of its LIKMS page give the member-level counts, and the counts in
the header of the same page give the tally's.

#### Effect on the default ideal points

`build_ideal_points.R` now reads the rows with source `api`, `likms` and
`likms_absent` of the 20th-22nd. Fifteen of the 16 members enter the 22nd
series. The sixteenth, 한동훈 (5DC8083A), has 12 contested yea or nay votes,
fewer than the 20 required.

- Per-assembly W-NOMINATE (`wnom_1d`, `wnom2d_dim1`, `wnom2d_dim2`) and
  `bridged_1d` of the 20th and 21st are identical to 0.7.1, value for value.
- For the 305 legislators in both releases, the 22nd `wnom_1d` and
  `bridged_1d` correlate at 0.99978 with those of 0.7.1. The largest shift is
  0.110 in `wnom_1d` and 0.081 in `bridged_1d`.
- Pooled DW-NOMINATE (`dwnom_1d`) is estimated jointly over the 20th-22nd,
  so the added 22nd votes move every assembly. Its 20th, 21st and 22nd values
  correlate at 0.99986, 0.99991 and 0.99987 with 0.7.1. The mean shift is
  -0.012, -0.010 and -0.010, and the largest shift 0.045, 0.055 and 0.031.
- The second dimension of the 22nd two-dimensional fit, `wnom2d_dim2`, is
  unstable. Over the 305 legislators in both releases it correlates at -0.354
  with 0.7.1, and the mean of the 개혁신당 members moved from 0.92 to -0.94.
  The first dimension, `wnom2d_dim1`, correlates at 0.9997. Treat the 22nd
  `wnom2d_dim2` as unreliable.

| Default series, v20260917 | 0.7.1 | 0.8.0 |
|---|---|---|
| Legislator-terms, 20th / 21st / 22nd | 317 / 318 / 305 | 317 / 318 / 320 |
| Contested votes of the 22nd | 223 | 226 |
| 22nd onto 21st, bridging legislators | 151 | 156 |
| 22nd onto 21st, slope and intercept | 0.7065 and -0.0307 | 0.7661 and -0.0525 |
| 22nd onto 21st, R² | 0.950 | 0.951 |
| 22nd bloc sizes, conservative / liberal / rebuilding | 108 / 179 / 13 | 113 / 188 / 14 |

The bloc distances of CODEBOOK.md section 10.4 change as follows. Distance
is the gap between the conservative and liberal bloc means, and the within-bloc
SD is the pooled standard deviation of the two blocs, for the 20th, 21st and
22nd.

| Series | Release | Distance | Within-bloc SD | Ratio | Growth of the distance, 20th to 22nd |
|---|---|---|---|---|---|
| `wnom_1d` | 0.7.1 | 0.818 / 0.931 / 1.145 | 0.158 / 0.132 / 0.111 | 5.18 / 7.04 / 10.35 | +40.1% |
| `wnom_1d` | 0.8.0 | 0.818 / 0.931 / 1.068 | 0.158 / 0.132 / 0.107 | 5.18 / 7.04 / 10.01 | +30.6% |
| `bridged_1d` | 0.7.1 | 0.818 / 0.836 / 0.809 | 0.158 / 0.119 / 0.078 | 5.18 / 7.04 / 10.35 | -1.0% |
| `bridged_1d` | 0.8.0 | 0.818 / 0.836 / 0.818 | 0.158 / 0.119 / 0.082 | 5.18 / 7.04 / 10.01 | +0.1% |
| `dwnom_1d` | 0.7.1 | 0.781 / 0.825 / 0.846 | 0.109 / 0.115 / 0.123 | 7.14 / 7.18 / 6.90 | +8.4% |
| `dwnom_1d` | 0.8.0 | 0.762 / 0.809 / 0.834 | 0.109 / 0.114 / 0.123 | 7.00 / 7.11 / 6.80 | +9.5% |

The vintage is still v20260917, because it names the date of the last vote,
so the 0.7.1 and 0.8.0 files carry the same label. The input SHA-256 in
`ideal_points_manifest.json` tells them apart. The archive
`ideal_points_archive/v20260312_corrected/` is unchanged. Rerun on the 0.8.0
roll calls with the same cutoff, `build_ideal_points.R` gives byte-identical
ideal-point CSV files and bridging parameters.

### 17th-19th roll calls rebuilt from the plenary minutes

`roll_calls_all` now holds the member-level recorded votes of the 17th, 18th
and 19th Assemblies. They were parsed from the name lists that the plenary
minutes print in the appendix 【전자투표 찬반 의원 성명】, one list per
recorded vote. Until now the repository had only meeting-level pseudo events
for these assemblies (entry of 2026-09-26, item (h)).

#### What changed

`collect_minutes_votes.py` lists the plenary meetings with nzbyfwhwaoanttzje,
downloads the minutes PDF of each, 188, 179 and 182 meetings, at most one
request per second, and parses them with `minutes_votes.py` into
`data/raw/minutes_votes_{17,18,19}.parquet`, one row per printed name, and
`data/raw/minutes_vote_events_{17,18,19}.parquet`, one row per vote.
`consolidate_votes.py` adds the names to `roll_calls_all` with source
`minutes_pdf`, and `integrate.py` adds the votes to `vote_events` and fills
the `vote_*` columns of `master_bills_17`-`19`, which were empty. The
appendix names are the record. The counts the chair announced are kept beside
them in `vote_events`, with a flag when they differ and a flag when the
appendix prints a correction note. The chair's counts and result are null
for exactly two votes, both of the 18th. The chair declared 18_33387_002 void,
and in 18_34089_006 the chair misspoke the counts, naming 반대 twice. Rows whose
printed name two members share keep member_id null when the minutes do not
say which member voted. No ideal-point series uses these rows.

| File | 0.7.1 | 0.8.0 |
|---|---|---|
| `roll_calls_all.parquet` | 20th-22nd | 17th-22nd, 1,585,378 rows of the 17th-19th added |
| `vote_events.parquet` | 8,611 tallies, 20th-22nd | 16,465 rows, 7,854 votes of the 17th-19th added |
| `master_bills_17`-`19` | `vote_*` empty | filled for 2,167, 2,539 and 3,095 bills |
| `roll_calls_16_19_experimental.parquet` | 41,281 rows, 16th-19th | 923 rows, 16th only |

| Assembly | Meetings | Votes | Rows | Votes with bill_id | Rows with member_id | Chair counts equal the names | Differ, explained by a correction note |
|---|---|---|---|---|---|---|---|
| 17 | 188 | 2,189 | 440,473 | 2,183 | 440,473 | 1,999 of 2,189 | 189 of 190 |
| 18 | 179 | 2,559 | 500,535 | 2,549 | 500,174 | 2,133 of 2,557 | 409 of 424 |
| 19 | 182 | 3,106 | 644,370 | 3,104 | 643,037 | 2,532 of 3,106 | 570 of 574 |

A correction note explains a difference when the counts it prints equal the
names.

#### How it was checked

The names equal the group counts printed in the appendix in 2,188 of 2,189,
2,558 of 2,559 and 3,106 of 3,106 votes. CODEBOOK.md section 8 names the two
exceptions. No member appears twice in one vote. For every vote on a bill
itself with a readable result, the chair's 가결 or 부결 agrees with the
master's `rgs_conf_rslt`. The lists were also compared with an independent
parse of the same minutes prepared for version 10 of kr-hearings-data, which
is not yet released. They are identical for 1,850 of 1,861, 2,510 of 2,510
and 3,104 of 3,105 votes that both hold. Eleven of the twelve differences are
parse errors on the other side, and the twelfth is a name the minutes print
twice. `tests/test_minutes_votes.py` repeats these checks on every build.

#### Correction to the entry of 2026-09-26, item (h)

The counts of votes with appendix name lists in item (h) were too low. The
minutes PDFs mark 2,187 votes in the 17th, 2,557 in the 18th and 3,106 in the
19th with '(찬반 의원 성명은 끝에 실음)', and their appendices hold 2,189,
2,559 and 3,106 votes. For the 16th, whose PDFs were not parsed, the marker
appears 466 times in the text of 41 plenary meetings as parsed for version 10
of kr-hearings-data.

In item (h), read "The plenary minutes mark 2,187 votes with appendix name
lists in the 17th and 2,557 in the 18th, against 108 and 62 events in the
file." for the sentence that begins "The plenary minutes refer to", and read
the last column of its first table as follows.

| Assembly | Votes with appendix name lists referred to in the minutes, as printed in (h) | Corrected |
|---|---|---|
| 16 | 175 | 466 |
| 17 | 2,062 | 2,187 |
| 18 | 1,706 | 2,557 |
| 19 | 468 | 3,106 |

The rebuild from the appendix PDFs that (h) calls deferred is the one this
entry describes.

### Asset panel rebuilt reproducibly and extended to wealth_year 2025

#### What was wrong

`assets_wealth_panel.parquet` was carried over unchanged from 0.6.0. No
script in the repository produced it, so its derivation from the source data
could not be checked, and it ended with wealth_year 2024.

#### What changed

`build_assets.py` builds the panel. `fetch` downloads the 국회공보 PDFs and
checks them against pinned SHA-256 values, and `build` reads them together
with the OpenWatch item-level files of the March regular disclosures of
2016-2025, which must be placed in the directory named by `KNA_ASSETS_DIR`.
The 2015-2024 rows come from the OpenWatch files, as before. The wealth_year
2025 rows are parsed from the official 국회공보 제2026-54호 of 2026-03-26,
which prints the March 2026 regular disclosure (국회공직자윤리위원회공고
제2026-3호). Members in the notice are matched to their MONA_CD by name
through `members_22`. The quartile columns keep the cut points of the pooled
2015-2024 rows, so the added year does not relabel earlier rows.
`build_all.sh` runs the build when `KNA_ASSETS_DIR` is set, and otherwise
carries the shipped panel over.

#### How it was checked

- The 2015-2024 rows of the rebuild equal the 0.7.1 file in every row and
  column.
- In the 2026 notice, the parsed items add up to all 2,323 printed category
  subtotals, and the subtotals to all 330 printed totals. The build stops
  otherwise.
- The same parser, applied to the March 2025 issue (국회공보 제2025-51호),
  reproduces all 299 member-years that the OpenWatch files give for
  wealth_year 2024 in the 33 columns compared, and its name matching gives the
  OpenWatch member codes.
- For all 283 members with a 2024 row and a 2025 row, the prior-year total
  printed in the 2026 notice equals the 2024 `net_worth`.

#### Before and after

| | 0.7.1 | 0.8.0 |
|---|---|---|
| Rows | 2,928 | 3,215 |
| Members | 772 | 776 |
| wealth_year | 2015-2024 | 2015-2025 |
| 22nd rows | 299, wealth_year 2024 | 586, wealth_year 2024 and 2025 |
| Built by | not reproducible in the repository | `build_assets.py` |

The notice lists 330 people, 287 of them members of the Assembly, and 275 of
these were serving at the member snapshot of 2026-09-25. Seven serving
members with a 2024 row are not in the notice. They are 정동영, 김윤덕,
윤호중, 김민석, 안규백, 정성호 and 김성환, and the reason has not been
verified. The members seated in 2026, the 16 of the section above and
김준환, are not in it either.

### The 17th alternative links, searched without a new source

#### What was checked

TVBPMBILL11 returns nothing for most 17th alternatives with a numeric
BILL_ID, so 1,099 of the 1,911 17th 대안반영폐기 bills are linked to their
alternative. A search for another official source of these links found none.
TVBPMBILL11 called with other parameters and the other bill services of the
Open Assembly catalog give no further links, and for the alternatives checked
the 대안정보 tab of LIKMS lists the same bills as the API, and nothing where
the API returns nothing.

An inference from the alternatives' own texts was tested. The BPMBILLSUMMARY
text of a 17th alternative often names the bills it replaces, with their
proposal dates and proposers. Matching these mentions to the 대안반영폐기
bills of the same committee with the same committee decision date, and keeping
the bills matched to exactly one alternative, recovers 47.7% of the known
links with a precision of 99.8% on the alternatives that TVBPMBILL11 does
link. On the unlinked alternatives it would add 176 bills from 92
alternatives. These links are inferred and not official, and 0.8.0 does not
include them.

| 17th Assembly | 0.7.1 | 0.8.0 | With the inferred links, not shipped |
|---|---|---|---|
| 대안반영폐기 bills linked to an alternative | 1,099 of 1,911 | 1,099 of 1,911 | 1,275 of 1,911 |
| Coverage | 57.5% | 57.5% | 66.7% |

### Action for users

- Analyses that use the 22nd default ideal points, or the pooled
  DW-NOMINATE series of any assembly, should be rerun. The 0.7.1 files carry
  the same vintage label, and `ideal_points_manifest.json` identifies them.
- Do not use the 22nd `wnom2d_dim2`, which is unstable.
- Code that assumed `roll_calls_all` holds only the 20th-22nd, that
  `member_id` is never null or that (term, bill_id, member_id) is unique in
  every assembly should filter on `term` or `source`. In the 17th-19th, use
  `vote_event_id` to identify a vote and treat rows without a member_id as
  missing in member-level analyses.
- The 17th-19th rows of `roll_calls_16_19_experimental.parquet` are gone.
  Use `roll_calls_all` instead.
- Text analyses should record `source`, because the API texts keep a
  heading that the scraped texts lack.

---

## 2026-09-27 - Release 0.7.1 corrects five member records

A downstream check of `members_{age}.parquet` against the National Assembly's
member records and Wikipedia found five member-terms whose district or
election type was inconsistent. `collect_members.py` now applies three
consistency rules after parsing, described in CODEBOOK.md section 11. No
other file changes. Roll calls, ideal points and bills do not use these two
columns.

| Member | Assembly | Column | 0.7.0 | 0.7.1 |
|---|---|---|---|---|
| 신용현 (MTK2954E) | 20 | `election_type` | 지역구 | 비례대표 |
| 권미혁 (RH454994) | 20 | `election_type` | 지역구 | 비례대표 |
| 손솔 (2KM3589W) | 22 | `district` | empty | 비례대표 |
| 최혁진 (CC78321E) | 22 | `district` | empty | 비례대표 |
| 박지원 (8BF5855P) | 22 | `district` | 전남광주통합특별시 해남군완도군진도군 | 전남 해남군완도군진도군 |

The first two rows repeat an inconsistency in the official roster, which
lists both members' district as 비례대표 and their election type as 지역구.
The last row reverses a 2026 renaming in the serving-member endpoint, so the
district reads as it did at the 2024 election.

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
