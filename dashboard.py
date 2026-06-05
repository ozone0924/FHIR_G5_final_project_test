"""
程式 C：Streamlit 即時公衛儀表板（Tab 版面）
============================================
使用方式：
  uv run streamlit run dashboard.py
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from pdf_report import generate_eicr_pdf

# ── 常數 ──────────────────────────────────────────────────────────────────────
DB_PATH             = os.getenv("DB_PATH", "data/cases.db")
REFRESH_INTERVAL_MS = 15_000

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
DISEASE_COLORS = {"COVID-19": "#E74C3C", "Dengue": "#F39C12", "Influenza": "#3498DB"}
DISEASE_EMOJI  = {"COVID-19": "🦠", "Dengue": "🦟", "Influenza": "🤧"}
DISEASE_ZH     = {"COVID-19": "COVID-19", "Dengue": "登革熱", "Influenza": "流感"}
STATUS_LABEL   = {"suspected": "🟡 疑似", "confirmed": "🔴 確診"}
GENDER_LABEL   = {"male": "男", "female": "女", "unknown": "未知"}


# ── 資料載入 ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=14)
def load_cases(db_path: str) -> pd.DataFrame:
    if not os.path.exists(db_path):
        return pd.DataFrame(columns=[
            "id", "patient_name", "disease", "county", "status",
            "report_date", "symptoms", "gender", "eicr_path",
        ])
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query("SELECT * FROM cases ORDER BY report_date DESC", conn)
    if df.empty:
        return df
    df["report_date"]   = pd.to_datetime(df["report_date"], utc=True, errors="coerce")
    df["date"]          = df["report_date"].dt.date
    df["symptoms_list"] = df["symptoms"].apply(
        lambda s: json.loads(s) if isinstance(s, str) and s else []
    )
    return df


# ── eICR 解析 ─────────────────────────────────────────────────────────────────

def _res(bundle: dict, rtype: str) -> dict:
    for e in bundle.get("entry", []):
        r = e.get("resource", {})
        if r.get("resourceType") == rtype:
            return r
    return {}


def parse_eicr(eicr_path: str) -> dict | None:
    if not eicr_path or not os.path.exists(str(eicr_path)):
        return None
    try:
        with open(eicr_path, encoding="utf-8") as f:
            bundle = json.load(f)
    except Exception:
        return None

    patient     = _res(bundle, "Patient")
    condition   = _res(bundle, "Condition")
    observation = _res(bundle, "Observation")
    encounter   = _res(bundle, "Encounter")
    org         = _res(bundle, "Organization")
    composition = _res(bundle, "Composition")

    cond_c  = (condition.get("code", {}).get("coding") or [{}])[0]
    obs_c   = (observation.get("code", {}).get("coding") or [{}])[0]
    obs_vc  = (observation.get("valueCodeableConcept", {}).get("coding") or [{}])[0]
    org_adr = (org.get("address") or [{}])[0]

    return {
        "bundle_id":   bundle.get("id", ""),
        "bundle_ts":   bundle.get("timestamp", ""),
        "comp_title":  composition.get("title", ""),
        "comp_status": composition.get("status", ""),
        "patient": {
            "name":      (patient.get("name") or [{}])[0].get("text", "未知"),
            "gender":    patient.get("gender", "unknown"),
            "birthdate": patient.get("birthDate", "未知"),
            "county":    (patient.get("address") or [{}])[0].get("district", "未知"),
            "phone":     next((t["value"] for t in patient.get("telecom", []) if t.get("value")), "未提供"),
        },
        "condition": {
            "disease":         cond_c.get("display", "未知"),
            "snomed":          cond_c.get("code", "未知"),
            "clinical_status": (condition.get("clinicalStatus", {}).get("coding") or [{}])[0].get("code", ""),
            "ver_status":      (condition.get("verificationStatus", {}).get("coding") or [{}])[0].get("code", ""),
            "onset":           condition.get("onsetDateTime", ""),
            "recorded":        condition.get("recordedDate", ""),
        },
        "symptoms": observation.get("valueCodeableConcept", {}).get("text", ""),
        "observation": {
            "loinc":         obs_c.get("code", "未知"),
            "loinc_display": obs_c.get("display", "未知"),
            "result":        obs_vc.get("display", ""),
        },
        "encounter": {
            "start":     encounter.get("period", {}).get("start", ""),
            "enc_class": encounter.get("class", {}).get("display", ""),
            "status":    encounter.get("status", ""),
        },
        "organization": {
            "name":    org.get("name", ""),
            "url":     next((t["value"] for t in org.get("telecom", []) if t.get("system") == "url"), ""),
            "address": "、".join(org_adr.get("line", [])) + org_adr.get("city", ""),
        },
        "_raw": bundle,
    }


def _fmt_dt(iso: str) -> str:
    if not iso:
        return "未知"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return iso


# ── eICR 通報單內嵌顯示（取代 @st.dialog，避免 auto-refresh 關閉） ────────────

def render_eicr_panel(eicr: dict, hospital_name: str):
    """將 eICR 通報單以 HTML 樣式渲染在頁面內，並提供 PDF 下載"""

    def section(title: str):
        st.markdown(
            f"<div style='background:#003F87;color:white;padding:6px 14px;"
            f"border-radius:4px;margin:14px 0 6px;font-size:0.95rem'>{title}</div>",
            unsafe_allow_html=True,
        )

    def field(label: str, value: str):
        st.markdown(
            f"<div style='margin-bottom:6px'>"
            f"<span style='color:#888;font-size:0.78rem'>{label}</span><br>"
            f"<span style='font-size:0.93rem;font-weight:500'>{value or '未知'}</span></div>",
            unsafe_allow_html=True,
        )

    # 頂部橫幅
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#003F87,#1a6db5);
            color:white;border-radius:8px;padding:14px 20px;margin-bottom:12px">
            <div style="font-size:1.1rem;font-weight:700">
                🏥 傳染病個案通報單（eICR）
            </div>
            <div style="font-size:0.8rem;opacity:0.8;margin-top:2px">
                {hospital_name} · HL7 FHIR R4 · MedMorph Reference Architecture
            </div>
            <div style="display:flex;gap:24px;margin-top:8px;font-size:0.78rem;opacity:0.7">
                <span>Bundle ID：{eicr["bundle_id"][:8]}…</span>
                <span>通報時間：{_fmt_dt(eicr["bundle_ts"])}</span>
                <span>狀態：{eicr["comp_status"].upper()}</span>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # 壹、病患
    section("壹、個案基本資料")
    p = eicr["patient"]
    c1, c2, c3 = st.columns(3)
    with c1: field("姓名", p["name"])
    with c2: field("性別", GENDER_LABEL.get(p["gender"], p["gender"]))
    with c3: field("出生日期", p["birthdate"])
    c4, c5 = st.columns(2)
    with c4: field("居住地區", p["county"])
    with c5: field("聯絡電話", p["phone"])

    # 貳、疾病
    section("貳、疾病及臨床資訊")
    cond = eicr["condition"]
    status_zh = {"suspected": "🟡 疑似（Suspected）",
                 "confirmed": "🔴 確診（Confirmed）"}.get(cond["clinical_status"], cond["clinical_status"])
    d1, d2 = st.columns(2)
    with d1:
        field("疾病名稱", cond["disease"])
        field("SNOMED-CT 代碼", cond["snomed"])
    with d2:
        field("臨床分類", status_zh)
        field("確認狀態", cond["ver_status"])
    d3, d4 = st.columns(2)
    with d3: field("發病日期", _fmt_dt(cond["onset"]))
    with d4: field("通報記錄時間", _fmt_dt(cond["recorded"]))

    # 參、症狀
    section("參、主訴症狀")
    symp = eicr["symptoms"]
    if symp:
        tags = "".join(
            f"<span style='background:#e8f0f8;color:#003F87;padding:4px 10px;"
            f"border-radius:10px;margin:3px;display:inline-block'>{s.strip()}</span>"
            for s in symp.replace("、", ",").split(",") if s.strip()
        )
        st.markdown(f"<div style='padding:4px 0'>{tags}</div>", unsafe_allow_html=True)
    else:
        st.caption("（未記載）")

    # 肆、檢驗
    section("肆、檢驗結果")
    obs = eicr["observation"]
    o1, o2, o3 = st.columns(3)
    with o1: field("LOINC 面板代碼", obs["loinc"])
    with o2: field("面板說明", obs["loinc_display"])
    with o3: field("觀察結果", obs["result"])

    # 伍、就診
    section("伍、就診紀錄")
    enc = eicr["encounter"]
    e1, e2, e3 = st.columns(3)
    with e1: field("就診時間", _fmt_dt(enc["start"]))
    with e2: field("就診類型", enc["enc_class"])
    with e3: field("就診狀態", {"finished": "已完成", "in-progress": "進行中"}.get(enc["status"], enc["status"]))

    # 陸、機構
    section("陸、通報醫療院所")
    org = eicr["organization"]
    g1, g2 = st.columns(2)
    with g1:
        field("機構名稱", org["name"])
        field("機構地址", org["address"])
    with g2:
        field("通報院所", hospital_name)
        field("機構網站", org["url"])

    # 原始 JSON
    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
    with st.expander("🔍 原始 eICR Bundle JSON（FHIR R4）"):
        st.code(json.dumps(eicr["_raw"], ensure_ascii=False, indent=2), language="json")

    # 下載按鈕
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.download_button(
            label="⬇️ 下載 eICR JSON",
            data=json.dumps(eicr["_raw"], ensure_ascii=False, indent=2),
            file_name=f"eicr_{eicr['bundle_id'][:8]}.json",
            mime="application/json",
            use_container_width=True,
            key="dl_json",
        )
    with btn_col2:
        try:
            pdf_bytes = generate_eicr_pdf(eicr, hospital_name=hospital_name)
            patient_name = eicr["patient"]["name"]
            st.download_button(
                label="📄 下載 PDF 通報單",
                data=pdf_bytes,
                file_name=f"{hospital_name}_傳染病通報單_{patient_name}_{eicr['bundle_id'][:8]}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="dl_pdf",
            )
        except Exception as e:
            st.warning(f"PDF 產生失敗：{e}")


# ── 圖表函式 ──────────────────────────────────────────────────────────────────

def make_map_figure(df: pd.DataFrame, disease_filter: str = "全部") -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.update_layout(mapbox_style="open-street-map",
                          mapbox_center={"lat": 23.8, "lon": 121.0},
                          mapbox_zoom=6, margin={"l": 0, "r": 0, "t": 0, "b": 0}, height=500)
        return fig
    plot_df = df if disease_filter == "全部" else df[df["disease"] == disease_filter]
    grp = plot_df.groupby(["county", "disease"]).size().reset_index(name="count")
    grp["lat"]        = grp["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[0])
    grp["lon"]        = grp["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[1])
    grp["disease_zh"] = grp["disease"].map(DISEASE_ZH)
    ct = grp.groupby("county")["count"].sum().reset_index(name="total")
    grp = grp.merge(ct, on="county")
    fig = px.scatter_mapbox(
        grp, lat="lat", lon="lon", size="total", color="disease",
        color_discrete_map=DISEASE_COLORS, hover_name="county",
        hover_data={"disease_zh": True, "count": True, "lat": False, "lon": False, "total": False},
        labels={"disease": "疾病", "count": "案例數", "disease_zh": "疾病名稱"},
        size_max=55, zoom=6, center={"lat": 23.8, "lon": 121.0},
        mapbox_style="open-street-map", height=500,
    )
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        legend=dict(title="疾病類型", orientation="h", yanchor="bottom", y=0.01,
                    xanchor="right", x=0.99, bgcolor="rgba(255,255,255,0.85)"),
    )
    return fig


def make_trend_figure(df: pd.DataFrame, days: int = 14,
                      disease_filter: str = "全部") -> go.Figure:
    if df.empty or "date" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title="每日新增案例趨勢（無資料）", height=360,
                          plot_bgcolor="rgba(0,0,0,0)")
        return fig
    cutoff    = (datetime.now() - timedelta(days=days)).date()
    recent    = df[df["date"] >= cutoff]
    all_dates = pd.date_range(start=cutoff, end=datetime.now().date(), freq="D").date
    diseases  = [disease_filter] if disease_filter != "全部" else list(DISEASE_ZH)
    fig = go.Figure()
    for d in diseases:
        sub  = recent[recent["disease"] == d]
        dly  = sub.groupby("date").size().reset_index(name="count")
        full = pd.DataFrame({"date": all_dates}).merge(dly, on="date", how="left").fillna(0)
        fig.add_trace(go.Scatter(
            x=full["date"], y=full["count"], mode="lines+markers",
            name=f"{DISEASE_EMOJI[d]} {DISEASE_ZH[d]}",
            line=dict(color=DISEASE_COLORS[d], width=2.5), marker=dict(size=6),
            hovertemplate="%{x}<br>案例數：%{y}<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text=f"📈 近 {days} 天每日新增案例趨勢", font_size=15),
        xaxis_title="日期", yaxis_title="新增案例數",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        height=360, hovermode="x unified", margin=dict(l=50, r=20, t=50, b=40),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)", rangemode="tozero")
    return fig


def make_county_bar(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    cc = df.groupby(["county", "disease"]).size().reset_index(name="count")
    ct = cc.groupby("county")["count"].sum().sort_values(ascending=True)
    ordered = ct.index.tolist()
    fig = go.Figure()
    for d in list(DISEASE_ZH):
        sub = cc[cc["disease"] == d].set_index("county")
        fig.add_trace(go.Bar(
            y=ordered, orientation="h",
            x=[sub.loc[c, "count"] if c in sub.index else 0 for c in ordered],
            name=f"{DISEASE_EMOJI[d]} {DISEASE_ZH[d]}",
            marker_color=DISEASE_COLORS[d],
            hovertemplate="%{y}：%{x} 例<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack", title=dict(text="各縣市案例分布", font_size=14),
        xaxis_title="案例數", height=max(400, len(ordered) * 22 + 80),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=80, r=20, t=50, b=40),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.08)")
    return fig


# ── 主頁面 ─────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="傳染病即時公衛儀表板",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    ss = st.session_state

    # ── Auto-refresh：一律執行，session_state 保持 eICR 選取不會消失 ─────────
    is_viewing = "eicr_case" in ss
    st_autorefresh(interval=REFRESH_INTERVAL_MS, key="auto_refresh")

    st.markdown("""
    <style>
    /* ── KPI 卡片 ── */
    .metric-card {
        border-radius:12px;padding:18px 20px;color:white;
        text-align:center;box-shadow:0 3px 10px rgba(0,0,0,0.12);
        background:linear-gradient(135deg,#1e3a5f,#2d6a9f);
    }
    .metric-value{font-size:2.6rem;font-weight:700;line-height:1}
    .metric-label{font-size:0.9rem;opacity:0.85;margin-top:4px}
    .metric-sub  {font-size:0.75rem;opacity:0.6;margin-top:4px}

    /* ── Tab 按鈕 ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: transparent;
        border-bottom: 2px solid #E0E6F0;
        padding-bottom: 0;
    }
    .stTabs [data-baseweb="tab"] {
        height: 52px;
        min-width: 155px;
        padding: 0 22px;
        background: #F0F4FA;
        border-radius: 10px 10px 0 0;
        border: 1.5px solid #D0DBF0;
        border-bottom: none;
        font-size: 1.02rem !important;
        font-weight: 600 !important;
        color: #4A6FA5 !important;
        transition: background 0.2s, color 0.2s;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: #E3EBF8;
        color: #003F87 !important;
    }
    .stTabs [aria-selected="true"] {
        background: white !important;
        color: #003F87 !important;
        border-color: #003F87 #D0DBF0 white !important;
        border-bottom: 2px solid white !important;
        box-shadow: 0 -2px 8px rgba(0,63,135,0.08);
    }
    /* Tab 內容區 */
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 18px;
    }
    </style>""", unsafe_allow_html=True)

    # 從 session_state 讀取篩選設定
    db_path_val      = ss.get("cfg_db_path",        DB_PATH)
    disease_val      = ss.get("cfg_disease_filter",  "全部")
    status_val       = ss.get("cfg_status_filter",   "全部")
    days_val         = ss.get("cfg_days_range",       14)
    hospital_name    = ss.get("cfg_hospital",        "XX 醫院")

    # ── 頂部標題 ────────────────────────────────────────────────────────────────
    h_left, h_right = st.columns([6, 1])
    with h_left:
        st.markdown("## 🏥 傳染病即時公衛儀表板")
        st.caption("MedMorph · FHIR R4 · HL7 eICR · NTU 智慧醫療期末專題 第五組")
    with h_right:
        st.markdown(f"<br>⏱ 每 {REFRESH_INTERVAL_MS//1000}s 刷新", unsafe_allow_html=True)
        st.caption(datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        if st.button("🔄 立即刷新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # 載入資料
    df_all = load_cases(db_path_val)
    df = df_all.copy()
    if disease_val != "全部":
        df = df[df["disease"] == disease_val]
    if status_val != "全部":
        df = df[df["status"] == status_val]

    # ── KPI 卡片（常駐） ──────────────────────────────────────────────────────
    def cnt(d): return 0 if df_all.empty else len(df_all[df_all["disease"] == d])
    def tc(d):
        if df_all.empty or "date" not in df_all.columns: return 0
        return len(df_all[(df_all["disease"] == d) & (df_all["date"] == datetime.now().date())])

    total_all = len(df_all)
    today_all = sum(tc(d) for d in DISEASE_ZH)
    k0, k1, k2, k3 = st.columns(4)
    with k0:
        st.markdown(
            f'<div class="metric-card"><div class="metric-value">{total_all}</div>'
            f'<div class="metric-label">📋 累計總案例</div>'
            f'<div class="metric-sub">今日 +{today_all}</div></div>',
            unsafe_allow_html=True,
        )
    for col, (d, grad) in zip([k1, k2, k3], [
        ("COVID-19",  "linear-gradient(135deg,#b71c1c,#e53935)"),
        ("Dengue",    "linear-gradient(135deg,#e65100,#ff9800)"),
        ("Influenza", "linear-gradient(135deg,#1565c0,#1e88e5)"),
    ]):
        with col:
            st.markdown(
                f'<div class="metric-card" style="background:{grad}">'
                f'<div class="metric-value">{cnt(d)}</div>'
                f'<div class="metric-label">{DISEASE_EMOJI[d]} {DISEASE_ZH[d]}</div>'
                f'<div class="metric-sub">今日 +{tc(d)}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    if df_all.empty:
        st.warning("⚠️ 尚無資料。請先執行：\n```bash\nuv run python seed_data.py\n```")
        return

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab_map, tab_trend, tab_cases, tab_settings = st.tabs([
        "🗺️ 地理分布", "📈 趨勢分析", "📋 案例明細 & 通報單", "⚙️ 設定",
    ])

    # ── Tab 1：地理分布 ─────────────────────────────────────────────────────────
    with tab_map:
        st.plotly_chart(make_map_figure(df, disease_val),
                        use_container_width=True, config={"scrollZoom": True})
        st.plotly_chart(make_county_bar(df), use_container_width=True)

    # ── Tab 2：趨勢分析 ─────────────────────────────────────────────────────────
    with tab_trend:
        st.plotly_chart(make_trend_figure(df_all, days_val, disease_val),
                        use_container_width=True)
        if "date" in df_all.columns:
            cutoff = (datetime.now() - timedelta(days=days_val)).date()
            summary = (
                df_all[df_all["date"] >= cutoff]
                .groupby("disease")
                .agg(案例數=("id", "count"),
                     疑似=("status", lambda x: (x == "suspected").sum()),
                     確診=("status", lambda x: (x == "confirmed").sum()))
                .reset_index()
            )
            summary["disease"] = summary["disease"].map(
                lambda d: f"{DISEASE_EMOJI.get(d,'')} {DISEASE_ZH.get(d,d)}"
            )
            summary.columns = ["疾病", f"近{days_val}天案例", "　疑似", "　確診"]
            st.dataframe(summary, use_container_width=True, hide_index=True)

    # ── Tab 3：案例明細 & 通報單（左右分割面板） ─────────────────────────────────
    with tab_cases:
        if df.empty:
            st.info("⚠️ 目前沒有符合條件的案例。請至「⚙️ 設定」調整篩選條件。")
        else:
            list_col, view_col = st.columns([0.42, 0.58], gap="medium")

            # ── 左：案例列表 ─────────────────────────────────────────────────
            with list_col:
                st.caption(f"共 {len(df)} 筆案例（顯示最近 50 筆）｜點 📋 查閱通報單")

                # 標頭
                hcols = st.columns([0.35, 1.7, 1.5, 1.3, 1.2, 0.5])
                for col, lbl in zip(hcols, ["#", "姓名", "疾病", "縣市", "狀態", ""]):
                    col.markdown(
                        f"<span style='font-size:0.82rem;font-weight:600;color:#555'>{lbl}</span>",
                        unsafe_allow_html=True,
                    )
                st.markdown("<hr style='margin:3px 0 1px;border-color:#ccc'>",
                            unsafe_allow_html=True)

                view_df = df.head(50).reset_index(drop=True)
                sel_idx = ss.get("eicr_index", -1)

                for i, row in view_df.iterrows():
                    is_selected = (i == sel_idx)
                    bg = "background:#EDF4FF;" if is_selected else ""
                    rcols = st.columns([0.35, 1.7, 1.5, 1.3, 1.2, 0.5])
                    d_zh  = f"{DISEASE_EMOJI.get(row['disease'],'')} {DISEASE_ZH.get(row['disease'], row['disease'])}"
                    s_zh  = STATUS_LABEL.get(row["status"], row["status"])
                    rcols[0].markdown(
                        f"<span style='color:#bbb;font-size:0.8rem;{bg}'>{i+1}</span>",
                        unsafe_allow_html=True,
                    )
                    rcols[1].markdown(
                        f"<span style='font-size:0.9rem;{bg}font-weight:{'600' if is_selected else '400'}'>"
                        f"{row['patient_name']}</span>",
                        unsafe_allow_html=True,
                    )
                    rcols[2].markdown(
                        f"<span style='font-size:0.87rem'>{d_zh}</span>",
                        unsafe_allow_html=True,
                    )
                    rcols[3].markdown(
                        f"<span style='font-size:0.87rem'>{row['county']}</span>",
                        unsafe_allow_html=True,
                    )
                    rcols[4].markdown(
                        f"<span style='font-size:0.87rem'>{s_zh}</span>",
                        unsafe_allow_html=True,
                    )
                    if rcols[5].button(
                        "📋", key=f"view_{i}", help="查閱 eICR 通報單",
                        type="primary" if is_selected else "secondary",
                    ):
                        ss["eicr_case"]  = df.iloc[i]
                        ss["eicr_index"] = i
                        st.rerun()

            # ── 右：eICR 通報單面板 ───────────────────────────────────────────
            with view_col:
                if not is_viewing:
                    st.markdown(
                        "<div style='height:200px;display:flex;align-items:center;"
                        "justify-content:center;border:2px dashed #ccc;"
                        "border-radius:12px;color:#aaa;font-size:1rem'>"
                        "← 點選左側案例的 📋 圖示查閱 eICR 通報單"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    sel = ss["eicr_case"]
                    sel_d = DISEASE_ZH.get(sel["disease"], sel["disease"])
                    sel_s = STATUS_LABEL.get(sel["status"], sel["status"])

                    # 通報單標題列 + 關閉按鈕
                    title_row, close_btn = st.columns([5, 1])
                    with title_row:
                        st.markdown(
                            f"**{DISEASE_EMOJI.get(sel['disease'],'')} {sel['patient_name']}**"
                            f"　{sel_d}　{sel_s}　{sel['county']}"
                        )
                    with close_btn:
                        if st.button("✕ 關閉", key="close_eicr"):
                            del ss["eicr_case"]
                            ss.pop("eicr_index", None)
                            st.rerun()

                    eicr = parse_eicr(sel.get("eicr_path", ""))
                    if eicr is None:
                        st.error("⚠️ 找不到 eICR 檔案（可能為舊版資料）。")
                    else:
                        render_eicr_panel(eicr, hospital_name=hospital_name)

    # ── Tab 4：設定 ─────────────────────────────────────────────────────────────
    with tab_settings:
        st.markdown("#### 🏥 通報院所設定")
        new_hospital = st.text_input("通報醫院名稱（顯示於通報單與 PDF）",
                                     value=hospital_name,
                                     help="此名稱將印在 PDF 通報單的「通報醫療院所」欄")

        st.markdown("#### 🗄️ 資料來源")
        new_db = st.text_input("SQLite 資料庫路徑", value=db_path_val)

        st.markdown("#### 🔍 篩選條件")
        new_disease = st.selectbox(
            "疾病類型",
            ["全部", "COVID-19", "Dengue", "Influenza"],
            index=["全部", "COVID-19", "Dengue", "Influenza"].index(disease_val),
            format_func=lambda x: f"{DISEASE_EMOJI.get(x,'📊')} {DISEASE_ZH.get(x,x)}",
        )
        new_status = st.selectbox(
            "案例狀態",
            ["全部", "suspected", "confirmed"],
            index=["全部", "suspected", "confirmed"].index(status_val),
            format_func=lambda x: {"全部":"全部","suspected":"🟡 疑似","confirmed":"🔴 確診"}.get(x,x),
        )
        new_days = st.slider("趨勢圖天數範圍", 7, 60, days_val, 7)

        if st.button("✅ 套用設定", type="primary"):
            ss["cfg_hospital"]       = new_hospital
            ss["cfg_db_path"]        = new_db
            ss["cfg_disease_filter"] = new_disease
            ss["cfg_status_filter"]  = new_status
            ss["cfg_days_range"]     = new_days
            st.cache_data.clear()
            st.success("✅ 設定已套用！")
            st.rerun()

        st.markdown("---")
        st.markdown("#### 📊 系統資訊")
        ia, ib = st.columns(2)
        with ia:
            st.markdown(f"- **資料庫**：`{db_path_val}`")
            st.markdown(f"- **總案例數**：{total_all} 筆 （今日 +{today_all}）")
            st.markdown(f"- **通報院所**：{hospital_name}")
        with ib:
            st.markdown(f"- **自動刷新**：每 {REFRESH_INTERVAL_MS//1000} 秒")
            st.markdown("- **標準**：HL7 FHIR R4 · MedMorph IG · HL7 eICR")
            st.markdown("- **查閱 eICR 時**：自動暫停刷新")

        st.markdown("---")
        st.markdown("#### 📌 使用說明")
        st.markdown(
            "1. 切換至「📋 案例明細」分頁，找到想查閱的案例\n"
            "2. 點選該列最右側 **📋** 圖示\n"
            "3. 通報單在列表下方展開；刷新**自動暫停**，不會跳掉\n"
            "4. 點「⬇️ 下載 PDF 通報單」存成 PDF（格式仿衛福部傳染病個案通報單）\n"
            "5. 點「✕ 關閉」後，自動刷新恢復"
        )
        st.markdown("---")
        st.markdown(
            "**NTU 智慧醫療期末專題 · 第五組**\n\n"
            "| 疾病 | SNOMED-CT | LOINC 面板 |\n"
            "|------|-----------|------------|\n"
            "| COVID-19 | 840539006 | 94531-1 |\n"
            "| 登革熱 | 38362002 | 86615-1 |\n"
            "| 流感 | 57386000 | 92142-9 |"
        )

    st.markdown("---")
    st.caption("🏥 NTU 智慧醫療期末專題 · 第五組 · FHIR R4 · MedMorph · HL7 eICR")


if __name__ == "__main__":
    main()
