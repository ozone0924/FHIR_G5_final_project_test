"""
程式 C：Streamlit 即時公衛儀表板（Tab 版面）
============================================
使用方式：
  uv run streamlit run dashboard.py
"""

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from pdf_report import generate_eicr_pdf

# ── 常數 ──────────────────────────────────────────────────────────────────────
DB_PATH             = os.getenv("DB_PATH", "data/cases.db")
REFRESH_INTERVAL_MS = 15_000
TZ_TPE              = ZoneInfo("Asia/Taipei")

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

    df["report_date"] = pd.to_datetime(df["report_date"], utc=True, errors="coerce")
    # 以台北時間計算「今日」日期，避免 UTC 日期跨日誤差
    df["date"] = df["report_date"].dt.tz_convert("Asia/Taipei").dt.date
    df["symptoms_list"] = df["symptoms"].apply(
        lambda s: json.loads(s) if isinstance(s, str) and s else []
    )

    # 確保新欄位存在（相容舊版 DB）
    for col in ["hospital_name", "hospital_address", "hospital_lat", "hospital_lon",
                "home_address", "home_lat", "home_lon"]:
        if col not in df.columns:
            df[col] = None

    # 計算年齡
    today = datetime.now(TZ_TPE).date()
    def _age(bd):
        try:
            bd_d = datetime.strptime(str(bd), "%Y-%m-%d").date()
            return (today - bd_d).days // 365
        except Exception:
            return None
    df["age"] = df["birthdate"].apply(_age)

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
    composition = _res(bundle, "Composition")

    # 取通報院所（custodian 以外的 Organization）和 CDC
    orgs = [e["resource"] for e in bundle.get("entry", [])
            if e.get("resource", {}).get("resourceType") == "Organization"]
    hosp_org = next((o for o in orgs if o.get("id", "").startswith("org-hosp")), {})
    cdc_org  = next((o for o in orgs if o.get("id") == "org-tw-cdc"), orgs[0] if orgs else {})

    cond_c = (condition.get("code", {}).get("coding") or [{}])[0]
    obs_c  = (observation.get("code", {}).get("coding") or [{}])[0]
    obs_vc = (observation.get("valueCodeableConcept", {}).get("coding") or [{}])[0]
    cdc_adr = (cdc_org.get("address") or [{}])[0]
    pat_adr = (patient.get("address") or [{}])[0]

    return {
        "bundle_id":   bundle.get("id", ""),
        "bundle_ts":   bundle.get("timestamp", ""),
        "comp_title":  composition.get("title", ""),
        "comp_status": composition.get("status", ""),
        "patient": {
            "name":      (patient.get("name") or [{}])[0].get("text", "未知"),
            "gender":    patient.get("gender", "unknown"),
            "birthdate": patient.get("birthDate", "未知"),
            "county":    pat_adr.get("city", pat_adr.get("district", "未知")),
            "district":  pat_adr.get("district", ""),
            "address":   "、".join(pat_adr.get("line", [])),
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
        "hospital": {
            "name":    hosp_org.get("name", ""),
            "address": (hosp_org.get("address") or [{}])[0].get("text", ""),
        },
        "organization": {
            "name":    cdc_org.get("name", ""),
            "url":     next((t["value"] for t in cdc_org.get("telecom", []) if t.get("system") == "url"), ""),
            "address": "、".join(cdc_adr.get("line", [])) + cdc_adr.get("city", ""),
        },
        "_raw": bundle,
    }


def _fmt_dt(iso: str) -> str:
    """ISO 8601 UTC → Asia/Taipei 格式化顯示"""
    if not iso:
        return "未知"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(TZ_TPE).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return iso


# ── eICR 通報單面板 ───────────────────────────────────────────────────────────

def render_eicr_panel(eicr: dict, hospital_name: str):
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

    section("壹、個案基本資料")
    p = eicr["patient"]
    c1, c2, c3 = st.columns(3)
    with c1: field("姓名", p["name"])
    with c2: field("性別", GENDER_LABEL.get(p["gender"], p["gender"]))
    with c3: field("出生日期", p["birthdate"])
    c4, c5 = st.columns(2)
    with c4: field("居住地區", f"{p['county']} {p.get('district','')}".strip())
    with c5: field("聯絡電話", p["phone"])
    if p.get("address"):
        field("住家地址", p["address"])

    section("貳、疾病及臨床資訊")
    cond = eicr["condition"]
    status_zh = {"suspected": "🟡 疑似（Suspected）",
                 "confirmed": "🔴 確診（Confirmed）"}.get(
        cond["clinical_status"], cond["clinical_status"])
    d1, d2 = st.columns(2)
    with d1:
        field("疾病名稱", cond["disease"])
        field("SNOMED-CT 代碼", cond["snomed"])
    with d2:
        field("臨床分類", status_zh)
        field("確認狀態", cond["ver_status"])
    d3, d4 = st.columns(2)
    with d3: field("發病（就診）日期", _fmt_dt(cond["onset"]))
    with d4: field("通報記錄時間",     _fmt_dt(cond["recorded"]))

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

    section("肆、檢驗結果")
    obs = eicr["observation"]
    o1, o2, o3 = st.columns(3)
    with o1: field("LOINC 面板代碼", obs["loinc"])
    with o2: field("面板說明", obs["loinc_display"])
    with o3: field("觀察結果", obs["result"])

    section("伍、就診紀錄")
    enc = eicr["encounter"]
    e1, e2, e3 = st.columns(3)
    with e1: field("就診時間", _fmt_dt(enc["start"]))
    with e2: field("就診類型", enc["enc_class"])
    with e3: field("就診狀態", {"finished": "已完成", "in-progress": "進行中"}.get(enc["status"], enc["status"]))

    section("陸、通報醫療院所")
    hosp = eicr.get("hospital", {})
    org  = eicr["organization"]
    g1, g2 = st.columns(2)
    with g1:
        field("通報院所", hosp.get("name") or hospital_name)
        field("院所地址", hosp.get("address", ""))
    with g2:
        field("公衛主管機構", org["name"])
        field("機構網站", org["url"])

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
    with st.expander("🔍 原始 eICR Bundle JSON（FHIR R4）"):
        st.code(json.dumps(eicr["_raw"], ensure_ascii=False, indent=2), language="json")


# ── 圖表函式 ──────────────────────────────────────────────────────────────────

# 寬鬆邊界：允許 zoom out 至可看到整個台灣（span ~13°），同時防止滑移至遠洋
_TW_BOUNDS = dict(west=113.0, east=128.0, south=17.0, north=30.0)
_LEGEND_STYLE = dict(
    font=dict(color="#222222", size=11),
    bgcolor="rgba(255,255,255,0.92)",
    bordercolor="rgba(0,0,0,0.08)",
    borderwidth=1,
)


def _empty_map(height: int = 460) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=23.8, lon=121.0),
            zoom=6,
            bounds=_TW_BOUNDS,
        ),
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        height=height,
    )
    return fig


def _norm_size(series: pd.Series, min_px: int = 8, max_px: int = 35) -> pd.Series:
    """sqrt 正規化後映射到 [min_px, max_px]，避免大值泡泡過大"""
    mx = series.max()
    if mx <= 0:
        return pd.Series([min_px] * len(series), index=series.index)
    return min_px + (max_px - min_px) * (series / mx) ** 0.5


def make_map_figure(df: pd.DataFrame, disease_filter: str = "全部",
                    height: int = 460) -> go.Figure:
    """縣市累積泡泡地圖（sqrt 正規化大小，上限 35px）"""
    if df.empty:
        return _empty_map(height)
    plot_df = df if disease_filter == "全部" else df[df["disease"] == disease_filter]
    grp = plot_df.groupby(["county", "disease"]).size().reset_index(name="count")
    grp["lat"]        = grp["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[0])
    grp["lon"]        = grp["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[1])
    grp["disease_zh"] = grp["disease"].map(DISEASE_ZH)
    # 以所有縣市中最大值為基準做 sqrt 正規化
    grp["size"] = _norm_size(grp["count"])

    fig = go.Figure()
    for d in list(DISEASE_ZH):
        sub = grp[grp["disease"] == d]
        if sub.empty:
            continue
        fig.add_trace(go.Scattermapbox(
            lat=sub["lat"].tolist(), lon=sub["lon"].tolist(),
            mode="markers",
            marker=dict(
                size=sub["size"].tolist(),
                color=DISEASE_COLORS[d],
                opacity=0.78,
                sizemode="diameter",
            ),
            name=f"{DISEASE_EMOJI[d]} {DISEASE_ZH[d]}",
            text=sub["county"].tolist(),
            customdata=list(zip(sub["disease_zh"], sub["count"])),
            hovertemplate="<b>%{text}</b><br>疾病=%{customdata[0]}<br>案例數=%{customdata[1]}<extra></extra>",
        ))

    fig.update_layout(
        mapbox=dict(
            style="open-street-map", zoom=6,
            center={"lat": 23.8, "lon": 121.0},
            bounds=_TW_BOUNDS,
        ),
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        height=height,
        legend=dict(
            title=dict(text="疾病類型", font=dict(color="#222")),
            orientation="h", yanchor="bottom", y=0.01, xanchor="right", x=0.99,
            **_LEGEND_STYLE,
        ),
    )
    return fig


def make_hospital_map(df: pd.DataFrame, disease_filter: str = "全部",
                      height: int = 460) -> go.Figure:
    """通報醫療院所分布地圖（sqrt 正規化大小，上限 30px）"""
    if df.empty:
        return _empty_map(height)
    plot_df = df if disease_filter == "全部" else df[df["disease"] == disease_filter]
    hdf = plot_df.dropna(subset=["hospital_lat", "hospital_lon"])
    hdf = hdf[(hdf["hospital_lat"] != 0) & (hdf["hospital_name"] != "")]
    if hdf.empty:
        return _empty_map(height)

    grp = (hdf.groupby(["hospital_name", "hospital_lat", "hospital_lon", "disease"])
             .size().reset_index(name="count"))
    grp["disease_zh"] = grp["disease"].map(DISEASE_ZH)
    grp["size"] = _norm_size(grp["count"], min_px=6, max_px=30)

    fig = go.Figure()
    for d in list(DISEASE_ZH):
        sub = grp[grp["disease"] == d]
        if sub.empty:
            continue
        fig.add_trace(go.Scattermapbox(
            lat=sub["hospital_lat"].tolist(), lon=sub["hospital_lon"].tolist(),
            mode="markers",
            marker=dict(
                size=sub["size"].tolist(),
                color=DISEASE_COLORS[d],
                opacity=0.78,
                sizemode="diameter",
            ),
            name=f"{DISEASE_EMOJI[d]} {DISEASE_ZH[d]}",
            text=sub["hospital_name"].tolist(),
            customdata=list(zip(sub["disease_zh"], sub["count"])),
            hovertemplate="<b>%{text}</b><br>疾病=%{customdata[0]}<br>案例數=%{customdata[1]}<extra></extra>",
        ))

    fig.update_layout(
        mapbox=dict(
            style="open-street-map", zoom=6,
            center={"lat": 23.8, "lon": 121.0},
            bounds=_TW_BOUNDS,
        ),
        margin={"l": 0, "r": 0, "t": 30, "b": 0},
        title=dict(text="🏥 通報醫療院所（泡泡大小 = 通報數）", font_size=13, y=0.97),
        height=height,
        legend=dict(
            title=dict(text="疾病類型", font=dict(color="#222")),
            orientation="h", yanchor="bottom", y=0.01, xanchor="right", x=0.99,
            **_LEGEND_STYLE,
        ),
    )
    return fig


def make_temporal_map(df: pd.DataFrame, height: int = 460) -> go.Figure:
    """
    疾病時間擴散地圖。
    - 每種疾病獨立一條 trace，顏色在該疾病的時間範圍內正規化：
      最舊案例 → 淺色透明，最新案例 → 深色不透明
    - 點大小也隨時間變化（近期較大），不會因 zoom 消失
    """
    if df.empty:
        return _empty_map(height)
    plot_df = df.copy()

    # 座標：優先 home_lat/lon，退回縣市中心
    has_home = ("home_lat" in plot_df.columns and "home_lon" in plot_df.columns)
    if has_home:
        lat_col = plot_df["home_lat"].where(
            plot_df["home_lat"].notna() & (plot_df["home_lat"] != 0),
            plot_df["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[0]),
        ).astype(float)
        lon_col = plot_df["home_lon"].where(
            plot_df["home_lon"].notna() & (plot_df["home_lon"] != 0),
            plot_df["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[1]),
        ).astype(float)
    else:
        lat_col = plot_df["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[0])
        lon_col = plot_df["county"].map(lambda c: COUNTY_COORDS.get(c, (23.8, 121.0))[1])

    today = datetime.now(TZ_TPE).date()
    plot_df["_lat"] = lat_col
    plot_df["_lon"] = lon_col
    plot_df["days_ago"] = plot_df["date"].apply(
        lambda d: (today - d).days if pd.notna(d) else 9999
    )

    # 每種疾病的漸層色階：[老 → 近] = [淺透明 → 深不透明]
    DISEASE_SCALES = {
        "COVID-19":  [[0, "rgba(255,205,210,0.15)"], [0.45, "#EF5350"], [1, "#B71C1C"]],
        "Dengue":    [[0, "rgba(255,236,179,0.15)"], [0.45, "#FB8C00"], [1, "#E65100"]],
        "Influenza": [[0, "rgba(187,222,251,0.15)"], [0.45, "#1E88E5"], [1, "#0D47A1"]],
    }

    fig = go.Figure()
    valid = plot_df[plot_df["days_ago"] < 9999]
    if valid.empty:
        return _empty_map(height)

    for disease in [d for d in list(DISEASE_ZH) if d in valid["disease"].unique()]:
        dsub = valid[valid["disease"] == disease].copy()
        d_min = float(dsub["days_ago"].min())
        d_max = float(dsub["days_ago"].max())
        span  = max(d_max - d_min, 1.0)

        # norm_recency: 1=最新 (days_ago=d_min), 0=最舊 (days_ago=d_max)
        norm = 1.0 - (dsub["days_ago"].astype(float) - d_min) / span
        sizes = (9 + 8 * norm).tolist()      # 9–17 px，近期更大

        date_strs = [
            r.strftime("%m/%d") if pd.notna(r) else ""
            for r in dsub["report_date"]
        ]

        fig.add_trace(go.Scattermapbox(
            lat=dsub["_lat"].tolist(),
            lon=dsub["_lon"].tolist(),
            mode="markers",
            marker=dict(
                size=sizes,
                color=norm.tolist(),       # 0–1 浮點，映射到 colorscale
                colorscale=DISEASE_SCALES[disease],
                cmin=0, cmax=1,
                showscale=False,           # 不顯示 colorbar
                opacity=0.9,
            ),
            name=f"{DISEASE_EMOJI.get(disease,'')} {DISEASE_ZH.get(disease,disease)}",
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                f"疾病：{DISEASE_ZH.get(disease, disease)}<br>"
                "縣市：%{customdata[1]}<br>"
                "通報日：%{customdata[2]}　距今 %{customdata[3]} 天<extra></extra>"
            ),
            customdata=list(zip(
                dsub["patient_name"].tolist(),
                dsub["county"].tolist(),
                date_strs,
                dsub["days_ago"].astype(int).tolist(),
            )),
            legendgroup=disease,
        ))

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=23.8, lon=121.0),
            zoom=6,
            bounds=_TW_BOUNDS,
        ),
        margin={"l": 0, "r": 0, "t": 36, "b": 0},
        height=height,
        title=dict(text="🕐 病患居住地 — 時間擴散漸層（深色=最近期，淺色=最早期）",
                   font_size=13, y=0.98),
        legend=dict(
            orientation="h", yanchor="bottom", y=0.01, xanchor="right", x=0.99,
            font=dict(size=13, color="#111"),
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="rgba(0,0,0,0.08)", borderwidth=1,
            itemclick="toggle", itemdoubleclick="toggleothers",
        ),
    )
    return fig


_DAYS_SL_KEYS = tuple(f"days_sl_{s}" for s in ("map", "trend", "cases", "demo", "track"))


def _sync_days(key: str) -> None:
    val = st.session_state[key]
    st.session_state["cfg_days_range"] = val
    for k in _DAYS_SL_KEYS:
        if k != key:
            st.session_state[k] = val


def _days_slider(suffix: str) -> None:
    key = f"days_sl_{suffix}"
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get("cfg_days_range", 35)
    val = int(st.session_state[key])
    lc, sc = st.columns([1.6, 3])
    with lc:
        st.markdown(
            f"<div style='padding:4px 0 2px 4px'>"
            f"<div style='font-size:0.75rem;color:#888;font-weight:500'>📅 顯示時間範圍</div>"
            f"<div style='font-size:1.25rem;font-weight:700;color:#4A9EFF;line-height:1.3'>"
            f"近 {val} 天</div>"
            f"<div style='font-size:0.68rem;color:#aaa'>⟳ 各頁籤同步套用</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with sc:
        st.slider(
            "天數", 7, 365, step=1, key=key,
            on_change=_sync_days, args=(key,),
            label_visibility="collapsed",
            format="%d 天",
            help=f"目前顯示近 {val} 天的資料，拖曳調整後各頁籤同步套用",
        )


def make_trend_figure(df: pd.DataFrame, days: int = 14,
                      disease_filter: str = "全部") -> go.Figure:
    if df.empty or "date" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title="每日新增案例趨勢（無資料）", height=320,
                          plot_bgcolor="rgba(0,0,0,0)")
        return fig
    today   = datetime.now(TZ_TPE).date()
    cutoff  = (datetime.now(TZ_TPE) - timedelta(days=days)).date()
    recent  = df[df["date"] >= cutoff]
    all_dates = pd.date_range(start=cutoff, end=today, freq="D").date
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
        height=320, hovermode="x unified", margin=dict(l=50, r=20, t=50, b=40),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)", rangemode="tozero")
    return fig


def _bar_legend() -> dict:
    """共用的大字型圖例設定（方便點選）"""
    return dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        font=dict(size=14, color="#111111"),
        bgcolor="rgba(255,255,255,0.88)",
        bordercolor="rgba(0,0,0,0.15)",
        borderwidth=1,
        itemclick="toggle", itemdoubleclick="toggleothers",
    )


def make_county_bar(df: pd.DataFrame) -> go.Figure:
    """各縣市疾病堆疊橫條圖（大字型圖例，可點選切換）"""
    if df.empty:
        return go.Figure()
    diseases_in_df = df["disease"].unique()
    cc = df.groupby(["county", "disease"]).size().reset_index(name="count")
    ct = cc.groupby("county")["count"].sum().sort_values(ascending=True)
    ordered = ct.index.tolist()
    fig = go.Figure()
    for d in list(DISEASE_ZH):
        if d not in diseases_in_df:
            continue
        sub = cc[cc["disease"] == d].set_index("county")
        fig.add_trace(go.Bar(
            y=ordered, orientation="h",
            x=[sub.loc[c, "count"] if c in sub.index else 0 for c in ordered],
            name=f"{DISEASE_EMOJI[d]} {DISEASE_ZH[d]}",
            marker_color=DISEASE_COLORS[d],
            hovertemplate="%{y}：%{x} 例<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        title=dict(text="各縣市案例分布", font_size=14),
        xaxis_title="案例數",
        height=max(380, len(ordered) * 22 + 80),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=_bar_legend(),
        margin=dict(l=80, r=20, t=60, b=40),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.08)")
    return fig


def make_hospital_bar(df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """各通報院所疾病堆疊橫條圖（格式與縣市圖一致）"""
    if df.empty:
        return go.Figure()
    hdf = df.dropna(subset=["hospital_name"])
    hdf = hdf[hdf["hospital_name"] != ""]
    if hdf.empty:
        return go.Figure()
    diseases_in_df = hdf["disease"].unique()
    cc = hdf.groupby(["hospital_name", "disease"]).size().reset_index(name="count")
    ct = (cc.groupby("hospital_name")["count"].sum()
          .sort_values(ascending=True).tail(top_n))
    ordered = ct.index.tolist()
    fig = go.Figure()
    for d in list(DISEASE_ZH):
        if d not in diseases_in_df:
            continue
        sub = cc[cc["disease"] == d].set_index("hospital_name")
        fig.add_trace(go.Bar(
            y=ordered, orientation="h",
            x=[sub.loc[h, "count"] if h in sub.index else 0 for h in ordered],
            name=f"{DISEASE_EMOJI[d]} {DISEASE_ZH[d]}",
            marker_color=DISEASE_COLORS[d],
            hovertemplate="%{y}：%{x} 例<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        title=dict(text=f"通報院所前 {top_n} 名", font_size=14),
        xaxis_title="案例數",
        height=max(380, len(ordered) * 22 + 80),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=_bar_legend(),
        margin=dict(l=130, r=20, t=60, b=40),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.08)")
    return fig


def make_age_chart(df: pd.DataFrame) -> go.Figure:
    """各疾病年齡分布 Box Plot"""
    if df.empty or "age" not in df.columns:
        return go.Figure()
    fig = go.Figure()
    for d in list(DISEASE_ZH):
        ages = df[df["disease"] == d]["age"].dropna()
        if ages.empty:
            continue
        fig.add_trace(go.Box(
            y=ages, name=f"{DISEASE_EMOJI[d]} {DISEASE_ZH[d]}",
            marker_color=DISEASE_COLORS[d],
            boxmean="sd",
            hovertemplate="年齡：%{y} 歲<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text="各疾病年齡分布", font_size=14),
        yaxis_title="年齡（歲）",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        height=300, margin=dict(l=50, r=20, t=50, b=40),
        showlegend=False,
    )
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    return fig


def make_symptom_chart(df: pd.DataFrame, top_n: int = 12) -> go.Figure:
    """主訴症狀排行，依疾病分色堆疊"""
    if df.empty or "symptoms_list" not in df.columns:
        return go.Figure()
    # 先找全局 top_n 症狀作為 y 軸順序
    all_syms = [s for row in df["symptoms_list"] for s in row]
    if not all_syms:
        return go.Figure()
    top_syms = [s for s, _ in Counter(all_syms).most_common(top_n)]
    top_syms_ordered = list(reversed(top_syms))  # 由少到多，橫條圖由下到上

    fig = go.Figure()
    for disease in list(DISEASE_ZH):
        sub = df[df["disease"] == disease]
        if sub.empty:
            continue
        disease_syms = [s for row in sub["symptoms_list"] for s in row]
        cnt = Counter(disease_syms)
        fig.add_trace(go.Bar(
            y=top_syms_ordered,
            x=[cnt.get(s, 0) for s in top_syms_ordered],
            name=f"{DISEASE_EMOJI[disease]} {DISEASE_ZH[disease]}",
            orientation="h",
            marker_color=DISEASE_COLORS[disease],
            hovertemplate="%{y}：%{x} 次<extra></extra>",
        ))

    fig.update_layout(
        barmode="stack",
        title=dict(text=f"主訴症狀 Top {top_n}（依疾病分色）", font_size=14),
        xaxis_title="出現次數",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        height=340, margin=dict(l=90, r=20, t=50, b=40),
        legend=_bar_legend(),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    return fig


# ── Phase B：通報記錄載入 ─────────────────────────────────────────────────────

@st.cache_data(ttl=14)
def load_submissions(db_path: str) -> pd.DataFrame:
    if not os.path.exists(db_path):
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "submissions" not in tables:
                return pd.DataFrame()
            df = pd.read_sql_query(
                """
                SELECT s.id, s.case_id, s.bundle_id, s.task_id, s.task_status,
                       s.doc_ref_id, s.comm_id, s.submitted_at, s.ack_at,
                       s.response, s.note,
                       COALESCE(s.retry_count, 0) AS retry_count,
                       c.patient_name, c.disease, c.county, c.status AS case_status
                FROM submissions s
                LEFT JOIN cases c ON s.case_id = c.id
                ORDER BY s.submitted_at DESC
                """,
                conn,
            )
        if df.empty:
            return df
        df["submitted_at"] = pd.to_datetime(df["submitted_at"], utc=True, errors="coerce")
        df["ack_at"]       = pd.to_datetime(df["ack_at"],       utc=True, errors="coerce")
        df["sub_date"]     = df["submitted_at"].dt.tz_convert("Asia/Taipei").dt.date
        return df
    except Exception:
        return pd.DataFrame()


# ── MedMorph 工作流程圖 ────────────────────────────────────────────────────────

def pipeline_html() -> str:
    """G1→G5 整體 Pipeline HTML（取代 Plotly 以避免 axref 版本相容問題）"""
    boxes = [
        ("G1",    "病患對話",              "#5C6BC0", "第一組"),
        ("G2",    "FHIR 資料庫",           "#1565C0", "第二組"),
        ("G3",    "CQL 決策引擎",          "#0277BD", "第三組"),
        ("G4",    "群聚分析",              "#00838F", "第四組"),
        ("G5 ★",  "自動通報<br>公衛儀表板", "#C62828", "第五組（本組）"),
    ]
    items = []
    for i, (tag, label, color, sub) in enumerate(boxes):
        last = i == len(boxes) - 1
        border = "border:3px solid #FFD700;box-shadow:0 0 14px rgba(255,215,0,0.35);" if last else "border:1px solid rgba(255,255,255,0.2);"
        items.append(
            f"<div style='background:{color};color:white;border-radius:10px;"
            f"padding:12px 16px;text-align:center;min-width:96px;{border}'>"
            f"<div style='font-size:1.05rem;font-weight:700'>{tag}</div>"
            f"<div style='font-size:0.8rem;margin-top:3px;opacity:0.9'>{label}</div>"
            f"<div style='font-size:0.68rem;margin-top:5px;opacity:0.6'>{sub}</div>"
            f"</div>"
        )
        if not last:
            items.append("<div style='font-size:1.8rem;color:#aaa;padding:0 6px;align-self:center'>→</div>")
    return (
        "<div style='display:flex;align-items:stretch;justify-content:center;"
        "padding:10px 4px;gap:0;flex-wrap:nowrap'>"
        + "".join(items) +
        "</div>"
    )


def sequence_html() -> str:
    """MedMorph 通報序列 HTML 表格（Phase A/B/C 標注）"""
    E = {
        "FHIR/CQL":    "#1565C0",
        "MedMorph引擎": "#C62828",
        "eICR產生器":   "#2E7D32",
        "SQLite/儀表板": "#E65100",
        "NSSP":         "#6A1B9A",
    }

    def badge(name: str) -> str:
        c = E.get(name, "#888")
        return (f"<span style='background:{c};color:white;padding:2px 7px;"
                f"border-radius:4px;font-size:0.72rem;white-space:nowrap'>{name}</span>")

    phases = [
        ("Phase A　觸發與產生", "#EBF5FB", [
            ("FHIR/CQL",    "MedMorph引擎",  "→", "① Condition (suspected) 偵測，PlanDefinition 觸發"),
            ("MedMorph引擎", "eICR產生器",    "→", "② 啟動 eICR 建立流程"),
            ("eICR產生器",   "MedMorph引擎",  "←", "③ FHIR R4 Bundle 回傳"),
        ]),
        ("Phase B　送出與追蹤", "#EAFAF1", [
            ("MedMorph引擎", "SQLite/儀表板", "→", "④ 案例寫入 SQLite DB"),
            ("MedMorph引擎", "",              "↺", "⑤ Task (requested) 建立"),
            ("MedMorph引擎", "NSSP",          "→", "⑥ POST eICR → NSSP（Task: in-progress）"),
            ("NSSP",         "MedMorph引擎",  "←", "⑦ Acknowledgement 回傳"),
            ("MedMorph引擎", "",              "↺", "⑧ Task (completed) + Communication 建立"),
        ]),
        ("Phase C　狀態更新",   "#FEF9E7", [
            ("MedMorph引擎", "SQLite/儀表板", "→", "⑨ DocumentReference 版本歷史記錄"),
            ("SQLite/儀表板", "",             "↺", "⑩ 儀表板自動刷新（每 15 秒）"),
        ]),
    ]

    rows = []
    for ph_label, ph_bg, msgs in phases:
        ph_color = {"A": "#1565C0", "B": "#2E7D32", "C": "#E65100"}.get(ph_label[6], "#888")
        rows.append(
            f"<tr><td colspan='4' style='background:{ph_bg};padding:5px 12px;"
            f"border-left:4px solid {ph_color};font-size:0.79rem;font-weight:700;color:#1a1a1a'>"
            f"{ph_label}</td></tr>"
        )
        for src, dst, arrow, msg in msgs:
            rows.append(
                f"<tr style='border-bottom:1px solid #eee;background:white'>"
                f"<td style='padding:6px 10px'>{badge(src)}</td>"
                f"<td style='padding:6px 4px;text-align:center;font-size:1.1rem;color:#555'>{arrow}</td>"
                f"<td style='padding:6px 10px'>{badge(dst) if dst else ''}</td>"
                f"<td style='padding:6px 14px;font-size:0.82rem;color:#111;font-weight:500'>{msg}</td>"
                f"</tr>"
            )

    return (
        "<div style='background:white;border-radius:8px;overflow:hidden;"
        "border:1px solid #ddd;margin-top:4px'>"
        "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
        "<thead><tr style='background:#2C3E50;color:white'>"
        "<th style='padding:8px 10px;text-align:left;font-size:0.8rem;white-space:nowrap'>發送方</th>"
        "<th style='padding:8px 4px;width:28px'></th>"
        "<th style='padding:8px 10px;text-align:left;font-size:0.8rem;white-space:nowrap'>接收方</th>"
        "<th style='padding:8px 14px;text-align:left;font-size:0.8rem'>訊息 / 動作</th>"
        "</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody>"
        "</table></div>"
    )


# ── 主頁面 ─────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="傳染病即時公衛儀表板",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    ss = st.session_state
    is_viewing = "eicr_case" in ss
    st_autorefresh(interval=REFRESH_INTERVAL_MS, key="auto_refresh")

    st.markdown("""
    <style>
    /* ═══ 全頁固定於 viewport ═══ */
    html { overflow-y: hidden !important; }
    .main .block-container {
        padding-top: 0.6rem !important;
        padding-bottom: 0 !important;
        max-height: calc(100vh - 58px) !important;
        overflow: hidden !important;
    }

    /* ═══ KPI 卡片 ═══ */
    .metric-card {
        border-radius:10px; padding:10px 14px; color:white;
        text-align:center; box-shadow:0 3px 8px rgba(0,0,0,0.1);
        background:linear-gradient(135deg,#1e3a5f,#2d6a9f);
    }
    .metric-value { font-size:2.1rem; font-weight:700; line-height:1; }
    .metric-label { font-size:0.85rem; opacity:0.85; margin-top:3px; }
    .metric-sub   { font-size:0.72rem; opacity:0.6;  margin-top:3px; }

    /* ═══ 地圖模式 Segmented Control ═══ */
    div[data-testid="stSegmentedControl"] {
        gap: 8px !important;
        padding: 2px 0 !important;
    }
    div[data-testid="stSegmentedControl"] button {
        min-height: 46px !important;
        font-size: 1.0rem !important;
        font-weight: 600 !important;
        padding: 0 20px !important;
        border-radius: 10px !important;
        transition: all 0.18s ease !important;
    }

    /* ═══ Tab 按鈕 ═══ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px; background: transparent;
        border-bottom: 2px solid #E0E6F0;
        padding-bottom: 0; margin-bottom: 0;
        /* 先讓 tab 自動縮排；真的塞不下才 scroll（不顯示捲動列） */
        overflow-x: auto !important;
        scrollbar-width: none !important;
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
        display: none !important;
    }
    /* 隱藏 baseweb 自動產生的左右 overflow 箭頭 */
    .stTabs [data-baseweb="tab-list"] > button[aria-label],
    .stTabs [data-baseweb="tab-list"] > div > button[aria-label] {
        display: none !important;
    }
    .stTabs [data-baseweb="tab"] {
        height: 44px;
        /* 取消固定最小寬，允許 flex 縮小 */
        min-width: 0 !important;
        flex: 1 1 auto !important;
        /* padding 跟隨視窗寬度等比縮小，最小 6px，最大 16px */
        padding: 0 clamp(6px, 1.4vw, 16px) !important;
        background: #F0F4FA; border-radius: 10px 10px 0 0;
        border: 1.5px solid #D0DBF0; border-bottom: none;
        /* 字型隨視窗等比縮小，最小 0.68rem，最大 0.95rem */
        font-size: clamp(0.68rem, 1.3vw, 0.95rem) !important;
        font-weight: 600 !important;
        color: #4A6FA5 !important; transition: background 0.2s, color 0.2s;
        white-space: nowrap !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: #E3EBF8; color: #003F87 !important;
    }
    .stTabs [aria-selected="true"] {
        background: white !important; color: #003F87 !important;
        border-color: #003F87 #D0DBF0 white !important;
        border-bottom: 2px solid white !important;
        box-shadow: 0 -2px 8px rgba(0,63,135,0.08);
    }
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 8px !important; overflow: hidden !important;
    }

    /* ═══ 通報單按鈕：emoji 置中 ═══ */
    [data-testid="stButton"] > button {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
        overflow: hidden !important;
    }
    [data-testid="stButton"] > button p {
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.2 !important;
        text-align: center !important;
        width: 100% !important;
        overflow: hidden !important;
        white-space: nowrap !important;
    }
    </style>""", unsafe_allow_html=True)

    db_path_val   = ss.get("cfg_db_path",   DB_PATH)
    days_val      = ss.get("cfg_days_range", 35)
    hospital_name = ss.get("cfg_hospital",  "測試醫院")

    # ── 頂部標題 ──────────────────────────────────────────────────────────────
    h_left, h_mid, h_right = st.columns([5, 2, 1])
    with h_left:
        st.markdown(
            "<h3 style='margin:0;padding:0;line-height:1.2'>🏥 傳染病即時公衛儀表板</h3>"
            "<p style='margin:0;font-size:0.78rem;color:#888'>"
            "MedMorph · FHIR R4 · HL7 eICR · NTU 智慧醫療期末專題 第五組</p>",
            unsafe_allow_html=True,
        )
    with h_mid:
        now_tpe = datetime.now(TZ_TPE)
        st.markdown(
            f"<div style='text-align:right;padding-top:4px;"
            f"font-size:0.82rem;color:#999'>⏱ 每 {REFRESH_INTERVAL_MS//1000}s 刷新　"
            f"{now_tpe.strftime('%H:%M:%S')} (TPE)</div>",
            unsafe_allow_html=True,
        )
    with h_right:
        if st.button("🔄 刷新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    df_all = load_cases(db_path_val)
    df = df_all

    # ── KPI 卡片 ──────────────────────────────────────────────────────────────
    today_tpe = datetime.now(TZ_TPE).date()

    def cnt(d):  return 0 if df_all.empty else len(df_all[df_all["disease"] == d])
    def tc(d):
        if df_all.empty or "date" not in df_all.columns:
            return 0
        return len(df_all[(df_all["disease"] == d) & (df_all["date"] == today_tpe)])

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

    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

    if df_all.empty:
        st.warning("⚠️ 尚無資料。請先執行：\n```bash\nuv run python seed_data.py\n```")
        return

    # ── Tabs ──────────────────────────────────────────────────────────────────
    TAB_H  = 560
    LIST_H = TAB_H - 2

    tab_map, tab_trend, tab_cases, tab_demo, tab_track, tab_settings, tab_arch = st.tabs([
        "🗺️ 地理分布", "📈 趨勢分析", "📋 案例明細 & 通報單",
        "📊 人口統計", "📡 通報追蹤", "⚙️ 設定", "🔬 架構說明",
    ])

    # ── Tab 1：地理分布 ─────────────────────────────────────────────────────────
    with tab_map:
        with st.container(height=TAB_H, border=False):
            # ── 第一列：地圖模式（全寬 segmented control） ──────────────────
            _MAP_MODES = ["🗺️ 縣市累積分布", "🏥 通報院所熱點", "🏠 病患居住地（時間擴散）"]
            map_mode = st.segmented_control(
                "地圖類型",
                options=_MAP_MODES,
                default=_MAP_MODES[0],
                label_visibility="collapsed",
                key="map_mode_seg",
            ) or _MAP_MODES[0]

            # ── 第二列：疾病 toggle + 天數 slider ───────────────────────────
            _, tc1, tc2, tc3 = st.columns([4, 1, 1, 1])
            s_covid  = tc1.checkbox(f"{DISEASE_EMOJI['COVID-19']} COVID-19",
                                    value=False, key="map_d_covid")
            s_dengue = tc2.checkbox(f"{DISEASE_EMOJI['Dengue']} 登革熱",
                                    value=False, key="map_d_dengue")
            s_flu    = tc3.checkbox(f"{DISEASE_EMOJI['Influenza']} 流感",
                                    value=False, key="map_d_flu")

            _days_slider("map")

            sel_d = [d for d, s in [
                ("COVID-19", s_covid), ("Dengue", s_dengue), ("Influenza", s_flu)
            ] if s] or list(DISEASE_ZH)  # 若全取消，退回顯示全部

            # 依 checkbox + 日期範圍過濾（以 df_all 為基底）
            cutoff_date = (datetime.now(TZ_TPE) - timedelta(days=days_val)).date()
            base = df_all.copy()
            if "date" in base.columns:
                base = base[base["date"] >= cutoff_date]
            map_df = base[base["disease"].isin(sel_d)]

            MAP_H = 450

            if map_mode == "🗺️ 縣市累積分布":
                mc, bc = st.columns([3, 2])
                with mc:
                    st.plotly_chart(make_map_figure(map_df, "全部", MAP_H),
                                    use_container_width=True, config={"scrollZoom": True})
                with bc:
                    st.plotly_chart(make_county_bar(map_df), use_container_width=True)

            elif map_mode == "🏥 通報院所熱點":
                mc, ic = st.columns([3, 2])
                with mc:
                    st.plotly_chart(make_hospital_map(map_df, "全部", MAP_H),
                                    use_container_width=True, config={"scrollZoom": True})
                with ic:
                    st.plotly_chart(make_hospital_bar(map_df), use_container_width=True)

            else:  # 時間擴散
                st.plotly_chart(make_temporal_map(map_df, MAP_H),
                                use_container_width=True, config={"scrollZoom": True})
                st.caption(
                    "📍 點位為病患居住地 | 每種疾病顏色在自身時間範圍內正規化 "
                    "（深色=該疾病最近案例，淺色=最早案例）| 點選圖例切換顯示"
                )

    # ── Tab 2：趨勢分析 ─────────────────────────────────────────────────────────
    with tab_trend:
        with st.container(height=TAB_H, border=False):
            _days_slider("trend")
            st.plotly_chart(make_trend_figure(df_all, days_val, "全部"),
                            use_container_width=True)
            if "date" in df_all.columns:
                cutoff = (datetime.now(TZ_TPE) - timedelta(days=days_val)).date()
                summary = (
                    df_all[df_all["date"] >= cutoff]
                    .groupby("disease")
                    .agg(
                        案例數=("id", "count"),
                        疑似=("status", lambda x: (x == "suspected").sum()),
                        確診=("status", lambda x: (x == "confirmed").sum()),
                    )
                    .reset_index()
                )
                summary["disease"] = summary["disease"].map(
                    lambda d: f"{DISEASE_EMOJI.get(d,'')} {DISEASE_ZH.get(d,d)}"
                )
                summary.columns = ["疾病", f"近{days_val}天案例", "　疑似", "　確診"]
                st.dataframe(summary, use_container_width=True, hide_index=True)

    # ── Tab 3：案例明細 & 通報單 ─────────────────────────────────────────────────
    with tab_cases:
        # ── 日期區間 picker ────────────────────────────────────────────────────
        today_d = datetime.now(TZ_TPE).date()
        if "cases_date_range" not in ss:
            ss["cases_date_range"] = (today_d - timedelta(days=35), today_d)

        dr_col, sp_col, info_col = st.columns([2.8, 0.2, 1])
        with dr_col:
            picked = st.date_input(
                "📅 日期篩選範圍",
                value=ss["cases_date_range"],
                min_value=today_d - timedelta(days=730),
                max_value=today_d,
                format="YYYY/MM/DD",
                key="cases_dr",
            )
        # 日期 input 回傳可能為 tuple(start,end) 或 tuple(start,)
        if isinstance(picked, (list, tuple)) and len(picked) == 2:
            start_d, end_d = picked[0], picked[1]
            if (start_d, end_d) != ss["cases_date_range"]:
                ss["cases_date_range"] = (start_d, end_d)
                ss.pop("cases_show_n", None)   # 日期變動時重置翻頁
        else:
            start_d = picked[0] if picked else today_d
            end_d   = today_d

        if "date" in df.columns:
            df_cases = df[(df["date"] >= start_d) & (df["date"] <= end_d)].reset_index(drop=True)
        else:
            df_cases = df.reset_index(drop=True)

        show_n = ss.get("cases_show_n", 50)

        with info_col:
            st.markdown(
                f"<div style='padding:22px 0 0 8px;font-size:0.82rem;color:#888'>"
                f"共 <b style='color:#4A9EFF;font-size:1rem'>{len(df_cases)}</b> 筆　"
                f"顯示前 <b>{min(show_n, len(df_cases))}</b> 筆</div>",
                unsafe_allow_html=True,
            )

        if df_cases.empty:
            st.info("⚠️ 此日期範圍內沒有符合條件的案例。請調整日期範圍或至「⚙️ 設定」修改篩選條件。")
        else:
            CASES_LIST_H = TAB_H - 110
            list_col, view_col = st.columns([0.50, 0.50], gap="small")

            with list_col:
                with st.container(height=CASES_LIST_H, border=True):
                    COLS = [0.28, 0.90, 1.45, 0.90, 0.82, 0.58]
                    hcols = st.columns(COLS, gap="small")
                    for col, lbl in zip(hcols, ["#", "姓名", "疾病", "縣市", "狀態", "通報單"]):
                        extra = "text-align:center;white-space:nowrap;" if lbl == "通報單" else ""
                        col.markdown(
                            f"<b style='font-size:0.8rem;color:#555;{extra}'>{lbl}</b>",
                            unsafe_allow_html=True,
                        )
                    st.markdown("<hr style='margin:2px 0;border-color:#ddd'>",
                                unsafe_allow_html=True)

                    view_df = df_cases.head(show_n).reset_index(drop=True)
                    sel_idx = ss.get("eicr_index", -1)

                    for i, row in view_df.iterrows():
                        is_sel = (i == sel_idx)
                        hl     = ("border-left:3px solid #4A9EFF;padding-left:4px;"
                                  "color:#4A9EFF !important;" if is_sel else "")
                        rcols  = st.columns(COLS, gap="small")
                        d_zh   = (f"{DISEASE_EMOJI.get(row['disease'],'')} "
                                  f"{DISEASE_ZH.get(row['disease'], row['disease'])}")
                        s_zh   = STATUS_LABEL.get(row["status"], row["status"])

                        rcols[0].markdown(
                            f"<span style='color:#bbb;font-size:0.78rem;white-space:nowrap'>{i+1}</span>",
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
                        if rcols[5].button(
                            "📋", key=f"v_{i}",
                            help=f"查閱 {row['patient_name']} 的 eICR 通報單",
                            type="primary" if is_sel else "secondary",
                            use_container_width=True,
                        ):
                            ss["eicr_case"]  = df_cases.iloc[i]
                            ss["eicr_index"] = i
                            st.rerun()

                # ── 顯示更多 ────────────────────────────────────────────────
                if show_n < len(df_cases):
                    b1, b2 = st.columns(2)
                    if b1.button(
                        f"顯示更多（+50 筆）", use_container_width=True,
                        help=f"目前 {min(show_n, len(df_cases))} 筆，共 {len(df_cases)} 筆",
                    ):
                        ss["cases_show_n"] = show_n + 50
                        st.rerun()
                    if b2.button(
                        f"顯示全部（{len(df_cases)} 筆）", use_container_width=True,
                    ):
                        ss["cases_show_n"] = len(df_cases)
                        st.rerun()

            with view_col:
                if not is_viewing:
                    st.markdown(
                        f"<div style='height:{CASES_LIST_H}px;display:flex;"
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

                    t_col, c_col = st.columns([5, 1])
                    with t_col:
                        st.markdown(
                            f"**{DISEASE_EMOJI.get(sel['disease'],'')} "
                            f"{sel['patient_name']}**　{sel_d}　{sel_s}　{sel['county']}"
                        )
                    with c_col:
                        if st.button("✕ 關閉", key="close_eicr", use_container_width=True):
                            del ss["eicr_case"]
                            ss.pop("eicr_index", None)
                            st.rerun()

                    panel_h = CASES_LIST_H - 42
                    with st.container(height=panel_h, border=True):
                        eicr = parse_eicr(sel.get("eicr_path", ""))
                        if eicr is None:
                            st.error("⚠️ 找不到 eICR 檔案。")
                        else:
                            render_eicr_panel(eicr, hospital_name=hospital_name)

    # ── Tab 4：人口統計 ─────────────────────────────────────────────────────────
    with tab_demo:
        with st.container(height=TAB_H, border=False):
            _days_slider("demo")
            _cutoff_demo = (datetime.now(TZ_TPE) - timedelta(days=days_val)).date()
            df_demo = (df_all[df_all["date"] >= _cutoff_demo]
                       if "date" in df_all.columns else df_all)

            d1c, d2c = st.columns(2)
            with d1c:
                st.plotly_chart(make_age_chart(df_demo), use_container_width=True)

                # 性別分布
                if not df_demo.empty and "gender" in df_demo.columns:
                    gender_counts = df_demo["gender"].map(GENDER_LABEL).value_counts()
                    fig_g = go.Figure(go.Bar(
                        x=gender_counts.index.tolist(),
                        y=gender_counts.values.tolist(),
                        marker_color=["#4A9EFF", "#F06292", "#90A4AE"],
                        hovertemplate="%{x}：%{y} 例<extra></extra>",
                    ))
                    fig_g.update_layout(
                        title=dict(text="性別分布", font_size=14),
                        yaxis_title="案例數",
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        height=200, margin=dict(l=50, r=20, t=40, b=30),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_g, use_container_width=True)

            with d2c:
                st.plotly_chart(make_symptom_chart(df_demo), use_container_width=True)

                # 疑似 vs 確診比率
                if not df_demo.empty and "status" in df_demo.columns:
                    st.markdown("**疾病確診率**")
                    stat_tbl = (
                        df_demo.groupby(["disease", "status"])
                        .size().unstack(fill_value=0)
                        .reset_index()
                    )
                    for col in ["suspected", "confirmed"]:
                        if col not in stat_tbl.columns:
                            stat_tbl[col] = 0
                    stat_tbl["確診率"] = (
                        stat_tbl["confirmed"] /
                        (stat_tbl["suspected"] + stat_tbl["confirmed"]) * 100
                    ).round(1).astype(str) + "%"
                    stat_tbl["disease"] = stat_tbl["disease"].map(
                        lambda d: f"{DISEASE_EMOJI.get(d,'')} {DISEASE_ZH.get(d,d)}"
                    )
                    stat_tbl = stat_tbl.rename(columns={
                        "disease": "疾病", "suspected": "疑似", "confirmed": "確診"
                    })[["疾病", "疑似", "確診", "確診率"]]
                    st.dataframe(stat_tbl, use_container_width=True, hide_index=True)

    # ── Tab 5：通報追蹤 ─────────────────────────────────────────────────────────
    with tab_track:
        with st.container(height=TAB_H, border=False):
            _days_slider("track")
            st.markdown("#### 📋 通報送出記錄")
            sdf = load_submissions(db_path_val)
            if not sdf.empty and "submitted_at" in sdf.columns:
                _cutoff_track = datetime.now(TZ_TPE) - timedelta(days=days_val)
                sdf = sdf[sdf["submitted_at"] >= _cutoff_track]

            if sdf.empty:
                st.info("尚無送出記錄。請執行 seed_data.py 或等候 MedMorph 引擎產生新案例。")
            else:
                # 統計卡片
                total_s  = len(sdf)
                accepted = (sdf["response"] == "accepted").sum()
                rejected = (sdf["response"] == "error").sum()
                pending  = total_s - accepted - rejected
                sc1, sc2, sc3, sc4 = st.columns(4)
                for col, label, val, color in [
                    (sc1, "📤 累計送出",   total_s,  "#1565C0"),
                    (sc2, "✅ Accepted",  accepted, "#2E7D32"),
                    (sc3, "❌ Error",     rejected, "#C62828"),
                    (sc4, "⏳ Pending",   pending,  "#E65100"),
                ]:
                    col.markdown(
                        f"<div style='background:{color};color:white;border-radius:8px;"
                        f"padding:8px 12px;text-align:center'>"
                        f"<div style='font-size:1.5rem;font-weight:700'>{val}</div>"
                        f"<div style='font-size:0.8rem;opacity:0.85'>{label}</div></div>",
                        unsafe_allow_html=True,
                    )
                st.markdown("<div style='margin:6px 0'></div>", unsafe_allow_html=True)

                # 格式化表格
                def _sub_status(row) -> str:
                    r  = row.get("response", "")
                    ts = row.get("task_status", "")
                    rc = int(row.get("retry_count") or 0)
                    if r == "accepted":
                        return "✅ 已接受"
                    if r == "error":
                        return "🚫 失敗（超過重試上限）" if ts == "failed" else "❌ 被拒絕"
                    if r == "pending":
                        return f"🔄 重試中（{rc}/3）" if rc > 0 else "⏳ 待回應"
                    return r or ts

                display = sdf.head(50).copy()
                display["通報時間 (TPE)"] = display["submitted_at"].apply(
                    lambda r: r.astimezone(TZ_TPE).strftime("%m/%d %H:%M") if pd.notna(r) else ""
                )
                display["回應時間 (TPE)"] = display["ack_at"].apply(
                    lambda r: r.astimezone(TZ_TPE).strftime("%m/%d %H:%M") if pd.notna(r) else "—"
                )
                display["通報狀態"] = display.apply(_sub_status, axis=1)
                display["疾病"] = display["disease"].map(
                    lambda d: f"{DISEASE_EMOJI.get(d,'')} {DISEASE_ZH.get(d,d)}"
                )

                st.dataframe(
                    display[[
                        "patient_name", "疾病", "county",
                        "通報狀態",
                        "通報時間 (TPE)", "回應時間 (TPE)", "note",
                    ]].rename(columns={
                        "patient_name": "病患", "county": "縣市", "note": "備註"
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

                # 送出成功率趨勢（按日）
                if "sub_date" in sdf.columns and not sdf.empty:
                    daily = (sdf.groupby(["sub_date", "response"])
                               .size().unstack(fill_value=0).reset_index())
                    if "accepted" in daily.columns or "error" in daily.columns:
                        fig_s = go.Figure()
                        if "accepted" in daily.columns:
                            fig_s.add_trace(go.Bar(
                                x=daily["sub_date"], y=daily.get("accepted", 0),
                                name="✅ Accepted", marker_color="#2E7D32"))
                        if "error" in daily.columns:
                            fig_s.add_trace(go.Bar(
                                x=daily["sub_date"], y=daily.get("error", 0),
                                name="❌ Error", marker_color="#C62828"))
                        fig_s.update_layout(
                            barmode="stack",
                            title=dict(text="每日送出狀態", font_size=13),
                            height=180, margin=dict(l=40, r=10, t=35, b=30),
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)",
                            legend=dict(orientation="h", y=1.15, x=1, xanchor="right"),
                        )
                        st.plotly_chart(fig_s, use_container_width=True)

    # ── Tab 6：設定 ─────────────────────────────────────────────────────────────
    with tab_settings:
        with st.container(height=TAB_H, border=False):
            s1, s2 = st.columns(2)
            with s1:
                st.markdown("#### 🏥 通報院所")
                new_hospital = st.text_input("醫院名稱（顯示於通報單與 PDF）", value=hospital_name)
                st.markdown("#### 🗄️ 資料來源")
                new_db = st.text_input("SQLite 資料庫路徑", value=db_path_val)
                if st.button("✅ 套用設定", type="primary", use_container_width=True):
                    ss["cfg_hospital"] = new_hospital
                    ss["cfg_db_path"]  = new_db
                    st.cache_data.clear()
                    st.success("✅ 設定已套用！")
                    st.rerun()

            with s2:
                st.markdown("#### 📊 系統資訊")
                st.markdown(f"- **資料庫**：`{db_path_val}`")
                st.markdown(f"- **通報院所**：{hospital_name}")
                st.markdown(f"- **總案例數**：{total_all} 筆（今日 +{today_all}）")
                st.markdown(f"- **自動刷新**：每 {REFRESH_INTERVAL_MS//1000} 秒")
                st.markdown(f"- **時區**：Asia/Taipei（UTC+8）")
                st.markdown("- **標準**：FHIR R4 · MedMorph · HL7 eICR")
                st.markdown("---")
                st.markdown("#### 📌 使用說明")
                st.markdown(
                    "1. **地理分布** Tab → 切換三種地圖模式\n"
                    "   - 縣市累積：縣市層級泡泡圖\n"
                    "   - 通報院所：點出高通報量院所\n"
                    "   - 時間擴散：顏色深淺代表通報新舊\n"
                    "2. **趨勢分析** Tab → 每日新增折線圖\n"
                    "3. **案例明細** Tab → 點 📋 查閱 eICR 通報單\n"
                    "4. **人口統計** Tab → 年齡分布、症狀排行\n\n"
                    "| 疾病 | SNOMED-CT | LOINC |\n"
                    "|------|-----------|-------|\n"
                    "| COVID-19 | 840539006 | 94531-1 |\n"
                    "| 登革熱 | 38362002 | 86615-1 |\n"
                    "| 流感 | 57386000 | 92142-9 |"
                )

    # ── Tab 7：架構說明 ─────────────────────────────────────────────────────────
    with tab_arch:
        with st.container(height=TAB_H, border=False):
            st.markdown("#### 🔄 MedMorph 自動通報架構")
            st.markdown(pipeline_html(), unsafe_allow_html=True)

            st.markdown("#### 🔬 MedMorph 完整通報序列圖")
            seq_col, info_col = st.columns([3, 1])
            with seq_col:
                st.markdown(sequence_html(), unsafe_allow_html=True)
            with info_col:
                st.markdown("""
**Phase A — 觸發與產生**
- FHIR Condition 疑似病例觸發
- 自動查詢病患完整資料
- 產生 HL7 eICR Bundle

**Phase B — 送出與追蹤**
- Task 資源管理送出狀態
- POST eICR 至 NSSP 公衛端點
- Communication 記錄通知
- DocumentReference 版本歷史

**Phase C — 狀態更新**
- SQLite 持久化儲存
- Streamlit 儀表板即時顯示

---
**FHIR 資源清單**
- `Bundle` (type=document)
- `Composition`, `Patient`
- `Condition`, `Observation`
- `Encounter`, `Organization` ×2
- `Task`, `Communication`
- `DocumentReference`
""")

    st.markdown(
        "<p style='text-align:center;font-size:0.75rem;color:#ccc;margin:0'>"
        "NTU 智慧醫療期末專題 · 第五組 · FHIR R4 · MedMorph · HL7 eICR</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
