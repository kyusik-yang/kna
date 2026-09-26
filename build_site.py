#!/usr/bin/env python3
"""
build_site.py - Generate interactive HTML tutorial for Korean National Assembly DB.

Reads parquet data, computes aggregated statistics, builds Plotly charts,
and outputs a single self-contained index.html file. Every number on the
page is computed from the data directory.

Usage:
    python3 build_site.py                                # data/processed -> docs/
    python3 build_site.py --data data/_build --out docs  # staged build
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import pyarrow.parquet as pq

from kna.data import BillDB
from kna.queries import funnel_stats

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent


def _parse_args():
    p = argparse.ArgumentParser(description="Build the kna overview page (index.html).")
    p.add_argument("--data", default=str(BASE / "data" / "processed"),
                   help="data directory to read (default data/processed)")
    p.add_argument("--out", default=str(BASE / "docs"),
                   help="directory to write index.html into (default docs)")
    return p.parse_args()


ARGS = _parse_args()
DATA = Path(ARGS.data).expanduser().resolve()
OUT = Path(ARGS.out).expanduser().resolve()
if not DATA.is_dir():
    raise SystemExit(f"ERROR: data directory {DATA} not found")
OUT.mkdir(parents=True, exist_ok=True)


def claim(ok, sentence: str):
    """Stop the build when the data no longer support a sentence on the page."""
    if not ok:
        raise SystemExit(f"ERROR: the data no longer support this page text, revise it: {sentence}")


def pct(num, den) -> float:
    return num / den * 100 if den else 0.0

# ---------------------------------------------------------------------------
# Okabe-Ito palette
# ---------------------------------------------------------------------------
OI = ['#E69F00', '#56B4E9', '#009E73', '#0072B2', '#D55E00', '#CC79A7', '#F0E442']
NYU_PURPLE = '#57068C'
PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"

CHART_CONFIG = dict(responsive=True, displayModeBar=False)
FONT_FAMILY = "-apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif"

# Standard layout defaults
BASE_LAYOUT = dict(
    font=dict(family=FONT_FAMILY, size=13),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=60, r=30, t=50, b=50),
    hoverlabel=dict(font_size=13, font_family=FONT_FAMILY),
)


def make_layout(**kwargs):
    """Merge kwargs with BASE_LAYOUT."""
    layout = {**BASE_LAYOUT, **kwargs}
    return go.Layout(**layout)


def fig_to_json(fig):
    """Serialize a Plotly figure to compact JSON for embedding."""
    return pio.to_json(fig, pretty=False)


# ===================================================================
# 1. Load data
# ===================================================================
print("Loading data...")

df22 = pd.read_parquet(DATA / "master_bills_22.parquet")
cm22 = pd.read_parquet(DATA / "committee_meetings_22.parquet")

other_frames = {}
for age in [17, 18, 19, 20, 21]:
    full_path = DATA / f"master_bills_{age}.parquet"
    lite_path = DATA / f"master_bills_{age}_lite.parquet"
    other_frames[age] = pd.read_parquet(full_path if full_path.exists() else lite_path)

# Build cross-assembly summary
all_frames = {**other_frames, 22: df22}

# ===================================================================
# 2. Cross-assembly statistics
# ===================================================================
print("Computing cross-assembly stats...")

assembly_stats = []
for age in sorted(all_frames.keys()):
    df = all_frames[age]
    total = len(df)
    laws = (df["bill_kind"] == "법률안").sum()
    passed = df["passed"].sum()
    enacted = df["enacted"].sum()
    yr_min = pd.to_datetime(df["ppsl_dt"]).min().year
    yr_max = pd.to_datetime(df["ppsl_dt"]).max().year

    ppsr_counts = df["ppsr_kind"].value_counts().to_dict()

    assembly_stats.append(dict(
        age=age,
        label=f"{age}대",
        total=int(total),
        laws=int(laws),
        passed=int(passed),
        enacted=int(enacted),
        passage_broad=round(passed / total * 100, 1),
        passage_narrow=round(enacted / total * 100, 1),
        yr_range=f"{yr_min}-{yr_max}",
        member_bills=int(ppsr_counts.get("의원", 0)),
        govt_bills=int(ppsr_counts.get("정부", 0)),
        chair_bills=int(ppsr_counts.get("위원장", 0)),
    ))

astats = pd.DataFrame(assembly_stats).set_index("age", drop=False)

# Grand totals. "Laws enacted" counts 법률안 passed as is or amended
# (enacted == 1), the same basis as `kna info`.
grand_total = int(astats["total"].sum())
grand_enacted_laws = int(sum(((df["bill_kind"] == "법률안") & (df["enacted"] == 1)).sum()
                             for df in all_frames.values()))
all_ppsl = pd.concat([pd.to_datetime(df["ppsl_dt"]) for df in all_frames.values()])
date_range_min = str(all_ppsl.min().year)
date_range_max = str(all_ppsl.max().year)
latest_ppsl = all_ppsl.max().strftime("%Y-%m-%d")

# Sentences in Section 1 and in the research-question cards
completed = [a for a in sorted(all_frames) if a < 22]
claim(astats.loc[completed, "total"].is_monotonic_increasing,
      "발의 건수는 꾸준히 증가 (17-21대)")
claim(astats["passage_broad"].is_monotonic_decreasing
      and astats["passage_narrow"].is_monotonic_decreasing,
      "가결률은 지속적으로 하락 (17-22대)")
growth_17_21 = astats.loc[21, "total"] / astats.loc[17, "total"]

# ===================================================================
# Chart 1: Bills per assembly by bill_kind composition
# ===================================================================
print("Building Chart 1: Bills per assembly...")

kind_order = ["법률안", "결의안", "동의안", "기타"]

fig1_traces = []
for i, kind in enumerate(kind_order):
    vals = []
    for age in sorted(all_frames.keys()):
        df = all_frames[age]
        if kind == "기타":
            count = len(df[~df["bill_kind"].isin(["법률안", "결의안", "동의안"])])
        else:
            count = (df["bill_kind"] == kind).sum()
        vals.append(count)
    fig1_traces.append(go.Bar(
        name=kind,
        x=[f"{a}대" for a in sorted(all_frames.keys())],
        y=vals,
        marker_color=OI[i],
        hovertemplate="%{x}<br>" + kind + ": %{y:,}건<extra></extra>",
    ))

fig1 = go.Figure(data=fig1_traces, layout=make_layout(
    title=dict(text="대수별 발의 법안 수", font=dict(size=18)),
    barmode="stack",
    xaxis=dict(title="", showgrid=False),
    yaxis=dict(title="법안 수", gridcolor="#eee"),
    legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
    height=420,
))
fig1_json = fig_to_json(fig1)

# ===================================================================
# Chart 2: Passage rate trend
# ===================================================================
print("Building Chart 2: Passage rate trend...")

fig2 = go.Figure()
fig2.add_trace(go.Scatter(
    x=astats["label"], y=astats["passage_broad"],
    mode="lines+markers+text",
    name="광의 (passed)",
    text=[f"{v}%" for v in astats["passage_broad"]],
    textposition="top center",
    textfont=dict(size=12),
    line=dict(color=OI[3], width=3),
    marker=dict(size=10),
    hovertemplate="%{x}: %{y:.1f}%<extra>광의 가결률</extra>",
))
fig2.add_trace(go.Scatter(
    x=astats["label"], y=astats["passage_narrow"],
    mode="lines+markers+text",
    name="협의 (enacted)",
    text=[f"{v}%" for v in astats["passage_narrow"]],
    textposition="bottom center",
    textfont=dict(size=12),
    line=dict(color=OI[4], width=3),
    marker=dict(size=10),
    hovertemplate="%{x}: %{y:.1f}%<extra>협의 가결률</extra>",
))
fig2.update_layout(make_layout(
    title=dict(text="대수별 법안 가결률 추이", font=dict(size=18)),
    xaxis=dict(title="", showgrid=False),
    yaxis=dict(title="가결률 (%)", gridcolor="#eee", range=[0, 60]),
    legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
    height=400,
))
fig2_json = fig_to_json(fig2)

# ===================================================================
# Chart 3: 22nd Assembly - Committee x Status stacked horizontal bar
# ===================================================================
print("Building Chart 3: Committee status breakdown...")

laws22 = df22[df22["bill_kind"] == "법률안"].copy()

status_map = {
    "계류중": "계류중",
    "대안반영폐기": "대안반영",
    "원안가결": "원안가결",
    "수정가결": "수정가결",
    "철회": "기타",
    "수정안반영폐기": "기타",
    "부결": "기타",
    "폐기": "기타",
}
laws22["status_short"] = laws22["status"].map(status_map).fillna("기타")

top_cmt = laws22["committee_nm"].value_counts().head(12).index.tolist()
laws22_top = laws22[laws22["committee_nm"].isin(top_cmt)]

cmt_status = (
    laws22_top.groupby(["committee_nm", "status_short"])
    .size()
    .reset_index(name="count")
    .pivot(index="committee_nm", columns="status_short", values="count")
    .fillna(0)
    .astype(int)
)

# Sort by total
cmt_status["_total"] = cmt_status.sum(axis=1)
cmt_status = cmt_status.sort_values("_total", ascending=True)
cmt_status = cmt_status.drop(columns=["_total"])

status_colors = {
    "계류중": "#bdc3c7",
    "대안반영": OI[0],
    "원안가결": OI[2],
    "수정가결": OI[1],
    "기타": OI[5],
}

fig3 = go.Figure()
for status_name in ["계류중", "대안반영", "수정가결", "원안가결", "기타"]:
    if status_name in cmt_status.columns:
        fig3.add_trace(go.Bar(
            y=cmt_status.index,
            x=cmt_status[status_name],
            name=status_name,
            orientation="h",
            marker_color=status_colors.get(status_name, "#ccc"),
            hovertemplate="<b>%{y}</b><br>" + status_name + ": %{x:,}건<extra></extra>",
        ))

fig3.update_layout(make_layout(
    title=dict(text="22대 위원회별 법률안 처리 현황 (상위 12개)", font=dict(size=18)),
    barmode="stack",
    xaxis=dict(title="법안 수", gridcolor="#eee"),
    yaxis=dict(title=""),
    legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"),
    height=520,
    margin=dict(l=180),
))
fig3_json = fig_to_json(fig3)

# ===================================================================
# Chart 4: Committee passage rate (horizontal bar)
# ===================================================================
print("Building Chart 4: Committee passage rate...")

cmt_stats = (
    laws22.groupby("committee_nm")
    .agg(total=("bill_id", "count"), passed=("passed", "sum"), enacted=("enacted", "sum"))
    .reset_index()
)
cmt_stats["passage_rate"] = (cmt_stats["enacted"] / cmt_stats["total"] * 100).round(1)
cmt_stats = cmt_stats[cmt_stats["total"] >= 50].sort_values("passage_rate", ascending=True)

fig4 = go.Figure(go.Bar(
    y=cmt_stats["committee_nm"],
    x=cmt_stats["passage_rate"],
    orientation="h",
    marker_color=[NYU_PURPLE if v >= 10 else OI[1] for v in cmt_stats["passage_rate"]],
    text=[f"{v}%" for v in cmt_stats["passage_rate"]],
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>가결률: %{x:.1f}%<br>총 %{customdata[0]:,}건 중 %{customdata[1]:,}건 가결<extra></extra>",
    customdata=list(zip(cmt_stats["total"], cmt_stats["enacted"])),
))
fig4.update_layout(make_layout(
    title=dict(text="위원회별 법률안 가결률 (enacted, 50건 이상)", font=dict(size=18)),
    xaxis=dict(title="가결률 (%)", gridcolor="#eee"),
    yaxis=dict(title=""),
    height=max(400, len(cmt_stats) * 30 + 100),
    margin=dict(l=200),
))
fig4_json = fig_to_json(fig4)

# ===================================================================
# Chart 5: Proposer type passage rates
# ===================================================================
print("Building Chart 5: Proposer type comparison...")

ppsr_stats = (
    laws22.groupby("ppsr_kind")
    .agg(total=("bill_id", "count"), passed=("passed", "sum"), enacted=("enacted", "sum"))
    .reset_index()
)
ppsr_stats = ppsr_stats[ppsr_stats["total"] >= 10]
ppsr_stats["pass_rate"] = (ppsr_stats["passed"] / ppsr_stats["total"] * 100).round(1)
ppsr_stats["enact_rate"] = (ppsr_stats["enacted"] / ppsr_stats["total"] * 100).round(1)

fig5 = go.Figure()
fig5.add_trace(go.Bar(
    name="광의 가결 (passed)",
    x=ppsr_stats["ppsr_kind"],
    y=ppsr_stats["pass_rate"],
    marker_color=OI[3],
    text=[f"{v}%" for v in ppsr_stats["pass_rate"]],
    textposition="outside",
    hovertemplate="%{x}<br>광의 가결률: %{y:.1f}%<extra></extra>",
))
fig5.add_trace(go.Bar(
    name="협의 가결 (enacted)",
    x=ppsr_stats["ppsr_kind"],
    y=ppsr_stats["enact_rate"],
    marker_color=OI[4],
    text=[f"{v}%" for v in ppsr_stats["enact_rate"]],
    textposition="outside",
    hovertemplate="%{x}<br>협의 가결률: %{y:.1f}%<extra></extra>",
))
fig5.update_layout(make_layout(
    title=dict(text="발의자 유형별 가결률 비교", font=dict(size=18)),
    barmode="group",
    xaxis=dict(title="", showgrid=False),
    yaxis=dict(title="가결률 (%)", gridcolor="#eee"),
    legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
    height=420,
))
fig5_json = fig_to_json(fig5)

# ===================================================================
# Chart 6: Monthly submission timeline
# ===================================================================
print("Building Chart 6: Monthly timeline...")

laws22["ppsl_month"] = laws22["ppsl_dt"].dt.to_period("M")
monthly = laws22.groupby("ppsl_month").size().reset_index(name="count")
monthly["month_str"] = monthly["ppsl_month"].astype(str)

fig6 = go.Figure()
fig6.add_trace(go.Scatter(
    x=monthly["month_str"],
    y=monthly["count"],
    mode="lines",
    fill="tozeroy",
    line=dict(color=NYU_PURPLE, width=2),
    fillcolor="rgba(87, 6, 140, 0.15)",
    hovertemplate="%{x}<br>%{y}건 발의<extra></extra>",
))
fig6.update_layout(make_layout(
    title=dict(text="22대 월별 법률안 발의 추이", font=dict(size=18)),
    xaxis=dict(title="", showgrid=False, tickangle=-45),
    yaxis=dict(title="발의 건수", gridcolor="#eee"),
    height=380,
))
fig6_json = fig_to_json(fig6)

# ===================================================================
# Chart 7: Processing time distribution by proposer type
# ===================================================================
print("Building Chart 7: Processing time distribution...")

proc_data = laws22[laws22["days_to_proc"].notna() & laws22["ppsr_kind"].isin(["의원", "정부", "위원장"])].copy()

fig7 = go.Figure()
for i, ppsr in enumerate(["의원", "정부", "위원장"]):
    subset = proc_data[proc_data["ppsr_kind"] == ppsr]["days_to_proc"]
    fig7.add_trace(go.Violin(
        y=subset,
        name=ppsr,
        box_visible=True,
        meanline_visible=True,
        fillcolor=OI[i],
        line_color=OI[i],
        opacity=0.7,
        hoverinfo="y",
    ))
fig7.update_layout(make_layout(
    title=dict(text="발의자 유형별 처리 소요일 분포", font=dict(size=18)),
    yaxis=dict(title="소요일 (days)", gridcolor="#eee"),
    xaxis=dict(title="", showgrid=False),
    showlegend=False,
    height=420,
))
fig7_json = fig_to_json(fig7)

# ===================================================================
# Chart 8: Legislative funnel (horizontal bar with gradient)
# ===================================================================
print("Building Chart 8: Legislative funnel...")

# Same definition as `kna stats funnel` (kna.queries.funnel_stats): 법률안
# only, and each stage counts the bills that reached it or any later stage.
# 본회의 의결 is plenary_decided (원안가결, 수정가결 or 부결 on the floor)
# and 공포 is promulgated.
db = BillDB(DATA)
funnel_stages = funnel_stats(db, 22)
funnel = dict(funnel_stages)

funnel_labels = [s[0] for s in funnel_stages]
funnel_values = [s[1] for s in funnel_stages]
funnel_pcts = [v / funnel_stages[0][1] * 100 for v in funnel_values]

# Color gradient from purple to orange
n = len(funnel_stages)
funnel_colors = [
    f"rgba({87 + int(i * (213-87)/n)}, {6 + int(i * (94-6)/n)}, {140 - int(i * (140-0)/n)}, 0.85)"
    for i in range(n)
]

fig8 = go.Figure()
fig8.add_trace(go.Bar(
    y=list(reversed(funnel_labels)),
    x=list(reversed(funnel_values)),
    orientation="h",
    marker=dict(color=list(reversed(funnel_colors))),
    text=[f"{v:,}건 ({p:.1f}%)" for v, p in zip(reversed(funnel_values), reversed(funnel_pcts))],
    textposition="inside",
    textfont=dict(color="#fff", size=13),
    hovertemplate="<b>%{y}</b><br>%{x:,}건<br>전체 대비 %{customdata:.1f}%<extra></extra>",
    customdata=list(reversed(funnel_pcts)),
))

# Add stage-to-stage drop rate annotations
drop_texts = []
for i in range(1, len(funnel_stages)):
    prev = funnel_stages[i-1][1]
    curr = funnel_stages[i][1]
    if prev > 0:
        drop = (1 - curr / prev) * 100
        drop_texts.append(f"-{drop:.0f}%")
    else:
        drop_texts.append("")

fig8.update_layout(make_layout(
    title=dict(text="법률안 입법 단계별 생존율 (22대)", font=dict(size=18)),
    xaxis=dict(title="법안 수", gridcolor="#eee"),
    yaxis=dict(title=""),
    height=420,
    margin=dict(l=120),
    showlegend=False,
))
fig8_json = fig_to_json(fig8)

# ===================================================================
# Chart 9: Vote patterns - scatter
# ===================================================================
print("Building Chart 9: Vote scatter...")

voted = df22[df22["vote_total"].notna()].copy()
voted["approval_rate"] = (voted["vote_yes"] / voted["vote_total"] * 100).round(1)
voted["contested"] = voted["approval_rate"] < 80

fig9 = go.Figure()
# Non-contested
nc = voted[~voted["contested"]]
fig9.add_trace(go.Scatter(
    x=nc["vote_total"],
    y=nc["vote_yes"],
    mode="markers",
    name="비쟁점 (찬성 80%+)",
    marker=dict(color=OI[1], size=6, opacity=0.5),
    hovertemplate="<b>%{customdata}</b><br>총 %{x}명 중 찬성 %{y}명<extra></extra>",
    customdata=nc["bill_nm"].str[:30],
))
# Contested
ct = voted[voted["contested"]]
fig9.add_trace(go.Scatter(
    x=ct["vote_total"],
    y=ct["vote_yes"],
    mode="markers",
    name="쟁점 법안 (찬성 <80%)",
    marker=dict(color=OI[4], size=8, opacity=0.8, line=dict(width=1, color="#333")),
    hovertemplate="<b>%{customdata}</b><br>총 %{x}명 중 찬성 %{y}명<extra></extra>",
    customdata=ct["bill_nm"].str[:30],
))
# Diagonal
fig9.add_trace(go.Scatter(
    x=[100, 300], y=[100, 300],
    mode="lines",
    line=dict(color="#ccc", dash="dash"),
    showlegend=False,
    hoverinfo="skip",
))
fig9.update_layout(make_layout(
    title=dict(text="표결 현황: 재석 vs 찬성", font=dict(size=18)),
    xaxis=dict(title="재석 (투표 참여 의원)", gridcolor="#eee"),
    yaxis=dict(title="찬성", gridcolor="#eee"),
    legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
    height=450,
))
fig9_json = fig_to_json(fig9)

# ===================================================================
# Chart 10: Approval rate histogram
# ===================================================================
print("Building Chart 10: Approval rate histogram...")

fig10 = go.Figure(go.Histogram(
    x=voted["approval_rate"],
    nbinsx=30,
    marker_color=NYU_PURPLE,
    opacity=0.85,
    hovertemplate="찬성률 %{x:.0f}%대<br>%{y}건<extra></extra>",
))
fig10.update_layout(make_layout(
    title=dict(text="본회의 표결 찬성률 분포", font=dict(size=18)),
    xaxis=dict(title="찬성률 (%)", gridcolor="#eee"),
    yaxis=dict(title="법안 수", gridcolor="#eee"),
    height=380,
))
fig10_json = fig_to_json(fig10)

# ===================================================================
# Chart 11: Top 20 legislators
# ===================================================================
print("Building Chart 11: Top legislators...")

# Count by MONA_CD, so each joint lead (comma-joined codes) is credited and
# same-name legislators stay apart. Names come from members_22.
member_bills = laws22[laws22["ppsr_kind"] == "의원"].copy()
lead_rows = member_bills.assign(mona=member_bills["rst_mona_cd"].str.split(",")).explode("mona")
lead_rows["mona"] = lead_rows["mona"].str.strip()
names22 = pd.read_parquet(DATA / "members_22.parquet", columns=["mona_cd", "member_name"])
leg_stats = (
    lead_rows.dropna(subset=["mona"]).groupby("mona")
    .agg(total=("bill_id", "count"), enacted=("enacted", "sum"))
    .reset_index()
    .merge(names22, left_on="mona", right_on="mona_cd", how="left")
)
# Label with the name, and add the code when two legislators share it
dup = leg_stats["member_name"].duplicated(keep=False)
leg_stats["rst_proposer"] = leg_stats["member_name"].fillna(leg_stats["mona"])
leg_stats.loc[dup, "rst_proposer"] += " (" + leg_stats.loc[dup, "mona"] + ")"
leg_stats["enact_rate"] = (leg_stats["enacted"] / leg_stats["total"] * 100).round(1)
top20 = leg_stats.nlargest(20, "total").sort_values("total", ascending=True)

fig11 = go.Figure(go.Bar(
    y=top20["rst_proposer"],
    x=top20["total"],
    orientation="h",
    marker=dict(
        color=top20["enact_rate"],
        colorscale=[[0, OI[1]], [0.5, OI[0]], [1, OI[4]]],
        colorbar=dict(title="가결률(%)"),
        cmin=0, cmax=max(top20["enact_rate"].max(), 15),
    ),
    text=[f"{t}건 (가결 {r}%)" for t, r in zip(top20["total"], top20["enact_rate"])],
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>발의: %{x}건<br>가결률: %{customdata:.1f}%<extra></extra>",
    customdata=top20["enact_rate"],
))
fig11.update_layout(make_layout(
    title=dict(text="22대 발의 상위 20인 (법률안, 공동 대표발의 포함)", font=dict(size=18)),
    xaxis=dict(title="대표발의 건수", gridcolor="#eee"),
    yaxis=dict(title=""),
    height=600,
    margin=dict(l=80, r=120),
))
fig11_json = fig_to_json(fig11)


# ===================================================================
# Data availability table
# ===================================================================
print("Building data availability table...")

# Bills with cosponsorship edges, per assembly (official edge table)
edges_path = DATA / "cosponsorship_edges.parquet"
edges = pd.read_parquet(edges_path) if edges_path.exists() else None
if edges is not None and "age" not in edges.columns:
    raise SystemExit(f"ERROR: {edges_path} has no age column. It predates the 0.7.0 rebuild, "
                     "so point --data at a 0.7.0 data directory.")
edge_bills = edges.groupby("age")["bill_id"].nunique().to_dict() if edges is not None else {}

avail_rows = []
for age in sorted(all_frames.keys()):
    df = all_frames[age]
    total = len(df)
    has_vote = int(df.get("vote_total", pd.Series(dtype="float64")).notna().sum()) if "vote_total" in df.columns else 0
    has_cmt_proc = int(df["cmt_proc_dt"].notna().sum()) if "cmt_proc_dt" in df.columns else 0
    has_prom = 0
    if "promulgated" in df.columns:
        has_prom = int(df["promulgated"].sum())
    elif "prom_dt" in df.columns:
        has_prom = int(df["prom_dt"].notna().sum())
    has_member = int(edge_bills.get(age, 0))
    has_days = int(df["days_to_proc"].notna().sum()) if "days_to_proc" in df.columns else 0

    avail_rows.append(dict(
        assembly=f"{age}대",
        total=f"{total:,}",
        vote_data="O" if has_vote > 0 else "-",
        vote_n=f"{has_vote:,}" if has_vote > 0 else "-",
        cmt_proc="O" if has_cmt_proc > 0 else "-",
        promulgated=f"{has_prom:,}" if has_prom > 0 else "-",
        member_list=f"{has_member:,}" if has_member > 0 else "-",
        proc_days="O" if has_days > 0 else "-",
        detail_level="Full Master" if "prom_dt" in df.columns else "Lite Master",
    ))


# ===================================================================
# Numbers quoted in the page text
# ===================================================================
print("Computing the numbers quoted in the text...")


def nrows(name: str):
    """Row count of a parquet file in DATA, or None when it is absent."""
    p = DATA / name
    return pq.read_metadata(p).num_rows if p.exists() else None


laws22_n = len(laws22)

# Proposer types (22nd, 법률안)
ppsr22 = ppsr_stats.set_index("ppsr_kind")
chair_enact = ppsr22.loc["위원장", "enact_rate"]
member_enact = ppsr22.loc["의원", "enact_rate"]
govt_enact = ppsr22.loc["정부", "enact_rate"]
claim(govt_enact > member_enact and chair_enact > member_enact,
      "정부 제출 법안과 위원장 발의 법안은 의원 발의 법안보다 가결률이 높습니다")

# Processing time, processed 22nd 법률안 only
proc_median = proc_data.groupby("ppsr_kind")["days_to_proc"].median().round().astype(int)
proc_n = proc_data.groupby("ppsr_kind").size()
first22 = pd.to_datetime(df22["ppsl_dt"]).min()

# Funnel text
f_total = funnel["발의"]
status22 = laws22["status"].value_counts()
pending22 = int(status22.get("계류중", 0))
absorbed22 = int(status22.get("대안반영폐기", 0))

# Votes (bills with a plenary tally)
yes_share = voted["vote_yes"] / voted["vote_total"]
hi_share = pct(int((yes_share >= 0.9).sum()), len(voted))
n_contested = int(voted["contested"].sum())
claim(hi_share > 50, "대다수 법안은 찬성률 90% 이상")

# Research-question previews
tax_nm = "조세특례제한법 일부개정법률안"
tax_n = int((df22["bill_nm"] == tax_nm).sum())
uniq_names22 = int(df22["bill_nm"].nunique())
cmt_lo, cmt_hi = cmt_stats.iloc[0], cmt_stats.iloc[-1]
law_marks = laws22[["law_submit_dt", "law_cmmt_dt"]].notna().any(axis=1)
law_reached = laws22[law_marks]
law_decided = law_reached[law_reached["law_proc_rslt"].notna()]
law_ok = int(law_decided["law_proc_rslt"].isin(["원안가결", "수정가결"]).sum())
claim(len(law_decided) and law_ok / len(law_decided) >= 0.95,
      "법사위에 도달한 법안은 대부분 가결 (핵심 필터는 법사위 회부 여부 자체)")
law_ok_text = (f"{law_ok:,}건은 모두 원안가결 또는 수정가결" if law_ok == len(law_decided) else
               f"{len(law_decided):,}건 가운데 {law_ok:,}건이 원안가결 또는 수정가결")
member_bills_all = int(sum((df["ppsr_kind"] == "의원").sum() for df in all_frames.values()))
if edges is not None:
    edge_rows = len(edges)
    edge_bill_n = int(edges["bill_id"].nunique())
    e22 = edges[edges["age"] == 22]
    leads22 = int(e22.loc[e22["role"] == "대표발의", "member_id"].nunique())
    edges22_n = len(e22)

# Limitations (Section 7)
limits = []
rc_path = DATA / "roll_calls_all.parquet"
ve_path = DATA / "vote_events.parquet"
if rc_path.exists() and ve_path.exists():
    rc22 = pd.read_parquet(rc_path, columns=["term", "bill_id", "member_id", "vote"],
                           filters=[("term", "==", 22)])
    last_vote = pd.read_parquet(rc_path, columns=["date"])["date"].max()[:8]
    no_rows = names22[~names22["mona_cd"].isin(rc22["member_id"])]
    counts = rc22.pivot_table(index="bill_id", columns="vote", aggfunc="size", fill_value=0)
    ve22 = pd.read_parquet(ve_path)
    ve22 = ve22[ve22["age"] == 22].set_index("vote_bill_id").join(counts, how="left").fillna(0)
    diff = ((ve22["찬성"] != ve22["yes"]) | (ve22["반대"] != ve22["no"])
            | (ve22["기권"] != ve22["abstain"]))
    below = diff & (ve22["찬성"] <= ve22["yes"]) & (ve22["반대"] <= ve22["no"]) \
        & (ve22["기권"] <= ve22["abstain"])
    other = int(diff.sum() - below.sum())
    ip_path = DATA / "ideal_points_bridged.csv"
    if ip_path.exists():
        ip = pd.read_csv(ip_path, dtype={"member_id": str})
        claim(not ip[(ip["term"] == 22) & ip["member_id"].isin(no_rows["mona_cd"])].shape[0],
              "기록이 없는 의원은 22대 이념점수가 없습니다")
    limits.append(
        f"22대 의원별 표결은 {last_vote[:4]}년 {int(last_vote[4:6])}월 {int(last_vote[6:])}일까지 수집했습니다. "
        f"의원별 표결 API에는 22대 재직 의원 {len(names22):,}명 중 {len(no_rows)}명의 기록이 없어 "
        f"이들은 22대 이념점수가 없습니다. 22대 표결 {len(ve22):,}건 중 {int(diff.sum()):,}건은 "
        f"의원별 찬성·반대·기권 수가 공식 집계와 다릅니다. 그중 {int(below.sum()):,}건은 세 수가 모두 "
        f"공식 집계 이하여서 빠진 기록으로 설명됩니다"
        + (f". 나머지 {other}건은 기록된 표 가운데 공식 집계와 다른 것이 있습니다." if other else "."))
aa_path = DATA / "alternative_absorption.parquet"
if aa_path.exists():
    absorbed_ids = set(pd.read_parquet(aa_path, columns=["absorbed_bill_id"])["absorbed_bill_id"])
    cover = {}
    for age, df in all_frames.items():
        u = df.loc[df["status"] == "대안반영폐기", "bill_id"]
        cover[age] = pct(int(u.isin(absorbed_ids).sum()), len(u))
    later = [a for a in cover if a != 17]
    limits.append(
        f"대안반영폐기 법안을 흡수한 대안에 연결하는 비율은 17대가 {cover[17]:.1f}%로, "
        f"18-22대의 {min(cover[a] for a in later):.1f}% 이상보다 낮습니다. 17대의 숫자형 의안 ID 대안은 "
        f"공식 API가 흡수 법안 목록을 거의 돌려주지 않기 때문입니다.")
if edges is not None:
    nonlaw_member = pd.concat([df.loc[(df["ppsr_kind"] == "의원") & (df["bill_kind"] != "법률안"), "bill_id"]
                               for df in all_frames.values()])
    nonlaw_edges = int(nonlaw_member.isin(edges["bill_id"]).sum())
    claim(nonlaw_edges == 0, "의원이 발의한 법률안 외 의안은 공동발의 edge가 없습니다")
    limits.append(
        f"의원이 발의한 결의안 등 법률안 외 의안 {len(nonlaw_member):,}건은 제안자 목록이 없어 "
        f"공동발의 edge가 없습니다.")
txt_path = DATA / "bill_texts_linked.parquet"
if txt_path.exists():
    txt_ids = set(pd.read_parquet(txt_path, columns=["BILL_ID"])["BILL_ID"])
    txt_last = max(pd.to_datetime(df.loc[df["bill_id"].isin(txt_ids), "ppsl_dt"]).max()
                   for df in all_frames.values() if df["bill_id"].isin(txt_ids).any())
    limits.append(
        f"제안이유 텍스트는 외부 저장소의 스냅샷에서 가져옵니다. 텍스트가 있는 가장 최근 법안은 "
        f"{txt_last:%Y-%m-%d}에 발의되었고, 그 뒤에 발의된 법안은 텍스트가 없습니다.")
limits_html = "".join(f"<li>{t}</li>" for t in limits)
if edges is not None:
    edge_data_text = (f"공식 공동발의 테이블 <code>cosponsorship_edges</code>. 17-22대 의원발의 법안 "
                      f"{edge_bill_n:,}건, edge {edge_rows:,}개.")
    edge_preview_text = (f"22대 기준 대표발의자 {leads22:,}명, 공동발의 edge {edges22_n:,}개. "
                         "대표발의, 공동발의, 찬성 역할이 구분되어 있습니다.")
else:
    edge_data_text = f"17-22대 의원발의 법안 {member_bills_all:,}건의 <code>publ_mona_cd</code>를 파싱."
    edge_preview_text = "<code>publ_mona_cd</code> 필드를 파싱하면 의원 간 공동발의 edge list를 만들 수 있습니다."
exp_rows = nrows("roll_calls_16_19_experimental.parquet")
exp_text = (f"16-19대 의원별 표결 기록 {exp_rows:,}행은 회의록에서 추출한 실험적 자료입니다. "
            "한 회의의 여러 표결이 하나로 합쳐지는 한계가 있어 roll_calls_16_19_experimental.parquet에 "
            "따로 담았고, 이념점수 추정에는 쓰지 않습니다." if exp_rows else "")

# Life of a Bill: the funnel stages, with the fields that mark them
LIFECYCLE = [
    ("발의", "ppsl_dt", "lc-stage lc-start"),
    ("소관위 회부", "committee_dt", "lc-stage"),
    ("소관위 처리", "cmt_proc_dt", "lc-stage"),
    ("법사위 회부", "law_submit_dt / law_cmmt_dt", "lc-stage"),
    ("본회의 의결", "plenary_decided", "lc-stage"),
    ("공포", "promulgated", "lc-stage lc-end"),
]
lifecycle_html = '\n            <div class="lc-connector"><span>&rarr;</span></div>\n'.join(
    f'''            <div class="{cls}">
                <div class="lc-name">{label}</div>
                <div class="lc-field">{field}</div>
                <div class="lc-n">{funnel[label]:,}</div>
            </div>'''
    for label, field, cls in LIFECYCLE)

# Official structural tables (drawn only when the file exists)
TABLE_CARDS = [
    ("&#128101;", "cosponsorship_edges", "공동발의 네트워크 (17-22대)", "1 row = 1 bill x 발의자",
     "bill_id (FK), member_id, role, party, age"),
    ("&#128269;", "subcommittee_reviews", "소위원회 회부·심사 (17-22대)", "1 row = 1 bill x 소위 단계",
     "bill_id (FK), sub_committee_name, present_dt, proc_dt, proc_result_cd"),
    ("&#128279;", "alternative_absorption", "대안에 흡수된 법안 (17-22대)", "1 row = 1 대안 x 흡수 법안",
     "alt_bill_id, absorbed_bill_id, absorbed_proc_rslt"),
    ("&#128188;", "committee_assignments", "의원 위원회 경력", "1 row = 1 의원 x 위원회 기간",
     "mona_cd, assembly, committee, start_date, end_date"),
    ("&#9888;", "veto_events", "재의요구 (거부권) 사건", "1 row = 1 재의요구",
     "bill_id (FK), veto_bill_id, veto_dt, revote_rslt, final_status"),
    ("&#128499;", "vote_events", "본회의 표결 집계 (20-22대)", "1 row = 1 표결",
     "vote_bill_id, master_bill_id, vote_type, yes, no, abstain"),
]
table_cards_html = "\n".join(
    f'''            <div class="schema-card schema-satellite">
                <div class="schema-icon">{icon}</div>
                <div class="schema-name">{name}</div>
                <div class="schema-desc">{desc}</div>
                <div class="schema-meta">{meta}</div>
                <div class="schema-cols">
                    {cols}
                </div>
                <div class="schema-stat">{nrows(name + ".parquet"):,} rows</div>
            </div>'''
    for icon, name, desc, meta, cols in TABLE_CARDS if nrows(name + ".parquet") is not None)

# ===================================================================
# 3. Build HTML
# ===================================================================
print("Generating HTML...")

# Build the data availability table HTML
avail_table_html = """
<table>
<thead>
<tr>
  <th>대수</th><th>총 법안</th><th>수준</th><th>표결 데이터</th><th>표결 건수</th>
  <th>소관위 처리</th><th>공포 (법률안)</th><th>공동발의 법안</th><th>처리 소요일</th>
</tr>
</thead>
<tbody>
"""
for r in avail_rows:
    cls = ' class="highlight-row"' if r["detail_level"] == "Full Master" else ""
    avail_table_html += f"""<tr{cls}>
  <td><strong>{r['assembly']}</strong></td>
  <td>{r['total']}</td>
  <td><span class="badge {'badge-full' if 'Full' in r['detail_level'] else 'badge-lite'}">{r['detail_level']}</span></td>
  <td>{r['vote_data']}</td>
  <td>{r['vote_n']}</td>
  <td>{r['cmt_proc']}</td>
  <td>{r['promulgated']}</td>
  <td>{r['member_list']}</td>
  <td>{r['proc_days']}</td>
</tr>"""
avail_table_html += "</tbody></table>"


html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Korean National Assembly Database</title>
<script src="{PLOTLY_CDN}"></script>
<style>
/* ============================================================
   CSS Reset & Base
   ============================================================ */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

html {{
    scroll-behavior: smooth;
    font-size: 16px;
}}

body {{
    font-family: {FONT_FAMILY};
    color: #222;
    background: #f8f8f8;
    line-height: 1.7;
}}

/* ============================================================
   Navigation
   ============================================================ */
nav {{
    position: fixed;
    top: 0;
    left: 0;
    width: 220px;
    height: 100vh;
    background: #1a1a2e;
    padding: 24px 16px;
    overflow-y: auto;
    z-index: 100;
    transition: transform 0.3s ease;
}}

nav .nav-title {{
    color: #fff;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 2px solid {NYU_PURPLE};
}}

nav a {{
    display: block;
    color: #aab;
    text-decoration: none;
    font-size: 13px;
    padding: 8px 10px;
    border-radius: 6px;
    margin-bottom: 2px;
    transition: all 0.2s;
}}

nav a:hover, nav a.active {{
    color: #fff;
    background: rgba(87, 6, 140, 0.4);
}}

nav a .nav-num {{
    display: inline-block;
    width: 22px;
    height: 22px;
    line-height: 22px;
    text-align: center;
    border-radius: 50%;
    background: rgba(255,255,255,0.08);
    font-size: 11px;
    margin-right: 8px;
}}

/* Mobile nav toggle */
.nav-toggle {{
    display: none;
    position: fixed;
    top: 12px;
    left: 12px;
    z-index: 200;
    background: {NYU_PURPLE};
    color: #fff;
    border: none;
    border-radius: 8px;
    width: 44px;
    height: 44px;
    font-size: 22px;
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}}

/* ============================================================
   Main content
   ============================================================ */
main {{
    margin-left: 220px;
    min-height: 100vh;
}}

/* ============================================================
   Hero section
   ============================================================ */
.hero {{
    background: linear-gradient(135deg, #1a1a2e 0%, {NYU_PURPLE} 100%);
    color: #fff;
    padding: 80px 60px 60px;
}}

.hero h1 {{
    font-size: 2.6rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin-bottom: 12px;
}}

.hero .subtitle {{
    font-size: 1.15rem;
    color: rgba(255,255,255,0.8);
    max-width: 640px;
    margin-bottom: 36px;
}}

.stat-cards {{
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
}}

.stat-card {{
    background: rgba(255,255,255,0.1);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 12px;
    padding: 20px 28px;
    min-width: 160px;
}}

.stat-card .num {{
    font-size: 2rem;
    font-weight: 800;
    display: block;
    line-height: 1.2;
}}

.stat-card .label {{
    font-size: 0.85rem;
    color: rgba(255,255,255,0.7);
    margin-top: 4px;
}}

/* ============================================================
   Sections
   ============================================================ */
.section {{
    padding: 60px;
    max-width: 1100px;
    margin: 0 auto;
}}

.section:nth-child(even) {{
    background: #fff;
}}

.section-header {{
    margin-bottom: 32px;
}}

.section-header h2 {{
    font-size: 1.7rem;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 8px;
}}

.section-header .section-num {{
    display: inline-block;
    background: {NYU_PURPLE};
    color: #fff;
    font-size: 0.75rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 10px;
    letter-spacing: 0.5px;
}}

.section-header p {{
    color: #555;
    font-size: 0.95rem;
    max-width: 720px;
    line-height: 1.8;
}}

.chart-container {{
    background: #fff;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 32px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    border: 1px solid #eee;
}}

.chart-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
}}

.narrative {{
    background: linear-gradient(135deg, #f5f0fa 0%, #ede7f6 100%);
    border-left: 4px solid {NYU_PURPLE};
    padding: 20px 24px;
    border-radius: 0 8px 8px 0;
    margin: 24px 0;
    font-size: 0.92rem;
    color: #333;
    line-height: 1.9;
}}

/* ============================================================
   Data table
   ============================================================ */
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
    background: #fff;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}}

thead {{
    background: #1a1a2e;
    color: #fff;
}}

th {{
    padding: 12px 16px;
    text-align: left;
    font-weight: 600;
    font-size: 0.82rem;
    letter-spacing: 0.3px;
}}

td {{
    padding: 10px 16px;
    border-bottom: 1px solid #f0f0f0;
}}

tr:hover td {{
    background: #faf8fd;
}}

.highlight-row td {{
    background: #f5f0fa;
    font-weight: 500;
}}

.badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
}}

.badge-full {{
    background: {NYU_PURPLE};
    color: #fff;
}}

.badge-lite {{
    background: #e0e0e0;
    color: #555;
}}

/* ============================================================
   Architecture Diagrams
   ============================================================ */
.arch-diagram {{
    background: #fff;
    border: 1px solid #e8e0f0;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}}

.arch-title {{
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: {NYU_PURPLE};
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid #f0e8f8;
}}

/* Pipeline row */
.pipe-row {{
    display: flex;
    align-items: stretch;
    gap: 0;
    overflow-x: auto;
    padding-bottom: 8px;
}}

.pipe-source {{
    background: #1a1a2e;
    color: #fff;
    border-radius: 10px;
    padding: 16px 20px;
    min-width: 120px;
    text-align: center;
    display: flex;
    flex-direction: column;
    justify-content: center;
}}

.pipe-label {{
    font-weight: 700;
    font-size: 0.88rem;
    line-height: 1.3;
}}

.pipe-sub {{
    font-size: 0.7rem;
    color: rgba(255,255,255,0.6);
    margin-top: 4px;
}}

.pipe-arrow {{
    display: flex;
    align-items: center;
    padding: 0 10px;
    font-size: 1.4rem;
    color: #bbb;
}}

.pipe-phase {{
    background: #f8f6fa;
    border: 1px solid #e0d6ec;
    border-radius: 10px;
    padding: 14px 16px;
    min-width: 130px;
    flex: 1;
}}

.pipe-phase-title {{
    font-size: 0.75rem;
    font-weight: 700;
    color: {NYU_PURPLE};
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

.pipe-api {{
    background: #fff;
    border: 1px solid #e8e0f0;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 0.75rem;
    margin-bottom: 4px;
    font-family: 'SF Mono', monospace;
}}

.pipe-note {{
    font-size: 0.7rem;
    color: #888;
    margin-top: 6px;
    font-style: italic;
}}

/* Lifecycle flow */
.lifecycle-flow {{
    display: flex;
    align-items: center;
    gap: 0;
    overflow-x: auto;
    padding: 8px 0;
}}

.lc-stage {{
    background: #f5f0fa;
    border: 2px solid #e0d6ec;
    border-radius: 10px;
    padding: 12px 14px;
    text-align: center;
    min-width: 100px;
    flex-shrink: 0;
}}

.lc-start {{
    background: {NYU_PURPLE};
    border-color: {NYU_PURPLE};
    color: #fff;
}}

.lc-start .lc-field {{ color: rgba(255,255,255,0.7); }}
.lc-start .lc-n {{ color: rgba(255,255,255,0.9); }}

.lc-end {{
    background: #e8f5e9;
    border-color: #4caf50;
}}

.lc-name {{
    font-weight: 700;
    font-size: 0.82rem;
    margin-bottom: 2px;
}}

.lc-field {{
    font-family: 'SF Mono', monospace;
    font-size: 0.68rem;
    color: #888;
}}

.lc-n {{
    font-size: 0.75rem;
    font-weight: 600;
    color: {NYU_PURPLE};
    margin-top: 4px;
}}

.lc-connector {{
    display: flex;
    align-items: center;
    padding: 0 6px;
    color: #bbb;
    font-size: 1rem;
    flex-shrink: 0;
}}

/* Schema grid */
.schema-grid {{
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
    gap: 16px;
}}

@media (max-width: 900px) {{
    .schema-grid {{ grid-template-columns: 1fr; }}
    .pipe-row {{ flex-direction: column; align-items: center; }}
    .pipe-arrow {{ transform: rotate(90deg); padding: 6px 0; }}
    .lifecycle-flow {{ flex-wrap: wrap; justify-content: center; }}
}}

.schema-card {{
    background: #fafafa;
    border: 2px solid #e0d6ec;
    border-radius: 10px;
    padding: 18px;
}}

.schema-satellite {{
    border-style: dashed;
}}

.schema-icon {{
    font-size: 1.4rem;
    margin-bottom: 6px;
}}

.schema-name {{
    font-weight: 700;
    font-size: 0.95rem;
    color: #1a1a2e;
    font-family: 'SF Mono', monospace;
}}

.schema-desc {{
    font-size: 0.8rem;
    color: #666;
    margin: 4px 0 8px;
}}

.schema-meta {{
    font-size: 0.72rem;
    color: #999;
    font-style: italic;
    margin-bottom: 10px;
}}

.schema-cols {{
    font-size: 0.75rem;
    color: #444;
    line-height: 1.8;
    font-family: 'SF Mono', monospace;
    background: #fff;
    border-radius: 6px;
    padding: 10px 12px;
    border: 1px solid #eee;
}}

.col-group {{
    display: inline-block;
    background: #f0e8f8;
    color: {NYU_PURPLE};
    font-size: 0.68rem;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 4px;
    margin-right: 2px;
    font-family: {FONT_FAMILY};
}}

.schema-stat {{
    font-size: 0.72rem;
    color: #999;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid #eee;
}}

/* ============================================================
   Research Question Cards
   ============================================================ */
.rq-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
}}

@media (max-width: 900px) {{
    .rq-grid {{ grid-template-columns: 1fr; }}
}}

.rq-card {{
    background: #fff;
    border: 1px solid #e8e0f0;
    border-radius: 12px;
    padding: 24px;
    transition: box-shadow 0.2s, transform 0.2s;
}}

.rq-card:hover {{
    box-shadow: 0 4px 20px rgba(87, 6, 140, 0.12);
    transform: translateY(-2px);
}}

.rq-card h3 {{
    font-size: 1.05rem;
    color: #1a1a2e;
    margin: 10px 0 8px;
    line-height: 1.4;
}}

.rq-question {{
    color: #333;
    font-size: 0.9rem;
    font-style: italic;
    margin-bottom: 14px;
    line-height: 1.7;
    border-left: 3px solid {NYU_PURPLE};
    padding-left: 12px;
}}

.rq-tag {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

.rq-descriptive {{ background: #e3f2fd; color: #1565c0; }}
.rq-causal {{ background: #e8f5e9; color: #2e7d32; }}
.rq-ml {{ background: #fff3e0; color: #e65100; }}
.rq-network {{ background: #fce4ec; color: #c62828; }}

.rq-detail {{
    font-size: 0.82rem;
    color: #555;
    line-height: 1.8;
    margin-bottom: 12px;
}}

.rq-detail code {{
    background: #f5f0fa;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 0.78rem;
    color: {NYU_PURPLE};
}}

.rq-preview {{
    background: #fafafa;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.8rem;
    color: #666;
    line-height: 1.7;
}}

/* ============================================================
   Code Blocks
   ============================================================ */
.code-block {{
    background: #1e1e2e;
    border-radius: 12px;
    margin-bottom: 20px;
    overflow: hidden;
}}

.code-header {{
    background: rgba(87, 6, 140, 0.8);
    color: #fff;
    padding: 8px 20px;
    font-size: 0.82rem;
    font-weight: 600;
    letter-spacing: 0.3px;
}}

.code-block pre {{
    padding: 16px 20px;
    margin: 0;
    overflow-x: auto;
}}

.code-block code {{
    color: #cdd6f4;
    font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    line-height: 1.7;
}}

/* ============================================================
   Footer
   ============================================================ */
footer {{
    background: #1a1a2e;
    color: rgba(255,255,255,0.6);
    text-align: center;
    padding: 32px;
    font-size: 0.82rem;
}}

footer a {{
    color: #ddd;
}}

/* ============================================================
   Responsive
   ============================================================ */
@media (max-width: 900px) {{
    nav {{
        transform: translateX(-100%);
    }}
    nav.open {{
        transform: translateX(0);
    }}
    .nav-toggle {{
        display: block;
    }}
    main {{
        margin-left: 0;
    }}
    .hero {{
        padding: 60px 24px 40px;
    }}
    .hero h1 {{
        font-size: 1.8rem;
    }}
    .section {{
        padding: 40px 20px;
    }}
    .chart-row {{
        grid-template-columns: 1fr;
    }}
    .stat-cards {{
        gap: 12px;
    }}
    .stat-card {{
        min-width: 120px;
        padding: 14px 18px;
    }}
    .stat-card .num {{
        font-size: 1.5rem;
    }}
}}
</style>
</head>
<body>

<!-- Mobile nav toggle -->
<button class="nav-toggle" onclick="document.querySelector('nav').classList.toggle('open')" aria-label="Toggle navigation">&#9776;</button>

<!-- Sidebar nav -->
<nav>
    <div class="nav-title">Bill Lifecycle DB</div>
    <a href="#hero"><span class="nav-num">0</span>Overview</a>
    <a href="#architecture"><span class="nav-num">&bull;</span>Data Architecture</a>
    <a href="#cross-assembly"><span class="nav-num">1</span>Cross-Assembly</a>
    <a href="#deep-dive"><span class="nav-num">2</span>22대 Deep Dive</a>
    <a href="#timeline"><span class="nav-num">3</span>Timeline</a>
    <a href="#funnel"><span class="nav-num">4</span>The Funnel</a>
    <a href="#votes"><span class="nav-num">5</span>Vote Patterns</a>
    <a href="#legislators"><span class="nav-num">6</span>Top Legislators</a>
    <a href="#data-avail"><span class="nav-num">7</span>Data Availability</a>
    <a href="#research-q"><span class="nav-num">8</span>Research Questions</a>
    <a href="#get-started"><span class="nav-num">9</span>Get Started</a>
</nav>

<main>

<!-- ============================================================
     Hero
     ============================================================ -->
<section class="hero" id="hero">
    <h1>Korean National Assembly Database</h1>
    <p class="subtitle">
        열린국회정보 Open API의 여러 endpoint를 결합하여 구축한 대한민국 국회 법안 생애주기 마스터 데이터베이스.
        17대부터 22대까지의 발의, 심사, 표결, 공포 전 과정을 추적합니다. {latest_ppsl}까지 발의된 법안을 포함합니다.
    </p>
    <div class="stat-cards">
        <div class="stat-card">
            <span class="num">{grand_total:,}</span>
            <span class="label">Total Bills</span>
        </div>
        <div class="stat-card">
            <span class="num">{len(all_frames)}</span>
            <span class="label">Assemblies ({min(all_frames)}-{max(all_frames)}대)</span>
        </div>
        <div class="stat-card">
            <span class="num">{grand_enacted_laws:,}</span>
            <span class="label">Laws Enacted (법률안 원안·수정가결)</span>
        </div>
        <div class="stat-card">
            <span class="num">{date_range_min}-{date_range_max}</span>
            <span class="label">Date Range</span>
        </div>
    </div>
</section>

<!-- ============================================================
     Data Architecture
     ============================================================ -->
<div class="section" id="architecture" style="background:#fff;">
    <div class="section-header">
        <span class="section-num">DATA ARCHITECTURE</span>
        <h2>데이터 구조와 수집 파이프라인</h2>
        <p>
            열린국회정보 Open API의 목록, 법안별 상세, 제안자·소위·대안 endpoint를 결합하여
            법안 단위(bill-level) 마스터 테이블과 회의·의원 단위 위성 테이블을 구축합니다.
        </p>
    </div>

    <!-- Pipeline diagram -->
    <div class="arch-diagram">
        <div class="arch-title">Collection Pipeline</div>
        <div class="pipe-row">
            <div class="pipe-source">
                <div class="pipe-label">열린국회정보<br>Open API</div>
                <div class="pipe-sub">open.assembly.go.kr</div>
            </div>
            <div class="pipe-arrow">&rarr;</div>
            <div class="pipe-phase">
                <div class="pipe-phase-title">Phase 1: Batch</div>
                <div class="pipe-api">의원발의법률안</div>
                <div class="pipe-api">접수목록 (BILLRCP)</div>
                <div class="pipe-api">심사정보 (BILLJUDGE)</div>
                <div class="pipe-api">표결현황</div>
                <div class="pipe-api">처리의안</div>
                <div class="pipe-note">대수별 목록 일괄 수집</div>
            </div>
            <div class="pipe-arrow">&rarr;</div>
            <div class="pipe-phase">
                <div class="pipe-phase-title">Phase 2: Per-Bill</div>
                <div class="pipe-api">BILLINFODETAIL</div>
                <div class="pipe-api">BILLJUDGECONF</div>
                <div class="pipe-api">BILLLWJUDGECONF</div>
                <div class="pipe-note">법안별 상세 조회</div>
            </div>
            <div class="pipe-arrow">&rarr;</div>
            <div class="pipe-phase">
                <div class="pipe-phase-title">Structure &amp; Votes</div>
                <div class="pipe-api">제안자 목록 (BILLINFOPPSR)</div>
                <div class="pipe-api">소위 심사 (TVBPMCONFINFO)</div>
                <div class="pipe-api">대안 흡수 (TVBPMBILL11)</div>
                <div class="pipe-api">의원별 표결</div>
                <div class="pipe-api">의원 명단·위원회 경력</div>
                <div class="pipe-note">공동발의·소위·대안·표결·위원회 테이블</div>
            </div>
            <div class="pipe-arrow">&rarr;</div>
            <div class="pipe-phase" style="background:linear-gradient(135deg, #57068C, #7b2faa); color:#fff;">
                <div class="pipe-phase-title" style="color:#fff;">Phase 3: Integration</div>
                <div class="pipe-api" style="background:rgba(255,255,255,0.15); color:#fff;">BILL_ID JOIN</div>
                <div class="pipe-api" style="background:rgba(255,255,255,0.15); color:#fff;">재의요구 병합</div>
                <div class="pipe-api" style="background:rgba(255,255,255,0.15); color:#fff;">Derived Variables</div>
                <div class="pipe-api" style="background:rgba(255,255,255,0.15); color:#fff;">.parquet + .sqlite</div>
            </div>
        </div>
    </div>

    <!-- Bill lifecycle flow -->
    <div class="arch-diagram" style="margin-top:28px;">
        <div class="arch-title">법안의 여정 (Life of a Bill)</div>
        <div class="lifecycle-flow">
{lifecycle_html}
        </div>
        <div style="text-align:center; font-size:0.78rem; color:#888; margin-top:8px;">
            각 단계의 날짜와 결과가 개별 변수로 기록됨 &middot; 22대 법률안 기준, 그 단계 또는 이후 단계에 도달한 법안 수
        </div>
    </div>

    <!-- Data schema -->
    <div class="arch-diagram" style="margin-top:28px;">
        <div class="arch-title">Master Database Schema</div>
        <div class="schema-grid">
            <div class="schema-card">
                <div class="schema-icon">&#128209;</div>
                <div class="schema-name">master_bills</div>
                <div class="schema-desc">법안 단위 마스터 테이블</div>
                <div class="schema-meta">1 row = 1 bill</div>
                <div class="schema-cols">
                    <span class="col-group">ID</span> bill_id, bill_no, age, bill_kind, bill_nm<br>
                    <span class="col-group">발의자</span> ppsr_kind, rst_proposer, rst_mona_cd, publ_mona_cd<br>
                    <span class="col-group">타임스탬프</span> ppsl_dt &rarr; committee_dt &rarr; cmt_proc_dt &rarr; law_proc_dt &rarr; rgs_rsln_dt &rarr; prom_dt<br>
                    <span class="col-group">결과</span> status, passed, enacted, plenary_decided, promulgated, law_reflected<br>
                    <span class="col-group">재의요구</span> vetoed, veto_dt, revote_rslt, first_plenary_rslt<br>
                    <span class="col-group">표결</span> vote_yes, vote_no, vote_abstain<br>
                    <span class="col-group">파생</span> days_to_proc, days_to_committee
                </div>
                <div class="schema-stat">{len(df22.columns)} variables &middot; {len(df22):,} rows (22대)</div>
            </div>
            <div class="schema-card schema-satellite">
                <div class="schema-icon">&#128197;</div>
                <div class="schema-name">committee_meetings</div>
                <div class="schema-desc">위원회 회의 기록 (1:N)</div>
                <div class="schema-meta">1 row = 1 bill-meeting step</div>
                <div class="schema-cols">
                    bill_id (FK), jrcmit_conf_nm, jrcmit_conf_dt, jrcmit_conf_rslt
                </div>
                <div class="schema-stat">{len(cm22):,} rows (22대)</div>
            </div>
            <div class="schema-card schema-satellite">
                <div class="schema-icon">&#9878;</div>
                <div class="schema-name">judiciary_meetings</div>
                <div class="schema-desc">법사위 회의 기록 (1:N)</div>
                <div class="schema-meta">1 row = 1 bill-meeting step</div>
                <div class="schema-cols">
                    bill_id (FK), lwcmit_conf_nm, lwcmit_conf_dt, lwcmit_conf_rslt
                </div>
                <div class="schema-stat">{nrows("judiciary_meetings_22.parquet") or 0:,} rows (22대)</div>
            </div>
{table_cards_html}
        </div>
    </div>
</div>

<!-- ============================================================
     Section 1: Cross-Assembly Overview
     ============================================================ -->
<div class="section" id="cross-assembly">
    <div class="section-header">
        <span class="section-num">SECTION 1</span>
        <h2>Cross-Assembly Overview</h2>
        <p>
            17대 국회(2004)부터 22대(2024-)까지 약 20년간 발의된 법안 현황을 조망합니다.
            발의 건수는 꾸준히 증가하는 반면, 가결률은 지속적으로 하락하는 추세를 보입니다.
        </p>
    </div>
    <div class="chart-row">
        <div class="chart-container">
            <div id="chart-assembly-bars"></div>
        </div>
        <div class="chart-container">
            <div id="chart-passage-trend"></div>
        </div>
    </div>
    <div class="narrative">
        <strong>Key finding:</strong>
        17대에 {astats.loc[17, 'total']:,}건이었던 발의 법안 수가 21대에는 {astats.loc[21, 'total']:,}건으로 약 {growth_17_21:.1f}배 증가했습니다.
        반면, 광의 가결률(대안반영 포함)은 {astats.loc[17, 'passage_broad']}%에서 {astats.loc[21, 'passage_broad']}%로,
        협의 가결률(원안·수정가결)은 {astats.loc[17, 'passage_narrow']}%에서 {astats.loc[21, 'passage_narrow']}%로 하락했습니다.
        '입법 인플레이션'의 전형적 패턴입니다. 22대는 아직 진행 중이므로 최종 수치는 변동될 수 있습니다.
    </div>
</div>

<!-- ============================================================
     Section 2: 22nd Assembly Deep Dive
     ============================================================ -->
<div class="section" id="deep-dive" style="background:#fff;">
    <div class="section-header">
        <span class="section-num">SECTION 2</span>
        <h2>22대 국회 심층 분석</h2>
        <p>
            22대 국회의 {len(df22):,}건 법안을 위원회별, 처리 상태별, 발의자 유형별로 살펴봅니다.
            현재 진행 중인 회기이므로 주기적으로 갱신됩니다.
        </p>
    </div>

    <div class="chart-container">
        <div id="chart-cmt-status"></div>
    </div>

    <div class="chart-row">
        <div class="chart-container">
            <div id="chart-cmt-passage"></div>
        </div>
        <div class="chart-container">
            <div id="chart-proposer-type"></div>
        </div>
    </div>

    <div class="narrative">
        <strong>발의자 유형 비교:</strong>
        정부 제출 법안과 위원장 발의 법안은 의원 발의 법안보다 가결률이 높습니다.
        위원장 발의 법안은 소관위에서 여야 합의로 마련된 대안(위원회안)으로, 22대 법률안 기준 협의 가결률이 {chair_enact}%입니다.
        정부 제출 법안은 {govt_enact}%, 의원 발의 법안은 {member_enact}%입니다.
    </div>
</div>

<!-- ============================================================
     Section 3: Legislative Timeline
     ============================================================ -->
<div class="section" id="timeline">
    <div class="section-header">
        <span class="section-num">SECTION 3</span>
        <h2>입법 타임라인</h2>
        <p>
            22대 국회 개원({first22.year}.{first22.month}) 이후 월별 법률안 발의 추이와, 발의자 유형에 따른 처리 소요일 분포를 보여줍니다.
        </p>
    </div>

    <div class="chart-row">
        <div class="chart-container">
            <div id="chart-monthly"></div>
        </div>
        <div class="chart-container">
            <div id="chart-proc-time"></div>
        </div>
    </div>

    <div class="narrative">
        <strong>처리 소요일:</strong>
        처리가 끝난 22대 법률안의 중위 처리 소요일은 위원장 발의 {proc_median['위원장']}일,
        정부 제출 {proc_median['정부']}일, 의원 발의 {proc_median['의원']}일입니다.
        아직 계류 중인 법안은 이 분포에 들어가지 않습니다.
    </div>
</div>

<!-- ============================================================
     Section 4: The Funnel
     ============================================================ -->
<div class="section" id="funnel" style="background:#fff;">
    <div class="section-header">
        <span class="section-num">SECTION 4</span>
        <h2>입법 퍼널</h2>
        <p>
            법률안이 발의부터 공포까지 각 단계를 얼마나 통과하는지 보여줍니다.
            각 단계의 건수는 그 단계에 도달했거나 이후 단계까지 간 법안 수입니다.
            위원장 대안처럼 앞 단계를 건너뛴 법안도 이후 단계에 도달했다면 앞 단계에 포함됩니다.
            본회의 의결은 본회의에서 원안가결, 수정가결 또는 부결된 법안(plenary_decided)이고,
            공포는 공포일이 기록된 법률안(promulgated)입니다. <code>kna stats funnel</code>과 같은 정의입니다.
        </p>
    </div>

    <div class="chart-container" style="max-width:700px;margin:0 auto;">
        <div id="chart-funnel"></div>
    </div>

    <div class="narrative">
        <strong>생존율:</strong>
        22대 법률안 {f_total:,}건 중 소관위 상정 단계에 이른 것은 {funnel['소관위 상정']:,}건으로 {pct(funnel['소관위 상정'], f_total):.1f}%,
        소관위 처리 단계에 이른 것은 {funnel['소관위 처리']:,}건으로 {pct(funnel['소관위 처리'], f_total):.1f}%,
        공포에 이른 것은 {funnel['공포']:,}건으로 {pct(funnel['공포'], f_total):.1f}%입니다.
        처리 상태로 보면 계류중이 {pending22:,}건, 대안반영폐기가 {absorbed22:,}건으로 둘을 합치면 전체의 {pct(pending22 + absorbed22, laws22_n):.1f}%입니다.
    </div>
</div>

<!-- ============================================================
     Section 5: Vote Patterns
     ============================================================ -->
<div class="section" id="votes">
    <div class="section-header">
        <span class="section-num">SECTION 5</span>
        <h2>표결 패턴</h2>
        <p>
            본회의 기명 표결이 이루어진 {len(voted):,}건의 법안에 대한 투표 현황입니다.
            찬성률 80% 미만 법안을 '쟁점 법안'으로 표시하여 여야 갈등 법안을 식별합니다.
        </p>
    </div>

    <div class="chart-row">
        <div class="chart-container">
            <div id="chart-vote-scatter"></div>
        </div>
        <div class="chart-container">
            <div id="chart-approval-hist"></div>
        </div>
    </div>

    <div class="narrative">
        <strong>표결 분포:</strong>
        표결이 기록된 법안의 {hi_share:.1f}%가 찬성률 90% 이상이며, 이는 본회의 상정 전에 이미 여야 합의가 이루어졌음을 시사합니다.
        찬성률 80% 미만인 쟁점 법안은 {n_contested:,}건으로 소수이지만, 정치적으로 중요한 법안이 포함되어 있습니다.
    </div>
</div>

<!-- ============================================================
     Section 6: Top Legislators
     ============================================================ -->
<div class="section" id="legislators" style="background:#fff;">
    <div class="section-header">
        <span class="section-num">SECTION 6</span>
        <h2>의원 발의 순위</h2>
        <p>
            22대 국회에서 법률안을 가장 많이 대표발의한 의원 20인입니다. 공동 대표발의도 각 의원의 건수에 포함합니다.
            막대 색상은 해당 의원의 협의 가결률(enacted rate)을 나타냅니다.
        </p>
    </div>

    <div class="chart-container">
        <div id="chart-top-legs"></div>
    </div>
</div>

<!-- ============================================================
     Section 7: Data Availability
     ============================================================ -->
<div class="section" id="data-avail">
    <div class="section-header">
        <span class="section-num">SECTION 7</span>
        <h2>데이터 구축 현황</h2>
        <p>
            대수별 마스터 데이터 구축 수준을 정리합니다.
            17-22대 모두 열린국회정보 API를 결합한 Full Master이며,
            공포 건수·소관위 처리·처리 소요일 등 법안 생애주기 전체를 포함합니다.
            표결 데이터(건별 찬반)는 20-22대에서 API로 제공됩니다.
        </p>
    </div>

    <div style="overflow-x:auto;">{avail_table_html}</div>

    <div class="narrative" style="margin-top:24px;">
        <strong>갱신 안내:</strong>
        22대 데이터는 현재 진행 중인 회기이므로 주기적으로 갱신됩니다. 이번 판은 {latest_ppsl}까지 발의된 법안을 포함합니다.
        {exp_text}
    </div>

    <div class="narrative">
        <strong>데이터 한계:</strong>
        <ul style="margin:8px 0 0 20px;">{limits_html}</ul>
    </div>
</div>

<!-- ============================================================
     Section 8: Research Questions
     ============================================================ -->
<div class="section" id="research-q" style="background:#fff;">
    <div class="section-header">
        <span class="section-num">SECTION 8</span>
        <h2>이 데이터로 답할 수 있는 연구 질문들</h2>
        <p>
            아래는 본 데이터베이스를 활용하여 탐구할 수 있는 연구 질문입니다.
            각 질문에 필요한 변수, 방법론, 그리고 데이터 가용 수준을 함께 표기합니다.
        </p>
    </div>

    <div class="rq-grid">
        <div class="rq-card">
            <div class="rq-tag rq-descriptive">Descriptive</div>
            <h3>입법 인플레이션과 중복 발의</h3>
            <p class="rq-question">법안 발의 건수의 급증은 실질적 의제 다양성 확대인가, 아니면 동일 법률에 대한 중복 발의(credit claiming)의 증가인가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>bill_nm</code>, <code>ppsl_dt</code>, <code>rst_proposer</code>, <code>committee_nm</code></div>
                <div><strong>방법론:</strong> 법안명 텍스트 클러스터링, 대수별 고유 법률명 수 대비 총 발의 건수 추세</div>
                <div><strong>데이터:</strong> 17-22대 lite master만으로 가능</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> 22대에서 <code>{tax_nm}</code>만 {tax_n:,}건이 발의되었습니다.
                {len(df22):,}건 중 고유 법안명은 {uniq_names22:,}종뿐입니다.
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-causal">Causal Inference</div>
            <h3>여소야대와 입법 효율</h3>
            <p class="rq-question">Divided government(여소야대)는 법안 통과율과 처리 소요기간에 어떤 영향을 미치는가? 어느 입법 단계에서 그 효과가 가장 두드러지는가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>passed</code>, <code>enacted</code>, <code>days_to_proc</code>, <code>ppsr_kind</code> + 외부 여소야대 코딩</div>
                <div><strong>방법론:</strong> DiD (대통령 교체/선거 전후), 단계별 생존분석</div>
                <div><strong>데이터:</strong> 17-22대 full master. 20-21대(박근혜 탄핵 전후)가 자연실험 조건.</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> 통과율이 17대 {astats.loc[17, 'passage_broad']}%에서 21대 {astats.loc[21, 'passage_broad']}%로 꾸준히 하락.
                이것이 여소야대의 빈도 증가 때문인지, 발의 건수 증가 때문인지 분리해야 합니다.
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-causal">Survival Analysis</div>
            <h3>위원회 병목과 법안의 죽음</h3>
            <p class="rq-question">법안은 입법 과정의 어느 단계에서 "죽는가"? 위원회별로 병목 패턴이 다른가? 위원회 위원장의 정당이 심사 속도에 영향을 미치는가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>ppsl_dt</code> ~ <code>prom_dt</code> (전 lifecycle 타임스탬프), <code>committee_nm</code>, <code>status</code></div>
                <div><strong>방법론:</strong> Multi-state survival model, Random Survival Forests, Cox proportional hazards</div>
                <div><strong>데이터:</strong> 22대 full master (lifecycle 날짜 완비). 확장 시 17-22대 전체.</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> 22대 법률안 {f_total:,}건 중 소관위 처리 단계에 이른 것은 {pct(funnel['소관위 처리'], f_total):.1f}%.
                법률안 50건 이상 위원회 가운데 {cmt_lo['committee_nm']} 가결률 {cmt_lo['passage_rate']}%로 최저, {cmt_hi['committee_nm']} {cmt_hi['passage_rate']}%로 최고.
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-causal">Causal Inference</div>
            <h3>법사위 Veto Player 가설</h3>
            <p class="rq-question">법제사법위원회가 야당 법안의 사실상 거부권자(veto player)로 기능하는가? 법사위 체계/자구 심사가 정치적 필터링 기제인가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>law_submit_dt</code>, <code>law_proc_dt</code>, <code>law_proc_rslt</code> + 발의자 여야 코딩</div>
                <div><strong>방법론:</strong> 법사위 단계 체류기간의 발의자 정당별 차이, hazard models</div>
                <div><strong>데이터:</strong> 17-22대 full master + judiciary_meetings 위성 테이블로 다세대 비교 가능.</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> 법사위 회부 기록이 있는 법안은 22대 법률안의 {pct(len(law_reached), laws22_n):.1f}%인 {len(law_reached):,}건에 불과.
                그중 법사위 처리 결과가 있는 {law_ok_text}. 핵심 필터는 법사위 회부 여부 자체.
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-ml">Machine Learning</div>
            <h3>법안 통과 예측과 제도적 변수의 중요도</h3>
            <p class="rq-question">법안 특성(발의 주체, 위원회, 공동발의 규모, 시기 등)으로 통과 여부를 예측할 수 있는가? 어떤 변수가 가장 예측력이 높은가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>passed</code>/<code>enacted</code> (Y), <code>ppsr_kind</code>, <code>committee_nm</code>, <code>proposer_text</code>(공동발의자 수 파싱), <code>ppsl_dt</code>(시기)</div>
                <div><strong>방법론:</strong> Gradient Boosting (XGBoost/LightGBM) + SHAP interpretability</div>
                <div><strong>데이터:</strong> 17-22대 전체. 완료된 국회(17-21대)로 학습, 22대로 검증.</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> 발의 주체가 가장 강력한 예측 변수일 가능성 높음.
                22대 법률안 협의 가결률은 의원 {member_enact}%, 정부 {govt_enact}%, 위원장 {chair_enact}%. 이 격차가 다른 변수 통제 후에도 유지되는지가 관건.
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-network">Network Analysis</div>
            <h3>공동발의 네트워크와 입법 성과</h3>
            <p class="rq-question">교차정당 공동발의 관계가 실제 법안 통과율을 높이는가? 네트워크상 중심성이 높은 의원의 법안이 더 성공적인가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>cosponsorship_edges</code>의 <code>bill_id</code>, <code>member_id</code>, <code>role</code>, <code>party</code> + 마스터의 <code>passed</code>, <code>enacted</code></div>
                <div><strong>방법론:</strong> Cosponsorship 네트워크 구축, centrality 측정, GNN (Graph Neural Networks)</div>
                <div><strong>데이터:</strong> {edge_data_text}</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> {edge_preview_text}
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-descriptive">Descriptive / NLP</div>
            <h3>정책 의제 공간의 구조와 변화</h3>
            <p class="rq-question">한국 국회의 정책 의제 공간은 어떤 구조이며, 정당 간/대수 간 어떻게 변화하는가? 여야가 다른 주제의 법안을 발의하는가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>bill_nm</code> (법안명 텍스트), <code>ppsr_kind</code>, <code>rst_mona_cd</code> + 의원 정당 정보</div>
                <div><strong>방법론:</strong> Korean LLM 임베딩 (KLUE-RoBERTa), UMAP 시각화, Zero-shot CAP 분류</div>
                <div><strong>데이터:</strong> 17-22대 법안명 {grand_total:,}건. 법안 원문 크롤링 시 더 정밀한 분류 가능.</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> 법안명만으로도 주제 분류 가능. "부동산", "조세", "형법" 등 키워드 기반 초기 분류 후
                임베딩으로 세밀한 의제 매핑이 가능합니다.
            </div>
        </div>
    </div>
</div>

<!-- ============================================================
     Section 9: Getting Started
     ============================================================ -->
<div class="section" id="get-started">
    <div class="section-header">
        <span class="section-num">SECTION 9</span>
        <h2>Getting Started</h2>
        <p>
            아래 코드 예시를 통해 데이터를 로드하고 기본적인 분석을 시작할 수 있습니다.
            Python + pandas 환경을 전제합니다.
        </p>
    </div>

    <div class="code-block">
        <div class="code-header">1. 데이터 로드</div>
        <pre><code>import pandas as pd

# 22대 Full Master (전 생애주기 타임스탬프 포함)
master = pd.read_parquet("data/processed/master_bills_22.parquet")
print(f"22대: {{len(master):,}} bills, {{len(master.columns)}} variables")

# 위원회 회의 기록 (1:N)
meetings = pd.read_parquet("data/processed/committee_meetings_22.parquet")

# 17-21대 Full Master
for age in range(17, 22):
    df = pd.read_parquet(f"data/processed/master_bills_{{age}}.parquet")
    print(f"{{age}}대: {{len(df):,}} bills, {{len(df.columns)}} variables")</code></pre>
    </div>

    <div class="code-block">
        <div class="code-header">2. 기본 필터링</div>
        <pre><code># 법률안만 필터링
laws = master[master["bill_kind"] == "법률안"]

# 의원 발의만
member_bills = laws[laws["ppsr_kind"] == "의원"]

# 특정 위원회
health = laws[laws["committee_nm"] == "보건복지위원회"]

# 처리 완료된 법안만
processed = laws[laws["status"] != "계류중"]

# 가결된 법안만
enacted = laws[laws["enacted"] == 1]</code></pre>
    </div>

    <div class="code-block">
        <div class="code-header">3. 공동발의자 네트워크 Edge List</div>
        <pre><code># 공식 공동발의 테이블 (17-22대, 1 row = 1 bill x 발의자)
edges = pd.read_parquet("data/processed/cosponsorship_edges.parquet")
edges22 = edges[edges["age"] == 22]
print(edges22["role"].value_counts())  # 대표발의 / 공동발의 / 찬성

# 법안 결과를 붙여 발의자-법안 네트워크 구성
edge_df = edges22.merge(master[["bill_id", "passed", "enacted"]], on="bill_id")
print(f"Edges: {{len(edge_df):,}}")</code></pre>
    </div>

    <div class="code-block">
        <div class="code-header">4. 다세대 통합 분석</div>
        <pre><code># 17-22대 통합
frames = []
for age in range(17, 23):
    suffix = "" if age == 22 else "_lite"
    path = f"data/processed/master_bills_{{age}}{{suffix}}.parquet"
    df = pd.read_parquet(path)
    frames.append(df)

all_bills = pd.concat(frames, ignore_index=True)
print(f"Total: {{len(all_bills):,}} bills across {{all_bills['age'].nunique()}} assemblies")

# 대수별 가결률 추이
trend = all_bills.groupby("age").agg(
    total=("bill_id", "count"),
    enacted=("enacted", "sum"),
).assign(rate=lambda x: x["enacted"] / x["total"] * 100)
print(trend)</code></pre>
    </div>

    <div class="code-block">
        <div class="code-header">5. SQLite로 쿼리하기</div>
        <pre><code>import sqlite3

conn = sqlite3.connect("data/processed/master_bills_22.sqlite")

# 위원회별 통과율
query = \"\"\"
SELECT committee_nm,
       COUNT(*) as total,
       SUM(enacted) as enacted,
       ROUND(SUM(enacted) * 100.0 / COUNT(*), 1) as rate
FROM bills
WHERE bill_kind = '법률안' AND committee_nm IS NOT NULL
GROUP BY committee_nm
HAVING total >= 50
ORDER BY rate DESC
\"\"\"
pd.read_sql(query, conn)</code></pre>
    </div>

    <h3 style="margin-top:48px; color:#1a1a2e;">R Implementation</h3>
    <p style="color:#555; font-size:0.92rem; margin-bottom:16px;">
        R(tidyverse + arrow) 환경에서의 동일한 분석 코드입니다.
    </p>

    <div class="code-block" style="border:2px solid #2166ac;">
        <div class="code-header" style="background:#2166ac;">1. 데이터 로드 (R)</div>
        <pre><code>library(arrow)
library(dplyr)
library(tidyr)
library(ggplot2)

# 22대 Full Master
master <- read_parquet("data/processed/master_bills_22.parquet")
cat(sprintf("22대: %s bills, %d variables\\n", format(nrow(master), big.mark=","), ncol(master)))

# 위원회 회의 기록
meetings <- read_parquet("data/processed/committee_meetings_22.parquet")

# 17-22대 통합
all_bills <- bind_rows(
  lapply(17:22, function(age) read_parquet(sprintf("data/processed/master_bills_%d.parquet", age)))
)
cat(sprintf("Total: %s bills\\n", format(nrow(all_bills), big.mark=",")))</code></pre>
    </div>

    <div class="code-block" style="border:2px solid #2166ac;">
        <div class="code-header" style="background:#2166ac;">2. 대수별 가결률 추이 (R + ggplot2)</div>
        <pre><code>library(tidyplots)  # 또는 ggplot2

trend <- all_bills %>%
  group_by(age) %>%
  summarise(
    total = n(),
    enacted = sum(enacted),
    passed = sum(passed),
    .groups = "drop"
  ) %>%
  mutate(
    enact_rate = enacted / total * 100,
    pass_rate = passed / total * 100
  )

# tidyplots 방식
trend %>%
  pivot_longer(cols = c(enact_rate, pass_rate),
               names_to = "measure", values_to = "rate") %>%
  tidyplot(x = factor(age), y = rate, color = measure) %>%
  add_data_points(size = 3) %>%
  add_line() %>%
  adjust_colors(c("#D55E00", "#0072B2")) %>%
  adjust_labels(x = "국회 대수", y = "가결률 (%)") %>%
  remove_title() %>%
  adjust_size(width = 150, height = 90) %>%
  save_plot("output/passage_trend.pdf")</code></pre>
    </div>

    <div class="code-block" style="border:2px solid #2166ac;">
        <div class="code-header" style="background:#2166ac;">3. 위원회별 가결률 비교 (R)</div>
        <pre><code>cmt_stats <- master %>%
  filter(bill_kind == "법률안", !is.na(committee_nm)) %>%
  group_by(committee_nm) %>%
  summarise(
    total = n(),
    enacted = sum(enacted),
    passed = sum(passed),
    avg_days = mean(days_to_proc, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  filter(total >= 50) %>%
  mutate(enact_rate = enacted / total * 100) %>%
  arrange(desc(total))

# 가결률 수평 막대
cmt_stats %>%
  tidyplot(x = enact_rate, y = reorder(committee_nm, enact_rate)) %>%
  add_barstack_absolute() %>%
  add_reference_lines(x = median(cmt_stats$enact_rate), linetype = "dashed") %>%
  adjust_colors("#57068C") %>%
  adjust_labels(x = "가결률 (%)", y = "") %>%
  remove_title() %>%
  adjust_size(width = 150, height = 120) %>%
  save_plot("output/committee_rates.pdf")</code></pre>
    </div>

    <div class="code-block" style="border:2px solid #2166ac;">
        <div class="code-header" style="background:#2166ac;">4. 생존분석 (R + survival)</div>
        <pre><code>library(survival)
library(fixest)

# 처리까지의 생존 데이터 구성
surv_data <- master %>%
  filter(bill_kind == "법률안", ppsr_kind %in% c("의원", "정부", "위원장")) %>%
  mutate(
    # 관측 종료: 처리일 또는 현재 날짜
    event = as.integer(!is.na(proc_dt)),
    duration = as.numeric(
      difftime(coalesce(proc_dt, Sys.Date()), ppsl_dt, units = "days")
    )
  ) %>%
  filter(duration >= 0)

# Kaplan-Meier by proposer type
km <- survfit(Surv(duration, event) ~ ppsr_kind, data = surv_data)
plot(km, col = c("#E69F00", "#56B4E9", "#009E73"),
     xlab = "Days", ylab = "Survival probability",
     lwd = 2, mark.time = FALSE)
legend("topright", levels(factor(surv_data$ppsr_kind)),
       col = c("#E69F00", "#56B4E9", "#009E73"), lwd = 2)

# Cox PH model
cox <- coxph(Surv(duration, event) ~ ppsr_kind + committee_nm, data = surv_data)
summary(cox)</code></pre>
    </div>

    <div class="code-block" style="border:2px solid #2166ac;">
        <div class="code-header" style="background:#2166ac;">5. 회귀분석: 통과 여부 예측 (R + fixest)</div>
        <pre><code>library(fixest)

# 공동발의자 수 파싱
reg_data <- master %>%
  filter(bill_kind == "법률안", ppsr_kind == "의원") %>%
  mutate(
    n_cosponsors = stringr::str_extract(proposer_text, "\\\\d+") %>% as.integer(),
    month = format(ppsl_dt, "%Y-%m")
  ) %>%
  filter(!is.na(n_cosponsors))

# Linear probability model with committee FE
m1 <- feols(enacted ~ n_cosponsors | committee_nm, data = reg_data)
m2 <- feols(passed ~ n_cosponsors | committee_nm, data = reg_data)

etable(m1, m2, se = "hetero",
       headers = c("Enacted", "Passed (broad)"),
       notes = "Committee FE included. Robust SE.")</code></pre>
    </div>

    <div class="narrative">
        <strong>추가 리소스:</strong>
        <code>CODEBOOK.md</code>에 마스터 테이블 {len(df22.columns)}개 변수의 상세 설명,
        <code>DATA_AVAILABILITY.md</code>에 대수별 데이터 가용성 및 제약사항,
        <code>CORRECTIONS.md</code>에 정정 이력이 정리되어 있습니다.
    </div>
</div>

</main>

<!-- Footer -->
<footer>
    <p>
        Korean National Assembly Database &middot;
        Data source: <a href="https://open.assembly.go.kr" target="_blank">열린국회정보 Open API</a> &middot;
        Built {pd.Timestamp.now().strftime('%Y-%m-%d')}
    </p>
</footer>

<script>
// ============================================================
// Render all Plotly charts
// ============================================================
const config = {json.dumps(CHART_CONFIG)};

Plotly.newPlot('chart-assembly-bars',
    ...(() => {{ const f = {fig1_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-passage-trend',
    ...(() => {{ const f = {fig2_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-cmt-status',
    ...(() => {{ const f = {fig3_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-cmt-passage',
    ...(() => {{ const f = {fig4_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-proposer-type',
    ...(() => {{ const f = {fig5_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-monthly',
    ...(() => {{ const f = {fig6_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-proc-time',
    ...(() => {{ const f = {fig7_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-funnel',
    ...(() => {{ const f = {fig8_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-vote-scatter',
    ...(() => {{ const f = {fig9_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-approval-hist',
    ...(() => {{ const f = {fig10_json}; return [f.data, f.layout]; }})(),
    config);

Plotly.newPlot('chart-top-legs',
    ...(() => {{ const f = {fig11_json}; return [f.data, f.layout]; }})(),
    config);

// ============================================================
// Scroll spy for nav highlighting
// ============================================================
const sections = document.querySelectorAll('section, .section');
const navLinks = document.querySelectorAll('nav a');

const observer = new IntersectionObserver(entries => {{
    entries.forEach(entry => {{
        if (entry.isIntersecting) {{
            const id = entry.target.id;
            navLinks.forEach(link => {{
                link.classList.toggle('active', link.getAttribute('href') === '#' + id);
            }});
        }}
    }});
}}, {{ rootMargin: '-20% 0px -70% 0px' }});

sections.forEach(s => {{ if (s.id) observer.observe(s); }});

// Close mobile nav on link click
navLinks.forEach(link => {{
    link.addEventListener('click', () => {{
        document.querySelector('nav').classList.remove('open');
    }});
}});
</script>

</body>
</html>
"""

# ===================================================================
# 4. Write output
# ===================================================================
outpath = OUT / "index.html"
outpath.write_text(html, encoding="utf-8")
fsize_mb = outpath.stat().st_size / (1024 * 1024)
print(f"\nDone! Output: {outpath}")
print(f"File size: {fsize_mb:.2f} MB")
