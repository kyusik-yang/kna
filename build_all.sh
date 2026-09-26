#!/usr/bin/env bash
# Rebuild every derived table from data/raw, with no API calls.
#
# Usage:
#   ./build_all.sh              # write to data/processed
#   ./build_all.sh data/_build  # write to a staging directory first
#
# Collection (API calls) is separate:
#   python3 collect.py phase1 --ages 17-22
#   python3 collect.py phase2 --age 22            (and --ids-file for re-fetches)
#   python3 collect_roll_calls.py --age 22 --refresh
#   python3 collect_members.py
#   python3 collect_structure.py all --ages 17-22
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-data/processed}"
mkdir -p "$OUT/reports"

python3 collect_members.py --build-only --out "$OUT"
python3 integrate.py --ages 17-22 --out "$OUT" --compare data/processed
python3 consolidate_votes.py --out "$OUT" --members-dir "$OUT"
Rscript build_ideal_points.R --input "$OUT/roll_calls_all.parquet" \
  --members-dir "$OUT" --out "$OUT"
python3 build_structure.py all --out "$OUT" --members-dir "$OUT" \
  --master-dir "$OUT" --report-dir "$OUT/reports"
# Bill texts come from the korean-assembly-bills repo (KNA_ASSEMBLY_BILLS_DIR).
# Speech links are not rebuilt: kr-hearings-data v9 is being replaced.
python3 link_external.py texts --out "$OUT" --in-dir "$OUT"
# KNA_WITNESSES_DIR (member-metadata flag) is optional; without it the flag is skipped.
python3 link_external.py idmap --out "$OUT" --in-dir "$OUT" --members-dir "$OUT" --allow-missing
echo "build_all: done -> $OUT"
