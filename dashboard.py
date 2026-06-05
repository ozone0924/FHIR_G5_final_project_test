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

    # 頂部橫幅 + 下載按鈕（同排）
    hdr_col, dl_col = st.columns([3, 1])
    with hdr_col:
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg,#003F87,#1a6db5);
                color:white;border-radius:8px;padding:10px 16px;margin-bottom:0">
                <div style="font-size:1.05rem;font-weight:700">
                    🏥 傳染病個案通報單（eICR）
                </div>
                <div style="font-size:0.78rem;opacity:0.8;margin-top:2px">
                    {hospital_name} · HL7 FHIR R4 · MedMorph
                </div>
                <div style="display:flex;gap:16px;margin-top:6px;font-size:0.75rem;opacity:0.7">
                    <span>Bundle：{eicr["bundle_id"][:8]}…</span>
                    <span>{_fmt_dt(eicr["bundle_ts"])}</span>
                    <span>{eicr["comp_status"].upper()}</span>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
    with dl_col:
        try:
            pdf_bytes    = generate_eicr_pdf(eicr, hospital_name=hospital_name)
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
        st.download_button(
            label="⬇️ 下載 JSON",
            data=json.dumps(eicr["_raw"], ensure_ascii=False, indent=2),
            file_name=f"eicr_{eicr['bundle_id'][:8]}.json",
            mime="application/json",
            use_container_width=True,
            key="dl_json",
        )

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

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
    /* ═══ 全頁固定於 viewport，禁止整頁捲動 ═══ */
    html { overflow-y: hidden !important; }
    .main .block-container {
        padding-top: 0.6rem !important;
        padding-bottom: 0 !important;
        max-height: calc(100vh - 58px) !important;
        overflow: hidden !important;
    }

    /* ═══ KPI 卡片（緊湊版） ═══ */
    .metric-card {
        border-radius:10px; padding:10px 14px; color:white;
        text-align:center; box-shadow:0 3px 8px rgba(0,0,0,0.1);
        background:linear-gradient(135deg,#1e3a5f,#2d6a9f);
    }
    .metric-value { font-size:2.1rem; font-weight:700; line-height:1; }
    .metric-label { font-size:0.85rem; opacity:0.85; margin-top:3px; }
    .metric-sub   { font-size:0.72rem; opacity:0.6;  margin-top:3px; }

    /* ═══ Tab 按鈕 ═══ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: transparent;
        border-bottom: 2px solid #E0E6F0;
        padding-bottom: 0;
        margin-bottom: 0;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        min-width: 150px;
        padding: 0 20px;
        background: #F0F4FA;
        border-radius: 10px 10px 0 0;
        border: 1.5px solid #D0DBF0;
        border-bottom: none;
        font-size: 1.0rem !important;
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
    /* Tab 內容區不產生自身捲動，由內部 container 負責 */
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 10px !important;
        overflow: hidden !important;
    }

    /* ═══ 內部滾動容器：移除預設灰框，顯示自訂捲軸 ═══ */
    [data-testid="stVerticalBlockBorderWrapper"] > div {
        border-radius: 8px;
    }

    /* ═══ 通報單按鈕：emoji 水平置中 ═══ */
    [data-testid="stButton"] > button {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
    }
    </style>""", unsafe_allow_html=True)

    # 從 session_state 讀取篩選設定
    db_path_val      = ss.get("cfg_db_path",        DB_PATH)
    disease_val      = ss.get("cfg_disease_filter",  "全部")
    status_val       = ss.get("cfg_status_filter",   "全部")
    days_val         = ss.get("cfg_days_range",       14)
    hospital_name    = ss.get("cfg_hospital",        "測試醫院")

    # ── 頂部標題（單行緊湊版） ────────────────────────────────────────────────────
    h_left, h_mid, h_right = st.columns([5, 2, 1])
    with h_left:
        st.markdown(
            "<h3 style='margin:0;padding:0;line-height:1.2'>🏥 傳染病即時公衛儀表板</h3>"
            "<p style='margin:0;font-size:0.78rem;color:#888'>"
            "MedMorph · FHIR R4 · HL7 eICR · NTU 智慧醫療期末專題 第五組</p>",
            unsafe_allow_html=True,
        )
    with h_mid:
        st.markdown(
            f"<div style='text-align:right;padding-top:4px;"
            f"font-size:0.82rem;color:#999'>⏱ 每 {REFRESH_INTERVAL_MS//1000}s 刷新　"
            f"{datetime.now().strftime('%H:%M:%S')}</div>",
            unsafe_allow_html=True,
        )
    with h_right:
        if st.button("🔄 刷新", use_container_width=True):
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

    # 去掉 <br> 間距，改為一小段 margin
    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

    if df_all.empty:
        st.warning("⚠️ 尚無資料。請先執行：\n```bash\nuv run python seed_data.py\n```")
        return

    # ── Tabs（所有內容都在固定高度 container 內捲動） ─────────────────────────
    # 根據視窗高度估算可用高度：100vh - 58(bar) - 55(title) - 90(KPI) - 55(tabs) ≈ 560px
    TAB_H = 560   # tab 內容區高度（像素）
    LIST_H = TAB_H - 2   # 清單/面板高度（含標頭略小）

    tab_map, tab_trend, tab_cases, tab_settings = st.tabs([
        "🗺️ 地理分布", "📈 趨勢分析", "📋 案例明細 & 通報單", "⚙️ 設定",
    ])

    # ── Tab 1：地理分布 ─────────────────────────────────────────────────────────
    with tab_map:
        with st.container(height=TAB_H, border=False):
            mc, bc = st.columns([3, 2])
            with mc:
                st.plotly_chart(
                    make_map_figure(df, disease_val),
                    use_container_width=True, config={"scrollZoom": True},
                )
            with bc:
                st.plotly_chart(make_county_bar(df), use_container_width=True)

    # ── Tab 2：趨勢分析 ─────────────────────────────────────────────────────────
    with tab_trend:
        with st.container(height=TAB_H, border=False):
            st.plotly_chart(
                make_trend_figure(df_all, days_val, disease_val),
                use_container_width=True,
            )
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

    # ── Tab 3：案例明細 & 通報單（左右分割，各自內捲） ───────────────────────────
    with tab_cases:
        if df.empty:
            st.info("⚠️ 目前沒有符合條件的案例。請至「⚙️ 設定」調整篩選條件。")
        else:
            list_col, view_col = st.columns([0.40, 0.60], gap="small")

            # ── 左：固定高度捲動清單 ─────────────────────────────────────────
            with list_col:
                st.caption(
                    f"共 {len(df)} 筆（最近 50 筆）｜點 📋 查閱通報單",
                    help="點選任一列的 📋 按鈕，右側即顯示 eICR 通報單內容",
                )
                # 捲動容器
                with st.container(height=LIST_H, border=True):
                    # 表頭（固定在捲動容器內最頂部）
                    COLS = [0.28, 1.55, 1.45, 1.15, 1.05, 0.72]
                    hcols = st.columns(COLS)
                    for col, lbl in zip(hcols, ["#", "姓名", "疾病", "縣市", "狀態", "通報單"]):
                        extra = "text-align:center;white-space:nowrap;" if lbl == "通報單" else ""
                        col.markdown(
                            f"<b style='font-size:0.8rem;color:#555;{extra}'>{lbl}</b>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        "<hr style='margin:2px 0;border-color:#ddd'>",
                        unsafe_allow_html=True,
                    )

                    view_df  = df.head(50).reset_index(drop=True)
                    sel_idx  = ss.get("eicr_index", -1)

                    for i, row in view_df.iterrows():
                        is_sel = (i == sel_idx)
                        # 選取指示：左側藍線 + 顯式文字色，避免 dark mode 亮底色蓋掉文字
                        hl = ("border-left:3px solid #4A9EFF;padding-left:4px;"
                              "color:#4A9EFF !important;" if is_sel else "")
                        rcols  = st.columns(COLS)
                        d_zh   = (f"{DISEASE_EMOJI.get(row['disease'],'')} "
                                  f"{DISEASE_ZH.get(row['disease'], row['disease'])}")
                        s_zh   = STATUS_LABEL.get(row["status"], row["status"])
                        dt_str = (row["report_date"].strftime("%m/%d")
                                  if pd.notna(row["report_date"]) else "")

                        rcols[0].markdown(
                            f"<span style='color:#bbb;font-size:0.78rem'>{i+1}</span>",
                            unsafe_allow_html=True,
                        )
                        rcols[1].markdown(
                            f"<span style='{hl}font-size:0.88rem;"
                            f"font-weight:{'600' if is_sel else '400'}'>"
                            f"{row['patient_name']}</span>",
                            unsafe_allow_html=True,
                        )
                        rcols[2].markdown(
                            f"<span style='font-size:0.82rem'>{d_zh}</span>",
                            unsafe_allow_html=True,
                        )
                        rcols[3].markdown(
                            f"<span style='font-size:0.85rem'>{row['county']}</span>",
                            unsafe_allow_html=True,
                        )
                        rcols[4].markdown(
                            f"<span style='font-size:0.82rem'>{s_zh}</span>",
                            unsafe_allow_html=True,
                        )
                        # 📋 按鈕：最後一欄夠寬，不會被擠
                        if rcols[5].button(
                            "📋", key=f"v_{i}",
                            help=f"查閱 {row['patient_name']} 的 eICR 通報單",
                            type="primary" if is_sel else "secondary",
                            use_container_width=True,
                        ):
                            ss["eicr_case"]  = df.iloc[i]
                            ss["eicr_index"] = i
                            st.rerun()

            # ── 右：eICR 通報單固定高度捲動面板 ─────────────────────────────
            with view_col:
                if not is_viewing:
                    # 佔位提示，高度與左欄對齊
                    st.markdown(
                        f"<div style='height:{LIST_H}px;display:flex;"
                        f"align-items:center;justify-content:center;"
                        f"border:2px dashed #ccc;border-radius:8px;"
                        f"color:#bbb;font-size:1rem'>"
                        f"← 點選左側 📋 按鈕查閱 eICR 通報單</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    sel   = ss["eicr_case"]
                    sel_d = DISEASE_ZH.get(sel["disease"], sel["disease"])
                    sel_s = STATUS_LABEL.get(sel["status"], sel["status"])

                    # 標題列（捲動容器外，固定顯示）
                    t_col, c_col = st.columns([5, 1])
                    with t_col:
                        st.markdown(
                            f"**{DISEASE_EMOJI.get(sel['disease'],'')} "
                            f"{sel['patient_name']}**　"
                            f"{sel_d}　{sel_s}　{sel['county']}"
                        )
                    with c_col:
                        if st.button("✕ 關閉", key="close_eicr", use_container_width=True):
                            del ss["eicr_case"]
                            ss.pop("eicr_index", None)
                            st.rerun()

                    # 通報單本體（固定高度，可在內部捲動）
                    panel_h = LIST_H - 42   # 扣掉標題列高度
                    with st.container(height=panel_h, border=True):
                        eicr = parse_eicr(sel.get("eicr_path", ""))
                        if eicr is None:
                            st.error("⚠️ 找不到 eICR 檔案。")
                        else:
                            render_eicr_panel(eicr, hospital_name=hospital_name)

    # ── Tab 4：設定 ─────────────────────────────────────────────────────────────
    with tab_settings:
        with st.container(height=TAB_H, border=False):
            s1, s2 = st.columns(2)
            with s1:
                st.markdown("#### 🏥 通報院所")
                new_hospital = st.text_input(
                    "醫院名稱（顯示於通報單與 PDF）", value=hospital_name)
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
                    format_func=lambda x: {
                        "全部": "全部", "suspected": "🟡 疑似", "confirmed": "🔴 確診"
                    }.get(x, x),
                )
                new_days = st.slider("趨勢圖天數範圍", 7, 60, days_val, 7)
                if st.button("✅ 套用設定", type="primary", use_container_width=True):
                    ss["cfg_hospital"]       = new_hospital
                    ss["cfg_db_path"]        = new_db
                    ss["cfg_disease_filter"] = new_disease
                    ss["cfg_status_filter"]  = new_status
                    ss["cfg_days_range"]     = new_days
                    st.cache_data.clear()
                    st.success("✅ 設定已套用！")
                    st.rerun()

            with s2:
                st.markdown("#### 📊 系統資訊")
                st.markdown(f"- **資料庫**：`{db_path_val}`")
                st.markdown(f"- **通報院所**：{hospital_name}")
                st.markdown(f"- **總案例數**：{total_all} 筆（今日 +{today_all}）")
                st.markdown(f"- **自動刷新**：每 {REFRESH_INTERVAL_MS//1000} 秒")
                st.markdown("- **標準**：FHIR R4 · MedMorph · HL7 eICR")
                st.markdown("---")
                st.markdown("#### 📌 使用說明")
                st.markdown(
                    "1. **案例明細** Tab → 找到想查閱的案例\n"
                    "2. 點按最右側 **📋** 按鈕\n"
                    "3. 右側面板即時顯示 eICR 通報單（可在面板內捲動）\n"
                    "4. 點「**📄 下載 PDF 通報單**」輸出正式格式\n"
                    "5. 點「**✕ 關閉**」返回清單模式\n\n"
                    "| 疾病 | SNOMED-CT | LOINC |\n"
                    "|------|-----------|-------|\n"
                    "| COVID-19 | 840539006 | 94531-1 |\n"
                    "| 登革熱 | 38362002 | 86615-1 |\n"
                    "| 流感 | 57386000 | 92142-9 |"
                )

    st.markdown(
        "<p style='text-align:center;font-size:0.75rem;color:#ccc;margin:0'>"
        "NTU 智慧醫療期末專題 · 第五組 · FHIR R4 · MedMorph · HL7 eICR</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
