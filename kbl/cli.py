"""kbl - Korean Bill Lifecycle CLI."""

from __future__ import annotations

from typing import Optional

import click

from kbl.data import BillDB
from kbl.formatters import console


def _get_db() -> BillDB:
    try:
        return BillDB()
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/] {e}")
        raise SystemExit(1)


@click.group()
@click.version_option(package_name="korean-bill-lifecycle")
def cli():
    """kbl - Korean Bill Lifecycle CLI.

    Query 110K+ bills across the 17th-22nd Korean National Assembly,
    with full lifecycle timestamps, roll call votes, and DW-NOMINATE
    ideal point estimates.
    """


# ── info ────────────────────────────────────────────────────────────

@cli.command()
def info():
    """Show database overview.

    \b
    Example:
        kbl info
    """
    from kbl.queries import db_info
    from kbl.formatters import print_info

    db = _get_db()
    data = db_info(db)
    print_info(
        data["file_info"], data["rc_count"], data["ip_count"],
        data["cm_count"], data["freshness"],
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
        kbl search "인공지능"
        kbl search "부동산" --age 22 --status enacted
        kbl search "형법" --proposer 박범계 --age 21
    """
    from kbl.queries import search_bills
    from kbl.formatters import print_search_results

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
        kbl show 2217673
        kbl show PRC_Y2Z6X0Y2F1G3E1D1D1B1C2Y6Y0W6X6
    """
    from kbl.queries import get_bill_detail
    from kbl.formatters import print_bill_detail

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
        kbl legislator 추미애 --age 21
        kbl legislator 김영식 --age 22
    """
    from kbl.queries import get_legislator_profile
    from kbl.formatters import print_legislator

    db = _get_db()
    profile = get_legislator_profile(db, name, age=age, mona=mona)
    if profile is None:
        console.print(f"  No bills found for \"{name}\"")
        return
    print_legislator(**profile)


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
        kbl stats funnel --age 22
    """
    from kbl.queries import funnel_stats
    from kbl.formatters import print_funnel

    db = _get_db()
    stages = funnel_stats(db, age)
    print_funnel(stages, age)


@stats.command("passage-rate")
def stats_passage_rate():
    """Passage rate trend across all assemblies.

    \b
    Example:
        kbl stats passage-rate
    """
    from kbl.queries import passage_rate_stats
    from kbl.formatters import print_passage_rate

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
        kbl export health.csv --age 22 --committee 보건복지
        kbl export enacted.parquet --status enacted
    """
    from kbl.queries import export_bills

    db = _get_db()
    df = export_bills(db, age=age, committee=committee, status=status, kind=kind)

    if output.endswith(".parquet"):
        df.to_parquet(output, index=False)
    elif output.endswith(".tsv"):
        df.to_csv(output, index=False, sep="\t")
    else:
        df.to_csv(output, index=False)

    console.print(f"  Exported {len(df):,} bills → {output}")
