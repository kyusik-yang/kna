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
    if status == "대안반영폐기":
        return f"[cyan]{status}[/]" if _COLOR else status
    return status


def truncate(s, maxlen: int = 60) -> str:
    if pd.isna(s):
        return ""
    s = str(s).replace("\n", " ").strip()
    return s[:maxlen] + "..." if len(s) > maxlen else s


# ── Info ────────────────────────────────────────────────────────────

def print_info(file_info: list[dict], rc_count: int, ip_count: int,
               cm_count: int, txt_count: int, mem_count: int = 0,
               freshness: str = "") -> None:
    """Print database overview."""
    total_bills = sum(r["total"] for r in file_info)
    total_enacted = sum(r["enacted"] for r in file_info)

    t = Table(
        title=accent("Korean National Assembly Database"),
        border_style="dim", show_lines=False, padding=(0, 1),
    )
    t.add_column("Assembly", style="bold", width=18)
    t.add_column("Bills", justify="right", width=8)
    t.add_column("Enacted", justify="right", width=8)
    t.add_column("Cols", justify="right", width=5, style="dim")

    age_labels = {
        17: "17th (2004-08)", 18: "18th (2008-12)", 19: "19th (2012-16)",
        20: "20th (2016-20)", 21: "21st (2020-24)", 22: "22nd (2024-)",
    }
    for r in file_info:
        t.add_row(age_labels.get(r["age"], ordinal(r["age"])),
                   f"{r['total']:,}", f"{r['enacted']:,}", str(r["ncol"]))

    t.add_section()
    t.add_row("[bold]Total[/]", f"[bold]{total_bills:,}[/]",
              f"[bold]{total_enacted:,}[/]", "")

    console.print(t)
    console.print()
    console.print(f"  Roll call votes   {rc_count:>10,}  {dim('(16-22nd, bulk: 20-22nd)')}")
    console.print(f"  Ideal points      {ip_count:>10,}  {dim('(20-22nd, DW-NOMINATE)')}")
    console.print(f"  Members           {mem_count:>10,}  {dim('(17-22nd, party/district/committee)')}")
    console.print(f"  Committee mtgs    {cm_count:>10,}  {dim('(17-22nd)')}")
    console.print(f"  Bill texts        {txt_count:>10,}  {dim('(20-22nd, propose-reason)')}")
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
    ("발의", "ppsl_dt"),
    ("소관위 회부", "committee_dt"),
    ("소관위 상정", "cmt_present_dt"),
    ("소관위 처리", "cmt_proc_dt"),
    ("법사위 회부", "law_submit_dt"),
    ("본회의 의결", "rgs_rsln_dt"),
    ("공포", "prom_dt"),
]


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
    for label, val in fields:
        val_str = truncate(val, 50)
        if label == "status":
            val_str = status_style(str(val))
        lines.append(f"  {dim(f'{label:<14}')} {val_str}")

    # Lifecycle timeline
    lines.append("")
    lines.append(f"  {'LIFECYCLE':<14}  {'date':>12}  {'days':>6}")

    base_dt = row.get("ppsl_dt")
    for label, col in _LIFECYCLE_STAGES:
        dt = row.get(col)
        if pd.notna(dt):
            dt_ts = pd.Timestamp(dt)
            date_str = dt_ts.strftime("%Y-%m-%d")
            if pd.notna(base_dt) and col != "ppsl_dt":
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

    # Vote tally
    vy = row.get("vote_yes")
    if pd.notna(vy):
        vn = int(row.get("vote_no", 0))
        va = int(row.get("vote_abstain", 0))
        vt = int(row.get("vote_member_total", 0))
        lines.append("")
        lines.append(f"  VOTE   찬성 {int(vy)} / 반대 {vn} / 기권 {va} (재석 {vt})")

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
    age: Optional[int],
    party: str,
    district: str = "",
    committee: str = "",
    sex: str = "",
    election_type: str = "",
    reelection: str = "",
    ideal_point: Optional[float] = None,
    rank: Optional[int] = None,
    total_in_term: Optional[int] = None,
    bills_df: pd.DataFrame = None,
    top_enacted: pd.DataFrame = None,
) -> None:
    """Print legislator profile."""
    age_str = f"{ordinal(age)} Assembly" if age else "All assemblies"
    console.print(f"\n  {accent(name)} · {age_str}")
    console.print(f"  {'─' * 40}")

    if party:
        console.print(f"  {dim('party'):<20} {party}")
    if district:
        console.print(f"  {dim('district'):<20} {district}")
    if committee:
        console.print(f"  {dim('committee'):<20} {committee}")
    if election_type:
        console.print(f"  {dim('election'):<20} {election_type}" + (f" ({reelection})" if reelection else ""))
    if ideal_point is not None:
        console.print(f"  {dim('ideal point'):<20} {ideal_point:.3f} (DW-NOMINATE)")
    if rank is not None and total_in_term is not None:
        console.print(f"  {dim('rank'):<20} {rank} / {total_in_term} (← 진보 ··· 보수 →)")

    # Bill record
    total = len(bills_df)
    enacted = int(bills_df["enacted"].sum()) if "enacted" in bills_df.columns else 0
    passed = int(bills_df["passed"].sum()) if "passed" in bills_df.columns else 0
    alt = passed - enacted

    console.print(f"\n  BILL RECORD")
    console.print(f"  {dim('led'):<20} {total} bills")
    console.print(f"  {dim('enacted'):<20} {enacted} ({enacted/total*100:.1f}%)" if total else "")
    if alt > 0:
        console.print(f"  {dim('alt-reflected'):<20} {alt}")

    if "days_to_proc" in bills_df.columns:
        med = bills_df["days_to_proc"].dropna().median()
        if pd.notna(med):
            console.print(f"  {dim('median days'):<20} {int(med)}d (proposal → processing)")

    # Top enacted bills
    if len(top_enacted) > 0:
        console.print(f"\n  TOP ENACTED BILLS")
        for i, (_, b) in enumerate(top_enacted.head(5).iterrows(), 1):
            dt = pd.Timestamp(b["ppsl_dt"]).strftime("%Y-%m-%d") if pd.notna(b.get("ppsl_dt")) else ""
            console.print(f"  {i}. {truncate(b.get('bill_nm', ''), 50)} ({dt}) → {b.get('status', '')}")

    console.print()


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
    console.print()


# ── Stats: passage rate ─────────────────────────────────────────────

def print_passage_rate(data: list[dict]) -> None:
    """Print cross-assembly passage rate trend."""
    console.print(f"\n  {accent('Passage Rate Trend')} · 17-22nd Assembly (법률안 only)\n")

    t = Table(border_style="dim", show_lines=False, padding=(0, 1))
    t.add_column("Assembly", width=10)
    t.add_column("Total", justify="right", width=8)
    t.add_column("Passed", justify="right", width=8)
    t.add_column("Rate", justify="right", width=7)
    t.add_column("Enacted", justify="right", width=8)
    t.add_column("Rate", justify="right", width=7)

    for r in data:
        t.add_row(
            ordinal(r["age"]),
            f"{r['total']:,}",
            f"{r['passed']:,}",
            f"{r['pass_rate']:.1f}%",
            f"{r['enacted']:,}",
            f"{r['enact_rate']:.1f}%",
        )

    console.print(t)
    console.print(f"\n  {dim('passed = 원안가결 + 수정가결 + 대안반영폐기')}")
    console.print(f"  {dim('enacted = 원안가결 + 수정가결 (actually became law)')}\n")
