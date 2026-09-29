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
#   python3 collect_structure.py summaries --ages 17-22   (BPMBILLSUMMARY texts, not in "all")
#   python3 collect_minutes_votes.py all --ages 17-19   (17th-19th roll calls from the minutes
#     PDFs. integrate.py and consolidate_votes.py read the data/raw tables it writes.)
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
# Bill texts: the LIKMS scrape of the korean-assembly-bills repo (KNA_ASSEMBLY_BILLS_DIR)
# plus data/raw/BPMBILLSUMMARY_{age}. Reports go to $OUT/reports/bill_texts_*.csv.
python3 link_external.py texts --out "$OUT" --in-dir "$OUT" --report-dir "$OUT/reports"
# KNA_WITNESSES_DIR (member-metadata flag) is optional; without it the flag is skipped.
python3 link_external.py idmap --out "$OUT" --in-dir "$OUT" --members-dir "$OUT" --allow-missing
# Asset panel: rebuilt only when KNA_ASSETS_DIR points to the OpenWatch files and
# the 국회공보 PDFs (build_assets.py fetch) and pdfplumber is installed. Otherwise
# the shipped panel is carried over unchanged.
if [[ -n "${KNA_ASSETS_DIR:-}" ]]; then
  python3 build_assets.py build --out "$OUT" --members-dir "$OUT" --compare data/processed
elif [[ "$OUT" != "data/processed" ]]; then
  cp data/processed/assets_wealth_panel.parquet "$OUT/" && echo "build_all: asset panel carried over (KNA_ASSETS_DIR not set)"
fi
# Hearing summary: rebuilt from kr-hearings-data v10 when KNA_HEARINGS_V10_DIR points
# to a v10 build or to a directory of v10 release assets (build_hearings_summary.py).
# Otherwise the shipped file is carried over.
if [[ -n "${KNA_HEARINGS_V10_DIR:-}" ]]; then
  if [[ "$OUT" != "data/processed" ]]; then
    python3 build_hearings_summary.py --source v10 --out "$OUT" \
      --compare data/processed/hearing_meetings_summary.parquet
  else
    python3 build_hearings_summary.py --source v10 --out "$OUT"
  fi
elif [[ "$OUT" != "data/processed" && -f data/processed/hearing_meetings_summary.parquet ]]; then
  cp data/processed/hearing_meetings_summary.parquet "$OUT/" && echo "build_all: hearing summary carried over (KNA_HEARINGS_V10_DIR not set)"
fi
echo "build_all: done -> $OUT"
