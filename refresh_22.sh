#!/usr/bin/env bash
# Refresh the ongoing 22nd Assembly from the Open Assembly API into a staging
# directory, rebuild every table there and run the test suite.
# Nothing is promoted to data/processed and nothing is committed or pushed.
#
# Usage:
#   ASSEMBLY_API_KEY=... ./refresh_22.sh [OUT_DIR]     (default data/_build)
#
# Takes about 4 hours (about 50,000 per-bill calls). The report is written to
# logs/refresh_<date>.md. Promote after reviewing it:
#   rsync -a data/_build/ data/processed/   (then regenerate docs and release)
set -euo pipefail
cd "$(dirname "$0")"
: "${ASSEMBLY_API_KEY:?ASSEMBLY_API_KEY is not set}"
OUT="${1:-data/_build}"
STAMP=$(date +%Y-%m-%d)
REPORT="logs/refresh_${STAMP}.md"
mkdir -p logs "$OUT"
export KNA_API_RATE="${KNA_API_RATE:-4}"

python3 collect_members.py --out "$OUT"
python3 collect.py phase1 --age 22
python3 collect.py phase2 --age 22 --refresh
python3 collect_roll_calls.py --age 22 --refresh
python3 collect_votes_likms.py --members-dir "$OUT"   # members the member-level API omits
python3 collect_structure.py subcommittee --ages 22
python3 collect_structure.py proposers --ages 22
python3 collect_structure.py alternatives --ages 22
if python3 collect_structure.py --help 2>/dev/null | grep -q summaries; then
  python3 collect_structure.py summaries --ages 22
fi
./build_all.sh "$OUT"

TESTS=$(KBL_DATA="$PWD/$OUT" python3 -m pytest -q tests 2>&1 | tail -1)
python3 - "$OUT" "$REPORT" "$TESTS" <<'PY'
import sys, pandas as pd
out, report, tests = sys.argv[1:]
rows = []
for name in ["master_bills_22.parquet", "members_22.parquet", "roll_calls_all.parquet",
             "committee_meetings_22.parquet", "cosponsorship_edges.parquet"]:
    old = len(pd.read_parquet(f"data/processed/{name}"))
    new = len(pd.read_parquet(f"{out}/{name}"))
    rows.append(f"| {name} | {old:,} | {new:,} | {new - old:+,} |")
with open(report, "w", encoding="utf-8") as f:
    f.write(f"# 22nd Assembly refresh into {out}\n\nTests: {tests}\n\n")
    f.write("| File | data/processed | refreshed | change |\n|---|---|---|---|\n")
    f.write("\n".join(rows) + "\n")
print(open(report, encoding="utf-8").read())
PY
