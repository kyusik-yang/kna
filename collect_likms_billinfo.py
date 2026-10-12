"""
LIKMS bill pages: the meetings that took up each law bill
=========================================================
The bill page of LIKMS (의안정보시스템, 의안 상세 > 위원회 심사 and 본회의
심의) lists the committee, subcommittee, related-committee, 법제사법위원회
and plenary meetings that took up a bill. Each meeting row links the minutes
in the record viewer (record.assembly.go.kr) by CONFER_NUM, which is
`conf_num` in hearing_meetings_summary.parquet and in kr-hearings-data. The
Open API meeting tables (committee_meetings_{age}, judiciary_meetings_{age})
carry no such number.

  fetch    POST billInfo.do for every law bill of the master and keep the
           answer as {html_dir}/{age}/{bill_no}.html.gz. A bill whose file
           exists is skipped, so an interrupted run resumes.
  extract  parse the cached pages into data/raw/likms_billinfo_{age}.parquet,
           every row of the review and meeting tables as listed,
           data/raw/likms_billinfo_docs_{age}.parquet, every document link
           of those rows (검토보고서, 심사보고서, 위원회의결안 and the rest),
           and data/raw/likms_billinfo_meta.json. collect_likms_docs.py
           downloads and measures the documents.
  build    write bill_meetings.parquet and reports/bill_meetings_coverage.csv
           to --out from the raw tables. build_all.sh runs this step.

The request is POST {URL} with billId, billNo and billKindCd=법률안 and no
login. fetch spaces requests --interval seconds apart (default 0.7), retries
with backoff and appends failures and empty answers to
data/raw/fetchlog/likms_billinfo.jsonl. A wrong billId also gets HTTP 200,
with the tab template and no review sections. fetch keeps such an answer
(status empty) and extract stops on it.

Rules, each of which stops extract or build when it fails:

  1. Every law bill of the master has a cached page, and every page holds at
     least one review section under a known heading.
  2. Every table row sits under a known heading, and its cells are the
     ones that heading lists.
  3. The page does not print the bill number, so it is matched to the bill
     through the committee. For every bill with a 소관위 심사정보 row and a
     committee in the master, the master's committee_nm must be one of the
     page's 소관위 committees, after spaces and parenthesized text are removed.
     At least 99.9% of the master's committee_dt must be among the page's
     회부일. In the 2026-10 collection 30 bills differ, 29 of them in the
     17th. 16 differ by one day, and three have no 회부일 on the page.
  4. A meeting date is a YYYY-MM-DD date, and (bill_no, stage, seq) is
     unique.
  5. Every document link carries a label and one bookId for its HWP and
     PDF files.

Usage:
    python3 collect_likms_billinfo.py fetch --html-dir DIR [--ages 17-22]
    python3 collect_likms_billinfo.py extract --html-dir DIR
    python3 collect_likms_billinfo.py build [--out data/processed]

fetch and extract need requests and beautifulsoup4 (pip install
"kna[likms]"). build needs neither.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from kna_api import write_parquet_atomic

REPO = Path(__file__).parent
DATA_DIR = REPO / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FETCHLOG = RAW_DIR / "fetchlog" / "likms_billinfo.jsonl"
META = RAW_DIR / "likms_billinfo_meta.json"
ALL_AGES = list(range(17, 23))

URL = "https://likms.assembly.go.kr/bill/bi/bill/detail/billInfo.do"
REFERER = "https://likms.assembly.go.kr/bill/billDetail.do?billId={}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
BACKOFF = [10, 30, 60, 120, 300]

# heading -> the cell classes its rows carry ("doc" holds links only)
SECTIONS = {
    "소관위 심사정보": {"committeeName", "submitDt", "presentDt", "procDt", "inscResultCd", "doc"},
    "소관위 회의정보": {"mtngName", "mtngDt", "procResultName", "doc"},
    "소위 심사정보": {"committeeName", "submitDt", "presentDt", "procDt", "inscResultCd"},
    "관련위 심사정보": {"committeeName", "submitDt", "presentDt", "procDt", "doc"},
    "관련위 회의정보": {"mtngName", "mtngDt", "procResultName", "doc"},
    "법사위 체계자구 심사정보": {"submitDt", "presentDt", "procDt", "inscResultCd", "doc"},
    "법사위 회의정보": {"mtngName", "mtngDt", "procResultName", "doc"},
    "본회의 심의정보": {"mtngName", "presentDt", "procDt", "inscResultCd", "doc"},
}
STAGES = {
    "소관위 회의정보": "committee",
    "관련위 회의정보": "related_committee",
    "법사위 회의정보": "judiciary",
    "본회의 심의정보": "plenary",
}
RAW_COLS = ["age", "bill_no", "section", "seq", "committee", "submit_dt", "present_dt",
            "proc_dt", "meeting_name", "meeting_dt", "result", "conf_num"]
CELL_COL = {"committeeName": "committee", "submitDt": "submit_dt", "presentDt": "present_dt",
            "procDt": "proc_dt", "mtngName": "meeting_name", "mtngDt": "meeting_dt",
            "procResultName": "result", "inscResultCd": "result"}
CONF_NUM = re.compile(r"minutes/(?:download/pdf\.do|xml\.do)\?id=(\d+)")
DOC_COLS = ["age", "bill_no", "section", "seq", "doc_seq", "doc_type", "book_id", "pdf_url", "hwp_url"]
BOOK_ID = re.compile(r"bookId=([0-9A-Za-z-]+)")
DOC_FORMAT = re.compile(r"\((HWP|PDF) 파일 다운로드\)")
LIKMS = "https://likms.assembly.go.kr"
OUT_COLS = ["age", "bill_no", "bill_id", "stage", "seq", "meeting_name", "meeting_date",
            "present_date", "result", "conf_num"]


def parse_ages(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def law_bills(master_dir: Path, ages: list[int]) -> pd.DataFrame:
    frames = []
    for age in ages:
        m = pd.read_parquet(master_dir / f"master_bills_{age}.parquet",
                            columns=["bill_no", "bill_id", "bill_kind", "committee_nm", "committee_dt"])
        m = m[m["bill_kind"] == "법률안"].drop(columns="bill_kind")
        frames.append(m.assign(age=age))
    return pd.concat(frames, ignore_index=True).astype({"bill_no": str})


def page_path(html_dir: Path, age: int, bill_no: str) -> Path:
    return html_dir / str(age) / f"{bill_no}.html.gz"


# ── fetch ───────────────────────────────────────────────────────────

def classify(status_code: int, body: bytes) -> str:
    if status_code != 200:
        return "retry"
    text = body.decode("utf-8", errors="ignore")
    if "billInfoTabClick" not in text:
        return "retry"
    return "ok" if "<h3>" in text and "bill_info_div" in text else "empty"


def fetch(args) -> None:
    import requests

    html_dir = Path(args.html_dir)
    bills = law_bills(Path(args.master_dir), parse_ages(args.ages))
    todo = [(r.age, r.bill_no, r.bill_id) for r in bills.itertuples()
            if not page_path(html_dir, r.age, r.bill_no).exists()]
    print(f"fetch: {len(bills):,} law bills, {len(bills) - len(todo):,} cached, {len(todo):,} to fetch")
    FETCHLOG.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    last, t0 = 0.0, time.time()
    for i, (age, bill_no, bill_id) in enumerate(todo, 1):
        verdict, body, err = "failed", b"", None
        for attempt in range(len(BACKOFF) + 1):
            time.sleep(max(0.0, last + args.interval - time.time()))
            last = time.time()
            try:
                r = session.post(URL, data={"billId": bill_id, "billNo": bill_no, "billKindCd": "법률안"},
                                 headers={"Referer": REFERER.format(bill_id)}, timeout=60)
                body, verdict = r.content, classify(r.status_code, r.content)
                err = None if verdict != "retry" else f"HTTP {r.status_code}, {len(body)} bytes"
            except requests.RequestException as exc:
                verdict, err = "retry", f"{type(exc).__name__}: {exc}"[:300]
            if verdict != "retry":
                break
            if attempt < len(BACKOFF):
                time.sleep(BACKOFF[attempt])
        else:
            verdict = "failed"
        if verdict in ("ok", "empty"):
            path = page_path(html_dir, age, bill_no)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with gzip.open(tmp, "wb") as f:
                f.write(body)
            tmp.replace(path)
        if verdict != "ok":
            with open(FETCHLOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"bill_no": bill_no, "bill_id": bill_id, "age": age, "status": verdict,
                                    "error": err, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                                   ensure_ascii=False) + "\n")
        if i % 500 == 0 or i == len(todo):
            rate = i / (time.time() - t0)
            print(f"  {i:,}/{len(todo):,}  {rate:.2f}/s  eta {(len(todo) - i) / rate / 3600:.1f} h", flush=True)


# ── extract ─────────────────────────────────────────────────────────

def cell_text(td) -> "str | None":
    span = td.find("span", recursive=False)
    if span is None:
        return None
    return " ".join(span.get_text(" ", strip=True).split()) or None


def parse_docs(doc_td, base: dict) -> list[dict]:
    """FileGate document links of one row; minutes links carry no bookId and are skipped."""
    docs = []
    for div in doc_td.find_all("div", class_="report"):
        links = {}
        for a in div.find_all("a"):
            fm, bm = DOC_FORMAT.search(a.get("title", "")), BOOK_ID.search(a.get("href", ""))
            if fm and bm:
                links[fm.group(1)] = (bm.group(1), LIKMS + a["href"].replace("&amp;", "&"))
        if not links:
            continue
        label = div.find("span", recursive=False)
        book_ids = {v[0] for v in links.values()}
        if label is None or len(book_ids) != 1:
            raise ValueError(f"{base['bill_no']}: document link without a label or with two bookIds")
        docs.append({**base, "doc_seq": len(docs) + 1, "doc_type": " ".join(label.get_text(" ", strip=True).split()),
                     "book_id": book_ids.pop(), "pdf_url": links.get("PDF", (None, None))[1],
                     "hwp_url": links.get("HWP", (None, None))[1]})
    return docs


def parse_page(age: int, bill_no: str, html: str) -> tuple[list[dict], list[dict]]:
    """Rows of the review and meeting tables, and the document links of those rows."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows, docs, n_sections = [], [], 0
    for h4 in soup.find_all("h4"):
        section = " ".join(h4.get_text(" ", strip=True).split())
        if section not in SECTIONS:
            raise ValueError(f"{bill_no}: unknown heading {section!r}")
        n_sections += 1
        table = h4.find_next("table")
        if table is None or table.find_previous("h4") is not h4:
            raise ValueError(f"{bill_no}: no table under {section!r}")
        body = table.find("tbody")
        seq = 0
        for tr in (body.find_all("tr", recursive=False) if body else []):
            cells = {}
            for td in tr.find_all("td", recursive=False):
                cls = (td.get("class") or ["_"])[0]
                cells[cls] = td
            if not cells or set(cells) == {"_"}:
                continue  # placeholder row of an empty table
            if set(cells) != SECTIONS[section]:
                raise ValueError(f"{bill_no}: cells {sorted(cells)} under {section!r}")
            seq += 1
            row = dict.fromkeys(RAW_COLS)
            row.update(age=age, bill_no=bill_no, section=section, seq=seq)
            for cls, td in cells.items():
                if cls in CELL_COL:
                    row[CELL_COL[cls]] = cell_text(td)
            if "doc" in cells and "mtngName" in cells:
                for a in cells["doc"].find_all("a"):
                    m = CONF_NUM.search(f"{a.get('href', '')} {a.get('data-url') or ''}")
                    if m:
                        row["conf_num"] = int(m.group(1))
                        break
            if "doc" in cells:
                docs += parse_docs(cells["doc"], {"age": age, "bill_no": bill_no, "section": section, "seq": seq})
            rows.append(row)
    if n_sections == 0:
        raise ValueError(f"{bill_no}: no review section (status empty?)")
    return rows, docs


def extract(args) -> None:
    html_dir = Path(args.html_dir)
    bills = law_bills(Path(args.master_dir), ALL_AGES)
    missing = [b for b in bills.itertuples() if not page_path(html_dir, b.age, b.bill_no).exists()]
    if missing:
        sys.exit(f"extract: {len(missing):,} law bills have no cached page (first {missing[0].bill_no})."
                 " Run fetch first.")
    mtimes = []
    for age in ALL_AGES:
        rows, docs = [], []
        for b in bills[bills["age"] == age].itertuples():
            path = page_path(html_dir, age, b.bill_no)
            mtimes.append(path.stat().st_mtime)
            r, d = parse_page(age, b.bill_no, gzip.open(path).read().decode("utf-8", errors="replace"))
            rows += r
            docs += d
        df = pd.DataFrame(rows, columns=RAW_COLS).astype({"conf_num": "Int64", "seq": "int32"})
        write_parquet_atomic(df, RAW_DIR / f"likms_billinfo_{age}.parquet")
        dd = pd.DataFrame(docs, columns=DOC_COLS).astype({"seq": "int32", "doc_seq": "int32"})
        write_parquet_atomic(dd, RAW_DIR / f"likms_billinfo_docs_{age}.parquet")
        print(f"  {age}: {len(df):,} rows and {len(dd):,} document links from "
              f"{int((bills['age'] == age).sum()):,} pages")
    utc = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="minutes")
    META.write_text(json.dumps({
        "source": URL, "bills": len(bills),
        "fetched_from": utc(min(mtimes)), "fetched_to": utc(max(mtimes)),
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"extract: wrote data/raw/likms_billinfo_{{17..22}}.parquet, likms_billinfo_docs_{{17..22}}.parquet"
          f" and {META.name}")


# ── build ───────────────────────────────────────────────────────────

def norm_committee(name) -> str:
    return re.sub(r"\([^)]*\)|\s", "", str(name))


def check_identity(raw: pd.DataFrame, bills: pd.DataFrame) -> dict:
    cmt = raw[raw["section"] == "소관위 심사정보"]
    pages = cmt.groupby("bill_no").agg(names=("committee", lambda s: {norm_committee(x) for x in s.dropna()}),
                                       dates=("submit_dt", lambda s: set(s.dropna())))
    x = bills.set_index("bill_no").join(pages, how="inner")
    named = x[x["committee_nm"].notna() & (x["committee_nm"].astype(str) != "")]
    bad = [b for b, n, s in zip(named.index, named["committee_nm"], named["names"]) if norm_committee(n) not in s]
    if bad:
        sys.exit(f"build: {len(bad)} bills whose master committee is not on the page (first {bad[:5]})")
    dated = x[x["committee_dt"].notna()]
    ok = sum(str(d)[:10] in s for d, s in zip(dated["committee_dt"], dated["dates"]))
    if ok < 0.999 * len(dated):
        sys.exit(f"build: referral date agrees for {ok:,} of {len(dated):,} bills only")
    return {"committee_checked": len(named), "referral_date_checked": len(dated),
            "referral_date_agrees": ok}


def build(args) -> None:
    out = Path(args.out)
    bills = law_bills(Path(args.master_dir), ALL_AGES)
    paths = [RAW_DIR / f"likms_billinfo_{age}.parquet" for age in ALL_AGES]
    absent = [p.name for p in paths if not p.exists()]
    if absent:
        sys.exit(f"build: missing {absent}. Run extract first.")
    raw = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)

    known = bills.set_index("bill_no")["age"]
    stray = raw[raw["bill_no"].map(known) != raw["age"]]
    if len(stray):
        sys.exit(f"build: {stray['bill_no'].nunique()} raw bills are not law bills of that assembly")
    ident = check_identity(raw, bills)

    m = raw[raw["section"].isin(STAGES) & (raw["meeting_name"].notna() | raw["conf_num"].notna())].copy()
    m["stage"] = m["section"].map(STAGES)
    # meeting rows give 회의일 (mtngDt); plenary rows give 의결일 (procDt) and 상정일
    m["meeting_date"] = m["meeting_dt"].fillna(m["proc_dt"])
    m["present_date"] = m["present_dt"].where(m["stage"] == "plenary")
    m["bill_id"] = m["bill_no"].map(bills.set_index("bill_no")["bill_id"])
    bad_dates = m[~m["meeting_date"].fillna("").str.fullmatch(r"\d{4}-\d{2}-\d{2}")]
    if len(bad_dates):
        sys.exit(f"build: {len(bad_dates)} meeting rows without a YYYY-MM-DD date")
    if m.duplicated(["bill_no", "stage", "seq"]).any():
        sys.exit("build: duplicate (bill_no, stage, seq)")
    stage_order = {s: i for i, s in enumerate(STAGES.values())}
    m = (m.assign(_s=m["stage"].map(stage_order)).sort_values(["age", "bill_no", "_s", "seq"])
         [OUT_COLS].reset_index(drop=True))
    m["age"] = m["age"].astype("int64")
    m["seq"] = m["seq"].astype("int32")
    out.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(m, out / "bill_meetings.parquet")

    # coverage report, with the share of linked minutes found in the hearing summary
    summary = next((p for p in [out / "hearing_meetings_summary.parquet",
                                PROCESSED_DIR / "hearing_meetings_summary.parquet"] if p.exists()), None)
    conf = set(pd.read_parquet(summary, columns=["conf_num"])["conf_num"]) if summary else set()
    linked = m[m["conf_num"].notna()]
    rep = (m.groupby(["age", "stage"]).agg(bills=("bill_no", "nunique"), rows=("bill_no", "size"))
           .join(linked.groupby(["age", "stage"]).agg(rows_with_conf_num=("conf_num", "size"),
                                                      meetings=("conf_num", "nunique")))
           .join(linked[linked["conf_num"].isin(conf)].groupby(["age", "stage"])
                 .agg(rows_in_hearing_summary=("conf_num", "size")))
           .fillna(0).astype("int64").reset_index())
    rep = rep.merge(bills.groupby("age").size().rename("law_bills").reset_index(), on="age")
    (out / "reports").mkdir(exist_ok=True)
    rep.to_csv(out / "reports" / "bill_meetings_coverage.csv", index=False)
    not_found = linked[~linked["conf_num"].isin(conf)]
    print(f"build: bill_meetings.parquet {len(m):,} rows, {m['bill_no'].nunique():,} bills, "
          f"{linked['conf_num'].nunique():,} meetings with minutes; committee checked on "
          f"{ident['committee_checked']:,} bills, referral date agrees on {ident['referral_date_agrees']:,} "
          f"of {ident['referral_date_checked']:,}")
    if summary:
        print(f"  minutes not in {summary.name}: {not_found['conf_num'].nunique()} meetings, "
              f"{len(not_found)} rows, dated {not_found['meeting_date'].min()} to {not_found['meeting_date'].max()}")


def main() -> None:
    p = argparse.ArgumentParser(description="LIKMS bill pages: meetings that took up each law bill")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--html-dir", required=True, help="cache of the pages, {age}/{bill_no}.html.gz")
    f.add_argument("--ages", default="17-22")
    f.add_argument("--interval", type=float, default=0.7, help="seconds between requests")
    e = sub.add_parser("extract")
    e.add_argument("--html-dir", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", default=str(PROCESSED_DIR))
    for s in (f, e, b):
        s.add_argument("--master-dir", default=str(PROCESSED_DIR),
                       help="directory with master_bills_{age}.parquet (default data/processed)")
    args = p.parse_args()
    {"fetch": fetch, "extract": extract, "build": build}[args.command](args)


if __name__ == "__main__":
    main()
