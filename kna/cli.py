"""kna - Korean National Assembly CLI."""

from __future__ import annotations

from typing import Optional

import click

from kna import __version__
from kna.data import BillDB
from kna.formatters import console
from kna.queries import STATUS_FLAGS, STATUS_GROUPS

ASSEMBLY = click.IntRange(17, 22)
STATUS_HELP = ("Status group: " + "; ".join(
    f"{k} = {'/'.join(v)}" + (f" with {STATUS_FLAGS[k]} = 1" if k in STATUS_FLAGS else "")
    for k, v in STATUS_GROUPS.items()))
EXPORT_FORMATS = (".csv", ".tsv", ".parquet")


def _get_db() -> BillDB:
    try:
        return BillDB()
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/] {e}")
        raise SystemExit(1)


@click.group()
@click.version_option(version=__version__, package_name="kna")
def cli():
    """kna - Korean National Assembly CLI.

    Comprehensive query tool for 110K+ bills across the 17th-22nd
    Korean National Assembly: full lifecycle timestamps, 4.1M roll call
    votes (17th-22nd), cross-assembly ideal points (20th-22nd), and
    propose-reason texts of law bills.
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
    print_info(**data)


# ── search ──────────────────────────────────────────────────────────

@cli.command()
@click.argument("keyword")
@click.option("--assembly", "age", type=ASSEMBLY, default=None, help="Assembly number (17-22)")
@click.option("--committee", default=None, help="Committee name (partial match)")
@click.option("--proposer", default=None,
              help="Lead proposer name (exact match, joint leads included)")
@click.option("--status", type=click.Choice(list(STATUS_GROUPS)),
              default=None, help=STATUS_HELP)
@click.option("--kind", default=None, help="Bill type (e.g. 법률안)")
@click.option("--from", "date_from", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--to", "date_to", default=None, help="End date (YYYY-MM-DD)")
@click.option("-n", "--limit", type=int, default=20, help="Max results (default 20)")
def search(keyword, age, committee, proposer, status, kind, date_from, date_to, limit):
    """Search bills by keyword.

    \b
    Examples:
        kna search "인공지능"
        kna search "부동산" --assembly 22 --status enacted
        kna search "형법" --proposer 박범계 --assembly 21
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
    Accepts bill_no (6-7 digits) or bill_id (PRC_/ARC_/GOV_ prefix).

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
@click.option("--assembly", "age", type=ASSEMBLY, default=None, help="Assembly number (17-22)")
@click.option("--mona", default=None, help="MONA_CD, required when several legislators share the name")
@click.pass_context
def legislator(ctx, name, age, mona):
    """Show legislator profile.

    \b
    Includes ideal point, bill record, and top enacted bills.
    The name must match a member exactly. When several legislators
    share it, their MONA_CDs are listed and --mona picks one.
    Without --assembly, every term served is shown.

    \b
    Examples:
        kna legislator 추미애 --assembly 22
        kna legislator 추미애
        kna legislator 김병욱 --assembly 21 --mona GFF1986K
    """
    from kna.queries import AmbiguousLegislator, get_legislator_profile, suggest_legislators
    from kna.formatters import ordinal, print_legislator, print_legislator_candidates

    db = _get_db()
    try:
        profile = get_legislator_profile(db, name, age=age, mona=mona)
    except AmbiguousLegislator as e:
        print_legislator_candidates(name, age, e.candidates)
        ctx.exit(2)
    if profile is None:
        scope = f" in the {ordinal(age)} Assembly" if age else ""
        key = f"MONA_CD {mona}" if mona else f"\"{name}\""
        console.print(f"  No legislator {key}{scope}")
        hints = [] if mona else suggest_legislators(db, name, age)
        if hints:
            console.print(f"  Similar names: {', '.join(hints)}")
        return
    if mona and profile["name"] != name.strip():
        console.print(f"  Note: MONA_CD {mona} is {profile['name']}")
    print_legislator(**profile)


# ── text ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("keyword")
@click.option("--assembly", "age", type=ASSEMBLY, default=None, help="Assembly number (17-22)")
@click.option("-n", "--limit", type=int, default=20, help="Max results (default 20)")
def text(keyword, age, limit):
    """Search within bill propose-reason texts.

    \b
    Full-text search across 109K+ propose-reason texts of law bills
    (17th-22nd Assembly).

    \b
    Examples:
        kna text "기후변화"
        kna text "인공지능" --assembly 22 -n 10
    """
    from kna.queries import search_bill_texts
    from kna.formatters import print_search_results, dim

    db = _get_db()
    results, total = search_bill_texts(db, keyword, age=age, limit=limit)
    if total == 0:
        console.print(f"  No results for \"{keyword}\" in propose-reason texts")
        if age is not None and age < 20:
            console.print("  Data files built before 0.8.0 have texts for the 20th-22nd assemblies only")
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
@click.option("--assembly", "age", type=ASSEMBLY, default=22, help="Assembly number (default 22)")
def stats_funnel(age):
    """Legislative funnel (법률안 only).

    \b
    Each stage counts bills that reached it or a later stage, so
    bills that skip a stage (위원장 대안, 법사위's own bills) still
    count. 본회의 의결 is a floor decision (원안가결, 수정가결, 부결).

    \b
    Example:
        kna stats funnel --assembly 22
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
@click.option("--assembly", "age", type=ASSEMBLY, default=None, help="Assembly number (17-22)")
@click.option("--committee", default=None, help="Committee name (partial match)")
@click.option("--status", type=click.Choice(list(STATUS_GROUPS)),
              default=None, help=STATUS_HELP)
@click.option("--kind", default=None, help="Bill type (e.g. 법률안)")
def export(output, age, committee, status, kind):
    """Export filtered bills to CSV or Parquet.

    \b
    Format is auto-detected from file extension (.csv, .parquet, .tsv).

    \b
    Examples:
        kna export health.csv --assembly 22 --committee 보건복지
        kna export enacted.parquet --status enacted
    """
    from kna.queries import export_bills

    if not output.lower().endswith(EXPORT_FORMATS):
        raise click.BadParameter(
            f"unsupported extension; use one of {', '.join(EXPORT_FORMATS)}",
            param_hint="OUTPUT")
    db = _get_db()
    df = export_bills(db, age=age, committee=committee, status=status, kind=kind)

    if output.lower().endswith(".parquet"):
        df.to_parquet(output, index=False)
    elif output.lower().endswith(".tsv"):
        df.to_csv(output, index=False, sep="\t")
    else:
        df.to_csv(output, index=False)

    console.print(f"  Exported {len(df):,} bills → {output}")


if __name__ == "__main__":
    cli()
