#!/usr/bin/env python3
"""
build_site.py - Generate interactive HTML tutorial for Korean Bill Lifecycle DB.

Reads parquet data, computes aggregated statistics, builds Plotly charts,
and outputs a single self-contained site/index.html file.

Usage:
    python3 build_site.py
"""

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent
DATA = BASE / "data" / "processed"
OUT = BASE / "docs"
OUT.mkdir(exist_ok=True)

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

lite_frames = {}
for age in [17, 18, 19, 20, 21]:
    lite_frames[age] = pd.read_parquet(DATA / f"master_bills_{age}_lite.parquet")

# Build cross-assembly summary from lite + 22
all_frames = {**lite_frames, 22: df22}

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

astats = pd.DataFrame(assembly_stats)

# Grand totals
grand_total = astats["total"].sum()
grand_enacted = astats["enacted"].sum()
date_range_min = "2004"
date_range_max = "2026"

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

bills_only = df22[df22["bill_kind"] == "법률안"]
funnel_stages = [
    ("발의", len(bills_only)),
    ("소관위 회부", int(bills_only["committee_dt"].notna().sum())),
    ("소관위 상정", int(bills_only["cmt_present_dt"].notna().sum())),
    ("소관위 처리", int(bills_only["cmt_proc_dt"].notna().sum())),
    ("법사위 회부", int(bills_only["law_submit_dt"].notna().sum())),
    ("본회의 의결", int(bills_only["rgs_rsln_dt"].notna().sum())),
    ("공포", int(bills_only["prom_dt"].notna().sum())),
]

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

member_bills = laws22[laws22["ppsr_kind"] == "의원"].copy()
leg_stats = (
    member_bills.groupby("rst_proposer")
    .agg(total=("bill_id", "count"), enacted=("enacted", "sum"))
    .reset_index()
)
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
    title=dict(text="22대 발의 상위 20인 (법률안, 대표발의 기준)", font=dict(size=18)),
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

avail_rows = []
for age in sorted(all_frames.keys()):
    df = all_frames[age]
    total = len(df)
    has_vote = int(df.get("vote_total", pd.Series(dtype="float64")).notna().sum()) if "vote_total" in df.columns else 0
    has_cmt_proc = int(df["cmt_proc_dt"].notna().sum()) if "cmt_proc_dt" in df.columns else 0
    has_prom = 0
    if "prom_dt" in df.columns:
        has_prom = int(df["prom_dt"].notna().sum())
    has_member = int(df["member_list"].notna().sum()) if "member_list" in df.columns else 0
    has_days = int(df["days_to_proc"].notna().sum()) if "days_to_proc" in df.columns else 0

    avail_rows.append(dict(
        assembly=f"{age}대",
        total=f"{total:,}",
        vote_data="O" if has_vote > 0 else "-",
        vote_n=f"{has_vote:,}" if has_vote > 0 else "-",
        cmt_proc="O" if has_cmt_proc > 0 else "-",
        promulgated=f"{has_prom:,}" if has_prom > 0 else "-",
        member_list="O" if has_member > 0 else "-",
        proc_days="O" if has_days > 0 else "-",
        detail_level="Full Master" if age == 22 else "Lite Master",
    ))


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
  <th>소관위 처리</th><th>공포 건수</th><th>공동발의자</th><th>처리 소요일</th>
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
<title>Korean Bill Lifecycle Database</title>
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
    min-width: 160px;
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
    <h1>Korean Bill Lifecycle Database</h1>
    <p class="subtitle">
        열린국회정보 Open API 8종을 결합하여 구축한 대한민국 국회 법안 생애주기 마스터 데이터베이스.
        17대부터 22대까지의 발의, 심사, 표결, 공포 전 과정을 추적합니다.
    </p>
    <div class="stat-cards">
        <div class="stat-card">
            <span class="num">{grand_total:,}</span>
            <span class="label">Total Bills</span>
        </div>
        <div class="stat-card">
            <span class="num">6</span>
            <span class="label">Assemblies (17-22대)</span>
        </div>
        <div class="stat-card">
            <span class="num">{grand_enacted:,}</span>
            <span class="label">Laws Enacted</span>
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
            8개의 열린국회정보 Open API를 결합하여 법안 단위(bill-level) 마스터 테이블과
            회의 단위(meeting-level) 위성 테이블을 구축합니다.
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
                <div class="pipe-note">~180 requests / 대수</div>
            </div>
            <div class="pipe-arrow">&rarr;</div>
            <div class="pipe-phase">
                <div class="pipe-phase-title">Phase 2: Per-Bill</div>
                <div class="pipe-api">BILLINFODETAIL</div>
                <div class="pipe-api">BILLJUDGECONF</div>
                <div class="pipe-api">BILLLWJUDGECONF</div>
                <div class="pipe-note">~17,000 x 3 calls / 대수</div>
            </div>
            <div class="pipe-arrow">&rarr;</div>
            <div class="pipe-phase" style="background:linear-gradient(135deg, #57068C, #7b2faa); color:#fff;">
                <div class="pipe-phase-title" style="color:#fff;">Phase 3: Integration</div>
                <div class="pipe-api" style="background:rgba(255,255,255,0.15); color:#fff;">BILL_ID JOIN</div>
                <div class="pipe-api" style="background:rgba(255,255,255,0.15); color:#fff;">Derived Variables</div>
                <div class="pipe-api" style="background:rgba(255,255,255,0.15); color:#fff;">.parquet + .sqlite</div>
            </div>
        </div>
    </div>

    <!-- Bill lifecycle flow -->
    <div class="arch-diagram" style="margin-top:28px;">
        <div class="arch-title">법안의 여정 (Life of a Bill)</div>
        <div class="lifecycle-flow">
            <div class="lc-stage lc-start">
                <div class="lc-name">발의</div>
                <div class="lc-field">ppsl_dt</div>
                <div class="lc-n">{len(df22):,}</div>
            </div>
            <div class="lc-connector"><span>&rarr;</span></div>
            <div class="lc-stage">
                <div class="lc-name">소관위 회부</div>
                <div class="lc-field">committee_dt</div>
                <div class="lc-n">{int(df22['committee_dt'].notna().sum()):,}</div>
            </div>
            <div class="lc-connector"><span>&rarr;</span></div>
            <div class="lc-stage">
                <div class="lc-name">소관위 심사</div>
                <div class="lc-field">cmt_proc_dt</div>
                <div class="lc-n">{int(df22['cmt_proc_dt'].notna().sum()):,}</div>
            </div>
            <div class="lc-connector"><span>&rarr;</span></div>
            <div class="lc-stage">
                <div class="lc-name">법사위</div>
                <div class="lc-field">law_proc_dt</div>
                <div class="lc-n">{int(df22['law_proc_dt'].notna().sum()):,}</div>
            </div>
            <div class="lc-connector"><span>&rarr;</span></div>
            <div class="lc-stage">
                <div class="lc-name">본회의</div>
                <div class="lc-field">rgs_rsln_dt</div>
                <div class="lc-n">{int(df22['rgs_rsln_dt'].notna().sum()) if 'rgs_rsln_dt' in df22.columns else 0:,}</div>
            </div>
            <div class="lc-connector"><span>&rarr;</span></div>
            <div class="lc-stage lc-end">
                <div class="lc-name">공포</div>
                <div class="lc-field">prom_dt</div>
                <div class="lc-n">{int(df22['prom_dt'].notna().sum()) if 'prom_dt' in df22.columns else 0:,}</div>
            </div>
        </div>
        <div style="text-align:center; font-size:0.78rem; color:#888; margin-top:8px;">
            각 단계의 날짜가 개별 변수로 기록됨 &middot; 22대 법안 기준 건수 표시
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
                    <span class="col-group">결과</span> status, passed, enacted, proc_rslt<br>
                    <span class="col-group">표결</span> vote_yes, vote_no, vote_abstain<br>
                    <span class="col-group">파생</span> days_to_proc, days_to_committee
                </div>
                <div class="schema-stat">{len(df22.columns)} variables &middot; {len(df22):,} rows (22대)</div>
            </div>
            <div class="schema-card schema-satellite">
                <div class="schema-icon">&#128197;</div>
                <div class="schema-name">committee_meetings</div>
                <div class="schema-desc">위원회 회의 기록 (1:N)</div>
                <div class="schema-meta">1 row = 1 bill-meeting</div>
                <div class="schema-cols">
                    bill_id (FK), conf_name, conf_dt, conf_result
                </div>
                <div class="schema-stat">108,749 rows (22대)</div>
            </div>
            <div class="schema-card schema-satellite">
                <div class="schema-icon">&#9878;</div>
                <div class="schema-name">judiciary_meetings</div>
                <div class="schema-desc">법사위 회의 기록 (1:N)</div>
                <div class="schema-meta">1 row = 1 bill-meeting</div>
                <div class="schema-cols">
                    bill_id (FK), conf_name, conf_dt, conf_result
                </div>
                <div class="schema-stat">1,082 rows (22대)</div>
            </div>
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
        17대에 {astats.iloc[0]['total']:,}건이었던 발의 법안 수가 21대에는 {astats.iloc[4]['total']:,}건으로 약 3.2배 증가했습니다.
        반면, 광의 가결률(대안반영 포함)은 {astats.iloc[0]['passage_broad']}%에서 {astats.iloc[4]['passage_broad']}%로,
        협의 가결률(공포 기준)은 {astats.iloc[0]['passage_narrow']}%에서 {astats.iloc[4]['passage_narrow']}%로 하락했습니다.
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
            전체 데이터(Full Master)가 구축된 유일한 대수입니다.
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
        정부제출 법안과 위원장 발의 법안은 의원 발의 법안 대비 현저히 높은 가결률을 보입니다.
        위원장 발의 법안은 소관위에서 여야 합의로 마련된 대안(위원회안)이기 때문에
        사실상 전수 통과합니다. 의원 발의 법안의 실질 가결률은 3.3%에 불과합니다.
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
            22대 국회 개원(2024.5) 이후 월별 법률안 발의 추이와, 발의자 유형에 따른 처리 소요일 분포를 보여줍니다.
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
        정부 제출 법안은 중위 처리기간이 상대적으로 짧으며 분포도 좁은 편입니다.
        의원 발의 법안은 편차가 크고, 장기 계류되는 사례가 많아 분포의 꼬리가 깁니다.
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
            대안반영(위원회 대안에 흡수)된 법안은 별도 경로를 거치므로, 단계별 수치가
            단순 감소하지 않을 수 있습니다.
        </p>
    </div>

    <div class="chart-container" style="max-width:700px;margin:0 auto;">
        <div id="chart-funnel"></div>
    </div>

    <div class="narrative">
        <strong>생존율:</strong>
        22대 법률안 {funnel_stages[0][1]:,}건 중 소관위에 상정된 것은 {funnel_stages[2][1]:,}건({funnel_stages[2][1]/funnel_stages[0][1]*100:.1f}%),
        소관위 처리까지 이른 것은 {funnel_stages[3][1]:,}건({funnel_stages[3][1]/funnel_stages[0][1]*100:.1f}%),
        최종 공포에 이른 것은 {funnel_stages[6][1]:,}건({funnel_stages[6][1]/funnel_stages[0][1]*100:.1f}%)입니다.
        대부분의 법안이 소관위 단계에서 계류 또는 대안반영으로 소멸합니다.
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
        대다수 법안은 찬성률 90% 이상으로 가결되며, 이는 본회의 상정 전에 이미 여야 합의가 이루어졌음을 시사합니다.
        찬성률이 낮은 쟁점 법안은 소수이지만, 정치적으로 중요한 법안이 포함되어 있습니다.
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
            22대 국회에서 법률안을 가장 많이 대표발의한 의원 20인입니다.
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
            22대는 열린국회정보 API 8종을 결합한 Full Master이며,
            17-21대는 기본 법안정보 + 처리 결과를 포함하는 Lite Master입니다.
        </p>
    </div>

    {avail_table_html}

    <div class="narrative" style="margin-top:24px;">
        <strong>Phase 2 계획:</strong>
        17-21대에 대해서도 개별 법안 상세정보(소관위 처리, 표결, 공동발의자 등)를 수집하여
        Full Master로 업그레이드할 예정입니다.
        22대 데이터는 현재 진행 중인 회기이므로 주기적으로 갱신됩니다.
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
                <em>Quick preview:</em> 22대에서 <code>조세특례제한법 일부개정법률안</code>만 661건이 발의되었습니다.
                17,205건 중 고유 법안명은 2,984종뿐입니다.
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-causal">Causal Inference</div>
            <h3>여소야대와 입법 효율</h3>
            <p class="rq-question">Divided government(여소야대)는 법안 통과율과 처리 소요기간에 어떤 영향을 미치는가? 어느 입법 단계에서 그 효과가 가장 두드러지는가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>passed</code>, <code>enacted</code>, <code>days_to_proc</code>, <code>ppsr_kind</code> + 외부 여소야대 코딩</div>
                <div><strong>방법론:</strong> DiD (대통령 교체/선거 전후), 단계별 생존분석</div>
                <div><strong>데이터:</strong> Phase 2 완료 후 17-22대 full master 권장. 20-21대(박근혜 탄핵 전후)가 자연실험 조건.</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> 통과율이 17대 53.3%에서 21대 35.7%로 꾸준히 하락.
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
                <em>Quick preview:</em> 22대 법률안 16,907건 중 소관위 처리까지 도달한 것은 23.6%.
                재정경제기획위원회 가결률 0.5%로 최저, 문화체육관광위원회 6.1%로 최고.
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-causal">Causal Inference</div>
            <h3>법사위 Veto Player 가설</h3>
            <p class="rq-question">법제사법위원회가 야당 법안의 사실상 거부권자(veto player)로 기능하는가? 법사위 체계/자구 심사가 정치적 필터링 기제인가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>law_submit_dt</code>, <code>law_proc_dt</code>, <code>law_proc_rslt</code> + 발의자 여야 코딩</div>
                <div><strong>방법론:</strong> 법사위 단계 체류기간의 발의자 정당별 차이, hazard models</div>
                <div><strong>데이터:</strong> 22대 full master + judiciary_meetings 위성 테이블. Phase 2 완료 후 다세대 비교 가능.</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> 법사위 회부까지 도달하는 법안은 22대 기준 3.0% (510건)에 불과.
                도달한 법안의 가결률은 99.6% (459/461건). 핵심 필터는 법사위 회부 여부 자체.
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
                의원 가결률 3.3% vs 정부 62.6% vs 위원장 99.7% - 이 격차가 다른 변수 통제 후에도 유지되는지가 관건.
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-network">Network Analysis</div>
            <h3>공동발의 네트워크와 입법 성과</h3>
            <p class="rq-question">교차정당 공동발의 관계가 실제 법안 통과율을 높이는가? 네트워크상 중심성이 높은 의원의 법안이 더 성공적인가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>rst_mona_cd</code>, <code>publ_mona_cd</code>(파싱 → edge list), <code>passed</code>, <code>enacted</code></div>
                <div><strong>방법론:</strong> Cosponsorship 네트워크 구축, centrality 측정, GNN (Graph Neural Networks)</div>
                <div><strong>데이터:</strong> 17-22대 의원발의 법안 (93,288건). na-legislative-events-korea 프로젝트와 직접 연결 가능.</div>
            </div>
            <div class="rq-preview">
                <em>Quick preview:</em> <code>publ_mona_cd</code> 필드를 파싱하면 의원 간 공동발의 edge list를 즉시 생성 가능.
                22대 기준 421명의 대표발의자, 13,894개의 고유 공동발의 조합이 존재합니다.
            </div>
        </div>

        <div class="rq-card">
            <div class="rq-tag rq-descriptive">Descriptive / NLP</div>
            <h3>정책 의제 공간의 구조와 변화</h3>
            <p class="rq-question">한국 국회의 정책 의제 공간은 어떤 구조이며, 정당 간/대수 간 어떻게 변화하는가? 여야가 다른 주제의 법안을 발의하는가?</p>
            <div class="rq-detail">
                <div><strong>핵심 변수:</strong> <code>bill_nm</code> (법안명 텍스트), <code>ppsr_kind</code>, <code>rst_mona_cd</code> + 의원 정당 정보</div>
                <div><strong>방법론:</strong> Korean LLM 임베딩 (KLUE-RoBERTa), UMAP 시각화, Zero-shot CAP 분류</div>
                <div><strong>데이터:</strong> 17-22대 법안명 (110,778건). 법안 원문 크롤링 시 더 정밀한 분류 가능.</div>
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

# 17-21대 Lite Master
for age in range(17, 22):
    df = pd.read_parquet(f"data/processed/master_bills_{{age}}_lite.parquet")
    print(f"{{age}}대: {{len(df):,}} bills")</code></pre>
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
        <div class="code-header">3. 공동발의자 네트워크 Edge List 생성</div>
        <pre><code># publ_mona_cd를 파싱하여 edge list 생성
edges = []
for _, row in member_bills.iterrows():
    if pd.notna(row["publ_mona_cd"]) and pd.notna(row["rst_mona_cd"]):
        co_sponsors = row["publ_mona_cd"].split(",")
        for cs in co_sponsors:
            edges.append({{
                "bill_id": row["bill_id"],
                "from": row["rst_mona_cd"],
                "to": cs.strip(),
                "passed": row["passed"],
            }})

edge_df = pd.DataFrame(edges)
print(f"Edges: {{len(edge_df):,}}")  # 수십만 개의 공동발의 관계</code></pre>
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
  lapply(17:21, function(age) read_parquet(sprintf("data/processed/master_bills_%d_lite.parquet", age))),
  master
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
      difftime(coalesce(proc_dt, as.Date("2026-03-22")), ppsl_dt, units = "days")
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
        <code>CODEBOOK.md</code>에 54개 변수의 상세 설명,
        <code>DATA_AVAILABILITY.md</code>에 대수별 데이터 가용성 및 제약사항,
        <code>MASTER_DATA_PLAN.md</code>에 확장 로드맵이 정리되어 있습니다.
    </div>
</div>

</main>

<!-- Footer -->
<footer>
    <p>
        Korean Bill Lifecycle Database &middot;
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
