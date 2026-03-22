# Korean Bill Lifecycle Database

대한민국 국회 법안의 전 생애주기를 추적하는 마스터 데이터베이스.

열린국회정보 Open API 8종을 BILL_ID 기준으로 결합하여, 17대(2004)부터 22대(2024-)까지 약 111,000건의 법안에 대한 발의-심사-표결-공포 과정을 단일 테이블로 제공합니다.

**[Interactive Explorer](https://kyusik-yang.github.io/korean-bill-lifecycle/)** | [Codebook](CODEBOOK.md) | [Data Availability](DATA_AVAILABILITY.md)

## Key Statistics

| | |
|---|---|
| **Total Bills** | 111,778 (17-22대) |
| **Full Master (22대)** | 17,205 bills, 54 variables |
| **Lite Masters (17-21대)** | 93,573 bills, 36 variables |
| **Committee Meetings** | 108,749 records (22대) |
| **Date Range** | 2004 - 2026 |

## Data Structure

```
master_bills (1 row = 1 bill)
├── Identifiers: bill_id, bill_no, age, bill_kind, bill_nm
├── Proposer: ppsr_kind, rst_proposer, rst_mona_cd, publ_mona_cd
├── Lifecycle: ppsl_dt → committee_dt → cmt_proc_dt → law_proc_dt → rgs_rsln_dt → prom_dt
├── Results: status, passed, enacted, proc_rslt
├── Votes: vote_yes, vote_no, vote_abstain
└── Derived: days_to_proc, days_to_committee

committee_meetings (1:N per bill)
└── bill_id, conf_name, conf_dt, conf_result

judiciary_meetings (1:N per bill)
└── bill_id, conf_name, conf_dt, conf_result
```

## Quick Start

### Python

```python
import pandas as pd

master = pd.read_parquet("data/processed/master_bills_22.parquet")
laws = master[master["bill_kind"] == "법률안"]

# Passage rate by proposer type
laws.groupby("ppsr_kind").agg(
    total=("bill_id", "count"),
    enacted=("enacted", "sum"),
).assign(rate=lambda x: x["enacted"] / x["total"] * 100)
```

### R

```r
library(arrow)
library(dplyr)

master <- read_parquet("data/processed/master_bills_22.parquet")
laws <- master |> filter(bill_kind == "법률안")

laws |>
  group_by(ppsr_kind) |>
  summarise(total = n(), enacted = sum(enacted)) |>
  mutate(rate = enacted / total * 100)
```

## Reproducing the Data

Data files are not included in the repo (too large). To regenerate:

```bash
# 1. Set up
pip install pandas requests pyarrow plotly

# 2. Collect 22nd Assembly (Phase 1: ~10 min, Phase 2: ~15 hours)
python3 collect.py phase1
python3 collect.py phase2

# 3. Build master DB
python3 integrate.py

# 4. Build 17-21대 lite masters (uses existing BILLRCP/BILLJUDGE + external data)
python3 build_multi_assembly.py lite

# 5. Collect remaining batch data for 17-21대
python3 build_multi_assembly.py batch

# 6. Phase 2 for older assemblies (sequential, ~39 hours total)
python3 build_multi_assembly.py phase2 --age 21
python3 build_multi_assembly.py phase2 --age 20
# ... etc

# 7. Rebuild interactive site
python3 build_site.py
```

**API Key**: Obtain from [열린국회정보](https://open.assembly.go.kr/) and set in `collect.py`.

## Documentation

| File | Description |
|------|-------------|
| [CODEBOOK.md](CODEBOOK.md) | Variable-level documentation (54 variables) |
| [DATA_OVERVIEW.md](DATA_OVERVIEW.md) | Summary statistics and visualizations |
| [DATA_AVAILABILITY.md](DATA_AVAILABILITY.md) | Per-assembly data coverage and limitations |
| [DATA_COLLECTION_STRATEGY.md](DATA_COLLECTION_STRATEGY.md) | Original API exploration notes |
| [MASTER_DATA_PLAN.md](MASTER_DATA_PLAN.md) | Expansion roadmap and cross-project integration |

## Project Structure

```
korean-bill-lifecycle/
├── collect.py                  # Phase 1+2 API collection
├── integrate.py                # Phase 3 data integration
├── build_multi_assembly.py     # Multi-assembly expansion
├── build_site.py               # Interactive site generator
├── tutorial.ipynb              # Jupyter tutorial notebook
├── site/index.html             # Interactive explorer (GitHub Pages)
├── data/
│   ├── raw/                    # API responses (parquet)
│   └── processed/              # Master tables (parquet + sqlite)
└── docs/                       # Documentation (*.md)
```

## Data Source

[열린국회정보 Open API](https://open.assembly.go.kr/) (open.assembly.go.kr)

## License

Data sourced from public government APIs. Code is MIT licensed.
