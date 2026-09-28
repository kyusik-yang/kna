"""
Build the member-year asset disclosure panel, assets_wealth_panel.parquet.
==========================================================================
Two sources, one set of variable definitions:

1. wealth_year 2015-2024: the OpenWatch item-level CSVs of the March regular
   disclosures 2016.03-2025.03 (CC BY-SA 4.0, https://docs.openwatch.kr/).
   OpenWatch republishes the sheets of 투명사회를 위한 정보공개센터 with the
   member code monaCode added. load_openwatch() repeats the cleaning of
   legislator-assets-korea/scripts/02_merge_and_clean.py and aggregate()
   repeats scripts/03_build_wealth_panel.py, so these rows reproduce the
   0.6.0 file.
2. wealth_year 2025 onward: the official 국회공보 PDF of each March regular
   disclosure (국회공직자윤리위원회 공고), parsed by parse_gongbo(). OpenWatch
   has no 2026.03 round, and the 정보공개센터 sheet of that round forbids
   derivative works, so the panel is built from the primary document.
   Members are matched to mona_cd by name through members_22.parquet.

The wealth year is the calendar year the wealth refers to. The March 2026
disclosure reports holdings on 2025-12-31 and gives wealth_year 2025. Amounts
are in thousands of won (천원), as printed.

Usage:
    python3 build_assets.py fetch                 # download the 국회공보 PDFs
    python3 build_assets.py build --out data/_build [--compare data/processed]
    python3 build_assets.py crosscheck            # parse the 2025.03 PDF and
                                                  # compare it with OpenWatch

    --out DIR          output directory (default data/processed)
    --members-dir DIR  members_22.parquet (default data/processed)
    --compare DIR      earlier panel to compare with (default: none)

Source location (environment variable, default in brackets):
    KNA_ASSETS_DIR  [no default; must point to the directory holding]
                    openwatch/assets_YYYYMM.csv  OpenWatch downloads
                    gongbo/                      국회공보 PDFs written by fetch

The PDF parser needs pdfplumber (pip install pdfplumber). It is not a
dependency of the kna package.
"""

import argparse
import hashlib
import itertools
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROCESSED = Path(__file__).parent / "data" / "processed"
SOURCE_DIR = Path(os.environ.get("KNA_ASSETS_DIR", "/nonexistent/KNA_ASSETS_DIR-not-set"))
OUT_NAME = "assets_wealth_panel.parquet"

# OpenWatch regular (정기) disclosure files and the wealth year each refers to
OPENWATCH_YEAR = {
    "201603": 2015, "201703": 2016, "201803": 2017, "201903": 2018,
    "202003": 2019, "202103": 2020, "202203": 2021, "202303": 2022,
    "202403": 2023, "202503": 2024,
}

# 국회공보 regular disclosures. The download URL is the portal's attachment
# link. sha256 pins the file that was parsed.
GONGBO = {
    2025: dict(
        issue="국회공보 제2026-54호(정기재산공개)", published="2026-03-26",
        notice="국회공직자윤리위원회공고 제2026-3호", pdf_id="379837",
        file="gongbo_2026-54_regular.pdf",
        url="https://www.assembly.go.kr/portal/cmmn/file/fileDown.do"
            "?atchFileId=0b500c662c0b4a57928afa682468b754&fileSn=1",
        sha256="6ce0805e1f0e64b66f4fc648737812749e12e11ac2b8a126a8fe388beacc9974"),
}
# Used only by crosscheck: the 2025.03 issue, also covered by OpenWatch
CROSSCHECK = dict(
    wealth_year=2024, openwatch="202503",
    issue="국회공보 제2025-51호(정기재산공개)", published="2025-03-27", pdf_id="379578",
    file="gongbo_2025-51_regular.pdf",
    url="https://www.assembly.go.kr/portal/cmmn/file/fileDown.do"
        "?atchFileId=1566ee279b40430c9faedcc0aec17268&fileSn=1",
    sha256="eb595e336bb0dd98ac9a676a2b94da1e9b4d4734557e8cf19f128baa2ab44df2")


def assembly_of(wealth_year: int) -> int:
    """Assembly in session at the March disclosure of the following year."""
    if wealth_year <= 2015:
        return 19
    if wealth_year <= 2019:
        return 20
    if wealth_year <= 2023:
        return 21
    return 22


# Positions in the 국회공보 list that are members of the Assembly. The rest
# are officials of the secretariat, library, budget office and research service.
MEMBER_POSITIONS = {"국회의원", "국회의장", "국회부의장"}

# Same-name members of the 22nd Assembly. A disclosure name with more than one
# roster match must be listed here for its wealth year, or the build stops.
# 박지원 H7X3372O (born 1987) was elected in the 2026-06-03 by-election for
# 전북 군산시김제시부안군을, after the March 2026 disclosure. The only 박지원 in
# the March 2025 and March 2026 disclosures is therefore 8BF5855P (born 1942).
# resolve_names() also checks that the disclosed prior-year total (종전가액 총계)
# equals the chosen member's net worth in the previous wealth year.
SAME_NAME = {
    ("박지원", 2024): "8BF5855P",  # used by crosscheck (March 2025 issue)
    ("박지원", 2025): "8BF5855P",
}

ASSET_TYPE_MAP = {  # from scripts/02_merge_and_clean.py
    "부동산에 관한 규정이 준용되는 권리와 자동차․건설기계․선박 및 항공기":
        "부동산에 관한 규정이 준용되는 권리와 자동차·건설기계·선박 및 항공기",
    "유가증권": "증권",
    "합명․합자․유한회사 출자지분": "합명·합자·유한회사 출자지분",
    "합명·합자·유한회사출자지분": "합명·합자·유한회사 출자지분",
    "비영리법인에의한 출연재산": "비영리법인에 출연한 재산",
}
RENAME = {  # the subset of 02's REGULAR_RENAME that 03 uses
    "성명": "name", "이름": "name",
    "재산구분": "asset_type", "재산 구분": "asset_type",
    "본인과의 관계": "relation", "본인과의관계": "relation",
    "재산의 종류": "asset_kind", "재산의종류": "asset_kind",
    "소재지 면적 등 권리의 명세": "detail",
    "현재가액": "current_value",
    "연월": "date",
}
ITEM_COLS = ["monaCode", "wealth_year", "name", "asset_type", "relation",
             "asset_kind", "detail", "current_value"]
AMOUNTS = ["prev_value", "increased", "decreased", "current_value"]
QUARTILE_COLS = ["total_realestate", "total_assets", "net_worth"]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pdf_path(meta: dict, verify: bool = True) -> Path:
    p = SOURCE_DIR / "gongbo" / meta["file"]
    if not p.exists():
        raise SystemExit(f"ERROR: {p} not found. Run: python3 build_assets.py fetch")
    if verify and sha256(p) != meta["sha256"]:
        raise SystemExit(f"ERROR: {p} does not match the pinned sha256 {meta['sha256']}")
    return p


def fetch():
    """Download the 국회공보 PDFs and check them against the pinned sha256."""
    out = SOURCE_DIR / "gongbo"
    out.mkdir(parents=True, exist_ok=True)
    for meta in list(GONGBO.values()) + [CROSSCHECK]:
        p = out / meta["file"]
        if p.exists() and sha256(p) == meta["sha256"]:
            print(f"  {p.name}: present, sha256 ok")
            continue
        import requests  # as in kna_api.py
        r = requests.get(meta["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
        r.raise_for_status()
        p.write_bytes(r.content)
        got = sha256(p)
        if got != meta["sha256"]:
            raise SystemExit(f"ERROR: {p.name} sha256 {got} differs from the pinned "
                             f"{meta['sha256']}. The portal file may have been replaced.")
        print(f"  {p.name}: downloaded, {p.stat().st_size:,} bytes, sha256 ok")


def clean_numeric(s):
    """scripts/02_merge_and_clean.py clean_numeric()."""
    if pd.isna(s) or s == "" or s == "-":
        return np.nan
    s = str(s).strip().replace(",", "").replace(" ", "")
    if s == "" or s == "-":
        return np.nan
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return np.nan


# Strings that pandas.read_csv reads as missing by default
CSV_NA = {"", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND",
          "1.#QNAN", "<NA>", "N/A", "NA", "NULL", "NaN", "None", "n/a", "nan", "null"}


def _text(col: pd.Series) -> pd.Series:
    """Strip, and treat what pandas reads as missing as missing.

    02 wrote assets_all.csv and 03 read it back, so an empty or NA-like string
    ('', 'nan', 'NA', ...) reached the aggregation as missing.
    """
    s = col.map(lambda v: v.strip() if isinstance(v, str) else v)
    return s.where(s.notna() & ~s.isin(CSV_NA), None)


def load_openwatch(src: Path = None) -> pd.DataFrame:
    """Item rows of the OpenWatch regular disclosures, as 03 saw them."""
    src = src or SOURCE_DIR / "openwatch"
    frames = []
    for ym, year in OPENWATCH_YEAR.items():
        p = src / f"assets_{ym}.csv"
        if not p.exists():
            raise SystemExit(f"ERROR: {p} not found. Set KNA_ASSETS_DIR to the directory "
                             "holding openwatch/ (see the module docstring).")
        df = pd.read_csv(p, dtype=str)
        df.columns = df.columns.str.strip()
        df = df.rename(columns=RENAME)
        df["current_value"] = pd.to_numeric(df["current_value"].map(clean_numeric), errors="coerce")
        for c in ["monaCode", "name", "asset_type", "relation", "asset_kind", "detail", "date"]:
            df[c] = _text(df[c])
        bad = set(df["date"].dropna()) - {ym}
        if bad:
            raise SystemExit(f"ERROR: {p.name} has 연월 values {sorted(bad)}, expected {ym}")
        df["wealth_year"] = year
        frames.append(df)
    items = pd.concat(frames, ignore_index=True)
    items["asset_type"] = items["asset_type"].replace(ASSET_TYPE_MAP)
    return items[ITEM_COLS]


# ---------------------------------------------------------------------------
# 국회공보 PDF parser
# ---------------------------------------------------------------------------

def _num(cell):
    """(amount, 실거래가격) from a cell such as '10,370' or '10,370\\n(3,000)'."""
    if cell is None:
        return None, None
    s = cell.strip()
    if s in ("", "-"):
        return None, None
    parts = [p.strip() for p in s.split("\n") if p.strip()]
    value = int(parts[0].replace(",", "").replace(" ", ""))
    rest = "".join(parts[1:]).replace(" ", "")
    real = None
    if rest:
        m = re.fullmatch(r"\((-?[\d,]+)\)", rest)
        if not m:
            raise ValueError(f"unreadable amount cell {cell!r}")
        real = int(m.group(1).replace(",", ""))
    return value, real


def _txt(cell):
    """Cell text with its line breaks removed, or None when empty.

    Lines are joined without a space, as in the 정보공개센터 and OpenWatch
    sheets, so that a place name broken across lines stays whole.
    """
    if cell is None:
        return None
    out = "".join(x.strip() for x in cell.split("\n")).strip()
    return out or None


def _blank(item):
    return all(item[c] is None for c in AMOUNTS)


def table_rows(pdf: Path) -> list:
    """Every table row of the PDF as (page, first_on_page, last_on_page, cells)."""
    try:
        import pdfplumber
    except ImportError:
        raise SystemExit("ERROR: the PDF parser needs pdfplumber (pip install pdfplumber)")
    rows = []
    with pdfplumber.open(pdf) as doc:
        for pno, page in enumerate(doc.pages, 1):
            tables = sorted(page.find_tables(), key=lambda t: (t.bbox[1], t.bbox[0]))
            page_rows = [r for t in tables for r in t.extract()]
            data = [i for i, r in enumerate(page_rows) if len(r) in (6, 8)]
            for i, r in enumerate(page_rows):
                rows.append((pno, bool(data) and i == data[0], bool(data) and i == data[-1], r))
    return rows


def parse_gongbo(rows: list):
    """Parse the table rows of a 정기재산변동신고 공개목록.

    Returns (people, items, subtotals, log). Every person block starts with a
    header row (소속, 직위, 성명), has one '▶ 재산구분(소계)' row per category and
    ends with a '총 계' row. Three layout rules are handled:

    - A row that continues across a page break is printed again on the next
      page. In some issues the continuation repeats relation, kind and all four
      amounts. Whether such a pair is one item or two identical items is
      decided by the category subtotal, and the build stops if the subtotal
      cannot decide. In other issues one part of the row carries the amounts
      and the other part is blank. Such parts are merged.
    - A relation or kind cell merged over several rows is read as None by
      pdfplumber and is filled from the row above within the same category.
    - A 총 계 row alone at the top of a page comes as a six-cell table.
    """
    people, raw, subs = [], [], []
    cur = cat = None
    for pno, first, last, r in rows:
        c0 = (r[0] or "").strip()
        if c0 == "소속" and len(r) == 8:
            cur = dict(pid=len(people), affiliation=_txt(r[1]), position=_txt(r[4]),
                       name=(_txt(r[7]) or "").replace(" ", ""), page=pno)
            if not cur["name"]:
                raise ValueError(f"page {pno}: header without a name: {r}")
            people.append(cur)
            cat = None
            continue
        if cur is None:
            continue  # front matter before the first person
        if c0.replace(" ", "") == "총계" and len(r) in (6, 8):
            amounts = r[1:5] if len(r) == 6 else r[3:7]
            cur.update({f"tot_{a}": _num(x)[0] for a, x in zip(AMOUNTS, amounts)})
            continue
        if len(r) != 8:
            if any((c or "").strip() for c in r) and pno > people[0]["page"]:
                raise ValueError(f"page {pno}: unexpected {len(r)}-cell row {r}")
            continue
        if c0.startswith("(단위") or c0.startswith("본인과의") or \
                (r[0] is None and (r[4] or "").startswith("증가액")):
            continue
        if c0.startswith("▶"):
            cat = re.sub(r"\(소계\)$", "", c0[1:].strip()).strip()
            subs.append(dict(pid=cur["pid"], asset_type=cat,
                             **{a: _num(x)[0] for a, x in zip(AMOUNTS, r[3:7])}))
            continue
        if cat is None:
            raise ValueError(f"page {pno}: item row before any category: {r}")
        pv, _ = _num(r[3])
        inc, inc_real = _num(r[4])
        dec, dec_real = _num(r[5])
        cv, _ = _num(r[6])
        raw.append(dict(pid=cur["pid"], page=pno, asset_type=cat,
                        relation=_txt(r[0]), asset_kind=_txt(r[1]), detail=_txt(r[2]),
                        rel_merged=r[0] is None, kind_merged=r[1] is None,
                        prev_value=pv, increased=inc, increased_real=inc_real,
                        decreased=dec, decreased_real=dec_real, current_value=cv,
                        reason=_txt(r[7]), first=first, last=last))

    items, repeated, n_blank = [], [], 0
    for it in raw:
        a = items[-1] if items else None
        straddle = (a is not None and a["last"] and it["first"] and a["pid"] == it["pid"]
                    and a["asset_type"] == it["asset_type"])
        if straddle:
            compatible = (it["relation"] in (None, a["relation"])
                          and it["asset_kind"] in (None, a["asset_kind"]))
            text_only = it["relation"] is None and it["asset_kind"] is None
            if compatible and (_blank(a) != _blank(it) or (_blank(a) and _blank(it) and text_only)):
                src = it if _blank(a) else a
                for c in AMOUNTS + ["increased_real", "decreased_real"]:
                    a[c] = src[c]
                a["relation"] = a["relation"] or it["relation"]
                a["asset_kind"] = a["asset_kind"] or it["asset_kind"]
                a["detail"] = ((a["detail"] or "") + (it["detail"] or "")) or None
                a["reason"] = a["reason"] or it["reason"]
                a["last"] = it["last"]
                n_blank += 1
                continue
            if ((a["relation"], a["asset_kind"]) == (it["relation"], it["asset_kind"])
                    and all(a[c] == it[c] for c in AMOUNTS)):
                repeated.append(len(items))
        if it["rel_merged"] or it["kind_merged"]:
            if a is None or a["pid"] != it["pid"] or a["asset_type"] != it["asset_type"]:
                raise ValueError(f"page {it['page']}: merged cell with no row above: {it}")
            if it["rel_merged"]:
                it["relation"] = a["relation"]
            if it["kind_merged"]:
                it["asset_kind"] = a["asset_kind"]
        items.append(it)

    P = pd.DataFrame(people)
    I = pd.DataFrame(items)
    S = pd.DataFrame(subs)
    target = S.set_index(["pid", "asset_type"])
    groups: dict = {}
    for j in repeated:
        groups.setdefault((I.at[j, "pid"], I.at[j, "asset_type"]), []).append(j)
    drop, decisions = set(), []
    for (pid, cat_), js in groups.items():
        cat_items = I[(I["pid"] == pid) & (I["asset_type"] == cat_)]
        sub = target.loc[(pid, cat_)]
        fits = [set(c) for n in range(len(js) + 1) for c in itertools.combinations(js, n)
                if all(pd.isna(sub[a]) or cat_items.drop(index=list(c))[a].fillna(0).sum() == sub[a]
                       for a in AMOUNTS)]
        empty = all(pd.isna(I.at[j, a]) or I.at[j, a] == 0 for j in js for a in AMOUNTS)
        if len(fits) == 1:
            drop |= fits[0]
            decisions.append((pid, cat_, len(js), "merged" if fits[0] else "kept"))
        elif len(fits) > 1 and empty:
            decisions.append((pid, cat_, len(js), "kept, amounts empty"))
        else:
            raise ValueError(f"cannot decide repeated rows {js} of person {pid} ({cat_}): {fits}")
    for j in sorted(drop):
        k = j - 1
        while k in drop:
            k -= 1
        I.at[k, "detail"] = ((I.at[k, "detail"] or "") + (I.at[j, "detail"] or "")) or None
        I.at[k, "reason"] = I.at[k, "reason"] or I.at[j, "reason"]
    I = (I.drop(index=sorted(drop))
          .drop(columns=["first", "last", "rel_merged", "kind_merged"])
          .reset_index(drop=True))
    log = dict(people=len(P), items=len(I), blank_continuations=n_blank,
               repeated_merged=sum(n for *_, n, d in decisions if d == "merged"),
               repeated_kept=sum(n for *_, n, d in decisions if d != "merged"))
    check_gongbo(P, I, S)
    return P, I, S, log


def check_gongbo(P: pd.DataFrame, I: pd.DataFrame, S: pd.DataFrame):
    """Stop unless the parsed items add up to every printed subtotal and total."""
    if P["tot_current_value"].isna().any():
        raise ValueError(f"no 총 계 row for {P.loc[P['tot_current_value'].isna(), 'name'].tolist()}")
    sums = I.groupby(["pid", "asset_type"])[AMOUNTS].sum(min_count=1)
    m = S.set_index(["pid", "asset_type"]).join(sums, rsuffix="_items", how="outer")
    for a in AMOUNTS:
        bad = m[m[a].notna() & (m[a] != m[f"{a}_items"].fillna(0))]
        if len(bad):
            raise ValueError(f"{len(bad)} category subtotals of {a} differ from their items:\n{bad}")
    sign = np.where(S["asset_type"] == "채무", -1, 1)
    total = (S["current_value"].fillna(0) * sign).groupby(S["pid"]).sum()
    bad = P[P.set_index("pid")["tot_current_value"].values != total.reindex(P["pid"]).values]
    if len(bad):
        raise ValueError(f"총 계 differs from the subtotals for {bad['name'].tolist()}")


def gongbo_items(meta: dict, wealth_year: int, members: pd.DataFrame, prior: pd.DataFrame):
    """Item rows of one 국회공보 issue for members of the Assembly, with mona_cd."""
    P, I, S, log = parse_gongbo(table_rows(pdf_path(meta)))
    P = P[P["position"].isin(MEMBER_POSITIONS)].copy()
    P["mona_cd"] = resolve_names(P, wealth_year, members, prior)
    I = I.merge(P[["pid", "mona_cd", "name"]], on="pid", how="inner")
    I = I.rename(columns={"mona_cd": "monaCode"})
    I["wealth_year"] = wealth_year
    I["asset_type"] = I["asset_type"].replace(ASSET_TYPE_MAP)
    I["current_value"] = pd.to_numeric(I["current_value"]).astype(float)
    log.update(members=len(P))
    return I[ITEM_COLS], P, log


def resolve_names(P: pd.DataFrame, wealth_year: int, members: pd.DataFrame,
                  prior: pd.DataFrame) -> pd.Series:
    """mona_cd for each disclosed member, by exact name. Stops on any ambiguity."""
    roster = members.groupby("member_name")["mona_cd"].apply(list)
    prior_nw = prior.set_index("mona_cd")["net_worth"] if len(prior) else pd.Series(dtype=float)
    out, problems = [], []
    for _, p in P.iterrows():
        cands = roster.get(p["name"], [])
        if len(cands) == 1:
            out.append(cands[0])
            continue
        if not cands:
            problems.append(f"{p['name']} ({p['position']}): not in the roster")
            out.append(None)
            continue
        chosen = SAME_NAME.get((p["name"], wealth_year))
        if chosen is None or chosen not in cands:
            problems.append(f"{p['name']}: {len(cands)} roster members {cands} and no SAME_NAME rule "
                            f"for wealth_year {wealth_year}")
            out.append(None)
            continue
        # The disclosed prior-year total should be the chosen member's last net worth
        if chosen in prior_nw.index and prior_nw[chosen] != p["tot_prev_value"]:
            problems.append(f"{p['name']}: SAME_NAME picks {chosen}, whose {wealth_year - 1} net worth "
                            f"{prior_nw[chosen]:,.0f} differs from the disclosed 종전가액 "
                            f"{p['tot_prev_value']:,.0f}")
        out.append(chosen)
    dup = pd.Series(out).dropna()
    dup = dup[dup.duplicated()]
    if len(dup):
        problems.append(f"mona_cd matched twice: {dup.tolist()}")
    if problems:
        raise SystemExit("ERROR: member matching failed:\n  " + "\n  ".join(problems))
    return pd.Series(out, index=P.index)


# ---------------------------------------------------------------------------
# Aggregation (scripts/03_build_wealth_panel.py)
# ---------------------------------------------------------------------------

def _has_region(detail, pattern):
    if pd.isna(detail):
        return False
    return bool(re.search(pattern, str(detail)))


def _is_apt(kind):
    return False if pd.isna(kind) else "아파트" in str(kind)


def _is_rental(kind):
    return False if pd.isna(kind) else ("임차" in str(kind) or "전세" in str(kind))


def _is_owned(kind):
    return True if pd.isna(kind) else ("임차" not in str(kind) and "전세" not in str(kind))


def aggregate(items: pd.DataFrame) -> pd.DataFrame:
    """One row per (monaCode, wealth_year), with the variables of 03."""
    results = []
    for (code, year), grp in items.groupby(["monaCode", "wealth_year"]):
        row = {"monaCode": code, "wealth_year": year, "name": grp["name"].iloc[0]}
        debt = grp["asset_type"] == "채무"
        row["total_assets"] = grp.loc[~debt, "current_value"].sum()
        row["total_debt"] = grp.loc[debt, "current_value"].sum()
        row["net_worth"] = row["total_assets"] - row["total_debt"]
        for cat, label in [("건물", "building"), ("토지", "land"), ("예금", "deposits"),
                           ("증권", "stocks"), ("채무", "debt")]:
            row[f"total_{label}"] = grp.loc[grp["asset_type"] == cat, "current_value"].sum()
        row["total_realestate"] = row["total_building"] + row["total_land"]

        re_items = grp[grp["asset_type"].isin(["건물", "토지"])]
        bldg = grp[grp["asset_type"] == "건물"]
        row["n_properties_all"] = len(bldg)
        row["n_properties_self"] = len(bldg[bldg["relation"] == "본인"])
        row["n_properties_owned"] = len(bldg[bldg["asset_kind"].apply(_is_owned)])
        row["n_apt_total"] = len(bldg[bldg["asset_kind"].apply(_is_apt)])
        row["n_apt_owned"] = len(bldg[bldg["asset_kind"].apply(_is_apt)
                                      & bldg["asset_kind"].apply(_is_owned)])
        row["n_rental_given"] = len(bldg[bldg["asset_kind"].apply(_is_rental)])
        row["has_seoul_re"] = int(re_items["detail"].apply(
            lambda x: _has_region(x, r"서울특별시|서울시")).any())
        row["has_gangnam_re"] = int(re_items["detail"].apply(
            lambda x: _has_region(x, r"강남구|서초구|송파구")).any())
        row["n_seoul_bldg"] = len(bldg[bldg["detail"].apply(
            lambda x: _has_region(x, r"서울특별시|서울시"))])
        for rel, suffix in [("본인", "self"), ("배우자", "spouse")]:
            row[f"re_{suffix}"] = re_items.loc[re_items["relation"] == rel, "current_value"].sum()
        row["n_stock_items"] = len(grp[(grp["asset_type"] == "증권") & (grp["asset_kind"] == "상장주식")])
        row["political_fund"] = grp.loc[grp["asset_type"].str.contains("정치자금", na=False),
                                        "current_value"].sum()
        row["n_family_relations"] = grp["relation"].nunique()
        row["n_land_parcels"] = len(grp[grp["asset_type"] == "토지"])
        row["re_share"] = (row["total_realestate"] / row["total_assets"]
                           if row["total_assets"] > 0 else np.nan)
        for col in ["total_realestate", "total_assets", "net_worth", "total_building",
                    "total_land", "total_deposits", "total_stocks"]:
            row[f"log_{col}"] = np.log(row[col]) if row[col] > 0 else np.nan
        results.append(row)
    panel = pd.DataFrame(results)
    for col in [c for c in panel.columns if c.startswith("total_") or c.startswith("re_")
                or c == "political_fund" or c.startswith("log_") or c == "net_worth"]:
        panel[col] = panel[col].astype(float)
    return panel


def add_quartiles(panel: pd.DataFrame, base_years) -> pd.DataFrame:
    """Quartiles of the three totals.

    The cut points are those of the 2015-2024 OpenWatch panel (pooled over
    member-years, as in 03), so adding a year does not relabel earlier rows.
    Later years are binned with the same cut points, open at both ends.
    """
    base = panel["wealth_year"].isin(base_years)
    labels = ["Q1", "Q2", "Q3", "Q4"]
    for col in QUARTILE_COLS:
        q, edges = pd.qcut(panel.loc[base, col], 4, labels=labels, retbins=True)
        out = pd.Series(None, index=panel.index, dtype=object)
        out[base] = q.astype(str)
        if (~base).any():
            bins = [-np.inf, *edges[1:-1], np.inf]
            out[~base] = pd.cut(panel.loc[~base, col], bins, labels=labels).astype(str)
        panel[f"{col}_q"] = out
    return panel


def finish(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.rename(columns={"monaCode": "mona_cd", "name": "member_name"})
    panel["assembly"] = panel["wealth_year"].map(assembly_of).astype("int64")
    panel["wealth_year"] = panel["wealth_year"].astype("int64")
    return panel.sort_values(["mona_cd", "wealth_year"], kind="stable").reset_index(drop=True)


def csv_floats(panel: pd.DataFrame) -> pd.DataFrame:
    """Pass the float columns through CSV text, as the 0.6.0 file was made.

    03 wrote wealth_panel_openwatch.csv with DataFrame.to_csv, and the 0.6.0
    parquet was read from that CSV with pandas.read_csv. The parser rounds a
    few decimal strings to a neighbouring double, so re_share and the log
    columns differ from a direct computation in the last bits (a relative
    difference below 1e-13). Repeating the round trip keeps the 2015-2024 rows
    bit for bit and treats later years the same way.
    """
    import io
    floats = panel.select_dtypes("float64").columns
    buf = io.StringIO()
    panel[floats].to_csv(buf, index=False)
    buf.seek(0)
    back = pd.read_csv(buf, float_precision="high")
    panel[floats] = back[floats].to_numpy()
    return panel


# ---------------------------------------------------------------------------
# Build and reports
# ---------------------------------------------------------------------------

def compare_panels(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Per-column comparison of the rows that both panels hold."""
    key = ["mona_cd", "wealth_year"]
    m = old.merge(new, on=key, how="outer", suffixes=("_old", "_new"), indicator=True)
    rows = [dict(column="(rows)", old=len(old), new=len(new),
                 only_old=int((m["_merge"] == "left_only").sum()),
                 only_new=int((m["_merge"] == "right_only").sum()), differ=0)]
    both = m[m["_merge"] == "both"]
    for c in [c for c in old.columns if c not in key and c in new.columns]:
        a, b = both[f"{c}_old"], both[f"{c}_new"]
        same = (a == b) | (a.isna() & b.isna())
        rows.append(dict(column=c, old=int(a.notna().sum()), new=int(b.notna().sum()),
                         only_old=0, only_new=0, differ=int((~same).sum())))
    return pd.DataFrame(rows)


def member_report(panel: pd.DataFrame, members: pd.DataFrame, disclosed: pd.DataFrame,
                  year: int) -> pd.DataFrame:
    """One row per 22nd-Assembly member: coverage and change against the prior year."""
    cur = panel[panel["wealth_year"] == year].set_index("mona_cd")
    prev = panel[panel["wealth_year"] == year - 1].set_index("mona_cd")
    rep = members[["mona_cd", "member_name", "is_current"]].copy()
    rep["disclosed"] = rep["mona_cd"].isin(cur.index)
    rep[f"row_{year - 1}"] = rep["mona_cd"].isin(prev.index)
    for c in ["net_worth", "total_assets", "total_realestate"]:
        rep[f"{c}_{year - 1}"] = rep["mona_cd"].map(prev[c])
        rep[f"{c}_{year}"] = rep["mona_cd"].map(cur[c])
    d = disclosed.set_index("mona_cd")
    rep["disclosed_prev_total"] = rep["mona_cd"].map(d["tot_prev_value"])
    rep["disclosed_total"] = rep["mona_cd"].map(d["tot_current_value"])
    rep["change"] = rep[f"net_worth_{year}"] - rep[f"net_worth_{year - 1}"]
    rep["log_ratio"] = np.log(rep[f"net_worth_{year}"] / rep[f"net_worth_{year - 1}"]).where(
        (rep[f"net_worth_{year}"] > 0) & (rep[f"net_worth_{year - 1}"] > 0))
    rep["prev_total_matches"] = rep["disclosed_prev_total"] == rep[f"net_worth_{year - 1}"]
    return rep.sort_values(["disclosed", "mona_cd"], ascending=[False, True]).reset_index(drop=True)


def build(out: Path, members_dir: Path, compare: Path = None):
    out.mkdir(parents=True, exist_ok=True)
    (out / "reports").mkdir(exist_ok=True)
    print("=" * 60)
    print("Asset disclosure panel")
    print("=" * 60)
    ow = load_openwatch()
    panel = aggregate(ow)
    print(f"  OpenWatch: {len(ow):,} items -> {len(panel):,} member-years, "
          f"wealth_year {panel['wealth_year'].min()}-{panel['wealth_year'].max()}")
    members = pd.read_parquet(members_dir / "members_22.parquet")
    new_years, disclosed = [], None
    for year, meta in sorted(GONGBO.items()):
        prior = finish(panel[panel["wealth_year"] == year - 1].copy())
        items, P, log = gongbo_items(meta, year, members, prior)
        add = aggregate(items)
        # 03 derives net worth from the items. It must equal the printed 총 계.
        chk = add.set_index("monaCode")["net_worth"]
        tot = P.set_index("mona_cd")["tot_current_value"].astype(float)
        if not chk.reindex(tot.index).eq(tot).all():
            raise SystemExit(f"ERROR: {year}: net worth differs from the printed 총 계")
        print(f"  {meta['issue']}: {log['people']} people, {log['members']} members, "
              f"{log['items']:,} items ({log['blank_continuations']} split rows joined, "
              f"{log['repeated_merged']} repeated rows merged, {log['repeated_kept']} kept) "
              f"-> {len(add)} member-years for wealth_year {year}")
        panel = pd.concat([panel, add], ignore_index=True)
        new_years.append(year)
        disclosed = P
    panel = add_quartiles(panel, OPENWATCH_YEAR.values())
    panel = csv_floats(finish(panel))

    path = out / OUT_NAME
    panel.to_parquet(path, index=False)
    print(f"  Saved: {path} ({len(panel):,} rows, {panel['mona_cd'].nunique()} members)")
    print(panel.groupby(["assembly", "wealth_year"]).size().to_string())

    if new_years:
        year = new_years[-1]
        rep = member_report(panel, members, disclosed, year)
        rep.to_csv(out / "reports" / "assets_member_check.csv", index=False)
        print(f"  22nd roster: {len(rep)} member records, {int(rep['disclosed'].sum())} with a "
              f"wealth_year {year} row. Report: reports/assets_member_check.csv")
    if compare is not None:
        old_path = compare / OUT_NAME
        if old_path.exists():
            cmp = compare_panels(pd.read_parquet(old_path), panel)
            cmp.to_csv(out / "reports" / "assets_compare.csv", index=False)
            print(f"  Compared with {old_path}: rows only in the earlier file "
                  f"{int(cmp.iloc[0]['only_old'])}, only in the new file {int(cmp.iloc[0]['only_new'])}, "
                  f"cells that differ {int(cmp['differ'].sum())}. Report: reports/assets_compare.csv")
    return panel


def crosscheck(members_dir: Path):
    """Parse the 2025.03 issue and compare it with the OpenWatch file of that round."""
    meta = CROSSCHECK
    year = meta["wealth_year"]
    members = pd.read_parquet(members_dir / "members_22.parquet")
    ow = load_openwatch()
    ow = ow[ow["wealth_year"] == year]
    base = finish(aggregate(ow))
    prior = finish(aggregate(load_openwatch().query("wealth_year == @year - 1")))
    items, P, log = gongbo_items(meta, year, members, prior)
    print(f"  {meta['issue']}: {log['people']} people, {log['members']} members, {log['items']:,} items")
    # member codes: name matching against OpenWatch's monaCode
    ow_codes = set(zip(ow["name"], ow["monaCode"])) - {(n, c) for n, c in zip(ow["name"], ow["monaCode"])
                                                        if pd.isna(c)}
    pdf_codes = set(zip(items["name"], items["monaCode"]))
    print(f"  mona_cd from name matching equals OpenWatch monaCode for all {len(ow_codes)} members: "
          f"{pdf_codes == ow_codes}")
    rebuilt = finish(aggregate(items))
    cmp = compare_panels(base, rebuilt)
    print(cmp[cmp["differ"] > 0].to_string(index=False) if cmp["differ"].sum() else
          f"  All {len(base)} member-years and {len(cmp) - 1} columns agree with the OpenWatch build.")
    return cmp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["fetch", "build", "crosscheck"])
    ap.add_argument("--out", type=Path, default=PROCESSED)
    ap.add_argument("--members-dir", type=Path, default=PROCESSED)
    ap.add_argument("--compare", type=Path, default=None)
    args = ap.parse_args()
    if args.command == "fetch":
        fetch()
    elif args.command == "build":
        build(args.out, args.members_dir, args.compare)
    else:
        crosscheck(args.members_dir)


if __name__ == "__main__":
    sys.exit(main())
