"""
LIKMS committee documents: one row per document link of the bill pages
======================================================================
The LIKMS bill page lists, under each review row, the documents of that
stage: the 전문위원 검토보고서, the 심사보고서, the 위원회의결안 and others,
and under 법사위 체계자구 심사정보 the 체계자구검토보고서.
collect_likms_billinfo.py extract writes these links to
data/raw/likms_billinfo_docs_{age}.parquet. This script downloads the three
report types (TYPES), measures each file and builds bill_documents.parquet.
No document text is stored in the repository.

  fetch    download every TYPES document into {docs_dir}/{age}/{bill_no}_{book_id}.pdf
           (or .hwp). It takes the link the page gives, the PDF where the page has
           one and the HWP otherwise, and tries the HWP when the PDF request returns
           no file. A document whose file exists is skipped, so an interrupted run
           resumes. Failures are appended to data/raw/fetchlog/likms_docs.jsonl.
  measure  read the files and write data/raw/likms_doc_files.parquet (pages,
           characters, text_status, report_key per document) and
           data/raw/likms_doc_files_meta.json.
  build    write bill_documents.parquet and reports/bill_documents_coverage.csv to
           --out. build_all.sh runs this step.

The request is GET https://likms.assembly.go.kr/filegate/servlet/FileGate?bookId=..&type=..
(type 1 PDF, 0 HWP), which redirects to the file server. A missing file
comes back as HTTP 200 with a 387-byte HTML page (status nofile). A few HWP
files are MarkAny DRM containers (status drm). fetch spaces requests
--interval seconds apart (default 0.7) and retries other failures with backoff.

measure reads PDF text with poppler's pdftotext and counts images with
pdfimages, reads HWP 5 with pyhwp's hwp5txt, and reads HWPX from the <hp:t>
runs of Contents/section*.xml. text_status is

  text          the file has text
  placeholder   a 검토보고서 link of one page (or an HWP) under PLACEHOLDER_CHARS
                characters that only says no review report was written, for
                example "국회법 제58조제4항에 따라 바로 법안심사소위원회에 회부하여
                검토보고서가 없음"
  empty         under NO_TEXT_PER_PAGE characters per page and no image (a blank
                file); a one-page file with at least 10 characters stays text
  scanned       as empty, but the PDF holds images (a scanned report)
  unreadable    the file does not open; the file server holds it truncated
  not_obtained  no file: nofile or drm in the fetch log

report_key is the first 16 hex digits of the SHA-1 of the text after Unicode
NFKC normalization with everything but Hangul, Hanja, Latin letters and
digits removed (the middle dots ㆍ, · and ‧ go too). It is set for text documents only. LIKMS issues a new bookId,
and a PDF with different bytes, for every bill a report is attached to, so
the key is what identifies one report across the bills it covers. Copies
that differ in any letter or digit (a revised edition, a typo on the cover)
get different keys.

Rules, each of which stops build when it fails:

  1. Every link belongs to a law bill of that assembly in the master, and
     (bill_no, stage, seq, doc_seq) is unique.
  2. Every TYPES document has one measured row, and a bookId is listed
     under one document type.
  3. report_key is set exactly for the documents whose text_status is text.

Usage:
    python3 collect_likms_docs.py fetch --docs-dir DIR [--ages 17-22]
    python3 collect_likms_docs.py measure --docs-dir DIR [--workers 8]
    python3 collect_likms_docs.py build [--out data/processed]

fetch needs requests (pip install "kna[likms]"). measure needs pdftotext and
pdfimages (poppler) and hwp5txt (pip install pyhwp). build needs none of them.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import subprocess
import sys
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from collect_likms_billinfo import ALL_AGES, PROCESSED_DIR, RAW_DIR, law_bills, parse_ages
from kna_api import write_parquet_atomic

FETCHLOG = RAW_DIR / "fetchlog" / "likms_docs.jsonl"
FILES = RAW_DIR / "likms_doc_files.parquet"
META = RAW_DIR / "likms_doc_files_meta.json"
TYPES = ("검토보고서", "심사보고서", "체계자구검토보고서")
STAGES = {"소관위 심사정보": "committee", "관련위 심사정보": "related_committee",
          "법사위 체계자구 심사정보": "judiciary"}
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9",
           "Referer": "https://likms.assembly.go.kr/bill/"}
BACKOFF = [10, 30, 60, 120, 300]
MAGIC = {"pdf": (b"%PDF",), "hwp": (b"\xd0\xcf\x11\xe0", b"PK\x03\x04")}

PLACEHOLDER = re.compile(r"검토보고서?[가는]?(?:없|생략)|(?:직접|바로)회부")
PLACEHOLDER_CHARS = 600
NO_TEXT_PER_PAGE = 50
WS = re.compile(r"\s+")
# ㆍ (U+318D) is a Hangul letter that Korean text uses as a middle dot, so it goes with the punctuation
KEY_DROP = re.compile(r"[^0-9A-Za-z\u3131-\u318C\uAC00-\uD7A3\u4E00-\u9FFF]")
HWPX_RUN = re.compile(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>|(</hp:p>)", re.S)
TAG = re.compile(r"<[^>]+>")
STATUSES = ["text", "placeholder", "empty", "scanned", "unreadable", "not_obtained"]
FILE_COLS = ["age", "bill_no", "book_id", "doc_type", "file_format", "bytes", "pages", "chars",
             "text_status", "report_key", "note"]
OUT_COLS = ["age", "bill_no", "bill_id", "stage", "seq", "committee", "doc_seq", "doc_type", "book_id",
            "pdf_url", "hwp_url", "file_format", "pages", "chars", "text_status", "report_key", "report_bills"]


def read_links(ages: list[int]) -> pd.DataFrame:
    paths = [RAW_DIR / f"likms_billinfo_docs_{age}.parquet" for age in ages]
    absent = [p.name for p in paths if not p.exists()]
    if absent:
        sys.exit(f"missing {absent}. Run collect_likms_billinfo.py extract first.")
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def targets(links: pd.DataFrame) -> pd.DataFrame:
    t = links[links["doc_type"].isin(TYPES)].drop_duplicates(["bill_no", "book_id"])
    return t[["age", "bill_no", "book_id", "doc_type", "pdf_url", "hwp_url"]].reset_index(drop=True)


def doc_path(docs_dir: Path, age: int, bill_no: str, book_id: str, fmt: str) -> Path:
    return docs_dir / str(age) / f"{bill_no}_{book_id}.{fmt}"


def existing(docs_dir: Path, r) -> "Path | None":
    for fmt in ("pdf", "hwp"):
        p = doc_path(docs_dir, r.age, r.bill_no, r.book_id, fmt)
        if p.exists():
            return p
    return None


# ── fetch ───────────────────────────────────────────────────────────

def classify(status_code: int, body: bytes, fmt: str) -> str:
    if status_code == 200 and body.startswith(MAGIC[fmt]):
        return "ok"
    if status_code == 200 and body.startswith(b"<MARKANY"):
        return "drm"
    if status_code == 200 and body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        return "nofile"
    return "retry"


def fetch(args) -> None:
    import requests

    docs_dir = Path(args.docs_dir)
    t = targets(read_links(parse_ages(args.ages)))
    todo = [r for r in t.itertuples() if existing(docs_dir, r) is None]
    print(f"fetch: {len(t):,} documents, {len(t) - len(todo):,} on disk, {len(todo):,} to fetch")
    FETCHLOG.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    last, t0 = 0.0, time.time()

    def get(url: str, fmt: str) -> tuple[str, bytes, "str | None"]:
        nonlocal last
        verdict, body, err = "failed", b"", None
        for attempt in range(len(BACKOFF) + 1):
            time.sleep(max(0.0, last + args.interval - time.time()))
            last = time.time()
            try:
                r = session.get(url, timeout=120)
                body, verdict = r.content, classify(r.status_code, r.content, fmt)
                err = None if verdict == "ok" else f"HTTP {r.status_code}, {len(body)} bytes, starts {body[:12]!r}"
            except requests.RequestException as exc:
                verdict, err = "retry", f"{type(exc).__name__}: {exc}"[:300]
            if verdict != "retry":
                return verdict, body, err
            if attempt < len(BACKOFF):
                time.sleep(BACKOFF[attempt])
        return "failed", body, err

    for i, r in enumerate(todo, 1):
        tries = [("pdf", r.pdf_url)] if r.pdf_url else []
        tries += [("hwp", r.hwp_url)] if r.hwp_url else []
        for fmt, url in tries:
            verdict, body, err = get(url, fmt)
            if verdict == "ok":
                path = doc_path(docs_dir, r.age, r.bill_no, r.book_id, fmt)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(body)
                tmp.replace(path)
                break
            with open(FETCHLOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"bill_no": r.bill_no, "book_id": r.book_id, "age": int(r.age), "format": fmt,
                                    "status": verdict, "error": err,
                                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                                   ensure_ascii=False) + "\n")
            if verdict == "failed":
                break  # a network or server failure, not a missing file: try again in a later run
        if i % 500 == 0 or i == len(todo):
            rate = i / (time.time() - t0)
            print(f"  {i:,}/{len(todo):,}  {rate:.2f}/s  eta {(len(todo) - i) / rate / 3600:.1f} h", flush=True)


# ── measure ─────────────────────────────────────────────────────────

def run(cmd: list[str]) -> tuple["str | None", "str | None"]:
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    if out.returncode != 0:
        return None, f"{Path(cmd[0]).name} exit {out.returncode}"
    return out.stdout.decode("utf-8", "replace"), None


def hwpx_text(body: bytes) -> tuple["str | None", "str | None"]:
    try:
        z = zipfile.ZipFile(io.BytesIO(body))
        names = sorted((n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)),
                       key=lambda n: int(re.search(r"\d+", n).group()))
        parts = ["".join("\n" if br else html.unescape(TAG.sub("", t))
                         for t, br in HWPX_RUN.findall(z.read(n).decode("utf-8", "replace"))) for n in names]
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        return None, f"hwpx: {exc}"[:200]
    return ("\n".join(parts), None) if names else (None, "hwpx: no section xml")


def text_status(doc_type: str, fmt: str, pages: "int | None", flat: str, images: int) -> str:
    chars = len(flat)
    one_page = fmt == "hwp" or pages == 1
    if doc_type == "검토보고서" and one_page and chars < PLACEHOLDER_CHARS and PLACEHOLDER.search(flat):
        return "placeholder"
    if fmt == "hwp":
        return "empty" if chars < 10 else "text"
    if chars < NO_TEXT_PER_PAGE * max(pages or 1, 1) and not (pages == 1 and chars >= 10):
        return "scanned" if images > 0 else "empty"
    return "text"


def report_key(text: str) -> str:
    return hashlib.sha1(KEY_DROP.sub("", unicodedata.normalize("NFKC", text)).encode("utf-8")).hexdigest()[:16]


def measure_one(r, path: Path) -> dict:
    body = path.read_bytes()
    fmt = path.suffix[1:]
    rec = {"file_format": fmt, "bytes": len(body), "pages": None, "chars": None, "text_status": None,
           "report_key": None, "note": None}
    if fmt == "pdf":
        text, err = run(["pdftotext", "-enc", "UTF-8", str(path), "-"])
    elif body.startswith(MAGIC["hwp"][0]):
        text, err = run(["hwp5txt", str(path)])
    else:
        text, err = hwpx_text(body)
    if text is None:
        return {**rec, "text_status": "unreadable", "note": err}
    if fmt == "pdf":
        rec["pages"] = len(text.split("\f")[:-1] if text.endswith("\f") else text.split("\f"))
    flat = WS.sub("", text)
    rec["chars"] = len(flat)
    images = 0
    if fmt == "pdf" and len(flat) < NO_TEXT_PER_PAGE * max(rec["pages"], 1):
        out, _ = run(["pdfimages", "-list", str(path)])
        images = len((out or "").splitlines()[2:])
    rec["text_status"] = text_status(r.doc_type, fmt, rec["pages"], flat, images)
    if rec["text_status"] == "text":
        rec["report_key"] = report_key(text)
    return rec


def measure(args) -> None:
    docs_dir = Path(args.docs_dir)
    t = targets(read_links(ALL_AGES))
    log = {}
    if FETCHLOG.exists():
        for line in FETCHLOG.open(encoding="utf-8"):
            e = json.loads(line)
            log[(e["bill_no"], e["book_id"])] = e["status"]  # the last entry wins
    paths = [existing(docs_dir, r) for r in t.itertuples()]
    print(f"measure: {len(t):,} documents, {sum(p is not None for p in paths):,} files")

    def one(job):
        r, path = job
        base = {"age": int(r.age), "bill_no": r.bill_no, "book_id": r.book_id, "doc_type": r.doc_type}
        if path is None:
            return {**base, "text_status": "not_obtained", "note": log.get((r.bill_no, r.book_id), "not fetched")}
        return {**base, **measure_one(r, path)}

    t0, recs = time.time(), []
    with ThreadPoolExecutor(args.workers) as ex:
        for i, rec in enumerate(ex.map(one, zip(t.itertuples(), paths)), 1):
            recs.append(rec)
            if i % 5000 == 0 or i == len(t):
                print(f"  {i:,}/{len(t):,}  {i / (time.time() - t0):.0f}/s", flush=True)
    df = pd.DataFrame(recs, columns=FILE_COLS).astype({"bytes": "Int64", "pages": "Int64", "chars": "Int64"})
    write_parquet_atomic(df, FILES)
    mt = [p.stat().st_mtime for p in paths if p is not None]
    utc = lambda x: datetime.fromtimestamp(x, timezone.utc).isoformat(timespec="minutes")
    version = lambda cmd: subprocess.run(cmd, capture_output=True, text=True).stderr.splitlines()[0]
    META.write_text(json.dumps({
        "source": "https://likms.assembly.go.kr/filegate/servlet/FileGate",
        "documents": len(df), "files": len(mt), "downloaded_from": utc(min(mt)), "downloaded_to": utc(max(mt)),
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pdftotext": version(["pdftotext", "-v"]),
        "text_status": df["text_status"].value_counts().to_dict(),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"measure: wrote {FILES.name} and {META.name}; " + ", ".join(
        f"{k} {v:,}" for k, v in df["text_status"].value_counts().items()))


# ── build ───────────────────────────────────────────────────────────

def build(args) -> None:
    out = Path(args.out)
    bills = law_bills(Path(args.master_dir), ALL_AGES)
    links = read_links(ALL_AGES)
    if not FILES.exists():
        sys.exit(f"build: missing {FILES.name}. Run measure first.")
    files = pd.read_parquet(FILES)

    known = bills.set_index("bill_no")["age"]
    stray = links[links["bill_no"].map(known) != links["age"]]
    if len(stray):
        sys.exit(f"build: {stray['bill_no'].nunique()} bills of the document links are not law bills of that assembly")
    if links.duplicated(["bill_no", "section", "seq", "doc_seq"]).any():
        sys.exit("build: duplicate (bill_no, section, seq, doc_seq)")
    if not links["section"].isin(STAGES).all():
        sys.exit(f"build: document links under {sorted(set(links['section']) - set(STAGES))}")
    types = links.drop_duplicates(["bill_no", "book_id", "doc_type"])
    if types.duplicated(["bill_no", "book_id"]).any():
        sys.exit("build: a bookId is listed under two document types")
    want = targets(links)[["bill_no", "book_id"]]
    got = files[["bill_no", "book_id"]]
    if len(got) != len(want) or len(want.merge(got)) != len(want):
        sys.exit(f"build: {FILES.name} does not match the documents to measure. Run measure again.")
    bad = files[~files["text_status"].isin(STATUSES) | (files["report_key"].notna() != (files["text_status"] == "text"))]
    if len(bad):
        sys.exit(f"build: {len(bad)} measured rows with a bad text_status or report_key")

    raw = pd.concat([pd.read_parquet(RAW_DIR / f"likms_billinfo_{a}.parquet", columns=["bill_no", "section", "seq",
                                                                                       "committee"])
                     for a in ALL_AGES], ignore_index=True)
    d = links.merge(raw, on=["bill_no", "section", "seq"], how="left")
    d = d.merge(files.drop(columns=["age", "doc_type", "bytes", "note"]), on=["bill_no", "book_id"], how="left")
    d["stage"] = d["section"].map(STAGES)
    d["bill_id"] = d["bill_no"].map(bills.set_index("bill_no")["bill_id"])
    keyed = d[d["report_key"].notna()].drop_duplicates(["report_key", "bill_no"])
    d["report_bills"] = d["report_key"].map(keyed.groupby("report_key").size()).astype("Int64")
    stage_order = {s: i for i, s in enumerate(STAGES.values())}
    d = (d.assign(_s=d["stage"].map(stage_order)).sort_values(["age", "bill_no", "_s", "seq", "doc_seq"])
         [OUT_COLS].reset_index(drop=True))
    d["age"] = d["age"].astype("int64")
    out.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(d, out / "bill_documents.parquet")

    m = d[d["doc_type"].isin(TYPES)].drop_duplicates(["bill_no", "book_id"])
    rep = (m.groupby(["age", "doc_type"]).agg(documents=("book_id", "size"), bills=("bill_no", "nunique"),
                                             report_keys=("report_key", "nunique"))
           .join(pd.crosstab([m["age"], m["doc_type"]], m["text_status"]).reindex(columns=STATUSES, fill_value=0))
           .reset_index())
    (out / "reports").mkdir(exist_ok=True)
    rep.to_csv(out / "reports" / "bill_documents_coverage.csv", index=False)
    print(f"build: bill_documents.parquet {len(d):,} links of {d['bill_no'].nunique():,} bills; "
          f"{len(m):,} measured documents, " + ", ".join(f"{k} {v:,}" for k, v in m["text_status"].value_counts().items())
          + f"; {m['report_key'].nunique():,} distinct reports")


def main() -> None:
    p = argparse.ArgumentParser(description="LIKMS committee documents of each law bill")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--docs-dir", required=True, help="where the files go, {age}/{bill_no}_{book_id}.pdf|hwp")
    f.add_argument("--ages", default="17-22")
    f.add_argument("--interval", type=float, default=0.7, help="seconds between requests")
    m = sub.add_parser("measure")
    m.add_argument("--docs-dir", required=True)
    m.add_argument("--workers", type=int, default=8)
    b = sub.add_parser("build")
    b.add_argument("--out", default=str(PROCESSED_DIR))
    b.add_argument("--master-dir", default=str(PROCESSED_DIR),
                   help="directory with master_bills_{age}.parquet (default data/processed)")
    args = p.parse_args()
    {"fetch": fetch, "measure": measure, "build": build}[args.command](args)


if __name__ == "__main__":
    main()
