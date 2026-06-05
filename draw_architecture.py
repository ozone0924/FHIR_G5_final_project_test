"""
draw_architecture.py — G5 系統架構圖產生器
==============================================
執行：  uv run python draw_architecture.py
輸出：  architecture_diagram.png（2160x1440 px）
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from matplotlib.font_manager import FontProperties

# ── 中文字型 ──────────────────────────────────────────────────────────────────
_FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]
_FONT_PATH = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), None)

def fp(size=11, bold=False):
    if _FONT_PATH:
        return FontProperties(fname=_FONT_PATH, size=size,
                              weight="bold" if bold else "normal")
    return FontProperties(size=size, weight="bold" if bold else "normal")

# ── 配色 ──────────────────────────────────────────────────────────────────────
C = {
    "bg":       "#F2F6FC",
    "banner":   "#003F87",
    # 上游
    "up_area":  "#EBF1FA",
    "g14_bg":   "#DCE8F8", "g14_bd": "#5B8DD9",
    "g2_bg":    "#DAEAF8", "g2_bd":  "#1565C0",
    "g3_bg":    "#DCE8F8", "g3_bd":  "#5B8DD9",
    "fhir_bg":  "#D6EAF8", "fhir_bd":"#0D47A1",
    # G5 核心
    "core_area":"#FFF8F0",
    "eng_bg":   "#FFF0DC", "eng_bd": "#E65100",
    "eicr_bg":  "#E8F5E9", "eicr_bd":"#2E7D32",
    "bun_bg":   "#E0F7FA", "bun_bd": "#006064",
    "std_bg":   "#FFFDE7", "std_bd": "#F57F17",
    # 輸出
    "out_area": "#F3EEF9",
    "db_bg":    "#F3E5F5", "db_bd":  "#6A1B9A",
    "dash_bg":  "#FCE4EC", "dash_bd":"#880E4F",
    "pdf_bg":   "#FFF8E1", "pdf_bd": "#F57F17",
    "cdc_bg":   "#FFEBEE", "cdc_bd": "#B71C1C",
    # 通用
    "dark":     "#212121",
    "mid":      "#555555",
    "light":    "#888888",
    "white":    "#FFFFFF",
    "arr_main": "#37474F",
    "arr_fhir": "#0D47A1",
    "arr_eicr": "#2E7D32",
    "arr_db":   "#6A1B9A",
    "arr_cdc":  "#B71C1C",
}


# ── 繪圖工具 ──────────────────────────────────────────────────────────────────

def rect(ax, x, y, w, h, bg, bd, lw=1.5, radius=0.008, alpha=1.0, zorder=3):
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle=f"round,pad=0,rounding_size={radius}",
                       linewidth=lw, edgecolor=bd, facecolor=bg,
                       alpha=alpha, zorder=zorder)
    ax.add_patch(p)
    return p


def label(ax, x, y, text, size=10, color=C["dark"], bold=False,
          ha="center", va="center", zorder=4):
    ax.text(x, y, text, ha=ha, va=va,
            fontproperties=fp(size, bold), color=color, zorder=zorder)


def box(ax, x, y, w, h, lines, bg, bd,
        title_size=11.5, body_size=9, lw=1.6):
    """圓角色塊：第一行為標題（粗），後續為內文"""
    rect(ax, x, y, w, h, bg, bd, lw=lw)
    n = len(lines)
    if n == 0:
        return
    # 標題
    label(ax, x+w/2, y+h*(1 - 0.5/n),
          lines[0], size=title_size, color=bd, bold=True)
    # 內文
    for i, ln in enumerate(lines[1:]):
        label(ax, x+w/2, y+h*(1 - (i+1.5)/n),
              ln, size=body_size, color=C["mid"])


def arr(ax, x1, y1, x2, y2, color=C["arr_main"], lw=1.8,
        lbl="", lbl_side="top", rad=0.0, head=0.018):
    style = dict(arrowstyle=f"->,head_width={head},head_length={head*1.2}",
                 color=color, lw=lw,
                 connectionstyle=f"arc3,rad={rad}")
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=style, zorder=6)
    if lbl:
        mx = (x1+x2)/2 + rad*abs(y2-y1)*0.5
        my = (y1+y2)/2
        dy = 0.016 if lbl_side == "top" else -0.022
        ax.text(mx, my+dy, lbl, ha="center", va="center",
                fontproperties=fp(8.5), color=color, zorder=7,
                bbox=dict(boxstyle="round,pad=0.18", fc="white",
                          ec=color, alpha=0.9, lw=0.8))


# ── 主繪圖 ────────────────────────────────────────────────────────────────────

def draw():
    W, H = 24, 15
    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")

    # ── 頂部橫幅 ─────────────────────────────────────────────────────────────
    rect(ax, 0.01, 0.935, 0.98, 0.055, C["banner"], C["banner"], zorder=3)
    label(ax, 0.5, 0.968,
          "FHIR-Driven 傳染病自動通報與公衛監測系統  ——  完整架構圖",
          size=17, color="white", bold=True)
    label(ax, 0.5, 0.944,
          "NTU 智慧醫療期末專題  ·  第五組  ·  MedMorph 自動通報引擎 + HL7 eICR + Streamlit 公衛儀表板",
          size=10, color="#BFD7FF")

    # ── 區塊背景 ──────────────────────────────────────────────────────────────
    # 上游
    rect(ax, 0.01, 0.755, 0.98, 0.165,
         C["up_area"], "#90A4AE", lw=1, alpha=0.7, zorder=1)
    label(ax, 0.025, 0.912, "上游 Pipeline（G1 → G4）",
          size=9, color="#37474F", bold=True, ha="left", va="top")

    # G5 核心
    rect(ax, 0.01, 0.395, 0.98, 0.345,
         C["core_area"], C["eng_bd"], lw=1.5, alpha=0.6, zorder=1)
    label(ax, 0.025, 0.732, "G5  核心處理層",
          size=9, color=C["eng_bd"], bold=True, ha="left", va="top")

    # 輸出
    rect(ax, 0.01, 0.04, 0.98, 0.335,
         C["out_area"], "#7B1FA2", lw=1, alpha=0.5, zorder=1)
    label(ax, 0.025, 0.368, "輸出 / 呈現層",
          size=9, color="#4A148C", bold=True, ha="left", va="top")

    # ── 上游：G1 G2 G3 G4 ────────────────────────────────────────────────────
    gw, gh = 0.18, 0.10
    gy = 0.775
    gxs = [0.03, 0.225, 0.42, 0.615]

    defs = [
        (C["g14_bg"], C["g14_bd"],
         ["G1  病患問診介面",
          "Rasa AI 對話機器人",
          "HL7 Questionnaire",
          "問診資料結構化收集"]),
        (C["g2_bg"], C["g2_bd"],
         ["G2  FHIR Box",
          "HAPI FHIR Server (R4)",
          "Patient / Observation",
          "Condition Bundle 儲存"]),
        (C["g3_bg"], C["g3_bd"],
         ["G3  臨床決策支援",
          "CQL 規則引擎",
          "PlanDefinition 觸發",
          "suspected case 旗標"]),
        (C["g14_bg"], C["g14_bd"],
         ["G4  群聚分析",
          "Bulk FHIR / NDJSON",
          "NSSP 症候群分類",
          "異常偵測 / 熱點定位"]),
    ]
    for gx, (bg, bd, lines) in zip(gxs, defs):
        box(ax, gx, gy, gw, gh, lines, bg, bd)

    # G1→G2→G3→G4 箭頭
    for i in range(3):
        arr(ax, gxs[i]+gw, gy+gh/2, gxs[i+1], gy+gh/2,
            color=C["g14_bd"], lw=2.2)

    # FHIR Server（右側，共用）
    fhir_x = 0.83
    box(ax, fhir_x, gy, 0.155, gh,
        ["HAPI FHIR Server",
         "RESTful API",
         "GET /Condition",
         "?clinical-status=suspected",
         "POST /Bundle (eICR)"],
        C["fhir_bg"], C["fhir_bd"], title_size=11)

    # G4 → FHIR Server
    arr(ax, gxs[3]+gw, gy+gh*0.6, fhir_x, gy+gh*0.6,
        color=C["fhir_bd"], lw=2.2,
        lbl="Condition (suspected)")

    # G2 ↔ FHIR Server (Patient/Obs)
    arr(ax, gxs[1]+gw*0.5, gy+gh, fhir_x+0.077, gy+gh,
        color=C["g2_bd"], lw=1.5, rad=-0.3,
        lbl="FHIR CRUD")

    # ── G5 核心：MedMorph Engine ──────────────────────────────────────────────
    eng_x, eng_y, eng_w, eng_h = 0.03, 0.515, 0.28, 0.195
    box(ax, eng_x, eng_y, eng_w, eng_h,
        ["MedMorph Control Engine",
         "medmorph_engine.py",
         "MockFHIRPoller  /  RealFHIRPoller",
         "每 10 秒輪詢 suspected Condition",
         "process_case()  觸發通報序列",
         "simulate_report_submission()"],
        C["eng_bg"], C["eng_bd"], title_size=12, body_size=9.5)

    # FHIR Server → MedMorph
    arr(ax, fhir_x, gy+0.025, eng_x+eng_w, eng_y+eng_h*0.65,
        color=C["fhir_bd"], lw=2.2,
        lbl="GET /Condition (poll)", lbl_side="top")

    # ── eICR Generator ────────────────────────────────────────────────────────
    eicr_x, eicr_y, eicr_w, eicr_h = 0.36, 0.515, 0.27, 0.195
    box(ax, eicr_x, eicr_y, eicr_w, eicr_h,
        ["eICR Generator",
         "eicr_generator.py",
         "generate_eicr(patient_data)",
         "FHIR R4 Document Bundle",
         "save_eicr() → output/",
         "SNOMED-CT + LOINC 代碼"],
        C["eicr_bg"], C["eicr_bd"], title_size=12, body_size=9.5)

    # MedMorph → eICR Generator
    arr(ax, eng_x+eng_w, eng_y+eng_h/2, eicr_x, eicr_y+eicr_h/2,
        color=C["eng_bd"], lw=2.2, lbl="patient_data")

    # ── eICR Bundle 結構 ──────────────────────────────────────────────────────
    bun_x, bun_y, bun_w, bun_h = 0.685, 0.515, 0.295, 0.195
    box(ax, bun_x, bun_y, bun_w, bun_h,
        ["eICR  FHIR R4 Document Bundle",
         "Composition  ——  主文件頭 (eICR-IG)",
         "Patient          ——  病患基本資料",
         "Condition       ——  診斷 (SNOMED-CT)",
         "Observation   ——  檢驗 (LOINC)",
         "Encounter      ——  就診紀錄",
         "Organization  ——  通報機構（疾管署）"],
        C["bun_bg"], C["bun_bd"], title_size=11.5, body_size=9.5)

    # eICR Generator → Bundle
    arr(ax, eicr_x+eicr_w, eicr_y+eicr_h/2, bun_x, bun_y+bun_h/2,
        color=C["eicr_bd"], lw=2.2, lbl="建立 Bundle")

    # Bundle → FHIR Server (POST)
    arr(ax, bun_x+bun_w*0.5, bun_y+bun_h, fhir_x+0.077, gy,
        color=C["fhir_bd"], lw=1.8, rad=0.2,
        lbl="POST /Bundle", lbl_side="top")

    # ── SQLite DB ─────────────────────────────────────────────────────────────
    db_x, db_y, db_w, db_h = 0.03, 0.405, 0.20, 0.085
    box(ax, db_x, db_y, db_w, db_h,
        ["SQLite  data/cases.db",
         "TABLE cases  ( id, disease, county, eicr_path, … )"],
        C["db_bg"], C["db_bd"], title_size=10.5, body_size=9)

    arr(ax, eng_x+eng_w*0.35, eng_y, eng_x+eng_w*0.35-0.05, db_y+db_h,
        color=C["db_bd"], lw=1.8, lbl="INSERT case")

    # ── 標準規範 ──────────────────────────────────────────────────────────────
    std_x, std_y, std_w, std_h = 0.26, 0.405, 0.42, 0.085
    box(ax, std_x, std_y, std_w, std_h,
        ["適用國際標準規範",
         "HL7 FHIR R4  ·  HL7 MedMorph IG  ·  HL7 eICR IG  ·  SNOMED-CT  ·  LOINC  ·  NSSP"],
        C["std_bg"], C["std_bd"], title_size=10.5, body_size=9)

    # ── 輸出層：Streamlit Dashboard ───────────────────────────────────────────
    dash_x, dash_y, dash_w, dash_h = 0.03, 0.065, 0.44, 0.28
    box(ax, dash_x, dash_y, dash_w, dash_h,
        ["Streamlit  即時公衛儀表板",
         "dashboard.py  (http://localhost:8501)",
         "[ Tab 1 ]  地圖熱力圖  ——  各縣市泡泡分布（Plotly Mapbox）",
         "[ Tab 2 ]  趨勢折線圖  ——  近 N 天每日新增案例",
         "[ Tab 3 ]  案例明細表  ——  每列一鍵查閱 eICR 通報單",
         "[ Tab 4 ]  設定         ——  院所名稱、篩選條件、系統資訊",
         "KPI 卡片（COVID / 登革熱 / 流感）+ 今日新增",
         "查閱 eICR 時自動暫停刷新，關閉後恢復"],
        C["dash_bg"], C["dash_bd"], title_size=12, body_size=9.5)

    # SQLite → Dashboard
    arr(ax, db_x+db_w*0.6, db_y, dash_x+dash_w*0.35, dash_y+dash_h,
        color=C["db_bd"], lw=1.8,
        lbl="SELECT  (ttl 14s)")

    # ── PDF 通報單 ────────────────────────────────────────────────────────────
    pdf_x, pdf_y, pdf_w, pdf_h = 0.52, 0.065, 0.20, 0.28
    box(ax, pdf_x, pdf_y, pdf_w, pdf_h,
        ["PDF 通報單",
         "pdf_report.py",
         "reportlab + 宋體字型",
         "仿衛福部疾管署",
         "傳染病個案通報單格式",
         "壹  個案基本資料",
         "貳  疾病臨床資訊",
         "參  主訴症狀",
         "肆  檢驗結果",
         "伍  就診紀錄",
         "陸  通報醫療院所",
         "簽章欄 + eICR 頁尾"],
        C["pdf_bg"], C["pdf_bd"], title_size=11, body_size=9)

    # Dashboard → PDF
    arr(ax, dash_x+dash_w, dash_y+dash_h*0.55, pdf_x, pdf_y+pdf_h*0.55,
        color=C["pdf_bd"], lw=1.8, lbl="generate_eicr_pdf()")

    # eICR JSON → Dashboard (eicr_path)
    arr(ax, eicr_x+eicr_w*0.3, eicr_y, dash_x+dash_w*0.3, dash_y+dash_h,
        color=C["eicr_bd"], lw=1.8, rad=-0.15,
        lbl="parse_eicr()", lbl_side="top")

    # ── 疾管署通報端點 ────────────────────────────────────────────────────────
    cdc_x, cdc_y, cdc_w, cdc_h = 0.775, 0.065, 0.205, 0.28
    box(ax, cdc_x, cdc_y, cdc_w, cdc_h,
        ["疾管署通報端點",
         "衛生福利部疾病管制署",
         "Taiwan CDC",
         "(模擬 / 真實 NSSP)",
         "POST eICR Bundle",
         "傳染病個案通報系統",
         "https://www.cdc.gov.tw",
         "",
         "未來可整合：",
         "真實 API / NPHIES"],
        C["cdc_bg"], C["cdc_bd"], title_size=11, body_size=9.5)

    # MedMorph → CDC (simulate POST)
    arr(ax, eng_x+eng_w*0.8, eng_y, cdc_x+cdc_w*0.5, cdc_y+cdc_h,
        color=C["cdc_bd"], lw=2, rad=0.18,
        lbl="simulate_report_submission()")

    # Bundle → CDC (POST eICR)
    arr(ax, bun_x+bun_w*0.7, bun_y, cdc_x+cdc_w*0.8, cdc_y+cdc_h,
        color=C["cdc_bd"], lw=1.8, rad=0.1,
        lbl="POST eICR JSON")

    # ── 圖例 ──────────────────────────────────────────────────────────────────
    items = [
        (C["g14_bg"], C["g14_bd"], "上游 G1/G3/G4"),
        (C["g2_bg"],  C["g2_bd"],  "G2 FHIR Server"),
        (C["eng_bg"], C["eng_bd"], "MedMorph 引擎"),
        (C["eicr_bg"],C["eicr_bd"],"eICR 產生"),
        (C["bun_bg"], C["bun_bd"], "FHIR Bundle"),
        (C["db_bg"],  C["db_bd"],  "資料庫"),
        (C["dash_bg"],C["dash_bd"],"Streamlit 儀表板"),
        (C["cdc_bg"], C["cdc_bd"], "疾管署端點"),
    ]
    lx = 0.03
    for i, (bg, bd, lbl_t) in enumerate(items):
        px = lx + i * 0.121
        r = FancyBboxPatch((px, 0.022), 0.018, 0.012,
                           boxstyle="round,pad=0,rounding_size=0.002",
                           lw=1.2, edgecolor=bd, facecolor=bg, zorder=4)
        ax.add_patch(r)
        ax.text(px+0.022, 0.028, lbl_t, va="center",
                fontproperties=fp(8.5), color="#333", zorder=5)

    label(ax, 0.99, 0.008,
          "NTU 智慧醫療期末專題 · 第五組 · MedMorph + HL7 eICR + FHIR R4",
          size=8, color="#9E9E9E", ha="right", va="bottom")

    # ── 儲存 ──────────────────────────────────────────────────────────────────
    out = "architecture_diagram.png"
    fig.savefig(out, dpi=180, bbox_inches="tight",
                facecolor=C["bg"], edgecolor="none")
    plt.close(fig)
    sz = os.path.getsize(out)
    print(f"✅ 架構圖已儲存：{out}  ({sz//1024} KB)")


if __name__ == "__main__":
    draw()
