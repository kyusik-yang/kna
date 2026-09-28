"""Rich terminal formatters for kna CLI."""

from __future__ import annotations

import sys
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# TTY detection for graceful degradation when piping
_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

# Accent: NYU violet
_ACCENT = (165, 110, 240)

_ORDINAL = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd"}


def ordinal(n: int) -> str:
    """Return ordinal string, e.g. 22 -> '22nd'."""
    return f"{n}{_ORDINAL.get(n, 'th')}"


def _rgb(r: int, g: int, b: int, text: str) -> str:
    if _COLOR:
        return f"[rgb({r},{g},{b})]{text}[/]"
    return text


def accent(text: str) -> str:
    return _rgb(*_ACCENT, text)


def dim(text: str) -> str:
    return f"[dim]{text}[/]" if _COLOR else text


def status_style(status: str) -> str:
    """Color-code bill status."""
    if status in ("원안가결", "수정가결"):
        return f"[green]{status}[/]" if _COLOR else status
    if status in ("부결", "폐기", "철회"):
        return f"[red]{status}[/]" if _COLOR else status
    if status == "계류중":
        return f"[yellow]{status}[/]" if _COLOR else status
    if status in ("대안반영폐기", "수정안반영폐기"):
        return f"[cyan]{status}[/]" if _COLOR else status
    if status == "임기만료폐기":
        return f"[dim]{status}[/]" if _COLOR else status
    return status


def truncate(s, maxlen: int = 60) -> str:
    if pd.isna(s):
        return ""
    s = str(s).replace("\n", " ").strip()
    return s[:maxlen] + "..." if len(s) > maxlen else s


# ── Info ────────────────────────────────────────────────────────────

def _num(v) -> str:
    return "-" if v is None else f"{v:,}"


def print_info(file_info: list[dict], rc_count: int, ip_count: int,
               cm_count: int, txt_count: int, mem_count: int = 0,
               asset_count: int = 0, freshness: str = "",
               rc_exp_count: int = 0, ip_vintage: str = "",
               extra: Optional[list[tuple[str, int, str]]] = None) -> None:
    """Print database overview.

    Laws, Enacted and Promulgated count 법률안 only.
    """
    total_bills = sum(r["total"] for r in file_info)
    total_laws = sum(r.get("laws", 0) for r in file_info)
    total_enacted = sum(r.get("enacted_laws", r["enacted"]) for r in file_info)
    proms = [r.get("promulgated") for r in file_info]
    total_prom = None if any(p is None for p in proms) else sum(proms)

    t = Table(
        title=accent("Korean National Assembly Database"),
        border_style="dim", show_lines=False, padding=(0, 1),
    )
    t.add_column("Assembly", style="bold", width=18)
    t.add_column("Bills", justify="right", width=8)
    t.add_column("Laws", justify="right", width=8)
    t.add_column("Enacted", justify="right", width=8)
    t.add_column("Promulg.", justify="right", width=8)
    t.add_column("Cols", justify="right", width=5, style="dim")

    age_labels = {
        17: "17th (2004-08)", 18: "18th (2008-12)", 19: "19th (2012-16)",
        20: "20th (2016-20)", 21: "21st (2020-24)", 22: "22nd (2024-)",
    }
    for r in file_info:
        t.add_row(age_labels.get(r["age"], ordinal(r["age"])),
                  f"{r['total']:,}", _num(r.get("laws")),
                  _num(r.get("enacted_laws", r["enacted"])),
                  _num(r.get("promulgated")), str(r["ncol"]))

    t.add_section()
    t.add_row("[bold]Total[/]", f"[bold]{total_bills:,}[/]",
              f"[bold]{total_laws:,}[/]", f"[bold]{total_enacted:,}[/]",
              f"[bold]{_num(total_prom)}[/]", "")

    console.print(t)
    console.print(f"  {dim('Laws = 법률안. Enacted = 법률안 원안가결 + 수정가결 (final result).')}")
    console.print(f"  {dim('Promulg. = 법률안 with a promulgation date (became law).')}")
    console.print()
    console.print(f"  Roll call votes   {rc_count:>10,}  {dim('(17-22nd, member-level votes)')}")
    if rc_exp_count:
        console.print(f"  16th votes        {rc_exp_count:>10,}  "
                      f"{dim('(experimental, fragmentary, separate file)')}")
    ip_note = "20-22nd, bridged W-NOMINATE" + (f", {ip_vintage}" if ip_vintage else "")
    console.print(f"  Ideal points      {ip_count:>10,}  {dim(f'({ip_note})')}")
    console.print(f"  Members           {mem_count:>10,}  {dim('(17-22nd, party/district/committee)')}")
    console.print(f"  Asset disclosures {asset_count:>10,}  {dim('(19-22nd, member-year wealth)')}")
    console.print(f"  Committee mtgs    {cm_count:>10,}  {dim('(17-22nd)')}")
    console.print(f"  Bill texts        {txt_count:>10,}  {dim('(17-22nd law bills, propose-reason)')}")
    for label, count, note in extra or []:
        console.print(f"  {label:<17} {count:>10,}  {dim(f'({note})')}")
    console.print(f"  Data freshness    {freshness:>10}")
    console.print()


# ── Search results ──────────────────────────────────────────────────

def print_search_results(df: pd.DataFrame, keyword: str,
                         age: Optional[int], total: int) -> None:
    """Print bill search results as a Rich table."""
    scope = f"{ordinal(age)} Assembly" if age else "All assemblies"
    console.print(f"  {accent(scope)} · \"{keyword}\" · {len(df)} of {total} results\n")

    t = Table(border_style="dim", show_lines=False, padding=(0, 1))
    t.add_column("No", style="dim", width=8)
    t.add_column("Date", width=10)
    t.add_column("Committee", width=10)
    t.add_column("Proposer", width=8)
    t.add_column("Status", width=10)
    t.add_column("Title", no_wrap=True, max_width=50)

    for _, row in df.iterrows():
        dt = row.get("ppsl_dt")
        date_str = pd.Timestamp(dt).strftime("%Y-%m-%d") if pd.notna(dt) else ""
        t.add_row(
            str(row.get("bill_no", "")),
            date_str,
            truncate(row.get("committee_nm", ""), 10),
            truncate(row.get("rst_proposer", ""), 8),
            status_style(str(row.get("status", ""))),
            truncate(row.get("bill_nm", ""), 50),
        )

    console.print(t)


# ── Bill detail (show) ──────────────────────────────────────────────

_LIFECYCLE_STAGES = [
    ("발의", ["ppsl_dt"]),
    ("소관위 회부", ["committee_dt"]),
    ("소관위 상정", ["cmt_present_dt"]),
    ("소관위 처리", ["cmt_proc_dt"]),
    ("법사위 회부", ["law_submit_dt", "law_cmmt_dt"]),
    ("본회의 의결", ["rgs_rsln_dt"]),
    ("공포", ["prom_dt"]),
]

_FLOOR_RESULTS = ("원안가결", "수정가결", "부결")


def _first_date(row: pd.Series, cols: list[str]):
    for col in cols:
        dt = row.get(col)
        if dt is not None and pd.notna(dt):
            return dt
    return None


def _floor_decided(row: pd.Series) -> bool:
    """True when the bill had a plenary floor decision.

    rgs_rsln_dt alone is not enough: it is the final disposition date of
    every processed bill (대안반영폐기, 철회, 임기만료폐기, ...).
    """
    flag = row.get("plenary_decided")
    if flag is not None and pd.notna(flag):
        return int(flag) == 1
    rslt = row.get("rgs_conf_rslt")
    if rslt is None or pd.isna(rslt):
        rslt = row.get("status")
    return rslt in _FLOOR_RESULTS


def print_bill_detail(row: pd.Series) -> None:
    """Print a single bill with lifecycle timeline."""
    lines = []
    lines.append(f"[bold]{row.get('bill_nm', '')}[/]")
    lines.append("")

    fields = [
        ("bill_no", row.get("bill_no", "")),
        ("assembly", ordinal(int(row.get("age", 0)))),
        ("kind", row.get("bill_kind", "")),
        ("proposer", row.get("proposer_text", row.get("rst_proposer", ""))),
        ("committee", row.get("committee_nm", "")),
        ("status", row.get("status", "")),
    ]
    vetoed = row.get("vetoed")
    if vetoed is not None and pd.notna(vetoed) and int(vetoed) == 1:
        first = row.get("first_plenary_rslt")
        fields.append(("vetoed", "재의요구" + (f" after {first}" if pd.notna(first) else "")))
    for label, val in fields:
        val_str = truncate(val, 50)
        if label == "status":
            val_str = status_style(str(val))
        lines.append(f"  {dim(f'{label:<14}')} {val_str}")

    # Lifecycle timeline
    lines.append("")
    lines.append(f"  {'LIFECYCLE':<14}  {'date':>12}  {'days':>6}")

    stages = list(_LIFECYCLE_STAGES)
    status = row.get("status")
    if not _floor_decided(row):
        # No floor decision: show the final disposition instead of 본회의 의결
        stages = [s for s in stages if s[0] != "본회의 의결"]
        if pd.notna(status) and status != "계류중":
            stages.insert(-1, (f"처리 ({status})", ["proc_dt", "rgs_rsln_dt"]))
    else:
        # Without rgs_rsln_dt, the floor date of a vetoed bill is its first
        # passage (veto_events); for any other bill it is the disposal date
        at = [s[0] for s in stages].index("본회의 의결")
        vetoed = pd.notna(row.get("veto_dt"))
        stages[at] = ("본회의 의결", ["rgs_rsln_dt", "first_plenary_dt" if vetoed else "proc_dt"])
        if vetoed:
            stages[at + 1:at + 1] = [("재의요구", ["veto_dt"])]
            if pd.notna(row.get("revote_dt")):
                stages[at + 2:at + 2] = [(f"재의결 ({row.get('revote_rslt')})", ["revote_dt"])]

    base_dt = row.get("ppsl_dt")
    for label, cols in stages:
        dt = _first_date(row, cols)
        if dt is not None:
            dt_ts = pd.Timestamp(dt)
            date_str = dt_ts.strftime("%Y-%m-%d")
            if pd.notna(base_dt) and cols[0] != "ppsl_dt":
                delta = (dt_ts - pd.Timestamp(base_dt)).days
                days_str = f"+{delta}"
            else:
                days_str = "-"
            marker = "[green]●[/]" if _COLOR else "●"
        else:
            date_str = "--"
            days_str = ""
            marker = "[dim]○[/]" if _COLOR else "○"
        lines.append(f"  {marker} {label:<10}  {date_str:>12}  {days_str:>6}")

    # Vote tally (the first floor passage for a vetoed bill)
    vy = row.get("vote_yes")
    if vy is not None and pd.notna(vy):
        vn = int(row.get("vote_no", 0))
        va = int(row.get("vote_abstain", 0))
        vt = row.get("vote_member_total")
        seats = f" (재적 {int(vt)})" if vt is not None and pd.notna(vt) else ""
        first = ", first passage" if pd.notna(row.get("veto_dt")) else ""
        lines.append("")
        lines.append(f"  VOTE   찬성 {int(vy)} / 반대 {vn} / 기권 {va}{seats}{first}")

    # Propose reason text
    text = row.get("propose_reason")
    if pd.notna(text) and str(text).strip():
        lines.append("")
        lines.append(f"  {dim('PROPOSE REASON')}")
        # Wrap text at ~70 chars
        text_str = str(text).strip()
        for i in range(0, min(len(text_str), 350), 70):
            lines.append(f"  {text_str[i:i+70]}")
        if len(text_str) > 350:
            lines.append(f"  {dim(f'... ({len(text_str):,} chars total)')}")

    # Link
    link = row.get("link_url")
    if pd.notna(link):
        lines.append("")
        lines.append(f"  {dim(str(link))}")

    panel = Panel(
        "\n".join(lines),
        border_style="dim",
        padding=(1, 2),
    )
    console.print(panel)


# ── Legislator profile ──────────────────────────────────────────────

def print_legislator(
    name: str,
    mona: str,
    age: Optional[int],
    term: int,
    party: str,
    party_current: str = "",
    party_end: str = "",
    district: str = "",
    committee: str = "",
    sex: str = "",
    election_type: str = "",
    seniority: str = "",
    reelection: str = "",
    ideal_point: Optional[float] = None,
    rank: Optional[int] = None,
    total_in_term: Optional[int] = None,
    ip_vintage: str = "",
    terms: pd.DataFrame = None,
    bills_df: pd.DataFrame = None,
    top_enacted: pd.DataFrame = None,
) -> None:
    """Print legislator profile.

    With an assembly, every field describes that term. Without one, the
    header fields describe the latest term and TERMS lists every term.
    """
    served = [int(a) for a in terms["age"]] if terms is not None and len(terms) else [term]
    if age:
        age_str = f"{ordinal(age)} Assembly"
    else:
        age_str = ", ".join(ordinal(a) for a in served) + " Assembly"
    console.print(f"\n  {accent(name)} ({mona}) · {age_str}")
    console.print(f"  {'─' * 40}")
    if not age and len(served) > 1:
        console.print(f"  {dim(f'latest term: {ordinal(term)}')}")

    if party:
        console.print(f"  {dim('party'):<20} {party} (at election)")
    if party_end and party_end != party:
        console.print(f"  {dim('party at end'):<20} {party_end} (end of term or departure)")
    if party_current and party_current not in (party, party_end):
        console.print(f"  {dim('current party'):<20} {party_current}")
    if district:
        console.print(f"  {dim('district'):<20} {district}")
    if committee:
        console.print(f"  {dim('committee'):<20} {truncate(committee, 60)}")
    if election_type:
        if seniority:
            tenure = f" ({seniority} in the {ordinal(term)})"
        elif reelection:
            tenure = f" ({reelection}, lifetime count)"
        else:
            tenure = ""
        console.print(f"  {dim('election'):<20} {election_type}{tenure}")
    if ideal_point is not None:
        label = f"{ordinal(term)}, bridged W-NOMINATE" + (f", {ip_vintage}" if ip_vintage else "")
        console.print(f"  {dim('ideal point'):<20} {ideal_point:.3f} ({label})")
    if rank is not None and total_in_term is not None:
        console.print(f"  {dim('rank'):<20} {rank} / {total_in_term} in the "
                      f"{ordinal(term)} (← 진보 ··· 보수 →)")

    # One row per term when the profile spans several assemblies
    if not age and terms is not None and len(terms) > 1:
        t = Table(border_style="dim", show_lines=False, padding=(0, 1))
        for col, kw in [("Term", {}), ("Party", {}), ("District", {}),
                        ("Seniority", {}), ("Ideal pt", {"justify": "right"}),
                        ("Rank", {"justify": "right"})]:
            t.add_column(col, **kw)
        for _, r in terms.iterrows():
            ip = r.get("ideal_point")
            has_ip = ip is not None and pd.notna(ip)
            t.add_row(
                ordinal(int(r["age"])),
                truncate(r.get("party", ""), 12),
                truncate(r.get("district", ""), 16),
                truncate(r.get("seniority", ""), 6),
                f"{ip:.3f}" if has_ip else "-",
                f"{int(r['rank'])} / {int(r['total_in_term'])}" if has_ip else "-",
            )
        console.print(f"\n  TERMS {dim('(ideal point: bridged W-NOMINATE; rank 1 = most liberal)')}")
        console.print(t)

    # Bill record
    total = len(bills_df)
    enacted = int(bills_df["enacted"].sum()) if "enacted" in bills_df.columns else 0
    passed = int(bills_df["passed"].sum()) if "passed" in bills_df.columns else 0
    alt = passed - enacted

    console.print(f"\n  BILL RECORD {dim('(lead proposer, including joint leads)')}")
    console.print(f"  {dim('led'):<20} {total} bills")
    if total:
        console.print(f"  {dim('enacted'):<20} {enacted} ({enacted/total*100:.1f}%)")
    if "promulgated" in bills_df.columns and total:
        console.print(f"  {dim('promulgated'):<20} {int(bills_df['promulgated'].sum())}")
    if alt > 0:
        console.print(f"  {dim('alt-reflected'):<20} {alt}")

    if "days_to_proc" in bills_df.columns:
        med = bills_df["days_to_proc"].dropna().median()
        if pd.notna(med):
            console.print(f"  {dim('median days'):<20} {int(med)}d (proposal → processing)")

    # Top enacted bills
    if top_enacted is not None and len(top_enacted) > 0:
        console.print(f"\n  TOP ENACTED BILLS")
        for i, (_, b) in enumerate(top_enacted.head(5).iterrows(), 1):
            dt = pd.Timestamp(b["ppsl_dt"]).strftime("%Y-%m-%d") if pd.notna(b.get("ppsl_dt")) else ""
            console.print(f"  {i}. {truncate(b.get('bill_nm', ''), 50)} ({dt}) → {b.get('status', '')}")

    console.print()


def print_legislator_candidates(name: str, age: Optional[int],
                                candidates: pd.DataFrame) -> None:
    """Print the legislators who share a name, so one can be picked by MONA_CD."""
    scope = f"the {ordinal(age)} Assembly" if age else "the 17th-22nd Assembly"
    n = candidates["mona_cd"].nunique()
    console.print(f"\n  {n} legislators named {accent(name)} in {scope}:\n")
    t = Table(border_style="dim", show_lines=False, padding=(0, 1))
    for col in ["MONA_CD", "Term", "Party", "District", "Election"]:
        t.add_column(col)
    for _, r in candidates.iterrows():
        t.add_row(str(r["mona_cd"]), ordinal(int(r["age"])),
                  truncate(r.get("party", ""), 14), truncate(r.get("district", ""), 24),
                  truncate(r.get("election_type", ""), 8))
    console.print(t)
    example = candidates["mona_cd"].iloc[0]
    where = f" --assembly {age}" if age else ""
    console.print(f"\n  Pick one with --mona, e.g. kna legislator {name}{where} --mona {example}\n")


# ── Stats: funnel ───────────────────────────────────────────────────

def print_funnel(stages: list[tuple[str, int]], age: int) -> None:
    """Print legislative funnel as a horizontal bar chart."""
    console.print(f"\n  {accent(f'{ordinal(age)} Assembly')} · Legislative Funnel (법률안 only)\n")

    base = stages[0][1] if stages else 1
    max_bar = 30

    t = Table(border_style="dim", show_lines=False, padding=(0, 1))
    t.add_column("Stage", width=12)
    t.add_column("Bills", justify="right", width=8)
    t.add_column("Rate", justify="right", width=7)
    t.add_column("", width=max_bar + 1)

    for label, count in stages:
        pct = count / base * 100 if base else 0
        bar_len = int(count / base * max_bar) if base else 0
        bar = Text("█" * bar_len, style="rgb(165,110,240)") if _COLOR else Text("█" * bar_len)
        t.add_row(label, f"{count:,}", f"{pct:.1f}%", bar)

    console.print(t)
    console.print(f"  {dim('Each stage counts bills that reached it or a later stage.')}")
    console.print(f"  {dim('본회의 의결 = floor decision (원안가결, 수정가결, 부결); 공포 = promulgated.')}")
    console.print()


# ── Stats: passage rate ─────────────────────────────────────────────

def print_passage_rate(data: list[dict]) -> None:
    """Print cross-assembly passage rate trend."""
    console.print(f"\n  {accent('Passage Rate Trend')} · 17-22nd Assembly (법률안 only)\n")

    t = Table(border_style="dim", show_lines=False, padding=(0, 1))
    t.add_column("Assembly", width=8)
    t.add_column("Total", justify="right", width=7)
    t.add_column("Passed", justify="right", width=7)
    t.add_column("Rate", justify="right", width=6)
    t.add_column("Enacted", justify="right", width=7)
    t.add_column("Rate", justify="right", width=6)
    t.add_column("Promul.", justify="right", width=7)
    t.add_column("Rate", justify="right", width=6)

    for r in data:
        t.add_row(
            ordinal(r["age"]),
            f"{r['total']:,}",
            f"{r['passed']:,}",
            f"{r['pass_rate']:.1f}%",
            f"{r['enacted']:,}",
            f"{r['enact_rate']:.1f}%",
            f"{r.get('promulgated', 0):,}",
            f"{r.get('prom_rate', 0):.1f}%",
        )

    console.print(t)
    console.print(f"\n  {dim('passed = 원안가결 + 수정가결 + 대안반영폐기')}")
    console.print(f"  {dim('enacted = 원안가결 + 수정가결 (final result: a vetoed bill counts only if re-passed)')}")
    console.print(f"  {dim('promulgated = promulgation date recorded (became law)')}\n")
