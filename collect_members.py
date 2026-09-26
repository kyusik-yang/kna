"""Collect member metadata for all assemblies (17-22).

Usage:
    python3 collect_members.py                  # Fetch raw + build all assemblies
    python3 collect_members.py --assembly 22    # Build a single assembly
    python3 collect_members.py --build-only     # Rebuild from the raw snapshots
    python3 collect_members.py --out DIR        # Write members_{age} to DIR

Sources (raw snapshots are kept in data/raw/members/):
    ALLNAMEMBER        all members ever; per-era party (at election) and district
                       as '/'-separated lists aligned with GTELT_ERACO
    npffdutiapkzbfyvr  역대 국회의원 현황, one call per assembly (UNIT_CD 1000{age});
                       the district and election type of that term. Its party
                       field is not used: it is the departure party for members
                       who left after that term but the election party for
                       members who continued, so it means different things.
    nwvrqwxyaytdsfvhu  currently serving members (22nd), current party
    nqbeopthavwwfbekw  위원회 경력 of former members, per assembly (dated spells)
    nyzrglyvagmrypezq  위원회 경력 of current members, all assemblies (dated spells)

Output: members_{age}.parquet (one file per assembly) and
committee_assignments.parquet (one row per member, assembly, committee spell).
"""

import argparse
import re
import time
from pathlib import Path

import pandas as pd

import kna_api

REPO = Path(__file__).parent
RAW_MEMBERS = REPO / "data" / "raw" / "members"
DEFAULT_OUT = REPO / "data" / "processed"
ASSEMBLIES = list(range(17, 23))

AIDE_COLUMNS = ["AIDE_NM", "CHF_SCRT_NM", "SCRT_NM", "STAFF", "SECRETARY", "SECRETARY2"]

SLASH_FIELDS = {
    "PLPT_NM": "party",
    "ELECD_NM": "district",
    "ELECD_DIV_NM": "election_type",
    "BLNG_CMIT_NM": "committee",
}


def era_list(s) -> list[int]:
    """'제17대, 제17대, 제18대' -> [17, 17, 18] (order kept, duplicates kept)."""
    return [int(x) for x in re.findall(r"제(\d+)대", s or "")]


def seniority_label(n: int) -> str:
    return "초선" if n == 1 else "재선" if n == 2 else f"{n}선"


# ── Fetch ──────────────────────────────────────────────────────────────────

def fetch_raw():
    RAW_MEMBERS.mkdir(parents=True, exist_ok=True)
    snap = time.strftime("%Y-%m-%d")

    def save(rows, name):
        # Names of legislators' aides are third-party personal data that no
        # build step uses, so they are not kept in the raw snapshots.
        df = pd.DataFrame(rows).drop(columns=AIDE_COLUMNS, errors="ignore")
        df["snapshot_date"] = snap
        kna_api.write_parquet_atomic(df, RAW_MEMBERS / f"{name}.parquet")
        print(f"  {name}: {len(df):,} rows")

    print("Fetching member sources...")
    save(kna_api.fetch("ALLNAMEMBER"), "ALLNAMEMBER")
    for age in ASSEMBLIES:
        save(kna_api.fetch("npffdutiapkzbfyvr", {"UNIT_CD": f"1000{age}"}),
             f"npffdutiapkzbfyvr_{age}")
        save(kna_api.fetch("nqbeopthavwwfbekw", {"PROFILE_UNIT_CD": f"1000{age}"}),
             f"nqbeopthavwwfbekw_{age}")
    save(kna_api.fetch("nwvrqwxyaytdsfvhu"), "nwvrqwxyaytdsfvhu")
    save(kna_api.fetch("nyzrglyvagmrypezq"), "nyzrglyvagmrypezq")


# ── Build ──────────────────────────────────────────────────────────────────

def build_committee_assignments() -> pd.DataFrame:
    """Dated committee spells, one row per (member, assembly, committee, start)."""
    frames = [pd.read_parquet(p) for p in sorted(RAW_MEMBERS.glob("nqbeopthavwwfbekw_*.parquet"))]
    frames.append(pd.read_parquet(RAW_MEMBERS / "nyzrglyvagmrypezq.parquet"))
    raw = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame({
        "mona_cd": raw["MONA_CD"],
        "member_name": raw["HG_NM"],
        "assembly": pd.to_numeric(raw["PROFILE_UNIT_CD"].astype(str).str[-2:], errors="coerce"),
        "committee": raw["PROFILE_SJ"].str.replace(r"^제\d+대\s*", "", regex=True).str.strip(),
        "frto_date": raw["FRTO_DATE"].fillna("").str.strip(),
    })
    parts = out["frto_date"].str.split("~", n=1, expand=True)
    out["start_date"] = pd.to_datetime(parts[0].str.strip(), format="%Y.%m.%d", errors="coerce")
    out["end_date"] = pd.to_datetime(parts[1].fillna("").str.strip(), format="%Y.%m.%d", errors="coerce")
    out["is_current"] = parts[1].fillna("").str.strip().eq("")
    out = (out.drop_duplicates(["mona_cd", "assembly", "committee", "start_date", "end_date"])
              .sort_values(["assembly", "mona_cd", "start_date", "committee"])
              .reset_index(drop=True))
    return out[["mona_cd", "member_name", "assembly", "committee",
                "start_date", "end_date", "is_current", "frto_date"]]


def parse_for_assembly(allname: pd.DataFrame, age: int) -> pd.DataFrame:
    """Per-assembly fields from ALLNAMEMBER, with explicit parse flags."""
    recs = []
    for r in allname.to_dict("records"):
        eras = era_list(r.get("GTELT_ERACO"))
        if age not in eras:
            continue
        uniq = list(dict.fromkeys(eras))
        rec = {
            "mona_cd": r.get("NAAS_CD") or "",
            "member_name": r.get("NAAS_NM") or "",
            "member_name_hanja": r.get("NAAS_CH_NM") or "",
            "member_name_eng": r.get("NAAS_EN_NM") or "",
            "sex": r.get("NTR_DIV") or "",
            "birth_date": r.get("BIRDY_DT") or "",
            # BIRDY_DIV_CD is coded the opposite way from the roster endpoints
            # (양 where they say 음 and vice versa), so it is only a fallback.
            "birth_calendar": {"양": "음", "음": "양"}.get(r.get("BIRDY_DIV_CD") or "", ""),
            "reelection": r.get("RLCT_DIV_NM") or "",
            "term_number": uniq.index(age) + 1,
            "email": r.get("NAAS_EMAIL_ADDR") or "",
            "homepage": r.get("NAAS_HP_URL") or "",
            "photo_url": r.get("NAAS_PIC") or "",
            "age": age,
        }
        idx = eras.index(age)
        for src, dst in SLASH_FIELDS.items():
            parts = [p.strip() for p in (r.get(src) or "").split("/")]
            if len(parts) == len(eras):
                rec[dst] = parts[idx]
            elif len(eras) == 1 and len(parts) == 1:
                rec[dst] = parts[0]
            else:
                # Misaligned list: the position of this era is unknown
                rec[dst] = None
            rec[f"_{dst}_aligned"] = rec[dst] is not None
        recs.append(rec)
    return pd.DataFrame(recs)


def build_members(age: int, allname: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    base = parse_for_assembly(allname, age)
    snap = allname["snapshot_date"].iloc[0]

    # Official per-assembly roster: district and election type of the term
    roster = pd.read_parquet(RAW_MEMBERS / f"npffdutiapkzbfyvr_{age}.parquet")
    roster = roster.drop_duplicates("MONA_CD").set_index("MONA_CD")
    in_roster = base["mona_cd"].isin(roster.index)
    for col, src in [("district", "ORIG_NM"), ("election_type", "ELECT_GBN_NM")]:
        official = base["mona_cd"].map(roster[src])
        base[col] = official.where(in_roster & official.notna(), base[col])

    # Currently serving members (only meaningful for the ongoing assembly)
    current = pd.read_parquet(RAW_MEMBERS / "nwvrqwxyaytdsfvhu.parquet").set_index("MONA_CD")
    if age == max(ASSEMBLIES):
        base["is_current"] = base["mona_cd"].isin(current.index)
        base["party_current"] = base["mona_cd"].map(current["POLY_NM"])
        # Serving members' district as of election (roster rows exist only for those who left)
        cur_orig = base["mona_cd"].map(current["ORIG_NM"])
        base["district"] = base["district"].where(base["district"].notna(), cur_orig)
    else:
        base["is_current"] = False
        base["party_current"] = None

    # Committees: dated history first, the ALLNAMEMBER list only when it is aligned
    hist = (assignments[assignments["assembly"] == age]
            .groupby("mona_cd")["committee"]
            .agg(lambda s: ", ".join(dict.fromkeys(s))))
    from_hist = base["mona_cd"].map(hist)
    base["committee_source"] = "assignment_history"
    base.loc[from_hist.isna() & base["committee"].notna(), "committee_source"] = "allnamember"
    base.loc[from_hist.isna() & base["committee"].isna(), "committee_source"] = None
    base["committee"] = from_hist.where(from_hist.notna(), base["committee"])

    # Solar/lunar flag of the birth date, from the roster endpoints
    cal = base["mona_cd"].map(roster["BTH_GBN_NM"])
    cal = cal.where(cal.notna(), base["mona_cd"].map(current["BTH_GBN_NM"]))
    base["birth_calendar"] = cal.where(cal.notna(), base["birth_calendar"])

    # Documented corrections where ALLNAMEMBER's per-era party is not the
    # party at election (data/raw/members/party_overrides.csv, with evidence)
    overrides = pd.read_csv(RAW_MEMBERS / "party_overrides.csv", dtype=str)
    ov = overrides[overrides["age"].astype(int) == age].set_index("mona_cd")
    for mona, row in ov.iterrows():
        hit = base["mona_cd"] == mona
        if hit.sum() != 1 or base.loc[hit, "party"].iloc[0] != row["party_allnamember"]:
            raise SystemExit(f"party override {age}/{mona} no longer matches ALLNAMEMBER")
        base.loc[hit, "party"] = row["party"]

    base["seniority"] = base["term_number"].map(seniority_label)
    base["snapshot_date"] = snap
    base["district"] = base["district"].str.strip()
    base = base.drop(columns=[c for c in base.columns if c.startswith("_")])

    cols = ["mona_cd", "member_name", "member_name_hanja", "member_name_eng", "sex",
            "birth_date", "birth_calendar", "reelection", "term_number", "seniority",
            "email", "homepage", "photo_url", "age", "party", "party_current", "district",
            "election_type", "committee", "committee_source", "is_current", "snapshot_date"]
    return base[cols].sort_values(["party", "member_name"]).reset_index(drop=True)


def check_seniority(frames: dict[int, pd.DataFrame]):
    """Compare seniority counts with the official 역대 국회의원 재선 현황 table."""
    try:
        official = pd.DataFrame(kna_api.fetch("ngdeoqgoablceakpp"))
    except SystemExit:
        return
    official = official[official["DIV"] == "인원"]
    cols = ["NEWELCT", "TWOTERM", "THRTERM", "FOURTERM", "FIVTERM", "SIXTERM", "SEVTERM"]
    for age, df in frames.items():
        row = official[official["ERACO"] == f"제{age}대"]
        if row.empty:
            continue
        want = [int(re.match(r"\d+", str(row.iloc[0][c])).group()) if re.match(r"\d+", str(row.iloc[0][c])) else 0
                for c in cols]
        got = [int((df["term_number"] == k).sum()) for k in range(1, 8)]
        flag = "OK" if want == got else "DIFF"
        print(f"  seniority {age}: official {want} vs kna {got} {flag}")


def main():
    parser = argparse.ArgumentParser(description="Collect member metadata")
    parser.add_argument("--assembly", type=int, help="Single assembly (default: all 17-22)")
    parser.add_argument("--build-only", action="store_true", help="Skip fetching")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    if not args.build_only:
        kna_api.get_key()
        fetch_raw()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    allname = pd.read_parquet(RAW_MEMBERS / "ALLNAMEMBER.parquet")
    assignments = build_committee_assignments()
    kna_api.write_parquet_atomic(assignments, out_dir / "committee_assignments.parquet")
    print(f"  committee_assignments: {len(assignments):,} spells")

    frames = {}
    for age in ([args.assembly] if args.assembly else ASSEMBLIES):
        df = build_members(age, allname, assignments)
        dup = df["mona_cd"].duplicated().sum()
        if dup:
            raise SystemExit(f"{age}: {dup} duplicate mona_cd")
        kna_api.write_parquet_atomic(df, out_dir / f"members_{age}.parquet")
        frames[age] = df
        print(f"  {age}th Assembly: {len(df)} members, committee filled "
              f"{df['committee'].notna().sum()}, district filled {df['district'].notna().sum()}")
    if not args.build_only:
        check_seniority(frames)
    print("Done.")


if __name__ == "__main__":
    main()
