#!/usr/bin/env python3
"""
build_voteview.py
Generate a Korean Voteview-style interactive website (docs/voteview.html).

Inspired by voteview.com but for the Korean National Assembly.
Uses DW-NOMINATE ideal point estimates for the 20th-22nd Assemblies.

Data:
  - data/processed/dw_ideal_points_20_22.csv  (936 legislator-terms)
  - data/processed/roll_calls_all.parquet     (2.4M individual votes)

Output:
  - docs/voteview.html  (standalone, self-contained HTML with Plotly CDN)
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data" / "processed"
OUT_DIR = ROOT / "docs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Load data ─────────────────────────────────────────────────────────
df = pd.read_csv(DATA_DIR / "dw_ideal_points_20_22.csv")

# Flip sign so that negative = liberal (진보), positive = conservative (보수)
# Matches conventional left-right political spectrum
df["aligned"] = -df["aligned"]

# ── Party color mapping ───────────────────────────────────────────────
# Conservative bloc -> red tones, liberal -> blue tones
PARTY_COLORS = {
    "국민의힘": "#E61E2B",
    "자유한국당": "#E61E2B",
    "미래통합당": "#E61E2B",
    "미래한국당": "#E61E2B",
    "더불어민주당": "#004EA2",
    "정의당": "#FFCC00",
    "조국혁신당": "#003764",
    "진보당": "#D6001C",
    "개혁신당": "#FF6B00",
    "무소속": "#808080",
    "열린민주당": "#004EA2",
    # Minor / others
    "민생당": "#999999",
    "새로운미래": "#999999",
    "우리공화당": "#999999",
    "국민의당": "#999999",
    "기본소득당": "#999999",
    "바른미래당": "#999999",
    "민주평화당": "#999999",
    "친박신당": "#999999",
    "민중당": "#999999",
    "자유통일당": "#999999",
    "사회민주당": "#999999",
}

# Party grouping for display order / legend (major parties first)
PARTY_ORDER = [
    "더불어민주당",
    "국민의힘",
    "미래통합당",
    "미래한국당",
    "자유한국당",
    "정의당",
    "조국혁신당",
    "진보당",
    "개혁신당",
    "열린민주당",
    "무소속",
    "민생당",
    "새로운미래",
    "우리공화당",
    "국민의당",
    "기본소득당",
    "바른미래당",
    "민주평화당",
    "친박신당",
    "민중당",
    "자유통일당",
    "사회민주당",
]

# Party bloc assignment for violin / aggregation
PARTY_BLOC = {
    "더불어민주당": "더불어민주당",
    "열린민주당": "더불어민주당 계열",
    "국민의힘": "국민의힘",
    "미래통합당": "국민의힘 계열",
    "미래한국당": "국민의힘 계열",
    "자유한국당": "국민의힘 계열",
    "정의당": "정의당",
    "조국혁신당": "조국혁신당",
    "진보당": "진보당",
    "개혁신당": "개혁신당",
    "무소속": "무소속",
}

# Broader grouping for polarization measure
BROAD_BLOC = {}
for p in [
    "국민의힘", "미래통합당", "미래한국당", "자유한국당",
    "우리공화당", "친박신당", "바른미래당",
]:
    BROAD_BLOC[p] = "conservative"
for p in [
    "더불어민주당", "열린민주당", "민생당", "민주평화당",
    "새로운미래",
]:
    BROAD_BLOC[p] = "liberal"
for p in ["정의당", "조국혁신당", "진보당", "민중당", "기본소득당", "사회민주당"]:
    BROAD_BLOC[p] = "progressive"
BROAD_BLOC["개혁신당"] = "centrist"
BROAD_BLOC["무소속"] = "independent"
BROAD_BLOC["국민의당"] = "centrist"
BROAD_BLOC["자유통일당"] = "conservative"


def get_color(party):
    return PARTY_COLORS.get(party, "#999999")


# ── Assign colors and jitter ─────────────────────────────────────────
np.random.seed(42)
df["color"] = df["party"].apply(get_color)
df["bloc"] = df["party"].map(BROAD_BLOC).fillna("other")

# Y-axis jitter for scatter
jitter_amount = 0.25
df["y_jitter"] = df["term"] + np.random.uniform(
    -jitter_amount, jitter_amount, size=len(df)
)

# ── Compute aggregations ─────────────────────────────────────────────

# 1. Polarization: mean distance between liberal and conservative blocs per term
polar_data = []
for term in sorted(df["term"].unique()):
    tdf = df[df["term"] == term]
    lib_mean = tdf[tdf["bloc"] == "liberal"]["aligned"].mean()
    con_mean = tdf[tdf["bloc"] == "conservative"]["aligned"].mean()
    gap = abs(lib_mean - con_mean)
    polar_data.append({
        "term": term,
        "liberal_mean": round(lib_mean, 3),
        "conservative_mean": round(con_mean, 3),
        "gap": round(gap, 3),
    })
polar_df = pd.DataFrame(polar_data)

# 2. Party means per term (for violin data)
party_term_stats = []
# Major parties present across terms
major_parties = ["더불어민주당", "국민의힘"]
for term in sorted(df["term"].unique()):
    for party in df[df["term"] == term]["party"].unique():
        subset = df[(df["term"] == term) & (df["party"] == party)]
        if len(subset) >= 3:
            party_term_stats.append({
                "term": term,
                "party": party,
                "mean": round(subset["aligned"].mean(), 3),
                "median": round(subset["aligned"].median(), 3),
                "std": round(subset["aligned"].std(), 3),
                "n": len(subset),
                "color": get_color(party),
            })
party_stats_df = pd.DataFrame(party_term_stats)

# 3. Rank within each term
df["rank"] = df.groupby("term")["aligned"].rank(ascending=False).astype(int)
df["total_in_term"] = df.groupby("term")["aligned"].transform("count").astype(int)

# ── Build Plotly JSON traces ──────────────────────────────────────────

# --- Main scatter (Section 2) ---
scatter_traces = []
# Sort parties by order for consistent layering
parties_in_data = [p for p in PARTY_ORDER if p in df["party"].values]
# Remaining parties not in our order list
extra_parties = [p for p in df["party"].unique() if p not in PARTY_ORDER]
all_parties = parties_in_data + extra_parties

for party in all_parties:
    pdf = df[df["party"] == party].copy()
    if pdf.empty:
        continue
    hover_text = []
    for _, row in pdf.iterrows():
        hover_text.append(
            f"<b>{row['member_name']}</b><br>"
            f"정당: {row['party']}<br>"
            f"대수: {int(row['term'])}대 국회<br>"
            f"DW-NOMINATE: {row['aligned']:.3f}<br>"
            f"순위: {int(row['rank'])}/{int(row['total_in_term'])}"
        )
    trace = {
        "x": pdf["aligned"].round(4).tolist(),
        "y": pdf["y_jitter"].round(3).tolist(),
        "mode": "markers",
        "type": "scatter",
        "name": party,
        "text": hover_text,
        "hoverinfo": "text",
        "marker": {
            "color": get_color(party),
            "size": 9,
            "opacity": 0.75,
            "line": {"width": 0.5, "color": "rgba(255,255,255,0.3)"},
        },
        "legendgroup": party,
    }
    scatter_traces.append(trace)

scatter_layout = {
    "title": None,
    "xaxis": {
        "title": {"text": "DW-NOMINATE (1st Dimension, Aligned)", "font": {"size": 13, "color": "#aab"}},
        "range": [-1.15, 1.15],
        "zeroline": True,
        "zerolinecolor": "rgba(255,255,255,0.15)",
        "zerolinewidth": 1,
        "gridcolor": "rgba(255,255,255,0.05)",
        "tickfont": {"color": "#889", "size": 11},
        "showline": False,
    },
    "yaxis": {
        "title": {"text": "국회 대수 (Assembly)", "font": {"size": 13, "color": "#aab"}},
        "tickvals": [20, 21, 22],
        "ticktext": ["20대<br>(2016-20)", "21대<br>(2020-24)", "22대<br>(2024-28)"],
        "range": [19.3, 22.7],
        "gridcolor": "rgba(255,255,255,0.05)",
        "tickfont": {"color": "#889", "size": 11},
        "showline": False,
    },
    "plot_bgcolor": "rgba(0,0,0,0)",
    "paper_bgcolor": "rgba(0,0,0,0)",
    "hovermode": "closest",
    "legend": {
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": "#ccc", "size": 11},
        "itemsizing": "constant",
        "orientation": "h",
        "y": -0.15,
        "x": 0.5,
        "xanchor": "center",
    },
    "margin": {"l": 80, "r": 30, "t": 20, "b": 80},
    "height": 520,
    "annotations": [
        {
            "x": -0.85, "y": 22.55, "text": "← 진보 Liberal",
            "showarrow": False, "font": {"color": "#004EA2", "size": 11},
            "xanchor": "left",
        },
        {
            "x": 0.85, "y": 22.55, "text": "보수 Conservative →",
            "showarrow": False, "font": {"color": "#E61E2B", "size": 11},
            "xanchor": "right",
        },
    ],
}

# --- Violin / box plot (Section 3) ---
# Use box plots grouped by party and term for the distribution view
violin_traces = []
# Select parties with enough members across terms
dist_parties = ["더불어민주당", "국민의힘", "정의당", "조국혁신당", "개혁신당", "무소속"]
dist_colors = {p: get_color(p) for p in dist_parties}

for term in [20, 21, 22]:
    for party in dist_parties:
        subset = df[(df["term"] == term) & (df["party"] == party)]
        if len(subset) < 2:
            continue
        violin_traces.append({
            "type": "violin",
            "x": [f"{term}대"] * len(subset),
            "y": subset["aligned"].round(4).tolist(),
            "name": party,
            "legendgroup": party,
            "showlegend": (term == 20),
            "scalemode": "width",
            "width": 0.45,
            "box": {"visible": True},
            "meanline": {"visible": True},
            "line": {"color": dist_colors.get(party, "#999")},
            "fillcolor": dist_colors.get(party, "#999"),
            "opacity": 0.6,
            "side": "both",
            "points": False,
            "spanmode": "hard",
        })

violin_layout = {
    "title": None,
    "xaxis": {
        "title": {"text": "국회 대수", "font": {"size": 13, "color": "#aab"}},
        "tickfont": {"color": "#889", "size": 12},
        "gridcolor": "rgba(255,255,255,0.05)",
    },
    "yaxis": {
        "title": {"text": "DW-NOMINATE (Aligned)", "font": {"size": 13, "color": "#aab"}},
        "range": [-1.15, 1.15],
        "zeroline": True,
        "zerolinecolor": "rgba(255,255,255,0.15)",
        "gridcolor": "rgba(255,255,255,0.05)",
        "tickfont": {"color": "#889", "size": 11},
    },
    "plot_bgcolor": "rgba(0,0,0,0)",
    "paper_bgcolor": "rgba(0,0,0,0)",
    "hovermode": "closest",
    "violinmode": "group",
    "violingap": 0.15,
    "violingroupgap": 0.05,
    "legend": {
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": "#ccc", "size": 11},
        "orientation": "h",
        "y": -0.18,
        "x": 0.5,
        "xanchor": "center",
    },
    "margin": {"l": 60, "r": 30, "t": 20, "b": 80},
    "height": 440,
}

# --- Polarization trend (Section 4) ---
polar_traces = [
    {
        "x": polar_df["term"].apply(lambda t: f"{t}대").tolist(),
        "y": polar_df["liberal_mean"].tolist(),
        "mode": "lines+markers+text",
        "type": "scatter",
        "name": "더불어민주당 계열 평균",
        "text": [f"{v:.3f}" for v in polar_df["liberal_mean"]],
        "textposition": "bottom center",
        "textfont": {"color": "#7799cc", "size": 11},
        "line": {"color": "#004EA2", "width": 3},
        "marker": {"color": "#004EA2", "size": 10},
    },
    {
        "x": polar_df["term"].apply(lambda t: f"{t}대").tolist(),
        "y": polar_df["conservative_mean"].tolist(),
        "mode": "lines+markers+text",
        "type": "scatter",
        "name": "국민의힘 계열 평균",
        "text": [f"{v:.3f}" for v in polar_df["conservative_mean"]],
        "textposition": "top center",
        "textfont": {"color": "#cc7777", "size": 11},
        "line": {"color": "#E61E2B", "width": 3},
        "marker": {"color": "#E61E2B", "size": 10},
    },
]
# Gap annotation traces (shaded area between means)
polar_traces.append({
    "x": polar_df["term"].apply(lambda t: f"{t}대").tolist()
       + polar_df["term"].apply(lambda t: f"{t}대").tolist()[::-1],
    "y": polar_df["liberal_mean"].tolist()
       + polar_df["conservative_mean"].tolist()[::-1],
    "fill": "toself",
    "fillcolor": "rgba(87,6,140,0.15)",
    "line": {"color": "rgba(0,0,0,0)"},
    "type": "scatter",
    "mode": "none",
    "name": "양극화 거리",
    "showlegend": True,
    "hoverinfo": "skip",
})

polar_layout = {
    "title": None,
    "xaxis": {
        "title": {"text": "국회 대수", "font": {"size": 13, "color": "#aab"}},
        "tickfont": {"color": "#889", "size": 12},
        "gridcolor": "rgba(255,255,255,0.05)",
    },
    "yaxis": {
        "title": {"text": "평균 DW-NOMINATE (Aligned)", "font": {"size": 13, "color": "#aab"}},
        "range": [-0.65, 0.75],
        "zeroline": True,
        "zerolinecolor": "rgba(255,255,255,0.15)",
        "gridcolor": "rgba(255,255,255,0.05)",
        "tickfont": {"color": "#889", "size": 11},
    },
    "plot_bgcolor": "rgba(0,0,0,0)",
    "paper_bgcolor": "rgba(0,0,0,0)",
    "hovermode": "closest",
    "legend": {
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": "#ccc", "size": 11},
        "orientation": "h",
        "y": -0.2,
        "x": 0.5,
        "xanchor": "center",
    },
    "margin": {"l": 60, "r": 30, "t": 20, "b": 80},
    "height": 400,
    "annotations": [
        {
            "x": f"{row['term']}대",
            "y": (row["liberal_mean"] + row["conservative_mean"]) / 2,
            "text": f"거리: {row['gap']:.3f}",
            "showarrow": False,
            "font": {"color": "#b388d9", "size": 12, "family": "monospace"},
            "bgcolor": "rgba(87,6,140,0.3)",
            "borderpad": 4,
        }
        for _, row in polar_df.iterrows()
    ],
}

# ── Build legislator table rows (Section 5) ──────────────────────────
table_rows = []
for _, row in df.sort_values("aligned", ascending=False).iterrows():
    table_rows.append({
        "name": row["member_name"],
        "party": row["party"],
        "term": int(row["term"]),
        "score": round(row["aligned"], 4),
        "rank": int(row["rank"]),
        "total": int(row["total_in_term"]),
        "color": row["color"],
    })

# ── HTML generation ───────────────────────────────────────────────────

html_template = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Korean National Assembly Voteview</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {
    --bg-primary: #0a0a1a;
    --bg-card: #111128;
    --bg-card-alt: #0d0d22;
    --accent: #57068C;
    --accent-light: #8b3fbf;
    --text-primary: #e0e0ee;
    --text-secondary: #8888aa;
    --text-muted: #555577;
    --border: #222244;
    --red: #E61E2B;
    --blue: #004EA2;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }

  .container {
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 24px;
  }

  /* ── Header ────────────────────────────────── */
  header {
    padding: 48px 0 32px;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(180deg, #0e0e2a 0%, var(--bg-primary) 100%);
  }

  header .container {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .header-top {
    display: flex;
    align-items: baseline;
    gap: 16px;
    flex-wrap: wrap;
  }

  h1 {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #e0e0ee 0%, #b388d9 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .subtitle-ko {
    font-size: 1.15rem;
    color: var(--accent-light);
    font-weight: 400;
  }

  .header-desc {
    color: var(--text-secondary);
    font-size: 0.9rem;
    max-width: 700px;
  }

  .stats-row {
    display: flex;
    gap: 32px;
    margin-top: 8px;
    flex-wrap: wrap;
  }

  .stat-item {
    display: flex;
    align-items: baseline;
    gap: 6px;
  }

  .stat-num {
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--accent-light);
    font-variant-numeric: tabular-nums;
  }

  .stat-label {
    font-size: 0.8rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  /* ── Sections ──────────────────────────────── */
  section {
    padding: 40px 0;
    border-bottom: 1px solid var(--border);
  }

  section:last-of-type {
    border-bottom: none;
  }

  .section-head {
    margin-bottom: 20px;
  }

  .section-head h2 {
    font-size: 1.3rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .section-head .section-sub {
    font-size: 0.85rem;
    color: var(--text-muted);
  }

  .chart-container {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    overflow: hidden;
  }

  /* ── Party legend (below main scatter) ─────── */
  .party-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 20px;
    margin-top: 16px;
    padding: 12px 16px;
    background: var(--bg-card-alt);
    border-radius: 6px;
    border: 1px solid var(--border);
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .legend-swatch {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* ── Table ─────────────────────────────────── */
  .table-controls {
    display: flex;
    gap: 12px;
    margin-bottom: 12px;
    flex-wrap: wrap;
    align-items: center;
  }

  .search-box {
    flex: 1;
    min-width: 200px;
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg-card);
    color: var(--text-primary);
    font-size: 0.9rem;
    font-family: inherit;
    outline: none;
    transition: border-color 0.2s;
  }

  .search-box:focus {
    border-color: var(--accent-light);
  }

  .search-box::placeholder {
    color: var(--text-muted);
  }

  .filter-select {
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg-card);
    color: var(--text-primary);
    font-size: 0.85rem;
    font-family: inherit;
    outline: none;
    cursor: pointer;
  }

  .filter-select:focus {
    border-color: var(--accent-light);
  }

  .data-table-wrap {
    max-height: 520px;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: 6px;
  }

  .data-table-wrap::-webkit-scrollbar {
    width: 6px;
  }
  .data-table-wrap::-webkit-scrollbar-track {
    background: var(--bg-card);
  }
  .data-table-wrap::-webkit-scrollbar-thumb {
    background: var(--border);
    border-radius: 3px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }

  thead {
    position: sticky;
    top: 0;
    z-index: 2;
  }

  th {
    background: var(--bg-card-alt);
    color: var(--text-secondary);
    font-weight: 600;
    text-align: left;
    padding: 10px 14px;
    border-bottom: 2px solid var(--accent);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  th:hover {
    color: var(--text-primary);
  }

  th .sort-arrow {
    margin-left: 4px;
    opacity: 0.4;
    font-size: 0.7rem;
  }

  th.sorted .sort-arrow {
    opacity: 1;
    color: var(--accent-light);
  }

  td {
    padding: 8px 14px;
    border-bottom: 1px solid rgba(34,34,68,0.5);
    color: var(--text-primary);
  }

  tr:hover td {
    background: rgba(87,6,140,0.08);
  }

  .party-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.82rem;
  }

  .party-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .score-cell {
    font-variant-numeric: tabular-nums;
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 0.82rem;
  }

  .score-bar {
    display: inline-block;
    height: 4px;
    border-radius: 2px;
    margin-left: 8px;
    vertical-align: middle;
    min-width: 2px;
  }

  .table-footer {
    padding: 8px 14px;
    font-size: 0.78rem;
    color: var(--text-muted);
    background: var(--bg-card-alt);
    border-top: 1px solid var(--border);
    border-radius: 0 0 6px 6px;
  }

  /* ── Methodology note ──────────────────────── */
  .method-note {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 24px;
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.7;
  }

  .method-note h3 {
    color: var(--text-primary);
    font-size: 1rem;
    margin-bottom: 12px;
  }

  .method-note p {
    margin-bottom: 10px;
  }

  .method-note a {
    color: var(--accent-light);
    text-decoration: none;
  }

  .method-note a:hover {
    text-decoration: underline;
  }

  .method-note code {
    background: rgba(87,6,140,0.15);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.82rem;
    font-family: 'SF Mono', 'Menlo', monospace;
  }

  /* ── Footer ────────────────────────────────── */
  footer {
    padding: 32px 0;
    text-align: center;
    color: var(--text-muted);
    font-size: 0.78rem;
  }

  footer a {
    color: var(--accent-light);
    text-decoration: none;
  }

  /* ── Grid for side-by-side charts ──────────── */
  .chart-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }

  @media (max-width: 768px) {
    h1 { font-size: 1.5rem; }
    .stats-row { gap: 16px; }
    .stat-num { font-size: 1.3rem; }
    .chart-grid { grid-template-columns: 1fr; }
    header { padding: 32px 0 24px; }
    section { padding: 28px 0; }
  }
</style>
</head>
<body>

<!-- ═══════════════ HEADER ═══════════════ -->
<header>
  <div class="container">
    <div class="header-top">
      <h1>Korean National Assembly Voteview</h1>
    </div>
    <div class="subtitle-ko">대한민국 국회 이념지도</div>
    <div class="header-desc">
      DW-NOMINATE Ideal Point Estimates, 20th - 22nd Assembly (2016 - 2026)
    </div>
    <div class="stats-row">
      <div class="stat-item">
        <span class="stat-num">936</span>
        <span class="stat-label">Legislator-Terms</span>
      </div>
      <div class="stat-item">
        <span class="stat-num">3</span>
        <span class="stat-label">Assemblies</span>
      </div>
      <div class="stat-item">
        <span class="stat-num">2.4M</span>
        <span class="stat-label">Roll Call Votes</span>
      </div>
    </div>
  </div>
</header>

<!-- ═══════════════ MAIN SCATTER ═══════════════ -->
<section>
  <div class="container">
    <div class="section-head">
      <h2>Legislator Ideal Point Map</h2>
      <div class="section-sub">Each dot represents one legislator-term. Hover for details.</div>
    </div>
    <div class="chart-container">
      <div id="scatter-chart"></div>
    </div>
    <div class="party-legend" id="party-legend"></div>
  </div>
</section>

<!-- ═══════════════ DISTRIBUTION + POLARIZATION ═══════════════ -->
<section>
  <div class="container">
    <div class="chart-grid">
      <div>
        <div class="section-head">
          <h2>Party Distribution</h2>
          <div class="section-sub">Ideological spread by party across assemblies</div>
        </div>
        <div class="chart-container">
          <div id="violin-chart"></div>
        </div>
      </div>
      <div>
        <div class="section-head">
          <h2>Polarization Trend</h2>
          <div class="section-sub">Distance between liberal and conservative bloc means</div>
        </div>
        <div class="chart-container">
          <div id="polar-chart"></div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ═══════════════ LEGISLATOR TABLE ═══════════════ -->
<section>
  <div class="container">
    <div class="section-head">
      <h2>Legislator Search</h2>
      <div class="section-sub">936 legislator-terms sorted by ideological score</div>
    </div>
    <div class="table-controls">
      <input type="text" class="search-box" id="search-input"
             placeholder="의원 이름 또는 정당 검색 (Search by name or party)">
      <select class="filter-select" id="term-filter">
        <option value="all">모든 대수</option>
        <option value="20">20대 (2016-20)</option>
        <option value="21">21대 (2020-24)</option>
        <option value="22">22대 (2024-28)</option>
      </select>
    </div>
    <div class="data-table-wrap">
      <table id="data-table">
        <thead>
          <tr>
            <th data-col="name">이름 <span class="sort-arrow">&#9650;</span></th>
            <th data-col="party">정당 <span class="sort-arrow">&#9650;</span></th>
            <th data-col="term">대수 <span class="sort-arrow">&#9650;</span></th>
            <th data-col="score" class="sorted">점수 <span class="sort-arrow">&#9660;</span></th>
            <th data-col="rank">순위 <span class="sort-arrow">&#9650;</span></th>
          </tr>
        </thead>
        <tbody id="table-body"></tbody>
      </table>
    </div>
    <div class="table-footer">
      <span id="table-count">936</span> results shown
    </div>
  </div>
</section>

<!-- ═══════════════ METHODOLOGY ═══════════════ -->
<section>
  <div class="container">
    <div class="section-head">
      <h2>Methodology</h2>
    </div>
    <div class="method-note">
      <h3>DW-NOMINATE Estimation</h3>
      <p>
        Ideal points are estimated using the <strong>DW-NOMINATE</strong> (Dynamic Weighted NOMINAl
        Three-step Estimation) scaling procedure, the same method used for the U.S. Congress at
        <a href="https://voteview.com" target="_blank" rel="noopener">voteview.com</a>. The model
        recovers latent ideological positions from observed roll call voting patterns.
      </p>
      <p>
        The first dimension typically captures the primary left-right (progressive-conservative)
        cleavage. Scores range from -1 to +1. In the Korean context, negative values correspond
        to the conservative bloc (국민의힘 and predecessor parties) while positive values
        correspond to the liberal-progressive bloc (더불어민주당 and allied parties). This polarity
        is arbitrary and reflects the alignment procedure described below.
      </p>

      <h3>Bridging Alignment</h3>
      <p>
        Because each assembly is estimated independently, raw NOMINATE scores are not directly
        comparable across terms. To address this, scores are <strong>aligned</strong> using
        legislators who served in multiple consecutive assemblies as bridging anchors. The
        <code>aligned</code> score shown in all visualizations reflects this cross-assembly
        normalization, making it meaningful to compare ideological positions across the 20th,
        21st, and 22nd assemblies.
      </p>

      <h3>Data Sources</h3>
      <p>
        Roll call voting data was collected from the
        <a href="https://open.assembly.go.kr" target="_blank" rel="noopener">열린국회정보 Open API</a>,
        covering all plenary votes in the 20th (2016-2020), 21st (2020-2024), and 22nd
        (2024-present) National Assemblies. The dataset includes 2,425,113 individual vote
        records from 936 legislator-terms.
      </p>
    </div>
  </div>
</section>

<!-- ═══════════════ FOOTER ═══════════════ -->
<footer>
  <div class="container">
    Korean National Assembly Voteview &middot;
    Built with <a href="https://plotly.com/javascript/" target="_blank" rel="noopener">Plotly.js</a>
    &middot; Data from
    <a href="https://open.assembly.go.kr" target="_blank" rel="noopener">열린국회정보 API</a>
  </div>
</footer>

<script>
// ── Chart data (embedded by Python) ──────────────────────────────────
const scatterTraces = SCATTER_TRACES_JSON;
const scatterLayout = SCATTER_LAYOUT_JSON;
const violinTraces  = VIOLIN_TRACES_JSON;
const violinLayout  = VIOLIN_LAYOUT_JSON;
const polarTraces   = POLAR_TRACES_JSON;
const polarLayout   = POLAR_LAYOUT_JSON;
const tableData     = TABLE_DATA_JSON;

const plotConfig = {responsive: true, displayModeBar: false};

// ── Render charts ────────────────────────────────────────────────────
Plotly.newPlot('scatter-chart', scatterTraces, scatterLayout, plotConfig);
Plotly.newPlot('violin-chart', violinTraces, violinLayout, plotConfig);
Plotly.newPlot('polar-chart', polarTraces, polarLayout, plotConfig);

// ── Build party legend ───────────────────────────────────────────────
const legendParties = LEGEND_PARTIES_JSON;
const legendEl = document.getElementById('party-legend');
legendParties.forEach(function(p) {
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.innerHTML = '<span class="legend-swatch" style="background:' + p.color + '"></span>' + p.name + ' (' + p.n + ')';
  legendEl.appendChild(item);
});

// ── Table logic ──────────────────────────────────────────────────────
const tbody = document.getElementById('table-body');
const searchInput = document.getElementById('search-input');
const termFilter = document.getElementById('term-filter');
const tableCount = document.getElementById('table-count');

let sortCol = 'score';
let sortAsc = false;
let currentData = tableData.slice();

function makeScoreBar(score) {
  // score is -1 to 1. Map to a bar.
  const absScore = Math.abs(score);
  const width = Math.round(absScore * 60);
  const color = score < 0 ? 'var(--red)' : 'var(--blue)';
  return '<span class="score-bar" style="width:' + width + 'px;background:' + color + '"></span>';
}

function renderTable(data) {
  let html = '';
  const limit = Math.min(data.length, 936);
  for (let i = 0; i < limit; i++) {
    const r = data[i];
    html += '<tr>'
      + '<td><strong>' + r.name + '</strong></td>'
      + '<td><span class="party-badge"><span class="party-dot" style="background:' + r.color + '"></span>' + r.party + '</span></td>'
      + '<td>' + r.term + '대</td>'
      + '<td class="score-cell">' + r.score.toFixed(4) + makeScoreBar(r.score) + '</td>'
      + '<td>' + r.rank + ' / ' + r.total + '</td>'
      + '</tr>';
  }
  tbody.innerHTML = html;
  tableCount.textContent = limit;
}

function filterAndSort() {
  const q = searchInput.value.trim().toLowerCase();
  const t = termFilter.value;
  let filtered = tableData.filter(function(r) {
    const matchQ = !q || r.name.toLowerCase().includes(q) || r.party.toLowerCase().includes(q);
    const matchT = t === 'all' || String(r.term) === t;
    return matchQ && matchT;
  });
  filtered.sort(function(a, b) {
    let va = a[sortCol], vb = b[sortCol];
    if (typeof va === 'string') { va = va.toLowerCase(); vb = vb.toLowerCase(); }
    if (va < vb) return sortAsc ? -1 : 1;
    if (va > vb) return sortAsc ? 1 : -1;
    return 0;
  });
  currentData = filtered;
  renderTable(filtered);
}

searchInput.addEventListener('input', filterAndSort);
termFilter.addEventListener('change', filterAndSort);

// Column sorting
document.querySelectorAll('#data-table th').forEach(function(th) {
  th.addEventListener('click', function() {
    const col = this.dataset.col;
    if (sortCol === col) { sortAsc = !sortAsc; }
    else { sortCol = col; sortAsc = (col === 'name' || col === 'party'); }
    // Update header arrows
    document.querySelectorAll('#data-table th').forEach(function(h) {
      h.classList.remove('sorted');
      h.querySelector('.sort-arrow').innerHTML = '&#9650;';
    });
    this.classList.add('sorted');
    this.querySelector('.sort-arrow').innerHTML = sortAsc ? '&#9650;' : '&#9660;';
    filterAndSort();
  });
});

// Initial render
filterAndSort();
</script>
</body>
</html>
"""

# ── Build legend data ─────────────────────────────────────────────────
legend_parties = []
seen = set()
for party in all_parties:
    if party in seen:
        continue
    seen.add(party)
    n = len(df[df["party"] == party])
    if n > 0:
        legend_parties.append({
            "name": party,
            "color": get_color(party),
            "n": n,
        })

# ── Inject JSON into template ─────────────────────────────────────────
def to_json(obj):
    return json.dumps(obj, ensure_ascii=False)


html = html_template
html = html.replace("SCATTER_TRACES_JSON", to_json(scatter_traces))
html = html.replace("SCATTER_LAYOUT_JSON", to_json(scatter_layout))
html = html.replace("VIOLIN_TRACES_JSON", to_json(violin_traces))
html = html.replace("VIOLIN_LAYOUT_JSON", to_json(violin_layout))
html = html.replace("POLAR_TRACES_JSON", to_json(polar_traces))
html = html.replace("POLAR_LAYOUT_JSON", to_json(polar_layout))
html = html.replace("TABLE_DATA_JSON", to_json(table_rows))
html = html.replace("LEGEND_PARTIES_JSON", to_json(legend_parties))

out_path = OUT_DIR / "voteview.html"
out_path.write_text(html, encoding="utf-8")

# ── Summary ───────────────────────────────────────────────────────────
print(f"Generated: {out_path}")
print(f"  File size: {out_path.stat().st_size / 1024:.0f} KB")
print(f"  Legislator-terms: {len(df)}")
print(f"  Parties: {df['party'].nunique()}")
print(f"  Assemblies: {sorted(df['term'].unique())}")
print(f"\nPolarization:")
for _, row in polar_df.iterrows():
    print(f"  {int(row['term'])}대: gap = {row['gap']:.3f}"
          f"  (liberal mean {row['liberal_mean']:.3f},"
          f" conservative mean {row['conservative_mean']:.3f})")
