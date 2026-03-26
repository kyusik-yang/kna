# kna - Korean National Assembly CLI

[![PyPI](https://img.shields.io/pypi/v/kna)](https://pypi.org/project/kna/)

Comprehensive CLI and master database for the Korean National Assembly.
Integrates 8 Open Assembly API endpoints into a single queryable interface
covering six assembly terms (17th-22nd, 2004-2026).

```bash
pip install kna
```

> If you see a PATH warning after install, either run `pipx install kna` instead, or add the displayed directory to your shell PATH.

**[Interactive Explorer](https://kyusik-yang.github.io/korean-bill-lifecycle/)** | **[Uijeong Jido 의정지도](https://kyusik-yang.github.io/korean-bill-lifecycle/voteview.html)** | **[Tutorial](https://kyusik-yang.github.io/assembly-tutorial/)** | **[PyPI](https://pypi.org/project/kna/)**

## Key Statistics

| | |
|---|---|
| **Total Bills** | 110,778 (17-22nd, full lifecycle) |
| **Roll Call Votes** | 2,425,113 member-level records |
| **DW-NOMINATE** | 936 legislator-terms (20-22nd, cross-assembly aligned) |
| **Committee Meetings** | 572,127 records |
| **Bill Texts** | 60,925 propose-reason texts (20-22nd) |
| **Date Range** | 2004 - 2026 |

## CLI Usage

```bash
# Database overview
kna info

# Search bills by title
kna search "인공지능" --age 22 --status enacted

# Full-text search in propose-reason texts
kna text "기후변화" --age 22

# Bill lifecycle timeline (proposal → promulgation)
kna show 2217673

# Legislator profile with DW-NOMINATE ideal point
kna legislator 이재명 --age 22

# Legislative funnel
kna stats funnel --age 22

# Passage rate trend across assemblies
kna stats passage-rate

# Export to CSV or Parquet
kna export health.csv --age 22 --committee 보건복지 --status enacted
```

## Python API

```python
from kna.data import BillDB

db = BillDB()

# Load bills (with column pruning)
bills = db.bills(age=22, columns=["bill_id", "bill_nm", "status", "ppsl_dt"])

# Ideal points (sign-flipped: negative = liberal, positive = conservative)
ip = db.ideal_points()

# Roll call votes
votes = db.roll_calls(age=22)

# Bill texts
texts = db.bill_texts()
```

## R

```r
library(arrow)
library(dplyr)

master <- read_parquet("data/processed/master_bills_22.parquet")
laws <- master %>% filter(bill_kind == "법률안")

laws %>%
  group_by(ppsr_kind) %>%
  summarise(total = n(), enacted = sum(enacted)) %>%
  mutate(rate = enacted / total * 100)
```

## Per-Assembly Breakdown

| Assembly | Bills | Enacted | Rate | Committee Mtgs |
|----------|------:|--------:|-----:|---------------:|
| 17th (2004-08) | 8,369 | 2,547 | 30.4% | 20,044 |
| 18th (2008-12) | 14,762 | 2,930 | 19.8% | 57,003 |
| 19th (2012-16) | 18,735 | 3,414 | 18.2% | 78,115 |
| 20th (2016-20) | 24,996 | 3,795 | 15.2% | 107,933 |
| 21st (2020-24) | 26,711 | 3,554 | 13.3% | 200,283 |
| 22nd (2024-) | 17,205 | 1,399 | 8.1% | 108,749 |

## Data Structure

```
master_bills (1 row = 1 bill, up to 55 columns)
├── Identifiers: bill_id, bill_no, age, bill_kind, bill_nm
├── Proposer: ppsr_kind, rst_proposer, rst_mona_cd, publ_mona_cd
├── Lifecycle: ppsl_dt → committee_dt → cmt_proc_dt → law_proc_dt → rgs_rsln_dt → prom_dt
├── Results: status, passed, enacted, proc_rslt
├── Votes: vote_yes, vote_no, vote_abstain
└── Derived: days_to_proc, days_to_committee

roll_calls_all (2.4M rows, member-level)
└── term, member_name, member_id, party, vote, bill_id, date

dw_ideal_points_20_22 (936 rows)
└── member_id, member_name, term, party, aligned, party_bloc

bill_texts_linked (60K rows)
└── BILL_ID, propose_reason, scrape_status
```

## Documentation

| Resource | Link |
|----------|------|
| Tutorial | [kyusik-yang.github.io/assembly-tutorial](https://kyusik-yang.github.io/assembly-tutorial/) |
| Codebook | [CODEBOOK.md](CODEBOOK.md) |
| Data Availability | [DATA_AVAILABILITY.md](DATA_AVAILABILITY.md) |
| Interactive Explorer | [kyusik-yang.github.io/korean-bill-lifecycle](https://kyusik-yang.github.io/korean-bill-lifecycle/) |
| Ideology Map | [Uijeong Jido 의정지도](https://kyusik-yang.github.io/korean-bill-lifecycle/voteview.html) |

## Companion Data

| Dataset | Description |
|---------|-------------|
| [kr-hearings-data](https://github.com/kyusik-yang/kr-hearings-data) | 9.9M speech-level records from 16,830 hearings (2000-2025) |
| [open-assembly-mcp](https://github.com/kyusik-yang/open-assembly-mcp) | MCP server for real-time API queries via Claude |
| [assembly-explorer](https://github.com/kyusik-yang/assembly-explorer) | Interactive Streamlit web app |

## Reproducing the Data

Data files are large and not included in the repo. To regenerate:

```bash
# Set API key (free from https://open.assembly.go.kr)
export ASSEMBLY_API_KEY=your_key

# Collect and build
python3 collect.py phase1 && python3 collect.py phase2
python3 integrate.py
python3 build_multi_assembly.py lite && python3 build_multi_assembly.py batch

# Roll call votes
python3 collect_roll_calls.py && python3 consolidate_votes.py

# Rebuild interactive site
python3 build_site.py && python3 build_voteview.py
```

## License

Data sourced from public government APIs. Code is MIT licensed.
