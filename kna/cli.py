"""kna - Korean National Assembly CLI."""

from __future__ import annotations

from typing import Optional

import click

from kna.data import BillDB
from kna.formatters import console


def _get_db() -> BillDB:
    try:
        return BillDB()
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/] {e}")
        raise SystemExit(1)


@click.group()
@click.version_option(package_name="korean-bill-lifecycle")
def cli():
    """kna - Korean National Assembly CLI.

    Comprehensive query tool for 110K+ bills across the 17th-22nd
    Korean National Assembly: full lifecycle timestamps, 2.4M roll call
    votes, DW-NOMINATE ideal points, and bill propose-reason texts.
    """


# ── info ────────────────────────────────────────────────────────────

@cli.command()
def info():
    """Show database overview.

    \b
    Example:
        kna info
    """
    from kna.queries import db_info
    from kna.formatters import print_info

    db = _get_db()
    data = db_info(db)
    print_info(
        data["file_info"], data["rc_count"], data["ip_count"],
        data["cm_count"], data["txt_count"], data["freshness"],
    )


# ── search ──────────────────────────────────────────────────────────

@cli.command()
@click.argument("keyword")
@click.option("--age", type=int, default=None, help="Assembly number (17-22)")
@click.option("--committee", default=None, help="Committee name (partial match)")
@click.option("--proposer", default=None, help="Lead proposer name")
@click.option("--status", type=click.Choice(["passed", "enacted", "pending", "rejected"]),
              default=None, help="Status group")
@click.option("--kind", default=None, help="Bill type (e.g. 법률안)")
@click.option("--from", "date_from", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--to", "date_to", default=None, help="End date (YYYY-MM-DD)")
@click.option("-n", "--limit", type=int, default=20, help="Max results (default 20)")
def search(keyword, age, committee, proposer, status, kind, date_from, date_to, limit):
    """Search bills by keyword.

    \b
    Examples:
        kna search "인공지능"
        kna search "부동산" --age 22 --status enacted
        kna search "형법" --proposer 박범계 --age 21
    """
    from kna.queries import search_bills
    from kna.formatters import print_search_results

    db = _get_db()
    results, total = search_bills(
        db, keyword, age=age, committee=committee, proposer=proposer,
        status=status, kind=kind, date_from=date_from, date_to=date_to,
        limit=limit,
    )
    if total == 0:
        console.print(f"  No results for \"{keyword}\"")
        return
    print_search_results(results, keyword, age, total)


# ── show ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("bill_ref")
def show(bill_ref):
    """Show bill detail with lifecycle timeline.

    \b
    Accepts bill_no (7-digit) or bill_id (PRC_/ARC_ prefix).

    \b
    Examples:
        kna show 2217673
        kna show PRC_Y2Z6X0Y2F1G3E1D1D1B1C2Y6Y0W6X6
    """
    from kna.queries import get_bill_detail
    from kna.formatters import print_bill_detail

    db = _get_db()
    row = get_bill_detail(db, bill_ref)
    if row is None:
        console.print(f"  Bill not found: {bill_ref}")
        return
    print_bill_detail(row)


# ── legislator ──────────────────────────────────────────────────────

@cli.command()
@click.argument("name")
@click.option("--age", type=int, default=None, help="Assembly number (17-22)")
@click.option("--mona", default=None, help="MONA_CD for exact match")
def legislator(name, age, mona):
    """Show legislator profile.

    \b
    Includes ideal point, bill record, and top enacted bills.

    \b
    Examples:
        kna legislator 추미애 --age 21
        kna legislator 김영식 --age 22
    """
    from kna.queries import get_legislator_profile
    from kna.formatters import print_legislator

    db = _get_db()
    profile = get_legislator_profile(db, name, age=age, mona=mona)
    if profile is None:
        console.print(f"  No bills found for \"{name}\"")
        return
    print_legislator(**profile)


# ── text ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("keyword")
@click.option("--age", type=int, default=None, help="Assembly number (20-22)")
@click.option("-n", "--limit", type=int, default=20, help="Max results (default 20)")
def text(keyword, age, limit):
    """Search within bill propose-reason texts.

    \b
    Full-text search across 60K+ propose-reason texts (20-22nd Assembly).

    \b
    Examples:
        kna text "기후변화"
        kna text "인공지능" --age 22 -n 10
    """
    from kna.queries import search_bill_texts
    from kna.formatters import print_search_results, dim

    db = _get_db()
    results, total = search_bill_texts(db, keyword, age=age, limit=limit)
    if total == 0:
        console.print(f"  No results for \"{keyword}\" in propose-reason texts")
        return
    console.print(f"  {dim('(searching propose-reason texts)')}")
    print_search_results(results, keyword, age, total)


# ── stats ───────────────────────────────────────────────────────────

@cli.group()
def stats():
    """Aggregate statistics.

    \b
    Subcommands:
        funnel          Legislative funnel for an assembly
        passage-rate    Cross-assembly passage rate trend
    """


@stats.command("funnel")
@click.option("--age", type=int, default=22, help="Assembly number (default 22)")
def stats_funnel(age):
    """Legislative funnel (법률안 only).

    \b
    Example:
        kna stats funnel --age 22
    """
    from kna.queries import funnel_stats
    from kna.formatters import print_funnel

    db = _get_db()
    stages = funnel_stats(db, age)
    print_funnel(stages, age)


@stats.command("passage-rate")
def stats_passage_rate():
    """Passage rate trend across all assemblies.

    \b
    Example:
        kna stats passage-rate
    """
    from kna.queries import passage_rate_stats
    from kna.formatters import print_passage_rate

    db = _get_db()
    data = passage_rate_stats(db)
    print_passage_rate(data)


# ── export ──────────────────────────────────────────────────────────

@cli.command()
@click.argument("output", type=click.Path())
@click.option("--age", type=int, default=None, help="Assembly number (17-22)")
@click.option("--committee", default=None, help="Committee name (partial match)")
@click.option("--status", type=click.Choice(["passed", "enacted", "pending", "rejected"]),
              default=None, help="Status group")
@click.option("--kind", default=None, help="Bill type (e.g. 법률안)")
def export(output, age, committee, status, kind):
    """Export filtered bills to CSV or Parquet.

    \b
    Format is auto-detected from file extension (.csv, .parquet, .tsv).

    \b
    Examples:
        kna export health.csv --age 22 --committee 보건복지
        kna export enacted.parquet --status enacted
    """
    from kna.queries import export_bills

    db = _get_db()
    df = export_bills(db, age=age, committee=committee, status=status, kind=kind)

    if output.endswith(".parquet"):
        df.to_parquet(output, index=False)
    elif output.endswith(".tsv"):
        df.to_csv(output, index=False, sep="\t")
    else:
        df.to_csv(output, index=False)

    console.print(f"  Exported {len(df):,} bills → {output}")
