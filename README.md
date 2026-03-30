# kna - Korean National Assembly CLI

[![PyPI](https://img.shields.io/pypi/v/kna)](https://pypi.org/project/kna/)

Comprehensive CLI and master database for the Korean National Assembly.
Integrates 8 Open Assembly API endpoints into a single queryable interface
covering six assembly terms (17th-22nd, 2004-2026).

## Installation

### Step 1: Install the CLI

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

Or use `pipx install kna` which handles PATH automatically.

### Step 2: Get the data

The CLI needs the parquet data files. The repository uses **Git LFS** for large files.

```bash
# Install Git LFS first (required, one-time)
brew install git-lfs    # macOS
# or: sudo apt install git-lfs    # Ubuntu/Debian

git lfs install         # one-time setup

# Clone with data
git clone https://github.com/kyusik-yang/kna.git
cd kna
```

If you already cloned without LFS, the parquet files will be tiny pointer files and `kna info` will fail. Fix it:

```bash
cd kna
git lfs install
git lfs pull            # downloads actual data files (~500MB)
```

### Step 3: Point the CLI to the data

```bash
# Set the environment variable
export KBL_DATA=~/kna/data/processed

# Make it permanent
echo 'export KBL_DATA="$HOME/kna/data/processed"' >> ~/.zshrc
source ~/.zshrc

# Verify
kna info
```

### Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `kna: command not found` | pip bin dir not in PATH | Add pip's bin directory to `~/.zshrc` PATH (see Step 1) |
| `ArrowInvalid: Parquet magic bytes not found` | Git LFS not installed; parquet files are pointer files | `brew install git-lfs && git lfs install && git lfs pull` |
| `Cannot find data directory` | KBL_DATA not set and not running from repo root | `export KBL_DATA=~/kna/data/processed` |
| `No master file for Nth assembly` | Data files missing for that assembly | Check `ls $KBL_DATA/master_bills_*.parquet` |
| `ERROR: requires Python >=3.9` | Python too old | `python3 --version` - need 3.9+ |
| `ModuleNotFoundError: No module named 'kna'` | Installed to wrong Python | `pip3 install --user kna` or use the same `python3 -m pip install kna` |

### Requirements

- Python 3.9+
- Git LFS (for data files)
- ~500MB disk space (data files)

**[Interactive Explorer](https://kyusik-yang.github.io/kna/)** | **[Uijeong Jido 의정지도](https://kyusik-yang.github.io/kna/voteview.html)** | **[Tutorial](https://kyusik-yang.github.io/assembly-tutorial/)** | **[PyPI](https://pypi.org/project/kna/)**

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
| 20th (2016-20) | 24,996 | 3,794 | 15.2% | 107,933 |
| 21st (2020-24) | 26,711 | 3,554 | 13.3% | 200,283 |
| 22nd (2024-) | 17,205 | 1,399 | 8.1% | 108,749 |

## Data Structure

```
master_bills (1 row = 1 bill, 49-55 columns)
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
| Interactive Explorer | [kyusik-yang.github.io/kna](https://kyusik-yang.github.io/kna/) |
| Ideology Map | [Uijeong Jido 의정지도](https://kyusik-yang.github.io/kna/voteview.html) |

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
