"""
LIKMS vote lists for the members the member-level API omits (22nd Assembly)
===========================================================================
The member-level vote endpoint nojepdqqaweusdfbi omits 16 members seated
during 2026, so 791 of the 1,847 22nd votes have fewer member rows than the
tally's MEMBER_TCNT. The per-member views of LIKMS and www.assembly.go.kr read
the same store and return nothing for these members either. The per-bill vote
page of LIKMS (의안 상세 > 표결정보) does list them. It gives the name of every
member who voted 찬성, 반대 or 기권, but no member ID and no list of 불참.

This script reads that page for every 22nd vote whose API rows fall short of
MEMBER_TCNT and writes only the rows the API lacks to
data/raw/roll_calls_22_supplement.parquet, with the columns of
data/raw/roll_calls_22.parquet plus `source`.

  source = likms         the member is on the page's 찬성, 반대 or 기권 list
  source = likms_absent  the member was seated but is on no list (vote 불참)

Rules, each of which stops the build when it fails:

  1. The page must be the requested vote (billId and billNo).
  2. Every 찬성, 반대 and 기권 row of the API must be on the page's list of the
     same kind. The names left over after removing the API rows are the
     members to add.
  3. A left-over name is matched to the one member of the 22nd roster
     (members_22.parquet) with that name and no API row on that vote. The page
     gives no MONA_CD, so the match is by name. The roster has one same-name
     pair, 박지원 (8BF5855P and H7X3372O). 8BF5855P has an API row on every
     vote, so a left-over 박지원 is H7X3372O. If a name has no such member, or
     more than one, the build stops.
  4. 불참 rows are written for the omitted members (those with no API row in
     the whole 22nd) who were seated but are on no list. A member is seated
     from the first vote at which MEMBER_TCNT minus the API rows steps up by
     their entry. Which member entered at which step is read from the date
     each omitted member first appears on a list. The build stops if the
     steps cannot be assigned to members unambiguously, or if the count ever
     falls.
  5. After the build, API rows plus supplement rows must equal MEMBER_TCNT on
     every vote read, and the 찬성, 반대 and 기권 counts must equal the page's
     lists.

The page is requested at most once per 1.1 seconds, without login. Each
answer is appended to data/raw/fetchlog/likms_voteinfo_22.jsonl, so an
interrupted run resumes and failed votes are retried on the next run. A
per-vote comparison of the page with the official tally is written to
data/raw/roll_calls_22_supplement_check.csv.

Usage:
    python3 collect_votes_likms.py                   # fetch what is missing, then build
    python3 collect_votes_likms.py --bill 2221432    # fetch one vote (BILL_NO or BILL_ID), no build
    python3 collect_votes_likms.py --build-only      # rebuild from the fetch log, no requests
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from kna_api import read_jsonl, write_parquet_atomic

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FETCHLOG_DIR = RAW_DIR / "fetchlog"

AGE = 22
AGE_NAME = "22nd"
VOTE_URL = "https://likms.assembly.go.kr/bill/bi/bill/detail/voteInfo.do"
DETAIL_URL = "https://likms.assembly.go.kr/bill/bi/billDetailPage.do?billId={}"
HEADERS = {"User-Agent": "Mozilla/5.0"}
MIN_INTERVAL = 1.1  # seconds between requests to the website
RETRY_WAITS = [5, 15, 45]

SOURCE_LISTED = "likms"
SOURCE_ABSENT = "likms_absent"
CATEGORIES = {"1": "찬성", "2": "반대", "3": "기권"}
VOTE_KINDS = list(CATEGORIES.values())
ABSENT = "불참"

# The one same-name pair of the 22nd roster. 8BF5855P is in the API
# throughout; H7X3372O, seated by the 2026 by-election, is omitted.
SAME_NAME_22 = {"박지원": ("8BF5855P", "H7X3372O")}

# Columns of data/raw/roll_calls_22.parquet that describe the vote, not the member
BILL_COLS = ["vote_date", "bill_no", "BILL_NAME", "bill_id_api", "LAW_TITLE",
             "CURR_COMMITTEE", "CURR_COMMITTEE_ID", "BILL_URL", "BILL_NAME_URL",
             "SESSION_CD", "CURRENTS_CD", "age_api", "bill_id", "age"]

LOG_DIR = Path(__file__).parent / "logs"
log = logging.getLogger("collect_votes_likms")


class SupplementError(RuntimeError):
    """A page or a match that the rules above do not allow."""


# ── Parsing ────────────────────────────────────────────────────────────────

_INFO_RE = re.compile(r"voteInfo = (\{.*?\});")
_SECTION_RE = re.compile(r'<h5 class="msal0(\d)">')
_ENTRY_RE = re.compile(
    r'<a href="([^"]*)"[^>]*>\s*<div>\s*<img[^>]*alt="국회의원:([^"]+)"')
_SLUG_RE = re.compile(r"/members/\d+nd/([^\"/?]+)")

INFO_KEYS = ["voteUnqId", "billId", "billNo", "procDt", "enrCnt", "voteCnt",
             "apprCnt", "opstCnt", "abstCnt", "nattCnt"]


def parse_vote_page(html: str) -> tuple[dict, dict[str, list[list]]]:
    """Return (vote info, {찬성|반대|기권: [[name, slug or None], ...]})."""
    m = _INFO_RE.search(html)
    if not m:
        raise SupplementError("no voteInfo object on the page")
    raw = json.loads(m.group(1))
    info = {k: raw.get(k) for k in INFO_KEYS}
    parts = _SECTION_RE.split(html)
    lists: dict[str, list[list]] = {}
    for i in range(1, len(parts), 2):
        kind = CATEGORIES.get(parts[i])
        if kind is None:
            raise SupplementError(f"unknown list section msal0{parts[i]}")
        entries = []
        for href, name in _ENTRY_RE.findall(parts[i + 1]):
            s = _SLUG_RE.search(href)
            entries.append([name.strip(), s.group(1) if s else None])
        lists[kind] = entries
    missing = [k for k in VOTE_KINDS if k not in lists]
    if missing:
        raise SupplementError(f"list sections missing: {missing}")
    return info, lists


# ── Fetching ───────────────────────────────────────────────────────────────

class Fetcher:
    """Sequential POSTs, at least MIN_INTERVAL seconds apart."""

    def __init__(self, min_interval: float = MIN_INTERVAL):
        self.min_interval = min_interval
        self.last = 0.0
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_page(self, bill_id: str, bill_no: str) -> str:
        last_err = ""
        for attempt, wait in enumerate([0] + RETRY_WAITS):
            if wait:
                time.sleep(wait)
            delay = self.last + self.min_interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.last = time.monotonic()
            try:
                r = self.session.post(
                    VOTE_URL, data={"billId": bill_id, "billNo": bill_no},
                    headers={"Referer": DETAIL_URL.format(bill_id)}, timeout=60)
                if r.status_code != 200:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                if "voteInfo = {" not in r.text:
                    raise SupplementError("answer without voteInfo")
                return r.text
            except (requests.RequestException, SupplementError) as e:
                last_err = f"{type(e).__name__}: {e}"
                log.warning(f"  {bill_no}: attempt {attempt + 1} failed ({last_err})")
        raise SupplementError(f"gave up after {len(RETRY_WAITS) + 1} attempts: {last_err}")


def fetch_pages(targets: pd.DataFrame, log_path: Path, fetcher: Fetcher | None = None,
                refresh: bool = False) -> dict[str, dict]:
    """Fetch the page of every target vote not yet logged as ok."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    done = read_jsonl(log_path)
    todo = targets if refresh else targets[
        targets["bill_id"].map(lambda b: done.get(b, {}).get("status") != "ok")]
    log.info(f"  LIKMS vote pages: {len(todo):,} to fetch, "
             f"{len(targets) - len(todo):,} already in {log_path.name}")
    if todo.empty:
        return done
    fetcher = fetcher or Fetcher()
    errors = 0
    with open(log_path, "a", encoding="utf-8") as out:
        for i, (bill_id, bill_no) in enumerate(zip(todo["bill_id"], todo["bill_no"]), 1):
            rec = {"key": bill_id, "bill_no": bill_no, "url": VOTE_URL,
                   "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            try:
                info, lists = parse_vote_page(fetcher.get_page(bill_id, bill_no))
                rec.update(status="ok", info=info, lists=lists)
            except SupplementError as e:
                rec.update(status="error", message=str(e))
                errors += 1
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            done[bill_id] = rec
            if i % 50 == 0 or i == len(todo):
                log.info(f"  {i:,}/{len(todo):,} pages, {errors} errors")
    if errors:
        log.warning(f"  {errors} pages failed; rerun to retry them")
    return done


# ── Inputs ─────────────────────────────────────────────────────────────────

def load_inputs(raw_dir: Path, members_dir: Path):
    api = pd.read_parquet(raw_dir / f"roll_calls_{AGE}.parquet")
    tallies = pd.read_parquet(raw_dir / f"ncocpgfiaoituanbr_{AGE}.parquet")
    roster = pd.read_parquet(members_dir / f"members_{AGE}.parquet",
                             columns=["mona_cd", "member_name", "member_name_hanja",
                                      "party_current", "district"])
    if roster["mona_cd"].duplicated().any():
        raise SupplementError(f"members_{AGE} has more than one row per mona_cd")
    return api, tallies, roster


def short_votes(api: pd.DataFrame, tallies: pd.DataFrame) -> pd.DataFrame:
    """Votes whose API rows fall short of MEMBER_TCNT, with the vote time."""
    t = tallies.rename(columns={"BILL_ID": "bill_id", "BILL_NO": "bill_no"})
    if t["bill_id"].duplicated().any():
        raise SupplementError("more than one 22nd tally row per BILL_ID")
    for c in ["MEMBER_TCNT", "VOTE_TCNT", "YES_TCNT", "NO_TCNT", "BLANK_TCNT"]:
        t[c] = pd.to_numeric(t[c], errors="coerce").astype("Int64")
    v = api.groupby("bill_id").agg(api_rows=("member_id", "size"),
                                   vote_time=("vote_date", "min"))
    out = t.merge(v, left_on="bill_id", right_index=True, how="left")
    out["api_rows"] = out["api_rows"].fillna(0).astype(int)
    out["rows_short"] = out["MEMBER_TCNT"] - out["api_rows"]
    return out


# ── Matching ───────────────────────────────────────────────────────────────

def leftover_names(api_bill: pd.DataFrame, lists: dict[str, list[list]]) -> dict[str, Counter]:
    """Names on each list after removing the API's rows of the same kind."""
    out = {}
    for kind in VOTE_KINDS:
        page = Counter(e[0] for e in lists[kind])
        api_names = Counter(api_bill.loc[api_bill["vote"] == kind, "member_name"])
        not_on_page = api_names - page
        if not_on_page:
            raise SupplementError(
                f"API {kind} rows not on the page's {kind} list: {dict(not_on_page)}")
        out[kind] = page - api_names
    return out


def match_names(leftover: dict[str, Counter], roster: pd.DataFrame,
                api_ids: set[str]) -> list[tuple[str, str]]:
    """(member_id, vote) for each left-over name, by name within the roster.

    Candidates are roster members with no API row on this vote. A name must
    match exactly one candidate, and each candidate at most one list entry.
    """
    cand = roster[~roster["mona_cd"].isin(api_ids)]
    by_name = cand.groupby("member_name")["mona_cd"].apply(list).to_dict()
    out, used = [], set()
    for kind in VOTE_KINDS:
        for name, n in sorted(leftover[kind].items()):
            ids = by_name.get(name, [])
            if name in SAME_NAME_22:
                pair = SAME_NAME_22[name]
                on_api = [p for p in pair if p in api_ids]
                if len(ids) != 1:
                    raise SupplementError(
                        f"{name} ({kind}): same-name pair {pair}, API rows for {on_api}, "
                        f"so the entry cannot be assigned")
            if len(ids) == 0:
                raise SupplementError(f"{name} ({kind}): no roster member of that name "
                                      f"without an API row on this vote")
            if len(ids) > 1:
                raise SupplementError(f"{name} ({kind}): ambiguous, candidates {ids}")
            if n > 1 or ids[0] in used:
                raise SupplementError(f"{name}: listed more than once")
            used.add(ids[0])
            out.append((ids[0], kind))
    return out


def seat_starts(votes: pd.DataFrame, listed: pd.DataFrame, omitted: list[str]) -> dict[str, str]:
    """First vote time at which each omitted member is counted in MEMBER_TCNT.

    votes: vote_time and rows_short (MEMBER_TCNT minus API rows) of every vote.
    listed: member_id and vote_time of every list entry of an omitted member.
    Members with no entry in the result were not seated during the votes read.
    """
    v = votes.sort_values("vote_time", kind="mergesort")
    first = listed.groupby("member_id")["vote_time"].min().to_dict()
    level = v.groupby("vote_time", sort=True)["rows_short"].agg(["min", "max"])
    if (level["min"] != level["max"]).any():
        bad = level[level["min"] != level["max"]].index.tolist()
        raise SupplementError(f"rows short of MEMBER_TCNT differ at one vote time: {bad[:5]}")
    level = level["min"]
    steps, prev = [], 0
    for t, n in level.items():
        if n < prev:
            raise SupplementError(f"rows short of MEMBER_TCNT fall from {prev} to {n} at {t}; "
                                  "a departure of an omitted member is not handled")
        if n > prev:
            steps.append((t, int(n - prev)))
        prev = n
    start: dict[str, str] = {}
    unassigned = set(omitted)
    for k, (t, inc) in enumerate(steps):
        t_next = steps[k + 1][0] if k + 1 < len(steps) else None
        early = [m for m in unassigned if m in first and first[m] < t]
        if early:
            raise SupplementError(f"{early} on a list before the step at {t}")
        now = sorted(m for m in unassigned if m in first
                     and (t_next is None or first[m] < t_next))
        if len(now) > inc:
            raise SupplementError(f"step at {t} adds {inc} members but {len(now)} "
                                  f"omitted members first appear before the next step: {now}")
        if len(now) < inc:
            pool = sorted(m for m in unassigned if m not in now)
            if len(pool) != inc - len(now):
                raise SupplementError(
                    f"step at {t} adds {inc} members, {len(now)} of them identified by a "
                    f"list entry; the other {inc - len(now)} cannot be chosen among {pool}")
            now += pool
        for m in now:
            start[m] = t
            unassigned.discard(m)
    return start


# ── Build ──────────────────────────────────────────────────────────────────

def build_supplement(api: pd.DataFrame, votes: pd.DataFrame, roster: pd.DataFrame,
                     pages: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Supplement rows and a per-vote check table, from the logged pages."""
    targets = votes[votes["rows_short"] > 0]
    missing = [b for b in targets["bill_id"] if pages.get(b, {}).get("status") != "ok"]
    if missing:
        raise SupplementError(f"{len(missing)} short votes have no page in the log, "
                              f"e.g. {missing[:3]}")
    omitted = sorted(set(roster["mona_cd"]) - set(api["member_id"]))
    log.info(f"  Omitted members (no API row in the {AGE_NAME}): {len(omitted)} "
             f"({', '.join(roster.set_index('mona_cd').loc[omitted, 'member_name'])})")

    api_by_bill = {b: g for b, g in api.groupby("bill_id")}
    listed_rows, checks = [], []
    for r in targets.itertuples(index=False):
        rec = pages[r.bill_id]
        info, lists = rec["info"], rec["lists"]
        if info["billId"] != r.bill_id or str(info["billNo"]) != str(r.bill_no):
            raise SupplementError(f"{r.bill_no}: page is for {info['billId']} / {info['billNo']}")
        a = api_by_bill[r.bill_id]
        try:
            matched = match_names(leftover_names(a, lists), roster, set(a["member_id"]))
        except SupplementError as e:
            raise SupplementError(f"{r.bill_no} ({r.bill_id}): {e}") from None
        for member_id, kind in matched:
            listed_rows.append((r.bill_id, member_id, kind, r.vote_time))
        checks.append({
            "bill_id": r.bill_id, "bill_no": r.bill_no, "proc_dt": r.PROC_DT,
            "fetched_at": rec["fetched_at"], "vote_unq_id": info["voteUnqId"],
            "tally_members": r.MEMBER_TCNT, "tally_voted": r.VOTE_TCNT,
            "tally_yes": r.YES_TCNT, "tally_no": r.NO_TCNT, "tally_abstain": r.BLANK_TCNT,
            "page_members": info["enrCnt"], "page_voted": info["voteCnt"],
            "page_yes": info["apprCnt"], "page_no": info["opstCnt"],
            "page_abstain": info["abstCnt"],
            "list_yes": len(lists["찬성"]), "list_no": len(lists["반대"]),
            "list_abstain": len(lists["기권"]),
            "api_rows": r.api_rows, "rows_short": r.rows_short,
            "added_listed": len(matched)})
    listed = pd.DataFrame(listed_rows, columns=["bill_id", "member_id", "vote", "vote_time"])
    not_omitted = sorted(set(listed["member_id"]) - set(omitted))
    if not_omitted:
        raise SupplementError(f"list entries matched to members the API has elsewhere: "
                              f"{not_omitted}")

    start = seat_starts(votes, listed[["member_id", "vote_time"]], omitted)
    names = roster.set_index("mona_cd")["member_name"]
    for m in omitted:
        log.info(f"    {names[m]} ({m}): counted from {start.get(m, 'never')}")

    # 불참 rows: seated omitted members on no list
    absent_rows = []
    listed_keys = set(zip(listed["bill_id"], listed["member_id"]))
    for r in targets.itertuples(index=False):
        for m, t in start.items():
            if t <= r.vote_time and (r.bill_id, m) not in listed_keys:
                absent_rows.append((r.bill_id, m, ABSENT, r.vote_time))
    absent = pd.DataFrame(absent_rows, columns=listed.columns)
    listed["source"] = SOURCE_LISTED
    absent["source"] = SOURCE_ABSENT
    supp = pd.concat([listed, absent], ignore_index=True)

    # Member columns from the roster, vote columns from the vote's API rows
    bill = (api.sort_values("vote_date", kind="mergesort")
            .drop_duplicates("bill_id")[BILL_COLS].set_index("bill_id"))
    ros = roster.set_index("mona_cd")
    out = supp.join(bill.drop(columns=["vote_date"]), on="bill_id")
    out["vote_date"] = out["vote_time"]
    out["member_name"] = out["member_id"].map(ros["member_name"])
    out["member_hanja"] = out["member_id"].map(ros["member_name_hanja"])
    out["party"] = out["member_id"].map(ros["party_current"])
    out["district"] = out["member_id"].map(ros["district"])
    for c in ["MEMBER_NO", "POLY_CD", "ORIG_CD", "DEPT_CD"]:
        out[c] = None
    out["DISP_ORDER"] = pd.array([pd.NA] * len(out), dtype="Int64")
    out = out[list(api.columns) + ["source"]]
    out = out.sort_values(["vote_date", "bill_id", "member_id"], kind="mergesort")
    out = out.reset_index(drop=True)

    # Rule 5
    check = pd.DataFrame(checks)
    added = out.groupby("bill_id").agg(
        added=("member_id", "size"), added_absent=("source", lambda s: (s == SOURCE_ABSENT).sum()))
    check = check.merge(added, left_on="bill_id", right_index=True, how="left")
    check[["added", "added_absent"]] = check[["added", "added_absent"]].fillna(0).astype(int)
    check["rows_after"] = check["api_rows"] + check["added"]
    both = pd.concat([api[["bill_id", "member_id", "vote"]],
                      out[["bill_id", "member_id", "vote"]]], ignore_index=True)
    if both.duplicated(["bill_id", "member_id"]).any():
        raise SupplementError("a supplement row duplicates an API row")
    cnt = both[both["bill_id"].isin(check["bill_id"])].groupby("bill_id")["vote"].value_counts()
    cnt = cnt.unstack(fill_value=0).reindex(columns=VOTE_KINDS, fill_value=0)
    check = check.join(cnt.rename(columns={"찬성": "yes_after", "반대": "no_after",
                                           "기권": "abstain_after"}), on="bill_id")
    short_left = check[check["rows_after"] != check["tally_members"]]
    if len(short_left):
        raise SupplementError(f"{len(short_left)} votes still differ from MEMBER_TCNT, e.g. "
                              f"{short_left['bill_no'].head(5).tolist()}")
    lists_off = check[(check["yes_after"] != check["list_yes"])
                      | (check["no_after"] != check["list_no"])
                      | (check["abstain_after"] != check["list_abstain"])]
    if len(lists_off):
        raise SupplementError(f"{len(lists_off)} votes differ from the page's lists")
    check["page_header_matches_tally"] = (
        (check["page_members"] == check["tally_members"])
        & (check["page_voted"] == check["tally_voted"])
        & (check["page_yes"] == check["tally_yes"]) & (check["page_no"] == check["tally_no"])
        & (check["page_abstain"] == check["tally_abstain"]))
    check["lists_match_tally"] = (
        (check["list_yes"] == check["tally_yes"]) & (check["list_no"] == check["tally_no"])
        & (check["list_abstain"] == check["tally_abstain"]))
    return out, check


def run_build(raw_dir: Path, members_dir: Path, log_path: Path):
    api, tallies, roster = load_inputs(raw_dir, members_dir)
    votes = short_votes(api, tallies)
    pages = read_jsonl(log_path)
    supp, check = build_supplement(api, votes, roster, pages)
    outpath = raw_dir / f"roll_calls_{AGE}_supplement.parquet"
    write_parquet_atomic(supp, outpath)
    check.to_csv(raw_dir / f"roll_calls_{AGE}_supplement_check.csv", index=False)
    by_src = supp["source"].value_counts().to_dict()
    log.info(f"  Saved: {outpath.name} ({len(supp):,} rows, {by_src}, "
             f"{supp['bill_id'].nunique():,} votes, {supp['member_id'].nunique()} members)")
    log.info(f"  Votes read: {len(check):,}. API plus supplement rows equal MEMBER_TCNT "
             f"on all of them.")
    log.info(f"  Page lists equal the official tally on {int(check['lists_match_tally'].sum()):,}; "
             f"page header equals the tally on {int(check['page_header_matches_tally'].sum()):,}")
    for r in check[~check["lists_match_tally"]].itertuples():
        log.warning(f"    {r.bill_no} ({r.proc_dt}): lists {r.list_yes}/{r.list_no}/"
                    f"{r.list_abstain}, tally {r.tally_yes}/{r.tally_no}/{r.tally_abstain}, "
                    f"page header {r.page_yes}/{r.page_no}/{r.page_abstain}")
    return supp, check


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--bill", help="Fetch one vote by BILL_NO or BILL_ID, and do not build")
    parser.add_argument("--build-only", action="store_true",
                        help="Build the supplement from the fetch log without requests")
    parser.add_argument("--refresh", action="store_true",
                        help="Fetch every short vote again, even if logged as ok")
    parser.add_argument("--members-dir", type=Path, default=PROCESSED_DIR,
                        help=f"Directory with members_{AGE}.parquet (default: data/processed)")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_DIR / "votes_likms.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)])

    log_path = FETCHLOG_DIR / f"likms_voteinfo_{AGE}.jsonl"
    if not args.build_only:
        api, tallies, _ = load_inputs(RAW_DIR, args.members_dir)
        votes = short_votes(api, tallies)
        targets = votes[votes["rows_short"] > 0]
        if args.bill:
            targets = votes[(votes["bill_no"] == args.bill) | (votes["bill_id"] == args.bill)]
            if targets.empty:
                raise SystemExit(f"{args.bill} is not a {AGE_NAME} vote")
        log.info(f"LIKMS vote pages for {len(targets):,} votes of the {AGE_NAME} Assembly")
        done = fetch_pages(targets, log_path, refresh=args.refresh or bool(args.bill))
        failed = [b for b in targets["bill_id"] if done.get(b, {}).get("status") != "ok"]
        if failed:
            log.error(f"  {len(failed)} pages failed; rerun to retry. Not building.")
            sys.exit(1)
        if args.bill:
            rec = done[targets["bill_id"].iloc[0]]
            log.info(f"  {rec['info']} lists "
                     f"{ {k: len(v) for k, v in rec['lists'].items()} }")
            return
    try:
        run_build(RAW_DIR, args.members_dir, log_path)
    except SupplementError as e:
        log.error(f"  Build stopped: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
