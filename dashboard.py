"""
程式 C：Streamlit 即時公衛儀表板
===================================
即時顯示傳染病案例統計，讀取由 MedMorph 引擎寫入的 SQLite 資料庫。

功能：
  - 三種疾病計數卡片（COVID-19 / 登革熱 / 流感）
  - 台灣各縣市案例分布熱力圖（Plotly）
  - 時間趨勢折線圖（每日新增案例數）
  - 每 15 秒自動刷新

使用方式：
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

# ── 設定 ──────────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "data/cases.db")
REFRESH_INTERVAL_MS = 15_000   # 15 秒自動刷新

# ── 台灣縣市中心座標 ───────────────────────────────────────────────────────────
COUNTY_COORDS = {
    "台北市":  (25.0330, 121.5654),
    "新北市":  (25.0120, 121.4653),
    "桃園市":  (24.9936, 121.3009),
    "台中市":  (24.1477, 120.6736),
    "台南市":  (23.0000, 120.2133),
    "高雄市":  (22.6273, 120.3014),
    "新竹縣":  (24.8387, 121.0177),
    "新竹市":  (24.8138, 120.9675),
    "苗栗縣":  (24.5202, 120.8214),
    "彰化縣":  (24.0518, 120.5161),
    "南投縣":  (23.9609, 120.9718),
    "雲林縣":  (23.7092, 120.4313),
    "嘉義縣":  (23.4518, 120.2554),
    "嘉義市":  (23.4800, 120.4491),
    "屏東縣":  (22.5519, 120.5487),
    "宜蘭縣":  (24.6941, 121.7380),
    "花蓮縣":  (23.9871, 121.6015),
    "台東縣":  (22.7972, 121.0714),
    "澎湖縣":  (23.5711, 119.5793),
    "基隆市":  (25.1276, 121.7392),
    "連江縣":  (26.1600, 119.9500),
    "金門縣":  (24.4493, 118.3765),
}

DISEASE_COLORS = {
    "COVID-19":  "#E74C3C",
    "Dengue":    "#F39C12",
    "Influenza": "#3498DB",
}

DISEASE_EMOJI = {
    "COVID-19":  "🦠",
    "Dengue":    "🦟",
    "Influenza": "🤧",
}

DISEASE_ZH = {
    "COVID-19":  "COVID-19",
    "Dengue":    "登革熱",
    "Influenza": "流感",
}


# ── 資料載入 ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=14)
def load_cases(db_path: str = DB_PATH) -> pd.DataFrame:
    """從 SQLite 載入所有案例，回傳 DataFrame"""
    if not os.path.exists(db_path):
        return pd.DataFrame(
            columns=["id", "patient_name", "disease", "county",
                     "status", "report_date", "symptoms", "gender"]
        )
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query("SELECT * FROM cases ORDER BY report_date DESC", conn)

    if df.empty:
        return df

    # 解析時間
    df["report_date"] = pd.to_datetime(df["report_date"], utc=True, errors="coerce")
    df["date"] = df["report_date"].dt.date

    # 解析症狀 JSON
    def parse_symptoms(s):
        try:
            return json.loads(s) if s else []
        except Exception:
            return []
    df["symptoms_list"] = df["symptoms"].apply(parse_symptoms)

    return df


# ── 圖表建立函式 ──────────────────────────────────────────────────────────────

def make_map_figure(df: pd.DataFrame, disease_filter: str = "全部") -> go.Figure:
    """產生台灣各縣市案例散布地圖"""
    if df.empty:
        fig = go.Figure()
        fig.update_layout(
            mapbox_style="open-street-map",
            mapbox_center={"lat": 23.8, "lon": 121.0},
            mapbox_zoom=6,
            margin={"l": 0, "r": 0, "t": 0, "b": 0},
            height=460,
        )
        return fig

    # 篩選疾病
    plot_df = df if disease_filter == "全部" else df[df["disease"] == disease_filter]

    # 依縣市+疾病彙總
    grouped = (
        plot_df.groupby(["county", "disease"])
        .size()
        .reset_index(name="count")
    )

    # 加入座標
    grouped["lat"] = grouped["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[0])
    grouped["lon"] = grouped["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[1])
    grouped["disease_zh"] = grouped["disease"].map(DISEASE_ZH)
    grouped["color"] = grouped["disease"].map(DISEASE_COLORS)

    # 計算縣市總案例（用於泡泡大小）
    county_total = grouped.groupby("county")["count"].sum().reset_index(name="total")
    grouped = grouped.merge(county_total, on="county")

    fig = px.scatter_mapbox(
        grouped,
        lat="lat",
        lon="lon",
        size="total",
        color="disease",
        color_discrete_map=DISEASE_COLORS,
        hover_name="county",
        hover_data={"disease_zh": True, "count": True, "lat": False, "lon": False, "total": False},
        labels={"disease": "疾病", "count": "案例數", "disease_zh": "疾病名稱"},
        size_max=55,
        zoom=6,
        center={"lat": 23.8, "lon": 121.0},
        mapbox_style="open-street-map",
        height=460,
    )
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        legend=dict(
            title="疾病類型",
            orientation="h",
            yanchor="bottom",
            y=0.01,
            xanchor="right",
            x=0.99,
            bgcolor="rgba(255,255,255,0.8)",
        ),
    )
    return fig


def make_trend_figure(df: pd.DataFrame, days: int = 14) -> go.Figure:
    """產生每日新增案例時間趨勢折線圖"""
    if df.empty or "date" not in df.columns:
        fig = go.Figure()
        fig.update_layout(
            title="每日新增案例趨勢（無資料）",
            height=320,
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    # 最近 N 天
    cutoff = (datetime.now() - timedelta(days=days)).date()
    recent = df[df["date"] >= cutoff]

    # 建立完整日期序列（補 0）
    all_dates = pd.date_range(
        start=cutoff,
        end=datetime.now().date(),
        freq="D",
    ).date

    fig = go.Figure()
    for disease in ["COVID-19", "Dengue", "Influenza"]:
        sub = recent[recent["disease"] == disease]
        daily = sub.groupby("date").size().reset_index(name="count")
        daily_full = (
            pd.DataFrame({"date": all_dates})
            .merge(daily, on="date", how="left")
            .fillna(0)
        )
        fig.add_trace(
            go.Scatter(
                x=daily_full["date"],
                y=daily_full["count"],
                mode="lines+markers",
                name=f"{DISEASE_EMOJI[disease]} {DISEASE_ZH[disease]}",
                line=dict(color=DISEASE_COLORS[disease], width=2.5),
                marker=dict(size=6),
                hovertemplate="%{x}<br>案例數：%{y}<extra></extra>",
            )
        )

    fig.update_layout(
        title=dict(text=f"📈 近 {days} 天每日新增案例趨勢", font_size=15),
        xaxis_title="日期",
        yaxis_title="新增案例數",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=320,
        hovermode="x unified",
        margin=dict(l=50, r=20, t=50, b=40),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)", rangemode="tozero")
    return fig


def make_county_bar(df: pd.DataFrame) -> go.Figure:
    """產生各縣市案例數橫條圖"""
    if df.empty:
        return go.Figure()

    county_counts = (
        df.groupby(["county", "disease"])
        .size()
        .reset_index(name="count")
    )
    county_total = county_counts.groupby("county")["count"].sum().sort_values(ascending=True)
    ordered = county_total.index.tolist()

    fig = go.Figure()
    for disease in ["COVID-19", "Dengue", "Influenza"]:
        sub = county_counts[county_counts["disease"] == disease].set_index("county")
        fig.add_trace(
            go.Bar(
                y=ordered,
                x=[sub.loc[c, "count"] if c in sub.index else 0 for c in ordered],
                name=f"{DISEASE_EMOJI[disease]} {DISEASE_ZH[disease]}",
                orientation="h",
                marker_color=DISEASE_COLORS[disease],
                hovertemplate="%{y}：%{x} 例<extra></extra>",
            )
        )

    fig.update_layout(
        barmode="stack",
        title=dict(text="🗺️ 各縣市案例分布", font_size=15),
        xaxis_title="案例數",
        height=max(350, len(ordered) * 22 + 80),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=80, r=20, t=60, b=40),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.08)")
    return fig


# ── 主頁面 ─────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="傳染病即時公衛儀表板",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── 自動刷新計數器（每 15 秒）──────────────────────────────────────────────
    count = st_autorefresh(interval=REFRESH_INTERVAL_MS, key="auto_refresh")

    # ── CSS 美化 ────────────────────────────────────────────────────────────────
    st.markdown(
        """
        <style>
        .metric-card {
            background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
            border-radius: 12px;
            padding: 20px 24px;
            color: white;
            text-align: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .metric-value { font-size: 3rem; font-weight: 700; line-height: 1; }
        .metric-label { font-size: 1rem; opacity: 0.85; margin-top: 4px; }
        .metric-sub   { font-size: 0.8rem; opacity: 0.65; margin-top: 6px; }
        .section-divider { border-top: 1px solid #ddd; margin: 24px 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── 標題列 ──────────────────────────────────────────────────────────────────
    col_title, col_refresh = st.columns([4, 1])
    with col_title:
        st.markdown("## 🏥 傳染病即時公衛儀表板")
        st.caption("資料來源：MedMorph 自動通報引擎 · FHIR R4 · eICR 標準")
    with col_refresh:
        st.markdown(f"<br>⏱ 自動刷新中（{REFRESH_INTERVAL_MS // 1000}s）", unsafe_allow_html=True)
        now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        st.caption(f"更新時間：{now_str}")

    # ── 側邊欄 ──────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.image(
            "https://www.cdc.gov.tw/File/Get/7kJSUCWKNpxGOVf0UF52YQ",
            width=120,
        ) if False else st.markdown("### ⚙️ 篩選條件")

        st.markdown("### ⚙️ 篩選條件")

        db_path_input = st.text_input("資料庫路徑", value=DB_PATH)

        disease_options = ["全部", "COVID-19", "Dengue", "Influenza"]
        disease_filter = st.selectbox(
            "疾病類型",
            disease_options,
            format_func=lambda x: f"{DISEASE_EMOJI.get(x, '📊')} {DISEASE_ZH.get(x, x)}",
        )

        status_options = ["全部", "suspected", "confirmed"]
        status_filter = st.selectbox(
            "案例狀態",
            status_options,
            format_func=lambda x: {"全部": "全部", "suspected": "🟡 疑似", "confirmed": "🔴 確診"}.get(x, x),
        )

        days_range = st.slider("趨勢圖天數範圍", min_value=7, max_value=60, value=14, step=7)

        st.markdown("---")
        st.markdown("**資料說明**")
        st.markdown(
            "本儀表板讀取 MedMorph 引擎\n"
            "產生的 SQLite 案例資料庫，\n"
            "每 15 秒自動刷新。"
        )
        st.markdown("**三組疾病**")
        for d, zh in DISEASE_ZH.items():
            st.markdown(f"- {DISEASE_EMOJI[d]} {zh}")

    # ── 資料載入 ────────────────────────────────────────────────────────────────
    df_all = load_cases(db_path_input)

    # 套用篩選
    df = df_all.copy()
    if disease_filter != "全部":
        df = df[df["disease"] == disease_filter]
    if status_filter != "全部":
        df = df[df["status"] == status_filter]

    # ── KPI 計數卡片 ──────────────────────────────────────────────────────────
    st.markdown("### 📊 即時案例統計")

    def get_count(disease: str) -> int:
        if df_all.empty:
            return 0
        return len(df_all[df_all["disease"] == disease])

    def get_today_count(disease: str) -> int:
        if df_all.empty or "date" not in df_all.columns:
            return 0
        today = datetime.now().date()
        return len(df_all[(df_all["disease"] == disease) & (df_all["date"] == today)])

    total_all = len(df_all)
    today_all = get_today_count("COVID-19") + get_today_count("Dengue") + get_today_count("Influenza")

    kpi_cols = st.columns(4)

    with kpi_cols[0]:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-value">{total_all}</div>
                <div class="metric-label">📋 累計總案例</div>
                <div class="metric-sub">今日 +{today_all}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    disease_meta = [
        ("COVID-19", "#E74C3C", "linear-gradient(135deg,#b71c1c,#e53935)"),
        ("Dengue",   "#F39C12", "linear-gradient(135deg,#e65100,#ff9800)"),
        ("Influenza","#3498DB", "linear-gradient(135deg,#1565c0,#1e88e5)"),
    ]
    for i, (disease, _, gradient) in enumerate(disease_meta):
        with kpi_cols[i + 1]:
            count_val = get_count(disease)
            today_val = get_today_count(disease)
            zh = DISEASE_ZH[disease]
            emoji = DISEASE_EMOJI[disease]
            st.markdown(
                f"""<div class="metric-card" style="background:{gradient}">
                    <div class="metric-value">{count_val}</div>
                    <div class="metric-label">{emoji} {zh}</div>
                    <div class="metric-sub">今日 +{today_val}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── 地圖 + 縣市橫條圖 ──────────────────────────────────────────────────────
    st.markdown("### 🗺️ 地理分布")
    map_col, bar_col = st.columns([3, 2])

    with map_col:
        st.markdown(f"**台灣各縣市傳染病熱點地圖**（篩選：{DISEASE_ZH.get(disease_filter, '全部')}）")
        fig_map = make_map_figure(df, disease_filter=disease_filter)
        st.plotly_chart(fig_map, use_container_width=True, config={"scrollZoom": True})

    with bar_col:
        st.markdown("**各縣市案例堆疊分布**")
        fig_bar = make_county_bar(df)
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── 時間趨勢折線圖 ──────────────────────────────────────────────────────────
    st.markdown("### 📈 時間趨勢")
    fig_trend = make_trend_figure(df_all, days=days_range)
    st.plotly_chart(fig_trend, use_container_width=True)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── 最近案例明細表 ─────────────────────────────────────────────────────────
    st.markdown("### 📋 最近案例明細")
    if df.empty:
        st.info("⚠️ 目前沒有符合條件的案例。請先執行 `python seed_data.py` 或啟動 MedMorph 引擎。")
    else:
        display_df = df[["patient_name", "disease", "county", "status", "report_date", "gender"]].copy()
        display_df.columns = ["姓名", "疾病", "縣市", "狀態", "通報時間", "性別"]
        display_df["疾病"] = display_df["疾病"].map(
            lambda d: f"{DISEASE_EMOJI.get(d, '')} {DISEASE_ZH.get(d, d)}"
        )
        display_df["狀態"] = display_df["狀態"].map(
            {"suspected": "🟡 疑似", "confirmed": "🔴 確診"}.get
        )
        display_df["性別"] = display_df["性別"].map(
            {"male": "男", "female": "女", "unknown": "未知"}.get
        )
        if "通報時間" in display_df.columns:
            display_df["通報時間"] = pd.to_datetime(
                display_df["通報時間"], utc=True, errors="coerce"
            ).dt.strftime("%Y/%m/%d %H:%M")

        st.dataframe(
            display_df.head(50),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"顯示最近 50 筆（共 {len(df)} 筆）")

    # ── 頁尾 ────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        "🏥 NTU 智慧醫療期末專題 · 第五組 · FHIR R4 · MedMorph Reference Architecture · HL7 eICR"
    )


if __name__ == "__main__":
    main()
