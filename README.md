# kna - Korean National Assembly CLI

[![PyPI](https://img.shields.io/pypi/v/kna)](https://pypi.org/project/kna/)


> **Correction, 2026-09-26 (release 0.7.0).** This release corrects ten
> defects in the data shipped up to 0.6.0. Among them, the 17th-20th committee
> meeting tables stopped at five rows per bill, the roll-call votes of
> same-name legislators were dropped, party labels were the API's current
> party applied to past votes, and vetoed bills were recorded as separate
> government bills. The default ideal-point series changes, and the 0.6.0
> series is kept in an archive folder. If you used earlier files, read the
> 2026-09-26 entry of [CORRECTIONS.md](CORRECTIONS.md) before reusing results.
> The earlier notice of 2026-07-18, on ideal points mislabeled as
> DW-NOMINATE, remains there too.

Comprehensive CLI and master database for the Korean National Assembly.
It integrates 17 Open Assembly API endpoints into one queryable database of
bills, committee and floor stages, vetoes, roll calls, ideal points, members,
committee assignments and cosponsorship, covering the 17th-22nd Assemblies
(2004-2026).

## Installation

### Step 1. Install the CLI

```bash
pip install kna
```

If you see a PATH warning like:

```
WARNING: The script kna is installed in '/Users/you/Library/Python/3.x/bin' which is not on PATH.
```

Add it to your shell:

```bash
# Find where pip installed it
python3 -c "import site; print(site.getusersitepackages().replace('lib/python/site-packages','bin'))"

# Add to PATH (adjust the path from above)
echo 'export PATH="$HOME/Library/Python/3.9/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Or use `pipx install kna`, which handles PATH automatically. From a
repository checkout, `python3 -m kna` runs the CLI without installing it.

### Step 2. Get the data

The data files are in this repository and use **Git LFS**. The package on
PyPI contains the code only.

```bash
# Install Git LFS first (required, one-time)
brew install git-lfs    # macOS
# or: sudo apt install git-lfs    # Ubuntu/Debian

git lfs install         # one-time setup

# Clone with data
git clone https://github.com/kyusik-yang/kna.git
cd kna
```

If you already cloned without LFS, the parquet files will be tiny pointer
files and `kna info` will fail. Fix it:

```bash
cd kna
git lfs install
git lfs pull            # downloads the data files, about 270 MB
```

The download holds about 185 MB of tables in `data/processed/` and about
85 MB of raw API files in `data/raw/`, which are needed only to rebuild the
tables. To download only the tables, run
`git lfs pull --include="data/processed/*"`.

### Step 3. Point the CLI to the data

```bash
# Set the environment variable
export KBL_DATA=~/kna/data/processed

# Make it permanent
echo 'export KBL_DATA="$HOME/kna/data/processed"' >> ~/.zshrc
source ~/.zshrc

# Verify
kna info
```

Without `KBL_DATA`, the CLI looks for `data/processed` next to the package in
a repository checkout, then under the working directory, then in
`~/.cache/kna`. An invalid `KBL_DATA` prints a warning and falls back to these
locations.

### Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `kna: command not found` | pip bin dir not in PATH | Add pip's bin directory to `~/.zshrc` PATH (see Step 1) |
| `ArrowInvalid: Parquet magic bytes not found` | Git LFS not installed, so the parquet files are pointer files | `brew install git-lfs && git lfs install && git lfs pull` |
| `Cannot find data directory` | `KBL_DATA` not set, and no `data/processed` in the checkout or the working directory | `export KBL_DATA=~/kna/data/processed` |
| `No master file for Nth assembly` | Data files missing for that assembly | Check `ls $KBL_DATA/master_bills_*.parquet` |
| `ERROR: requires Python >=3.9` | Python too old | `python3 --version`, 3.9 or later is needed |
| `ModuleNotFoundError: No module named 'kna'` | Installed to another Python | `python3 -m pip install kna` with the Python you run |

### Requirements

- Python 3.9+
- Git LFS (for data files)
- About 190 MB of disk space for `data/processed/`, and 85 MB more for `data/raw/`

**[Interactive Explorer](https://kyusik-yang.github.io/kna/)** | **[Ideology map](https://kyusik-yang.github.io/kna/voteview.html)** | **[Tutorial](https://kyusik-yang.github.io/assembly-tutorial/)** | **[PyPI](https://pypi.org/project/kna/)**

## Key Statistics

Release 0.7.0. Most data were collected from the Open Assembly API on
2026-09-25, and DATA_AVAILABILITY.md lists the exceptions.

| | |
|---|---|
| **Bills** | 115,149 bills of all kinds, 17th-22nd, of which 110,245 are law bills (법률안) |
| **Enacted law bills** | 14,857 law bills with a final result of 원안가결 or 수정가결, of which 14,768 were promulgated |
| **Roll-call votes** | 2,557,618 member-level records on 8,610 recorded votes, 20th-22nd |
| **Ideal points** | 940 legislator-terms, 20th-22nd, three series, vintage v20260917 |
| **Committee meetings** | 818,448 rows, one per bill, meeting and agenda step, 17th-22nd |
| **Subcommittee reviews** | 93,981 bill-stage rows, 17th-22nd |
| **Alternative absorption** | 25,439 links from committee alternatives to the bills they absorbed |
| **Cosponsorship** | 1,379,763 bill-member edges on 97,263 member law bills, 17th-22nd |
| **Vetoes** | 47 presidential reconsideration requests with their outcomes |
| **Members** | 1,948 member-terms, 17th-22nd, with party, district, seniority and dated committee assignments |
| **Asset disclosures** | 2,928 member-year rows, 19th-22nd |
| **Bill texts** | 60,925 member law bills of the 20th-22nd, 60,546 with a propose-reason text |
| **Dates** | Bills proposed 2004-05-31 to 2026-09-23, votes through 2026-09-17 |

## CLI Usage

```bash
# Database overview
kna info

# Search bills by title
kna search "인공지능" --assembly 22 --status enacted

# Bills led by one legislator (exact name, joint leads included)
kna search "조세특례제한법" --proposer 박범계 --assembly 21

# Status groups also include expired (임기만료폐기) and reflected (법률반영)
kna search "법" --assembly 21 --status reflected -n 5

# Full-text search in propose-reason texts (20th-22nd)
kna text "기후변화" --assembly 22

# Bill lifecycle timeline (proposal to promulgation)
kna show 2217673

# A vetoed bill: first passage, 재의요구 and 재의결
kna show 2200851

# Legislator profile with ideal point
kna legislator 추미애 --assembly 22

# Same-name legislators: the CLI lists their MONA_CDs, and --mona picks one
kna legislator 김병욱 --assembly 21 --mona GFF1986K

# Legislative funnel (each stage counts bills that reached it or a later stage)
kna stats funnel --assembly 22

# Passage rate trend across assemblies
kna stats passage-rate

# Export to CSV, TSV or Parquet
kna export health.csv --assembly 22 --committee 보건복지 --status enacted
```

`--status` groups are `passed` (원안가결, 수정가결, 대안반영폐기), `enacted`
(원안가결, 수정가결), `reflected` (bills with `law_reflected` = 1),
`pending` (계류중), `rejected` (부결, 폐기, 철회) and `expired` (임기만료폐기).
`law_reflected` uses the four result codes of the official LIKMS 법률반영
statistic, 원안가결, 수정가결, 대안반영폐기 and 수정안반영폐기, less the bills
absorbed into a vetoed alternative. It equals the official count in the 18th
and 20th only, and CODEBOOK.md section 1.6 explains the gap.
`kna legislator NAME` without `--assembly` shows every term the legislator
served.

## Python API

```python
from kna.data import BillDB

db = BillDB()        # uses KBL_DATA, or data/processed in a repository checkout

# Bills, reading only the columns you ask for
bills = db.bills(assembly=22, columns=["bill_id", "bill_nm", "status",
                                       "enacted", "promulgated", "vetoed"])
db.bill_columns(22)                     # the 67 master columns

# Roll calls (20th-22nd), plenary tallies and vetoes
votes = db.roll_calls(assembly=22, columns=["member_id", "bill_id", "vote", "party"])
tallies = db.vote_events(assembly=22)
vetoes = db.veto_events()

# Ideal points: "bridged" (default), "wnominate" or "dwnominate"
ip = db.ideal_points()                  # column ideal_point, positive = conservative

# Members and dated committee assignments
members = db.members(assembly=22)       # 321 member-terms
spells = db.committee_assignments(assembly=22)

# Committee process
meetings = db.committee_meetings(22)    # lowercase columns in every assembly
judiciary = db.judiciary_meetings(22)
subcommittee = db.subcommittee_reviews(assembly=22)
alternatives = db.alternative_absorption(assembly=22)

# Cosponsorship edges with roles 대표발의, 공동발의 and 찬성
edges = db.cosponsorship_edges(assembly=22)

# Texts, assets and the ID map
texts = db.bill_texts()
assets = db.assets(assembly=22)         # member-year wealth panel, thousands of won
idmap = db.legislator_map()

# 16th-19th rows parsed from minutes: not a roll-call matrix, see CODEBOOK.md
experimental = db.roll_calls_16_19_experimental()
```

Legislators are looked up by exact name and MONA_CD:

```python
from kna.queries import AmbiguousLegislator, get_legislator_profile

try:
    profile = get_legislator_profile(db, "김병욱", age=21)
except AmbiguousLegislator as e:
    print(e.candidates)                 # one row per MONA_CD
    profile = get_legislator_profile(db, "김병욱", age=21, mona="GFF1986K")
```

## R

```r
library(arrow)
library(dplyr)

master <- read_parquet("data/processed/master_bills_22.parquet")
laws <- master %>% filter(bill_kind == "법률안")

laws %>%
  group_by(ppsr_kind) %>%
  summarise(total = n(), enacted = sum(enacted), promulgated = sum(promulgated)) %>%
  mutate(rate = enacted / total * 100)
```

## Per-Assembly Breakdown

"Enacted law bills" are law bills whose final result is 원안가결 or 수정가결.
A vetoed bill counts only if it was passed again. The rate is enacted law
bills over law bills.

| Assembly | Bills, all kinds | Law bills | Enacted law bills | Promulgated laws | Enacted-law rate | Committee meeting rows |
|----------|------:|------:|------:|------:|-----:|------:|
| 17th (2004-08) | 8,368 | 7,489 | 1,913 | 1,913 | 25.5% | 24,156 |
| 18th (2008-12) | 14,762 | 13,913 | 2,353 | 2,353 | 16.9% | 105,229 |
| 19th (2012-16) | 18,735 | 17,822 | 2,793 | 2,793 | 15.7% | 150,192 |
| 20th (2016-20) | 24,996 | 24,141 | 3,195 | 3,195 | 13.2% | 202,335 |
| 21st (2020-24) | 26,707 | 25,858 | 2,959 | 2,959 | 11.4% | 199,384 |
| 22nd (2024-) | 21,581 | 21,022 | 1,644 | 1,555 | 7.8% | 137,152 |

The 22nd Assembly is in session, and 15,105 of its bills are pending.
Committee meeting rows count agenda steps, not meetings. The master's
`enacted` column counts every bill kind, including resolutions and budgets,
so filter on `bill_kind == "법률안"` for law counts.

## Data Structure

Every shipped table, in `data/processed/`. CODEBOOK.md documents each column.

| File | One row per | Rows | Content |
|---|---|---|---|
| `master_bills_{17..22}.parquet` | bill | 115,149 | 67 columns: identifiers, proposers, lifecycle dates, results, derived flags (`passed`, `enacted`, `promulgated`, `law_reflected`, `plenary_decided`, `expired_at_term_end`), veto columns, linked alternative and plenary tally |
| `master_bills_{17..21}_lite.parquet` | bill | 93,568 | The 36 legacy columns |
| `master_bills_22.sqlite` | | | The 22nd master and meeting tables in SQLite |
| `committee_meetings_{17..22}.parquet` | bill x meeting x agenda step | 818,448 | Committee meeting records (BILLJUDGECONF) |
| `judiciary_meetings_{17..22}.parquet` | bill x meeting | 15,858 | 법제사법위원회 review records (BILLLWJUDGECONF) |
| `subcommittee_reviews.parquet` | bill x subcommittee stage | 93,981 | Subcommittee referrals, reviews, direct referrals and 안건조정위원회 (TVBPMCONFINFO) |
| `alternative_absorption.parquet` | alternative x linked bill | 25,439 | Committee alternatives and the bills linked to them (TVBPMBILL11) |
| `cosponsorship_edges.parquet` | bill x member | 1,379,763 | Lead proposers, co-proposers and supporters, 17th-22nd, with party and its source |
| `veto_events.parquet` | vetoed bill | 47 | 재의요구 date, first passage, re-vote and final status |
| `vote_events.parquet` | plenary tally | 8,611 | Every tally of the 20th-22nd, typed as original, amendment or other |
| `roll_calls_all.parquet` | member x vote | 2,557,618 | Member-level votes, 20th-22nd, with party at election and the API's party label |
| `roll_calls_16_19_experimental.parquet` | parsed row | 41,281 | 16th-19th rows parsed from minutes, experimental and not a roll-call matrix |
| `ideal_points_bridged.csv` | legislator-term | 940 | Default series, comparable across assemblies |
| `ideal_points_wnominate.csv` | legislator-term | 940 | Per-assembly W-NOMINATE, one and two dimensions |
| `ideal_points_dwnominate.csv` | legislator-term | 940 | Pooled DW-NOMINATE, one position per legislator |
| `ideal_points_bridging_params.csv`, `ideal_points_manifest.json`, `ideal_points_sessioninfo.txt`, `dwnominate_fit.rds` | | | Bridging parameters, vintage manifest, R session and the fitted DW-NOMINATE object |
| `ideal_points_archive/v0.6.0_legacy/` | legislator-term | 936 | The ideal points shipped in 0.6.0 |
| `ideal_points_archive/v20260312_corrected/` | legislator-term | 939 | Corrected build on the 0.6.0 vote range |
| `members_{17..22}.parquet` | member-term | 1,948 | Party at election, current party, district, election type, seniority, committees |
| `committee_assignments.parquet` | committee spell | 13,616 | Dated committee assignments |
| `legislator_id_mapping.parquet` | legislator | 1,156 | MONA_CD, terms and coverage flags across tables |
| `bill_texts_linked.parquet` | bill | 60,925 | Propose-reason texts of 20th-22nd member law bills |
| `hearing_meetings_summary.parquet` | meeting | 16,829 | Meeting-level summary of the kr-hearings-data speech corpus, provisional |
| `assets_wealth_panel.parquet` | member-year | 2,928 | Asset disclosures, 19th-22nd |
| `reports/` | | | Validation reports written by the build |

`dw_ideal_points_20_22.csv`, deprecated since 2026-07-18, is no longer
distributed. Read `ideal_points_bridged.csv` instead.

## Documentation

| Resource | Link |
|----------|------|
| Codebook | [CODEBOOK.md](CODEBOOK.md) |
| Data availability and known limitations | [DATA_AVAILABILITY.md](DATA_AVAILABILITY.md) |
| Corrections | [CORRECTIONS.md](CORRECTIONS.md) |
| Interactive Explorer | [kyusik-yang.github.io/kna](https://kyusik-yang.github.io/kna/) |
| Ideology map | [kyusik-yang.github.io/kna/voteview.html](https://kyusik-yang.github.io/kna/voteview.html) |
| Tutorial | [kyusik-yang.github.io/assembly-tutorial](https://kyusik-yang.github.io/assembly-tutorial/) |

The tutorial was last updated in March 2026, before release 0.5.0. It reads
`dw_ideal_points_20_22.csv`, which 0.7.0 no longer ships, so use the three
ideal-point files described in CODEBOOK.md instead.

## Companion Data

kna is an offline master database for statistical analysis in Python and R. For real-time lookups and exploratory queries via Claude, use [open-assembly-mcp](https://github.com/kyusik-yang/open-assembly-mcp).

| Dataset | Description |
|---------|-------------|
| [kr-hearings-data](https://github.com/kyusik-yang/kr-hearings-data) | Speech-level records of committee and plenary meetings. kna's hearing summary and speech links use its version 9, which is being rebuilt |
| [korean-assembly-bills](https://github.com/kyusik-yang/korean-assembly-bills) | Source of the propose-reason texts in `bill_texts_linked.parquet` |
| [open-assembly-mcp](https://github.com/kyusik-yang/open-assembly-mcp) | MCP server for real-time API queries via Claude |
| [assembly-explorer](https://github.com/kyusik-yang/assembly-explorer) | Interactive Streamlit web app |

## Reproducing the Data

Every table in `data/processed/` can be rebuilt from `data/raw/` with the
scripts in this repository, except where the list after the commands below
says otherwise. `data/raw/members/party_overrides.csv` holds the six documented
corrections of party at election (CODEBOOK.md section 11). Collection needs
a free API key from [open.assembly.go.kr](https://open.assembly.go.kr).
Without a key the API still answers, but it returns a five-row sample for
every request, which is how the 0.6.0 committee meeting tables were
truncated. The collectors therefore refuse to run without `ASSEMBLY_API_KEY`,
and they check that every request returned as many rows as the API reports.

```bash
export ASSEMBLY_API_KEY=your_key

# 1. Collect raw data into data/raw (API calls; runs resume from data/raw/fetchlog)
python3 collect.py phase1 --ages 17-22                          # bill lists, tallies, review records
for age in 17 18 19 20 21 22; do python3 collect.py phase2 --age $age; done   # per-bill detail and meetings
python3 collect_roll_calls.py --age 22 --refresh                # member-level votes (all of 20-22 without --age)
python3 collect_members.py                                      # members and committee careers
python3 collect_structure.py all --ages 17-22                   # subcommittees, alternatives, proposer lists

# 2. Build the tables (no API calls)
./build_all.sh data/_build      # stage the new build and compare it with data/processed
./build_all.sh                  # or write data/processed directly

# 3. Ideal-point archive (not part of build_all.sh). Run it after data/processed holds the new build.
A=data/processed/ideal_points_archive
mkdir -p $A/v0.6.0_legacy                  # the files of release 0.6.0, commit 4e28c1e
for f in ideal_points_wnominate.csv ideal_points_bridged.csv ideal_points_dwnominate.csv \
         ideal_points_bridging_params.csv ideal_points_sessioninfo.txt dwnominate_fit.rds; do
  git show 4e28c1e:data/processed/$f > $A/v0.6.0_legacy/$f
done
Rscript build_ideal_points.R --input data/processed/roll_calls_all.parquet \
  --members-dir data/processed --out $A/v20260312_corrected --cutoff 20260312
```

`build_all.sh` runs `collect_members.py --build-only`, `integrate.py`,
`consolidate_votes.py`, `build_ideal_points.R`, `build_structure.py` and
`link_external.py`, and writes validation reports to `reports/`. It makes no
API calls. A few inputs come from outside `data/raw/`, and a few files are not
rebuilt by it:

- `build_ideal_points.R` needs R with `arrow`, `dplyr`, `tidyr`, `pscl`,
  `wnominate`, `jsonlite` and `digest`, and the `dwnominate` package from
  GitHub, which is not on CRAN. The 0.7.0 build used commit
  `fd39e6a85ada1ba491030ac14a1b0f3c1fefb736`:
  `remotes::install_github("wmay/dwnominate@fd39e6a85ada1ba491030ac14a1b0f3c1fefb736")`.
- `link_external.py texts` reads the bill texts of the korean-assembly-bills
  dataset from `KNA_ASSEMBLY_BILLS_DIR`, which defaults to
  `../korean-assembly-bills/data`, a checkout next to this repository.
  `build_all.sh` stops if they are missing, and
  `python3 link_external.py texts --allow-missing` skips them.
- `link_external.py idmap` reads an external legislator table from
  `KNA_WITNESSES_DIR` for one coverage flag of the ID map. The variable has no
  default. `build_all.sh` runs this step with `--allow-missing`, so the flag is
  null when the variable is not set.
- Speech links read `KNA_HEARINGS_DIR`, which defaults to
  `../kr-hearings-data/data`. They are not rebuilt while kr-hearings-data is
  being replaced. `parse_plenary_votes.py` and `extract_appendix_votes.py`,
  the parsers behind the 16th-19th experimental vote rows, read the speech
  corpus from the same variable, with the same default.
- `build_structure.py` keeps the edges of the earlier edge file for the bills
  it had not truncated, `source` = `legacy_edges`, and reads them from
  `data/processed/cosponsorship_edges.parquet`. A rebuild from the 0.7.0 file
  reads back the same rows.
- The 16th-19th experimental vote rows are copied from the previous release
  by `consolidate_votes.py`, because the name matching that produced their
  member IDs cannot be reproduced.
- `hearing_meetings_summary.parquet` and `assets_wealth_panel.parquet` are
  not rebuilt. They are carried over unchanged from 0.6.0.
- `ideal_points_archive/` is produced by step 3. `v0.6.0_legacy/` is a copy
  of the six ideal-point files of release 0.6.0, and `v20260312_corrected/`
  is `build_ideal_points.R` run on the 0.7.0 roll calls and members with
  votes up to 2026-03-12, the vote range of 0.6.0.

To check a data directory, run the test suite against it:

```bash
pip install -e '.[test]'
KBL_DATA=data/processed python3 -m pytest tests
```

Some tests also read the raw inputs in `data/raw/`, or in `KNA_RAW_DIR` when
it is set. `tests/test_regressions.py` checks the birth calendar against the
rosters, that every committee alternative was queried, and that the party
overrides reach the members, roll calls and ideal points. A test is skipped
when its raw file is missing, for example the fetch logs in
`data/raw/fetchlog/`, which are not in the repository.

The interactive site is rebuilt separately with `python3 build_site.py` and
`python3 build_voteview.py`.

## License

The code is released under the MIT License, see [LICENSE](LICENSE).

The bill, committee, vote and member data are compiled from public
records of the National Assembly published through the Open Assembly API
(열린국회정보, [open.assembly.go.kr](https://open.assembly.go.kr)). Check the
portal's terms of use before redistributing them.

`assets_wealth_panel.parquet` is derived from the asset disclosure data of
[OpenWatch](https://docs.openwatch.kr/). The OpenWatch documentation states
that its data may be used under the Creative Commons
Attribution-ShareAlike 4.0 International license, CC BY-SA 4.0 (checked on
2026-09-26). If you use or redistribute this file or a work derived from it,
credit OpenWatch as the source and share the derived data under the same
license.
