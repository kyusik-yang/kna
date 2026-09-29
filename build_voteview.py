#!/usr/bin/env python3
"""
build_voteview.py
Generate a Korean Voteview-style interactive website (voteview.html).

Inspired by voteview.com but for the Korean National Assembly.
Uses the default bridged ideal-point series for the 20th-22nd Assemblies,
labelled with each legislator's party at election. Party blocs come from
the party_bloc column of the ideal-point files, and every number on the
page is computed from the data directory. See CODEBOOK.md, section
'Ideal Points', for how the series is built.

Data (read from --data, default data/processed):
  - ideal_points_bridged.csv          default series (bridged_1d, party, party_bloc, vintage)
  - ideal_points_wnominate.csv        per-assembly W-NOMINATE (comparison text)
  - ideal_points_dwnominate.csv       pooled DW-NOMINATE (comparison text)
  - ideal_points_bridging_params.csv  bridging legislators per term
  - ideal_points_manifest.json        vote dates, record counts, scaling settings
  - roll_calls_all.parquet, members_22.parquet  record count, coverage note

Output:
  - voteview.html in --out (default docs), standalone HTML with Plotly CDN

Usage:
    python3 build_voteview.py                                # data/processed -> docs/
    python3 build_voteview.py --data data/_build --out docs  # staged build
"""

import argparse
import json
import re
import numpy as np
import pandas as pd
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent


def _parse_args():
    p = argparse.ArgumentParser(description="Build the ideal-point map (voteview.html).")
    p.add_argument("--data", default=str(ROOT / "data" / "processed"),
                   help="data directory to read (default data/processed)")
    p.add_argument("--out", default=str(ROOT / "docs"),
                   help="directory to write voteview.html into (default docs)")
    return p.parse_args()


ARGS = _parse_args()
DATA_DIR = Path(ARGS.data).expanduser().resolve()
OUT_DIR = Path(ARGS.out).expanduser().resolve()
if not (DATA_DIR / "ideal_points_bridged.csv").exists():
    raise SystemExit(f"ERROR: {DATA_DIR / 'ideal_points_bridged.csv'} not found")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Load data ─────────────────────────────────────────────────────────
df = pd.read_csv(DATA_DIR / "ideal_points_bridged.csv", dtype={"member_id": str})

# ideal_points_bridged.csv is already oriented to the Voteview convention:
# positive = conservative (보수), negative = liberal (진보). No flip needed.
df["aligned"] = df["bridged_1d"]

# Vintage: one label per file, "v" + the date of the last vote used
vintages = sorted(df["vintage"].dropna().unique()) if "vintage" in df.columns else []
if len(vintages) > 1:
    raise SystemExit(f"ERROR: ideal_points_bridged.csv mixes vintages {vintages}")
VINTAGE = vintages[0] if vintages else None
manifest_path = DATA_DIR / "ideal_points_manifest.json"
MANIFEST = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
if MANIFEST and VINTAGE and MANIFEST.get("vintage") != VINTAGE:
    raise SystemExit(f"ERROR: manifest vintage {MANIFEST.get('vintage')} != CSV vintage {VINTAGE}")

rc_path = DATA_DIR / "roll_calls_all.parquet"
if MANIFEST.get("terms"):
    FIRST_VOTE = min(t["first_vote_date"] for t in MANIFEST["terms"])
    LAST_VOTE = max(t["last_vote_date"] for t in MANIFEST["terms"])
    N_VOTE_RECORDS = MANIFEST["input"]["api_rows_after_cutoff"]
else:
    rc_dates = pd.read_parquet(rc_path, columns=["date"])["date"]
    FIRST_VOTE, LAST_VOTE = rc_dates.min()[:8], rc_dates.max()[:8]
    if VINTAGE and re.fullmatch(r"v\d{8}", VINTAGE):
        LAST_VOTE = VINTAGE[1:]
    N_VOTE_RECORDS = int(((rc_dates.str[:8] <= LAST_VOTE)).sum())


def ymd(s: str) -> str:
    """'YYYYMMDD...' -> 'YYYY-MM-DD'."""
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


TERMS = sorted(int(t) for t in df["term"].unique())
SETTINGS = MANIFEST.get("settings", {})
bridge_path = DATA_DIR / "ideal_points_bridging_params.csv"
BRIDGING = pd.read_csv(bridge_path) if bridge_path.exists() else pd.DataFrame()

# ── Party color mapping ───────────────────────────────────────────────
# Parties are the party at election, so the conservative and liberal
# lineages appear under their election-time names and satellite parties.
PARTY_COLORS = {
    "국민의힘": "#E61E2B",
    "자유한국당": "#E61E2B",
    "미래통합당": "#E61E2B",
    "미래한국당": "#E61E2B",
    "새누리당": "#E61E2B",
    "국민의미래": "#E61E2B",
    "더불어민주당": "#004EA2",
    "더불어시민당": "#004EA2",
    "더불어민주연합": "#004EA2",
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
    "시대전환": "#999999",
}

# Party grouping for display order / legend (major parties first)
PARTY_ORDER = [
    "더불어민주당",
    "더불어시민당",
    "더불어민주연합",
    "국민의힘",
    "국민의미래",
    "미래통합당",
    "미래한국당",
    "자유한국당",
    "새누리당",
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
    "시대전환",
]

# Party blocs come from the party_bloc column written by
# build_ideal_points.R, so the page, the CSV files and CODEBOOK share one
# coding. The polarization gap is conservative minus liberal bloc means.
BLOC_ORDER = ["liberal", "conservative", "progressive", "rebuilding",
              "centrist", "liberal_minor", "independent"]
BLOC_LABELS = {
    "liberal": "더불어민주당 계열",
    "conservative": "국민의힘 계열",
    "progressive": "진보 정당",
    "rebuilding": "조국혁신당",
    "centrist": "중도 정당",
    "liberal_minor": "민주 계열 소수정당",
    "independent": "무소속·기타",
}
BLOC_COLORS = {
    "liberal": "#004EA2",
    "conservative": "#E61E2B",
    "progressive": "#FFCC00",
    "rebuilding": "#003764",
    "centrist": "#FF6B00",
    "liberal_minor": "#5B8FD6",
    "independent": "#808080",
}


def get_color(party):
    return PARTY_COLORS.get(party, "#999999")


# ── Assign colors and jitter ─────────────────────────────────────────
np.random.seed(42)
df["color"] = df["party"].apply(get_color)
df["bloc"] = df["party_bloc"]
blocs_in_data = [b for b in BLOC_ORDER if b in set(df["bloc"])] + \
    sorted(set(df["bloc"]) - set(BLOC_ORDER))

# Y-axis jitter for scatter
jitter_amount = 0.25
df["y_jitter"] = df["term"] + np.random.uniform(
    -jitter_amount, jitter_amount, size=len(df)
)

# ── Compute aggregations ─────────────────────────────────────────────


def bloc_gaps(frame: pd.DataFrame, col: str) -> pd.DataFrame:
    """Liberal and conservative bloc means per term, and their distance."""
    rows = []
    for term, tdf in frame.groupby("term"):
        lib = tdf.loc[tdf["party_bloc"] == "liberal", col].mean()
        con = tdf.loc[tdf["party_bloc"] == "conservative", col].mean()
        rows.append({"term": int(term), "liberal_mean": lib,
                     "conservative_mean": con, "gap": abs(con - lib)})
    return pd.DataFrame(rows)


def gap_growth(frame: pd.DataFrame, col: str) -> float:
    """Percent change of the bloc distance from the first to the last term."""
    g = bloc_gaps(frame, col).set_index("term")["gap"]
    return (g.iloc[-1] - g.iloc[0]) / g.iloc[0] * 100


def change_words(x: float) -> str:
    """Korean phrase for a percent change, rounded to a whole percent."""
    r = int(round(abs(x)))
    if r == 0:
        return "거의 변하지 않는다"
    return f"약 {r}% {'증가한다' if x > 0 else '감소한다'}"


# 1. Polarization: mean distance between liberal and conservative blocs per term
polar_df = bloc_gaps(df, "aligned").round(3)

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

# 3. Rank within each term. 1 = most liberal, the same convention as the
# kna CLI (kna legislator), so ranks are comparable between the two.
df["rank"] = df.groupby("term")["aligned"].rank(ascending=True, method="min").astype(int)
df["total_in_term"] = df.groupby("term")["aligned"].transform("count").astype(int)

# 4. Numbers for the page text
wnom_path = DATA_DIR / "ideal_points_wnominate.csv"
dw_path = DATA_DIR / "ideal_points_dwnominate.csv"
growth = {"bridged": gap_growth(df, "aligned")}
if wnom_path.exists():
    growth["wnom"] = gap_growth(pd.read_csv(wnom_path), "wnom_1d")
if dw_path.exists():
    growth["dw"] = gap_growth(pd.read_csv(dw_path), "dwnom_1d")

# Members of the latest term with no member-level votes, hence no score
last_term = TERMS[-1]
mem_path = DATA_DIR / f"members_{last_term}.parquet"
no_votes = None
if mem_path.exists() and rc_path.exists():
    mem_last = pd.read_parquet(mem_path, columns=["mona_cd"])
    rc_ids = pd.read_parquet(rc_path, columns=["term", "member_id"],
                             filters=[("term", "==", last_term)])["member_id"]
    no_votes = mem_last[~mem_last["mona_cd"].isin(rc_ids)]
    scored = df.loc[df["term"] == last_term, "member_id"]
    if no_votes["mona_cd"].isin(scored).any():
        raise SystemExit("ERROR: a legislator without member-level votes has an ideal point")
    n_members_last = len(mem_last)

# Bloc composition, listed under the charts
bloc_parties = {
    b: df.loc[df["bloc"] == b, "party"].value_counts().index.tolist()
    for b in blocs_in_data
}

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
            f"정당 (선거 당시): {row['party']}<br>"
            f"대수: {int(row['term'])}대 국회<br>"
            f"이념점수: {row['aligned']:.3f}<br>"
            f"순위: {int(row['rank'])}/{int(row['total_in_term'])} (1 = 가장 진보)"
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

PLOT_FONT = {
    "family": "-apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', "
              "'Noto Sans KR', 'Segoe UI', Roboto, sans-serif",
    "color": "#ccd",
}

scatter_layout = {
    "title": None,
    "font": PLOT_FONT,
    "xaxis": {
        "title": {"text": "이념점수 (1차원, bridging 정렬)", "font": {"size": 13, "color": "#aab"}},
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
# Distributions by party bloc and term. Election-time party names split the
# two main lineages across terms (새누리당, 미래통합당, 국민의힘, ...), so
# the view groups them by party_bloc.
violin_traces = []
legend_shown = set()

for term in TERMS:
    for bloc in blocs_in_data:
        subset = df[(df["term"] == term) & (df["bloc"] == bloc)]
        if len(subset) < 2:
            continue
        label = BLOC_LABELS.get(bloc, bloc)
        violin_traces.append({
            "type": "violin",
            "x": [f"{term}대"] * len(subset),
            "y": subset["aligned"].round(4).tolist(),
            "name": label,
            "legendgroup": bloc,
            "showlegend": bloc not in legend_shown,
            "scalemode": "width",
            "width": 0.45,
            "box": {"visible": True},
            "meanline": {"visible": True},
            "line": {"color": BLOC_COLORS.get(bloc, "#999")},
            "fillcolor": BLOC_COLORS.get(bloc, "#999"),
            "opacity": 0.6,
            "side": "both",
            "points": False,
            "spanmode": "hard",
        })
        legend_shown.add(bloc)

violin_layout = {
    "title": None,
    "font": PLOT_FONT,
    "xaxis": {
        "title": {"text": "국회 대수", "font": {"size": 13, "color": "#aab"}},
        "tickfont": {"color": "#889", "size": 12},
        "gridcolor": "rgba(255,255,255,0.05)",
    },
    "yaxis": {
        "title": {"text": "이념점수 (bridging 정렬)", "font": {"size": 13, "color": "#aab"}},
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
    "font": PLOT_FONT,
    "xaxis": {
        "title": {"text": "국회 대수", "font": {"size": 13, "color": "#aab"}},
        "tickfont": {"color": "#889", "size": 12},
        "gridcolor": "rgba(255,255,255,0.05)",
    },
    "yaxis": {
        "title": {"text": "평균 이념점수 (bridging 정렬)", "font": {"size": 13, "color": "#aab"}},
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
            "x": f"{int(row['term'])}대",
            "y": (row["liberal_mean"] + row["conservative_mean"]) / 2,
            "text": f"거리 {row['gap']:.3f}",
            "showarrow": False,
            "font": {"color": "#e8d4ff", "size": 12},
            "bgcolor": "rgba(87,6,140,0.45)",
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
<title>Korean National Assembly Voteview - 대한민국 국회 이념지도</title>
<meta name="description" content="__META_DESC__">
<meta name="author" content="Kyusik Yang">
<meta property="og:title" content="Korean National Assembly Voteview">
<meta property="og:description" content="Interactive ideology map for Korean legislators, __TERM_RANGE_EN__ Assemblies.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://kyusik-yang.github.io/kna/voteview.html">
<meta name="twitter:card" content="summary">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
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

  .home-link {
    color: var(--text-muted);
    text-decoration: none;
    font-size: 0.85rem;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    width: fit-content;
    transition: color 0.2s;
  }

  .home-link:hover {
    color: var(--accent-light);
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
    <a href="index.html" class="home-link">&larr; kna home</a>
    <div class="header-top">
      <h1>Korean National Assembly Voteview</h1>
    </div>
    <div class="subtitle-ko">대한민국 국회 이념지도</div>
    <div class="header-desc">
      __HEADER_DESC__
    </div>
    <div class="stats-row">
      <div class="stat-item">
        <span class="stat-num">__N_LEG__</span>
        <span class="stat-label">Legislator-Terms</span>
      </div>
      <div class="stat-item">
        <span class="stat-num">__N_TERMS__</span>
        <span class="stat-label">Assemblies</span>
      </div>
      <div class="stat-item">
        <span class="stat-num">__N_VOTES__</span>
        <span class="stat-label">Vote Records</span>
      </div>
    </div>
  </div>
</header>

<!-- ═══════════════ MAIN SCATTER ═══════════════ -->
<section>
  <div class="container">
    <div class="section-head">
      <h2>Legislator Ideal Point Map</h2>
      <div class="section-sub">Each dot represents one legislator-term, colored by party at election. Hover for details.</div>
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
          <div class="section-sub">Ideological spread by party bloc across assemblies</div>
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
    <div class="section-sub" style="margin-top:4px; line-height:1.9;">
      __BLOC_NOTE__
    </div>
  </div>
</section>

<!-- ═══════════════ LEGISLATOR TABLE ═══════════════ -->
<section>
  <div class="container">
    <div class="section-head">
      <h2>Legislator Search</h2>
      <div class="section-sub">__N_LEG__ legislator-terms sorted by ideological score. Rank 1 is the most liberal legislator of the term.</div>
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
            <th data-col="rank">순위 (1=진보) <span class="sort-arrow">&#9650;</span></th>
          </tr>
        </thead>
        <tbody id="table-body"></tbody>
      </table>
    </div>
    <div class="table-footer">
      <span id="table-count">__N_LEG__</span> results shown
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
__METHOD_HTML__
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
  // score is -1 to 1. Match scatter map: negative = liberal (blue), positive = conservative (red).
  const absScore = Math.abs(score);
  const width = Math.round(absScore * 60);
  const color = score < 0 ? 'var(--blue)' : 'var(--red)';
  return '<span class="score-bar" style="width:' + width + 'px;background:' + color + '"></span>';
}

function renderTable(data) {
  let html = '';
  const limit = data.length;
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

# ── Page text (every number computed above) ──────────────────────────
def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def amount(x: float) -> str:
    """Absolute percent change, whole percent unless it rounds to zero."""
    return f"{abs(x):.0f}%" if round(abs(x)) else f"{abs(x):.1f}%"


def stem(x: float) -> str:
    return "증가" if x > 0 else "감소"


# The fixed axis ranges must still hold every point
if df["aligned"].abs().max() > 1.15:
    raise SystemExit("ERROR: an ideal point lies outside the scatter/violin axis range [-1.15, 1.15]")
if polar_df["liberal_mean"].min() < -0.65 or polar_df["conservative_mean"].max() > 0.75:
    raise SystemExit("ERROR: a bloc mean lies outside the polarization axis range [-0.65, 0.75]")

n_leg = len(df)
term_range_ko = f"{TERMS[0]}대 - {TERMS[-1]}대"
term_range_en = f"{ordinal(TERMS[0])}-{ordinal(TERMS[-1])}"
vintage_ko = f"추정 계열 {VINTAGE}, " if VINTAGE else ""
header_desc = (f"이념점수 추정치, {term_range_ko} 국회 ({FIRST_VOTE[:4]} - {LAST_VOTE[:4]}) &middot; "
               f"{vintage_ko}{ymd(LAST_VOTE)}까지의 본회의 표결")
meta_desc = (f"Bridging-aligned ideal point estimates for {n_leg:,} legislator-terms across the "
             f"{term_range_en} Korean National Assemblies ({FIRST_VOTE[:4]}-{LAST_VOTE[:4]}), "
             f"with polarization trends and party-bloc distributions.")
n_votes_short = f"{N_VOTE_RECORDS / 1e6:.1f}M"

bloc_note = "<strong>정당 계열 구성</strong> (선거 당시 정당, 이념점수 파일의 party_bloc) &middot; " + \
    " &middot; ".join(f"{BLOC_LABELS.get(b, b)} = {', '.join(bloc_parties[b])}" for b in blocs_in_data) + \
    "<br>양극화 거리 = 국민의힘 계열 평균 - 더불어민주당 계열 평균"

# Methodology
bparts = []
for i, r in enumerate(BRIDGING.sort_values("term").itertuples() if len(BRIDGING) else []):
    ref = f"{r.reference_term}대" if i == 0 else f"정렬된 {r.reference_term}대"
    who = "bridging 의원 " if i == 0 else ""
    bparts.append(f"{ref}를 기준으로 {r.term}대를 정렬할 때는 {who}{r.n_bridging}명을")
bridging_txt = (", ".join(bparts) + " 쓴다.") if bparts else ""
if SETTINGS.get("min_minority") is not None and SETTINGS.get("min_votes") is not None:
    filter_txt = (f"소수파 비율 {SETTINGS['min_minority'] * 100:g}% 미만인 표결은 사실상 만장일치로 보고 제외하고, "
                  f"남은 표결에 {SETTINGS['min_votes']}회 미만 참여한 의원도 제외한다.")
else:
    filter_txt = "사실상 만장일치인 표결과, 남은 표결에 참여한 횟수가 너무 적은 의원은 제외한다."
if df["aligned"].abs().max() > 1.0 + 1e-9:
    raise SystemExit("ERROR: the text says the scale runs from -1 to +1, revise it")

if "wnom" in growth and "dw" in growth:
    w, b, d = growth["wnom"], growth["bridged"], growth["dw"]
    if not w > max(b, d):
        raise SystemExit("ERROR: the per-assembly series no longer shows the largest growth, revise the text")
    compare_txt = (
        f"{TERMS[0]}대와 {TERMS[-1]}대 사이 양대 정당 계열 간 거리는 원점수로는 약 {amount(w)} {stem(w)}하지만, "
        f"이 사이트가 쓰는 bridging 정렬로는 약 {amount(b)} {stem(b)}하고, "
        f"통합 DW-NOMINATE로는 약 {amount(d)} {stem(d)}한다. 저장소는 세 계열을 모두 제공한다.")
else:
    compare_txt = "저장소는 대수별 원점수, bridging 정렬, 통합 DW-NOMINATE의 세 계열을 제공한다."

missing_ko = missing_en = ""
if no_votes is not None and len(no_votes):
    missing_ko = (f" {last_term}대 재직 의원 {n_members_last}명 중 {len(no_votes)}명은 의원별 표결 API에 "
                  f"기록이 없어 {last_term}대 이념점수가 없다.")
    missing_en = (f" {len(no_votes)} of the {n_members_last} members of the {ordinal(last_term)} Assembly "
                  f"are missing from the member-level vote feed and have no score for that Assembly.")

method_html = f"""      <h3>추정 방법</h3>
      <p>
        이념점수는 본회의 기명표결에 <strong>W-NOMINATE</strong> 스케일링을 적용해 추정한다.
        각 대수를 독립적으로 추정한 뒤, 두 대수 모두에 재직한 <strong>bridging 의원</strong>을
        이용해 이후 대수를 이전 대수의 단위로 사상(affine map)한다. {bridging_txt}
      </p>
      <p>
        {filter_txt} 부호는 <strong>양수 = 보수, 음수 = 진보</strong>로 통일했다.
        척도는 대략 -1에서 +1 사이다. 정당은 <strong>선거 당시 정당</strong>이며, 정당 계열은 이념점수 파일의
        <code>party_bloc</code> 분류를 그대로 쓴다.
      </p>
      <p>
        이 페이지의 계열은 <strong>{VINTAGE or "vintage 표기 없음"}</strong>로, {ymd(FIRST_VOTE)}부터
        {ymd(LAST_VOTE)}까지의 본회의 표결을 쓴다.{missing_ko}
      </p>

      <p>
        <strong>대수 간 비교 시 주의.</strong> 대수별로 따로 추정한 원점수를 그대로
        비교하면 각 대수가 재정규화되기 때문에 양극화 증가폭이 과대평가된다. {compare_txt}
      </p>

      <h3>Data Sources</h3>
      <p>
        Roll call voting data was collected from the
        <a href="https://open.assembly.go.kr" target="_blank" rel="noopener">열린국회정보 Open API</a>,
        covering plenary votes in the {term_range_en} National Assemblies from {ymd(FIRST_VOTE)} to
        {ymd(LAST_VOTE)}. The estimates use {N_VOTE_RECORDS:,} individual vote records and cover
        {n_leg:,} legislator-terms.{missing_en}
      </p>"""

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
for token, value in {
    "__META_DESC__": meta_desc,
    "__TERM_RANGE_EN__": term_range_en,
    "__HEADER_DESC__": header_desc,
    "__N_LEG__": f"{n_leg:,}",
    "__N_TERMS__": str(len(TERMS)),
    "__N_VOTES__": n_votes_short,
    "__BLOC_NOTE__": bloc_note,
    "__METHOD_HTML__": method_html,
}.items():
    html = html.replace(token, value)
if "__" in "".join(re.findall(r"__[A-Z_]+__", html)):
    raise SystemExit(f"ERROR: unfilled tokens {sorted(set(re.findall(r'__[A-Z_]+__', html)))}")

out_path = OUT_DIR / "voteview.html"
out_path.write_text(html, encoding="utf-8")

# ── Summary ───────────────────────────────────────────────────────────
print(f"Generated: {out_path}")
print(f"  File size: {out_path.stat().st_size / 1024:.0f} KB")
print(f"  Legislator-terms: {len(df)}")
print(f"  Parties: {df['party'].nunique()}")
print(f"  Assemblies: {sorted(df['term'].unique())}")
print(f"  Vintage: {VINTAGE}, votes {ymd(FIRST_VOTE)} to {ymd(LAST_VOTE)}, {N_VOTE_RECORDS:,} records")
print(f"  Gap growth, first to last term: " + ", ".join(f"{k} {v:+.2f}%" for k, v in growth.items()))
print(f"\nPolarization:")
for _, row in polar_df.iterrows():
    print(f"  {int(row['term'])}대: gap = {row['gap']:.3f}"
          f"  (liberal mean {row['liberal_mean']:.3f},"
          f" conservative mean {row['conservative_mean']:.3f})")
