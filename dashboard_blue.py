"""
Real-time Public Health Dashboard (Morandi Deep Blue Theme)
===========================================================
Displays infectious disease case statistics from a SQLite database.

Features:
  - Page 1: Case overview — COVID-19 / Dengue / Influenza KPI cards + donut charts + county bar chart
  - Page 2: Hotspot map — Taiwan county bubble map + county ranking
  - Page 3: Trend analysis — daily trend lines + 7-day moving average + weekly distribution
  - Page 4: Case details — recent filterable case table
  - Auto-refreshes every 15 seconds
  - Tab-based page navigation
  - Fixed light mode with Morandi deep blue styling

Usage:
  streamlit run dashboard.py
  streamlit run dashboard.py -- --db data/cases.db
"""

import os
import sqlite3
import json
import argparse
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ── Settings ──────────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "data/cases.db")
REFRESH_INTERVAL_MS = 15_000

# ── Taiwan county center coordinates ───────────────────────────────────────────────────────────
COUNTY_COORDS = {
    "台北市": (25.0330, 121.5654), "新北市": (25.0120, 121.4653),
    "桃園市": (24.9936, 121.3009), "台中市": (24.1477, 120.6736),
    "台南市": (23.0000, 120.2133), "高雄市": (22.6273, 120.3014),
    "新竹縣": (24.8387, 121.0177), "新竹市": (24.8138, 120.9675),
    "苗栗縣": (24.5202, 120.8214), "彰化縣": (24.0518, 120.5161),
    "南投縣": (23.9609, 120.9718), "雲林縣": (23.7092, 120.4313),
    "嘉義縣": (23.4518, 120.2554), "嘉義市": (23.4800, 120.4491),
    "屏東縣": (22.5519, 120.5487), "宜蘭縣": (24.6941, 121.7380),
    "花蓮縣": (23.9871, 121.6015), "台東縣": (22.7972, 121.0714),
    "澎湖縣": (23.5711, 119.5793), "基隆市": (25.1276, 121.7392),
    "連江縣": (26.1600, 119.9500), "金門縣": (24.4493, 118.3765),
}

COUNTY_NAME_EN = {
    "台北市": "Taipei City", "新北市": "New Taipei City",
    "桃園市": "Taoyuan City", "台中市": "Taichung City",
    "台南市": "Tainan City", "高雄市": "Kaohsiung City",
    "新竹縣": "Hsinchu County", "新竹市": "Hsinchu City",
    "苗栗縣": "Miaoli County", "彰化縣": "Changhua County",
    "南投縣": "Nantou County", "雲林縣": "Yunlin County",
    "嘉義縣": "Chiayi County", "嘉義市": "Chiayi City",
    "屏東縣": "Pingtung County", "宜蘭縣": "Yilan County",
    "花蓮縣": "Hualien County", "台東縣": "Taitung County",
    "澎湖縣": "Penghu County", "基隆市": "Keelung City",
    "連江縣": "Lienchiang County", "金門縣": "Kinmen County",
}

# ── Design language: Morandi deep blue theme ──────────────────────────────────
THEME_PALETTES = {
    "Light": {
        "bg_page":    "#D4D4D5",
        "bg_card":    "#F7F8F8",
        "bg_nav":     "#2F4154",
        "bg_topbar":  "#253748",
        "blue_500":   "#405B73",
        "blue_300":   "#6F8798",
        "blue_100":   "#B9C7D0",
        "blue_50":    "#D9E0E4",
        "text_pri":   "#24313C",
        "text_sec":   "#4E6475",
        "text_muted": "#7E8D96",
        "border":     "rgba(64,91,115,0.18)",
        "covid":      "#9C6B68",
        "dengue":     "#B29A70",
        "flu":        "#6F8798",
        "ok":         "#6A6A70",
        "warn":       "#9797A4",
        "map_style":  "carto-positron",
        "plot_grid":  "rgba(64,91,115,0.12)",
        "legend_bg":  "rgba(247,248,248,0.88)",
    },
    "Dark": {
        "bg_page":    "#182330",
        "bg_card":    "#223140",
        "bg_nav":     "#15202B",
        "bg_topbar":  "#111C27",
        "blue_500":   "#8FA6B8",
        "blue_300":   "#A8BBC8",
        "blue_100":   "#D3DCE2",
        "blue_50":    "#314354",
        "text_pri":   "#E7ECEF",
        "text_sec":   "#C2CED6",
        "text_muted": "#8EA0AC",
        "border":     "rgba(184,202,214,0.16)",
        "covid":      "#C28A86",
        "dengue":     "#D1B87F",
        "flu":        "#9FB4C4",
        "ok":         "#8F97A8",
        "warn":       "#3E659C",
        "map_style":  "carto-darkmatter",
        "plot_grid":  "rgba(184,202,214,0.12)",
        "legend_bg":  "rgba(34,49,64,0.88)",
    },
}

PALETTE = THEME_PALETTES["Light"]
DISEASE_COLORS = {
    "COVID-19":  PALETTE["covid"],
    "Dengue":    PALETTE["dengue"],
    "Influenza": PALETTE["flu"],
}



DISEASE_LABELS = {"COVID-19": "COVID-19", "Dengue": "Dengue", "Influenza": "Influenza"}

# ── CSS ────────────────────────────────────────────────────────────────────────
def build_global_css(palette: dict) -> str:
    PALETTE = palette
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {{
    font-family: 'DM Sans', sans-serif !important;
    background-color: {PALETTE['bg_page']} !important;
}}
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
[data-testid="stVerticalBlock"],
section.main {{
    background-color: {PALETTE['bg_page']} !important;
}}
[data-testid="stHeader"] {{
    background: transparent !important;
}}

/* Hide default Streamlit elements */
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding: 0 !important; max-width: 100% !important; }}
[data-testid="stSidebar"] {{
    background: {PALETTE['bg_card']} !important;
    border-right: 0.5px solid {PALETTE['border']} !important;
}}
[data-testid="stSidebar"] * {{ color: {PALETTE['text_pri']} !important; }}

/* ── Top bar ── */
.top-bar {{
    background: {PALETTE['bg_topbar']};
    padding: 14px 32px;
    min-height: 62px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 0;
}}
.brand {{
    display: flex; align-items: center; gap: 10px;
}}
.brand-dot {{
    width: 8px; height: 8px; border-radius: 50%;
    background: {PALETTE['blue_300']};
    box-shadow: 0 0 6px {PALETTE['blue_300']};
}}
.brand-name {{
    font-size: 15px; font-weight: 500;
    color: {PALETTE['blue_100']}; letter-spacing: 0.02em;
}}
.brand-sub {{
    font-size: 11px; color: rgba(255,255,255,0.35);
    margin-left: 4px;
}}
.live-badge {{
    display: inline-flex; align-items: center; gap: 5px;
    background: rgba(255,255,255,0.07);
    border: 0.5px solid rgba(255,255,255,0.15);
    border-radius: 20px; padding: 3px 10px;
    font-size: 10.5px; font-weight: 500;
    color: rgba(255,255,255,0.6); letter-spacing: 0.06em;
}}
.live-dot {{
    width: 6px; height: 6px; border-radius: 50%;
    background: #6EC97F;
    animation: blink 1.8s infinite;
}}
@keyframes blink {{
    0%, 100% {{ opacity: 1; }}
    50%       {{ opacity: 0.3; }}
}}
.ts-text {{
    font-size: 11px; color: rgba(255,255,255,0.35);
    font-family: 'DM Mono', monospace;
}}
/* ── Nav bar ── */
.nav-bar {{
    background: {PALETTE['bg_nav']};
    display: flex; padding: 0 32px; gap: 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    margin-bottom: 0;
}}
.nav-btn {{
    background: none; border: none; cursor: pointer;
    padding: 0 20px; height: 46px;
    display: flex; align-items: center; gap: 7px;
    font-size: 12.5px; font-weight: 400; font-family: 'DM Sans', sans-serif;
    color: rgba(255,255,255,0.40);
    letter-spacing: 0.03em;
    border-bottom: 2px solid transparent;
    transition: color .15s, border-color .15s;
    position: relative; top: 1px;
    text-decoration: none;
}}
.nav-btn:hover {{ color: rgba(255,255,255,0.7); }}
.nav-btn.active {{
    color: {PALETTE['blue_100']};
    border-bottom-color: {PALETTE['blue_300']};
    font-weight: 500;
}}

/* ── Content wrapper ── */
.content {{ padding: 28px 32px; }}

/* ── KPI cards ── */
.kpi-grid {{
    display: grid; grid-template-columns: repeat(4,1fr); gap: 14px;
    margin-bottom: 22px;
}}
.kpi-card {{
    background: {PALETTE['bg_card']};
    border: 0.5px solid {PALETTE['border']};
    border-radius: 12px; padding: 20px 22px;
    position: relative; overflow: hidden;
}}
.kpi-card::before {{
    content: ''; position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
}}
.kpi-total::before {{ background: linear-gradient(90deg,{PALETTE['blue_300']},{PALETTE['blue_100']}); }}
.kpi-covid::before  {{ background: {PALETTE['covid']}; }}
.kpi-dengue::before {{ background: {PALETTE['dengue']}; }}
.kpi-flu::before    {{ background: {PALETTE['flu']}; }}

.kpi-label {{
    font-size: 10.5px; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.08em;
    color: {PALETTE['text_muted']}; margin-bottom: 8px;
}}
.kpi-value {{
    font-family: 'DM Mono', monospace;
    font-size: 38px; font-weight: 300;
    color: {PALETTE['text_pri']}; line-height: 1; margin-bottom: 8px;
}}
.kpi-today {{
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 11.5px; color: {PALETTE['blue_500']};
    background: {PALETTE['blue_50']};
    padding: 3px 9px; border-radius: 20px;
}}

/* ── Cards / panels ── */
.panel {{
    background: {PALETTE['bg_card']};
    border: 0.5px solid {PALETTE['border']};
    border-radius: 12px; padding: 20px 22px;
    margin-bottom: 16px;
}}
.panel-title {{
    font-size: 18px; font-weight: 500;
    color: {PALETTE['text_pri']}; margin-bottom: 14px;
}}
.panel-sub {{
    font-size: 11.5px; color: {PALETTE['text_muted']};
    margin-top: 2px; font-weight: 400;
}}

/* ── Section divider ── */
.divider {{ border-top: 0.5px solid {PALETTE['border']}; margin: 20px 0; }}

/* ── Page title ── */
.page-title {{
    font-size: 17px; font-weight: 500;
    color: {PALETTE['text_pri']}; margin-bottom: 3px;
}}
.page-sub {{
    font-size: 12.5px; color: {PALETTE['text_muted']};
    margin-bottom: 20px;
}}

/* Disease filter radio text color */
div[data-testid="stRadio"] [role="radiogroup"] label p {{
    color: #405B73 !important;
    font-weight: 500 !important;
}}

/* Form labels + row count text */
div[data-testid="stSelectbox"] label p,
div[data-testid="stSlider"] label p,
.row-count-text {{
    color: {PALETTE['text_pri']} !important;
    font-weight: 600 !important;
}}

/* Slider min/max/value text */
div[data-testid="stSlider"] p,
div[data-testid="stSlider"] span {{
    color: {PALETTE['text_pri']} !important;
}}

.row-count-text {{
    font-size: 13px;
    margin: 6px 0 12px 0;
}}

/* ── Status badge ── */
.badge-confirmed {{
    display: inline-block; padding: 2px 8px; border-radius: 20px;
    font-size: 11px; font-weight: 500;
    background: rgba(224,75,106,0.08); color: {PALETTE['covid']};
}}
.badge-suspected {{
    display: inline-block; padding: 2px 8px; border-radius: 20px;
    font-size: 11px; font-weight: 500;
    background: rgba(232,162,43,0.1); color: #B87A18;
}}
/* ── Plotly overrides ── */
.js-plotly-plot .plotly {{ background: transparent !important; }}

/* ── Streamlit tab override ── */
.stTabs [data-baseweb="tab-list"] {{
    background: {PALETTE['bg_nav']} !important;
    padding: 0 32px !important; gap: 0 !important;
    border-bottom: 1px solid rgba(255,255,255,0.05) !important;
}}
.stTabs [data-baseweb="tab"] {{
    background: none !important;
    color: rgba(255,255,255,0.40) !important;
    font-size: 12.5px !important;
    font-family: 'DM Sans', sans-serif !important;
    padding: 12px 20px !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
}}
.stTabs [aria-selected="true"] {{
    color: {PALETTE['blue_100']} !important;
    border-bottom: 2px solid {PALETTE['blue_300']} !important;
    font-weight: 500 !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{ display: none !important; }}
.stTabs [data-baseweb="tab-border"]   {{ display: none !important; }}
.stTabs [data-baseweb="tab-panel"]    {{ padding: 28px 32px !important; }}
</style>
"""


# ── Data loading ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=14)
def load_cases(db_path: str = DB_PATH) -> pd.DataFrame:
    if not os.path.exists(db_path):
        return pd.DataFrame(
            columns=["id", "patient_name", "disease", "county",
                     "status", "report_date", "symptoms", "gender"]
        )
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT * FROM cases ORDER BY report_date DESC", conn
        )
    if df.empty:
        return df
    df["report_date"] = pd.to_datetime(df["report_date"], utc=True, errors="coerce")
    df["date"] = df["report_date"].dt.date
    return df


# ── Chart builders ──────────────────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans", color=PALETTE["text_pri"]),
    margin=dict(l=50, r=16, t=48, b=40),
    xaxis=dict(showgrid=True, gridcolor=PALETTE["plot_grid"], zeroline=False),
    yaxis=dict(showgrid=True, gridcolor=PALETTE["plot_grid"], zeroline=False, rangemode="tozero"),
)


def fig_donut(df_all: pd.DataFrame) -> go.Figure:
    counts = [len(df_all[df_all["disease"] == d]) for d in ["COVID-19", "Dengue", "Influenza"]]
    labels = ["COVID-19", "Dengue", "Influenza"]
    colors = [PALETTE["covid"], PALETTE["dengue"], PALETTE["flu"]]
    fig = go.Figure(go.Pie(
        labels=labels, values=counts,
        hole=0.62,
        marker=dict(colors=colors, line=dict(color=PALETTE["bg_card"], width=2)),
        textinfo="percent",
        textfont=dict(size=12, family="DM Sans"),
        hovertemplate="%{label}: %{value} cases<extra></extra>",
    ))
    total = sum(counts)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=220,
        showlegend=False,
        annotations=[dict(text=f"<b>{total}</b><br><span style='font-size:11px'>Total</span>",
                          x=0.5, y=0.5, showarrow=False,
                          font=dict(size=20, family="DM Sans, DM Mono"))],
    )
    return fig


def fig_status_donut(df_all: pd.DataFrame) -> go.Figure:
    c = len(df_all[df_all["status"] == "confirmed"])
    s = len(df_all[df_all["status"] == "suspected"])
    fig = go.Figure(go.Pie(
        labels=["Confirmed", "Suspected"], values=[c, s],
        hole=0.62,
        marker=dict(colors=[PALETTE["ok"], PALETTE["warn"]],
                    line=dict(color=PALETTE["bg_card"], width=2)),
        textinfo="percent",
        textfont=dict(size=12, family="DM Sans"),
        hovertemplate="%{label}: %{value} cases<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=220, showlegend=False,
    )
    return fig


def fig_county_bar(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    grp = df.groupby(["county", "disease"]).size().reset_index(name="count")
    total = grp.groupby("county")["count"].sum().sort_values(ascending=True)
    ordered = total.index.tolist()
    fig = go.Figure()
    for d in ["COVID-19", "Dengue", "Influenza"]:
        sub = grp[grp["disease"] == d].set_index("county")
        fig.add_trace(go.Bar(
            y=[COUNTY_NAME_EN.get(c, c) for c in ordered],
            x=[sub.loc[c, "count"] if c in sub.index else 0 for c in ordered],
            name=f"{DISEASE_LABELS[d]}",
            orientation="h",
            marker=dict(color=DISEASE_COLORS[d], line=dict(width=0)),
            hovertemplate="%{y}: %{x} cases<extra></extra>",
        ))
    h = max(380, len(ordered) * 24 + 80)
    fig.update_layout(
        barmode="stack", height=h,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color=PALETTE["text_pri"]),
        margin=dict(l=70, r=16, t=12, b=30),
        showlegend=False,
        xaxis=dict(
            showgrid=True,
            gridcolor=PALETTE["plot_grid"],
            zeroline=False,
            tickfont=dict(size=11, color="#253748")
        ),
        yaxis=dict(
            showgrid=False,
            tickfont=dict(size=11, color="#253748")
        ),
    )
    return fig


def _hex_to_rgba(hex_color: str, alpha: float = 0.78) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def fig_map(df: pd.DataFrame, disease_filter: str = "All") -> go.Figure:
    def _empty():
        fig = go.Figure()
        fig.update_layout(
            mapbox=dict(style=PALETTE["map_style"],
                        center={"lat": 23.8, "lon": 121.0}, zoom=6),
            margin={"l": 0, "r": 0, "t": 0, "b": 0}, height=460,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    plot_df = df if disease_filter == "All" else df[df["disease"] == disease_filter]
    if plot_df.empty:
        return _empty()

    grp = plot_df.groupby(["county", "disease"]).size().reset_index(name="count")
    grp["lat"] = grp["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[0])
    grp["lon"] = grp["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[1])
    county_total = grp.groupby("county")["count"].sum().reset_index(name="total")
    grp = grp.merge(county_total, on="county")

    # sqrt 正規化泡泡大小（上限 40px）
    mx = grp["total"].max() or 1
    grp["size"] = (8 + 32 * (grp["total"] / mx) ** 0.5).round(1)

    fig = go.Figure()
    for disease, color in DISEASE_COLORS.items():
        sub = grp[grp["disease"] == disease]
        if sub.empty:
            continue
        county_en = sub["county"].map(lambda c: COUNTY_NAME_EN.get(c, c))
        fig.add_trace(go.Scattermapbox(
            lat=sub["lat"].tolist(), lon=sub["lon"].tolist(),
            mode="markers",
            marker=dict(size=sub["size"].tolist(), color=color,
                        opacity=0.80, sizemode="diameter"),
            name=f"{DISEASE_LABELS[disease]}",
            text=county_en.tolist(),
            customdata=list(zip(sub["count"].tolist(), sub["total"].tolist())),
            hovertemplate=(
                "<b>%{text}</b><br>"
                f"{DISEASE_LABELS[disease]}: %{{customdata[0]}} cases<br>"
                "County total: %{customdata[1]}<extra></extra>"
            ),
        ))

    fig.update_layout(
        mapbox=dict(style=PALETTE["map_style"],
                    center={"lat": 23.8, "lon": 121.0}, zoom=6.3),
        margin={"l": 0, "r": 0, "t": 0, "b": 0}, height=460,
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(
            title="", orientation="h",
            yanchor="bottom", y=0.01, xanchor="right", x=0.99,
            bgcolor=PALETTE["legend_bg"],
            font=dict(family="DM Sans", size=12),
        ),
    )
    return fig


def fig_trend(df_all: pd.DataFrame, days: int = 30) -> go.Figure:
    if df_all.empty or "date" not in df_all.columns:
        return go.Figure()
    cutoff = (datetime.now() - timedelta(days=days)).date()
    recent = df_all[df_all["date"] >= cutoff]
    all_dates = pd.date_range(
        start=cutoff, end=datetime.now().date(), freq="D"
    ).date

    fig = go.Figure()
    for d in ["COVID-19", "Dengue", "Influenza"]:
        sub = recent[recent["disease"] == d]
        daily = sub.groupby("date").size().reset_index(name="count")
        full = (pd.DataFrame({"date": all_dates})
                .merge(daily, on="date", how="left").fillna(0))
        fig.add_trace(go.Scatter(
            x=full["date"], y=full["count"],
            mode="lines+markers",
            name=DISEASE_LABELS[d],
            line=dict(color=DISEASE_COLORS[d], width=2.2),
            marker=dict(size=5, color=PALETTE["bg_card"],
                        line=dict(color=DISEASE_COLORS[d], width=1.8)),
            fill="tozeroy",
            fillcolor=DISEASE_COLORS[d].replace("#", "") and
                      f"rgba({int(DISEASE_COLORS[d][1:3],16)},"
                      f"{int(DISEASE_COLORS[d][3:5],16)},"
                      f"{int(DISEASE_COLORS[d][5:7],16)},0.06)",
            hovertemplate="%{x}<br>Cases: %{y}<extra></extra>",
        ))
    fig.update_layout(
        height=300, hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color=PALETTE["text_pri"]),
        margin=dict(l=50, r=16, t=12, b=36),
        xaxis=dict(showgrid=True, gridcolor=PALETTE["plot_grid"], zeroline=False,
                   tickfont=dict(size=11)),
        yaxis=dict(showgrid=True, gridcolor=PALETTE["plot_grid"], zeroline=False,
                   rangemode="tozero", tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(family="DM Sans", size=12)),
    )
    return fig


def fig_ma7(df_all: pd.DataFrame, days: int = 30) -> go.Figure:
    """7-Day Moving Average"""
    if df_all.empty or "date" not in df_all.columns:
        return go.Figure()
    cutoff = (datetime.now() - timedelta(days=days)).date()
    recent = df_all[df_all["date"] >= cutoff]
    all_dates = pd.date_range(
        start=cutoff, end=datetime.now().date(), freq="D"
    ).date

    fig = go.Figure()
    for d in ["COVID-19", "Dengue", "Influenza"]:
        sub = recent[recent["disease"] == d]
        daily = sub.groupby("date").size().reset_index(name="count")
        full = (pd.DataFrame({"date": all_dates})
                .merge(daily, on="date", how="left").fillna(0))
        ma = full["count"].rolling(7, min_periods=1).mean().round(1)
        fig.add_trace(go.Scatter(
            x=full["date"], y=ma,
            mode="lines", name=DISEASE_LABELS[d],
            line=dict(color=DISEASE_COLORS[d], width=2.5, dash="solid"),
            hovertemplate="%{x}<br>7-day avg: %{y:.1f}<extra></extra>",
        ))
    fig.update_layout(
        height=220,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color=PALETTE["text_pri"]),
        margin=dict(l=50, r=16, t=12, b=36),
        xaxis=dict(showgrid=True, gridcolor=PALETTE["plot_grid"], zeroline=False,
                   tickfont=dict(size=11)),
        yaxis=dict(showgrid=True, gridcolor=PALETTE["plot_grid"], zeroline=False,
                   rangemode="tozero", tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(family="DM Sans", size=12)),
    )
    return fig


def fig_weekly(df_all: pd.DataFrame, weeks: int = 8) -> go.Figure:
    """Weekly stacked bar chart."""
    if df_all.empty or "date" not in df_all.columns:
        return go.Figure()
    rows = []
    for w in range(weeks):
        end = (datetime.now() - timedelta(weeks=weeks - w - 1)).date()
        start = end - timedelta(days=6)
        sub = df_all[(df_all["date"] >= start) & (df_all["date"] <= end)]
        for d in ["COVID-19", "Dengue", "Influenza"]:
            rows.append({
                "week": f"W{end.month}/{end.day}",
                "disease": d,
                "count": len(sub[sub["disease"] == d]),
            })
    wdf = pd.DataFrame(rows)
    fig = go.Figure()
    for d in ["COVID-19", "Dengue", "Influenza"]:
        sub = wdf[wdf["disease"] == d]
        fig.add_trace(go.Bar(
            x=sub["week"], y=sub["count"],
            name=DISEASE_LABELS[d],
            marker=dict(color=DISEASE_COLORS[d], line=dict(width=0)),
            hovertemplate="%{x}<br>%{y} cases<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack", height=220,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color=PALETTE["text_pri"]),
        margin=dict(l=40, r=16, t=12, b=36),
        xaxis=dict(showgrid=False, tickfont=dict(size=11)),
        yaxis=dict(showgrid=True, gridcolor=PALETTE["plot_grid"], zeroline=False,
                   tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(family="DM Sans", size=12)),
    )
    return fig


# ── Helper HTML ───────────────────────────────────────────────────────────────
def html_kpi(css_class, label, value, today_value):
    return f"""
    <div class="kpi-card {css_class}">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-today">↑ Today +{today_value}</div>
    </div>"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="Public Health Dashboard",
        page_icon="",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st_autorefresh(interval=REFRESH_INTERVAL_MS, key="auto_refresh")

    theme_mode = "Light"

    global PALETTE, DISEASE_COLORS
    PALETTE = THEME_PALETTES["Light"]
    DISEASE_COLORS = {
        "COVID-19":  PALETTE["covid"],
        "Dengue":    PALETTE["dengue"],
        "Influenza": PALETTE["flu"],
    }

    st.markdown(build_global_css(PALETTE), unsafe_allow_html=True)

    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    # ── Top bar ──────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="top-bar">
        <div class="brand">
            <div class="brand-dot"></div>
            <span class="brand-name">Public Health Dashboard</span>
            <span class="brand-sub">Real-time Infectious Disease Surveillance · MedMorph · FHIR R4</span>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
            <span class="live-badge"><span class="live-dot"></span>LIVE</span>
            <span class="ts-text">{now_str}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    db_path = DB_PATH
    df_all = load_cases(db_path)

    def get_count(disease: str) -> int:
        return 0 if df_all.empty else len(df_all[df_all["disease"] == disease])

    def get_today(disease: str) -> int:
        if df_all.empty or "date" not in df_all.columns:
            return 0
        return len(df_all[(df_all["disease"] == disease) &
                           (df_all["date"] == datetime.now().date())])

    total_today = sum(get_today(d) for d in ["COVID-19", "Dengue", "Influenza"])

    # ── Four-page tab navigation ────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "Case Overview",
        "Hotspot Map",
        "Trend Analysis",
        "Case Details",
    ])

    # ═══════════════════════════════════════════════════════════════════════
    # PAGE 1 — Case Counts
    # ═══════════════════════════════════════════════════════════════════════
    with tab1:
        st.markdown('<p class="page-title">Real-time Case Overview</p>'
                    '<p class="page-sub">Cumulative and daily new cases for three infectious diseases</p>',
                    unsafe_allow_html=True)

        # KPI row
        kpi_html = f"""
        <div class="kpi-grid">
            {html_kpi("kpi-total", "Total Cases", len(df_all), total_today)}
            {html_kpi("kpi-covid",  "COVID-19", get_count('COVID-19'), get_today('COVID-19'))}
            {html_kpi("kpi-dengue", "Dengue",   get_count('Dengue'),   get_today('Dengue'))}
            {html_kpi("kpi-flu",    "Influenza",     get_count('Influenza'), get_today('Influenza'))}
        </div>"""
        st.markdown(kpi_html, unsafe_allow_html=True)

        # Row: two donuts
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="panel"><div class="panel-title">Disease Distribution</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(fig_donut(df_all), width="stretch",
                            config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            st.markdown('<div class="panel"><div class="panel-title">Case Status Distribution</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(fig_status_donut(df_all), width="stretch",
                            config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)

        # County bar
        st.markdown('<div class="panel"><div class="panel-title">Stacked Case Distribution by County</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(fig_county_bar(df_all), width="stretch",
                        config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PAGE 2 — Hotspot Map
    # ═══════════════════════════════════════════════════════════════════════
    with tab2:
        st.markdown('<p class="page-title">Geographic Hotspot Distribution</p>'
                    '<p class="page-sub">Cluster overview of suspected and confirmed cases by Taiwan county</p>',
                    unsafe_allow_html=True)

        disease_opts = ["All", "COVID-19", "Dengue", "Influenza"]
        d_filter = st.radio(
            "Disease Filter",
            disease_opts,
            format_func=lambda x: f"{DISEASE_LABELS.get(x, 'All')}",
            horizontal=True,
            label_visibility="collapsed",
        )

        map_col, rank_col = st.columns([3, 1])
        with map_col:
            st.markdown('<div class="panel" style="padding:16px"><div class="panel-title">Taiwan Case Hotspot Map</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(fig_map(df_all, d_filter),
                            width="stretch",
                            config={"scrollZoom": True, "displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)

        with rank_col:
            st.markdown('<div class="panel"><div class="panel-title">County Case Ranking</div>',
                        unsafe_allow_html=True)
            if not df_all.empty:
                rank_df = (df_all.groupby("county").size()
                           .reset_index(name="count")
                           .sort_values("count", ascending=False)
                           .head(12))
                max_v = rank_df["count"].max() or 1
                for i, row in enumerate(rank_df.itertuples(), 1):
                    pct = int(row.count / max_v * 100)
                    st.markdown(
                        f"""<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                            <span style="font-size:11px;color:{PALETTE['text_muted']};min-width:16px;text-align:right">{i}</span>
                            <span style="font-size:12.5px;color:{PALETTE['text_pri']};flex:1">{COUNTY_NAME_EN.get(row.county, row.county)}</span>
                            <div style="flex:2;height:5px;background:{PALETTE['blue_50']};border-radius:3px;overflow:hidden">
                                <div style="height:100%;background:{PALETTE['blue_300']};border-radius:3px;width:{pct}%"></div>
                            </div>
                            <span style="font-size:12px;color:{PALETTE['text_sec']};min-width:24px;text-align:right">{row.count}</span>
                        </div>""",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No data available")
            st.markdown('</div>', unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PAGE 3 — Trend Lines
    # ═══════════════════════════════════════════════════════════════════════
    with tab3:
        st.markdown('<p class="page-title">Temporal Trend Analysis</p>'
                    '<p class="page-sub">Daily reported case trajectories by disease</p>',
                    unsafe_allow_html=True)

        days_sel = st.select_slider(
            "Date Range",
            options=[7, 14, 21, 30, 45, 60],
            value=30,
            label_visibility="collapsed",
        )

        st.markdown('<div class="panel"><div class="panel-title">Daily New Case Trend</div>'
                    '<div class="panel-sub">Daily reported counts for three infectious diseases</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(fig_trend(df_all, days_sel), width="stretch",
                        config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="panel"><div class="panel-title">7-Day Moving Average</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(fig_ma7(df_all, days_sel), width="stretch",
                            config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            st.markdown('<div class="panel"><div class="panel-title">Weekly Case Distribution</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(fig_weekly(df_all), width="stretch",
                            config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PAGE 4 — Case Details
    # ═══════════════════════════════════════════════════════════════════════
    with tab4:
        st.markdown('<p class="page-title">Recent Case Details</p>'
                    '<p class="page-sub">Recently reported case records</p>',
                    unsafe_allow_html=True)

        f_col1, f_col2, f_col3 = st.columns([1, 1, 1])
        with f_col1:
            d_sel = st.selectbox(
                "Disease", ["All"] + list(DISEASE_LABELS.keys()),
                format_func=lambda x: f"{DISEASE_LABELS.get(x, x)}",
                label_visibility="visible",
            )
        with f_col2:
            s_sel = st.selectbox(
                "Status", ["All", "confirmed", "suspected"],
                format_func=lambda x: {"All": "All", "confirmed": "🔴 Confirmed", "suspected": "🟡 Suspected"}.get(x, x),
                label_visibility="visible",
            )
        with f_col3:
            n_rows = st.slider("Rows to Display", 10, 200, 50, 10, label_visibility="visible")

        df_view = df_all.copy()
        if d_sel != "All":
            df_view = df_view[df_view["disease"] == d_sel]
        if s_sel != "All":
            df_view = df_view[df_view["status"] == s_sel]

        st.markdown(
            f"""
            <div class="row-count-text">
                Showing {min(n_rows, len(df_view))} rows / {len(df_view)} total
            </div>
            """,
            unsafe_allow_html=True,
        )

        if df_view.empty:
            st.info("⚠️ No matching cases found. Run `python seed_data.py` or start the MedMorph engine first.")
        else:
            disp = df_view[["patient_name", "disease", "county",
                    "status", "report_date", "gender"]].head(n_rows).copy()

            disp.columns = ["Patient Name", "Disease", "County", "Status", "Report Time", "Gender"]

            disp["Disease"] = disp["Disease"].map(
                lambda d: f"{DISEASE_LABELS.get(d, d)}"
            )

            disp["County"] = disp["County"].map(
                lambda c: COUNTY_NAME_EN.get(c, c)
            )

            disp["Status"] = disp["Status"].map({
                "suspected": "Suspected",
                "confirmed": "Confirmed"
            })

            disp["Gender"] = disp["Gender"].map({
                "male": "Male",
                "female": "Female",
                "unknown": "Unknown"
            })

            disp["Report Time"] = pd.to_datetime(
                disp["Report Time"], utc=True, errors="coerce"
            ).dt.strftime("%Y/%m/%d %H:%M")

            def color_status(val):
                if val == "Suspected":
                    return "color: #D1A84F; font-weight: 600;"   # Morandi yellow
                elif val == "Confirmed":
                    return "color: #B85C5C; font-weight: 600;"   # Morandi red
                return ""

            styled_disp = disp.style.map(color_status, subset=["Status"])

            st.dataframe(
                styled_disp,
                height=500,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Patient Name": st.column_config.TextColumn(width="medium"),
                    "Disease": st.column_config.TextColumn(width="medium"),
                    "County": st.column_config.TextColumn(width="small"),
                    "Status": st.column_config.TextColumn(width="small"),
                    "Gender": st.column_config.TextColumn(width="small"),
                    "Report Time": st.column_config.TextColumn(width="large"),
                },
            )


    # ── Footer ───────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='padding:16px 32px;border-top:0.5px solid {PALETTE['border']};font-size:11px;color:{PALETTE['text_muted']}'>"
        "NTU Next-Generation Electronic Medical Records and Smart Healthcare Ecosystem Final Project · Group 5 · FHIR R4 · MedMorph Reference Architecture · HL7 eICR"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
