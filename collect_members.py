"""Collect member metadata from ALLNAMEMBER endpoint for all assemblies.

Usage:
    python3 collect_members.py                  # All assemblies (17-22)
    python3 collect_members.py --assembly 22    # Single assembly

Output: data/processed/members_{age}.parquet (one file per assembly)
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path

import httpx
import pandas as pd

BASE_URL = "https://open.assembly.go.kr/portal/openapi"
EP_ALLNAME = "ALLNAMEMBER"

AGE_LABEL = {str(i): f"제{i}대" for i in range(1, 30)}

SLASH_FIELDS = {
    "PLPT_NM": "party",
    "ELECD_NM": "district",
    "ELECD_DIV_NM": "election_type",
    "BLNG_CMIT_NM": "committee",
}


def get_api_key() -> str:
    key = os.getenv("ASSEMBLY_API_KEY")
    if not key:
        print("Error: ASSEMBLY_API_KEY not set")
        sys.exit(1)
    return key


def fetch_all_members(api_key: str) -> list[dict]:
    """Fetch all rows from ALLNAMEMBER (paginated)."""
    all_rows = []
    page = 1
    while True:
        params = {
            "KEY": api_key,
            "Type": "json",
            "pIndex": page,
            "pSize": 100,
        }
        r = httpx.get(f"{BASE_URL}/{EP_ALLNAME}", params=params, timeout=30)
        body = r.json()

        data = body.get(EP_ALLNAME, [])
        if not data or len(data) < 2:
            break
        head = data[0].get("head", [])
        if len(head) < 2:
            break
        code = head[1]["RESULT"]["CODE"]
        if code == "INFO-200":
            break
        if code != "INFO-000":
            print(f"  API error: {code} - {head[1]['RESULT']['MESSAGE']}")
            break
        total = head[0].get("list_total_count", 0)
        rows = data[1].get("row", [])
        if isinstance(rows, dict):
            rows = [rows]
        all_rows.extend(rows)
        print(f"  Page {page}: {len(all_rows)}/{total}")
        if len(all_rows) >= total:
            break
        page += 1
        time.sleep(0.3)

    return all_rows


def parse_for_assembly(rows: list[dict], age: int) -> list[dict]:
    """Parse ALLNAMEMBER rows, extract per-assembly data."""
    label = AGE_LABEL[str(age)]
    result = []

    for r in rows:
        era_str = r.get("GTELT_ERACO") or ""
        eras = [e.strip() for e in era_str.split(", ") if e.strip()]
        if label not in eras:
            continue
        idx = eras.index(label)
        n_eras = len(eras)

        rec = {
            "mona_cd": r.get("NAAS_CD") or "",
            "member_name": r.get("NAAS_NM") or "",
            "member_name_hanja": r.get("NAAS_CH_NM") or "",
            "member_name_eng": r.get("NAAS_EN_NM") or "",
            "sex": r.get("NTR_DIV") or "",
            "birth_date": r.get("BIRDY_DT") or "",
            "reelection": r.get("RLCT_DIV_NM") or "",
            "email": r.get("NAAS_EMAIL_ADDR") or "",
            "homepage": r.get("NAAS_HP_URL") or "",
            "photo_url": r.get("NAAS_PIC") or "",
            "age": age,
        }

        for src, dst in SLASH_FIELDS.items():
            val = r.get(src) or ""
            parts = val.split("/")
            if len(parts) == n_eras:
                rec[dst] = parts[idx].strip()
            elif len(parts) == 1:
                rec[dst] = parts[0].strip()
            else:
                rec[dst] = parts[min(idx, len(parts) - 1)].strip() if parts else ""

        result.append(rec)

    return result


def main():
    parser = argparse.ArgumentParser(description="Collect member metadata")
    parser.add_argument("--assembly", type=int, help="Single assembly (default: all 17-22)")
    args = parser.parse_args()

    api_key = get_api_key()
    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)

    assemblies = [args.assembly] if args.assembly else list(range(17, 23))

    print("Fetching all members from ALLNAMEMBER...")
    raw_rows = fetch_all_members(api_key)
    print(f"Total raw rows: {len(raw_rows)}")

    for age in assemblies:
        parsed = parse_for_assembly(raw_rows, age)
        if not parsed:
            print(f"  {age}th Assembly: no members found")
            continue

        df = pd.DataFrame(parsed)
        # Sort by party then name
        df = df.sort_values(["party", "member_name"]).reset_index(drop=True)

        out_path = out_dir / f"members_{age}.parquet"
        df.to_parquet(out_path, index=False)
        print(f"  {age}th Assembly: {len(df)} members -> {out_path}")

    print("Done.")


if __name__ == "__main__":
    main()
