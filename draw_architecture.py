"""
draw_architecture.py — G5 系統架構圖（簡潔版）
================================================
專注於整體架構、組間對接與資料交換，不展示實作細節。
輸出至上層 G5_報告素材/ 資料夾（不上傳 GitHub）。

  uv run python draw_architecture.py
"""

import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.font_manager import FontProperties

# ── 字型 ─────────────────────────────────────────────────────────────────────
_FONTS = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]
_FONT = next((p for p in _FONTS if os.path.exists(p)), None)

def fp(size=11, bold=False):
    if _FONT:
        return FontProperties(fname=_FONT, size=size,
                              weight="bold" if bold else "normal")
    return FontProperties(size=size, weight="bold" if bold else "normal")

# ── 配色 ──────────────────────────────────────────────────────────────────────
BG       = "#F7F9FC"
BANNER   = "#003F87"
UP_AREA  = "#E9F0FA"
G_STROKE = "#4A7BC2"
G_FILL   = "#DDEAF8"
G5_AREA  = "#FFF8F0"
G5_STROKE= "#D84315"
G5_FILL  = "#FFF3E0"
INT_FILL = "#E8F5E9"
INT_STR  = "#2E7D32"
DASH_FILL= "#FCE4EC"
DASH_STR = "#880E4F"
CDC_FILL = "#FFEBEE"
CDC_STR  = "#B71C1C"
FHIR_FILL= "#E3F2FD"
FHIR_STR = "#1565C0"
ARR_UP   = "#4A7BC2"
ARR_G5   = "#D84315"
ARR_DATA = "#1565C0"
DGRAY    = "#37474F"
WHITE    = "#FFFFFF"

# ── 工具 ─────────────────────────────────────────────────────────────────────

def rbox(ax, x, y, w, h, fill, stroke, lw=1.8, r=0.015, alpha=1.0, z=3):
    p = FancyBboxPatch((x,y), w, h,
                       boxstyle=f"round,pad=0,rounding_size={r}",
                       linewidth=lw, edgecolor=stroke, facecolor=fill,
                       alpha=alpha, zorder=z)
    ax.add_patch(p)

def txt(ax, x, y, s, size=10, color="#212121", bold=False,
        ha="center", va="center", z=5):
    ax.text(x, y, s, ha=ha, va=va, zorder=z,
            fontproperties=fp(size, bold), color=color)

def arrow(ax, x1, y1, x2, y2, color=ARR_UP, lw=2.2,
          label="", lpos="mid", rad=0.0):
    ax.annotate("",
        xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="->,head_width=0.022,head_length=0.025",
            color=color, lw=lw,
            connectionstyle=f"arc3,rad={rad}",
        ), zorder=6)
    if label:
        if lpos == "mid":
            lx, ly = (x1+x2)/2, (y1+y2)/2
        elif lpos == "right":
            lx, ly = max(x1,x2)+0.01, (y1+y2)/2
        else:
            lx, ly = (x1+x2)/2, (y1+y2)/2 + 0.018
        ax.text(lx, ly, label, ha="center", va="center", zorder=7,
                fontproperties=fp(8.5), color=color,
                bbox=dict(boxstyle="round,pad=0.2", fc="white",
                          ec=color, alpha=0.92, lw=0.9))

def hdiv(ax, x, y, w, color, lw=0.8, label=""):
    ax.plot([x, x+w], [y, y], color=color, lw=lw,
            linestyle="--", alpha=0.5, zorder=2)
    if label:
        ax.text(x+0.005, y+0.005, label, fontproperties=fp(8, True),
                color=color, va="bottom", alpha=0.7, zorder=3)


# ── 主繪圖 ───────────────────────────────────────────────────────────────────

def draw():
    fig, ax = plt.subplots(figsize=(20, 14))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")

    # ────────────────────────────────────────────────────────────────────────
    # 1. BANNER
    # ────────────────────────────────────────────────────────────────────────
    rbox(ax, 0.01, 0.93, 0.98, 0.06, BANNER, BANNER, lw=0, r=0.01)
    txt(ax, 0.5, 0.966,
        "FHIR-Driven 傳染病自動通報與公衛監測系統  —  系統架構與組間對接",
        size=17, color="white", bold=True)
    txt(ax, 0.5, 0.942,
        "NTU 智慧醫療期末專題  ·  五組協作 Pipeline  ·  HL7 FHIR R4 / MedMorph / eICR",
        size=10, color="#BFD7FF")

    # ────────────────────────────────────────────────────────────────────────
    # 2. 上游四組（左→右 横向 Pipeline）
    # ────────────────────────────────────────────────────────────────────────
    rbox(ax, 0.01, 0.72, 0.98, 0.185,
         UP_AREA, "#90A4AE", lw=1, r=0.012, alpha=0.7, z=1)
    txt(ax, 0.085, 0.898, "上游 Pipeline  G1 → G4",
        size=9, color="#37474F", bold=True, ha="center")

    gw, gh, gy = 0.195, 0.115, 0.745
    gxs = [0.025, 0.245, 0.465, 0.685]

    groups = [
        ("G1\n病患問診層",
         "Rasa 對話 AI\nHL7 Questionnaire\n問診資料數位化",
         G_FILL, G_STROKE),
        ("G2\nFHIR 資料庫層",
         "HAPI FHIR Server\nPatient / Condition\nObservation 儲存",
         FHIR_FILL, FHIR_STR),
        ("G3\n臨床決策層",
         "CQL 規則引擎\nPlanDefinition\n疑似病例判斷",
         G_FILL, G_STROKE),
        ("G4\n群聚分析層",
         "Bulk FHIR Export\nNSSP 症候群分類\n時空異常偵測",
         G_FILL, G_STROKE),
    ]

    for gx, (title, body, fill, stroke) in zip(gxs, groups):
        rbox(ax, gx, gy, gw, gh, fill, stroke, lw=2)
        # 標題底色
        rbox(ax, gx, gy+gh-0.038, gw, 0.038, stroke, stroke, lw=0, r=0.01, z=4)
        txt(ax, gx+gw/2, gy+gh-0.019, title,
            size=11, color="white", bold=True)
        for i, line in enumerate(body.split("\n")):
            txt(ax, gx+gw/2, gy+gh-0.065-i*0.025, line,
                size=9.5, color=DGRAY)

    # 組間箭頭 + 資料標籤
    data_labels = [
        "QuestionnaireResponse\n(FHIR R4)",
        "Patient / Condition\nObservation (FHIR R4)",
        "疑似病例旗標\nCondition (suspected)",
    ]
    for i in range(3):
        arrow(ax,
              gxs[i]+gw, gy+gh/2,
              gxs[i+1], gy+gh/2,
              color=ARR_UP, lw=2.2,
              label=data_labels[i], lpos="top")

    # ────────────────────────────────────────────────────────────────────────
    # 3. G4 → G5 連接箭頭（關鍵交接點）
    # ────────────────────────────────────────────────────────────────────────
    # 從 G4 中央往下到 G5 左上
    arrow(ax, gxs[3]+gw/2, gy, gxs[3]+gw/2, 0.695,
          color=ARR_DATA, lw=2.8,
          label="Condition (clinicalStatus=suspected)\nHL7 FHIR R4  →  G5 MedMorph 觸發", lpos="top")

    # ────────────────────────────────────────────────────────────────────────
    # 4. FHIR Server（G2 管理，G5 共用）
    # ────────────────────────────────────────────────────────────────────────
    rbox(ax, 0.855, 0.745, 0.13, 0.115, FHIR_FILL, FHIR_STR, lw=2)
    rbox(ax, 0.855, 0.821, 0.13, 0.039, FHIR_STR, FHIR_STR, lw=0, r=0.01, z=4)
    txt(ax, 0.92, 0.840, "HAPI FHIR Server",
        size=10, color="white", bold=True)
    txt(ax, 0.92, 0.800, "共用 API 端點", size=9, color=DGRAY)
    txt(ax, 0.92, 0.778, "G2 管理 · G5 讀取", size=8.5, color="#555")
    txt(ax, 0.92, 0.757, "RESTful API (R4)", size=8.5, color="#555")

    # G2 ↔ FHIR Server
    arrow(ax, gxs[1]+gw, gy+gh*0.65, 0.855, gy+gh*0.65,
          color=FHIR_STR, lw=1.5, label="管理 / CRUD", lpos="top")

    # ────────────────────────────────────────────────────────────────────────
    # 5. G5 核心區塊（我們組）
    # ────────────────────────────────────────────────────────────────────────
    rbox(ax, 0.01, 0.29, 0.98, 0.39,
         G5_FILL, G5_STROKE, lw=2.5, r=0.015, z=2)

    # G5 標頭
    rbox(ax, 0.01, 0.634, 0.98, 0.05, G5_STROKE, G5_STROKE, lw=0, r=0.015, z=3)
    txt(ax, 0.5, 0.659,
        "G5  自動通報與公衛監測層  ——  本組負責範圍",
        size=13, color="white", bold=True)

    # G5 內部三大組件
    # A. MedMorph 引擎
    rbox(ax, 0.04, 0.32, 0.27, 0.285, INT_FILL, INT_STR, lw=2)
    rbox(ax, 0.04, 0.570, 0.27, 0.038, INT_STR, INT_STR, lw=0, r=0.01, z=4)
    txt(ax, 0.175, 0.589, "MedMorph 控制引擎", size=11, color="white", bold=True)
    for i, line in enumerate([
        "自動通報控制中心",
        "輪詢 FHIR Server",
        "偵測 suspected 案例",
        "觸發通報工作流程",
        "模擬送出至疾管署",
    ]):
        txt(ax, 0.175, 0.545 - i*0.038, line, size=9.5, color=DGRAY)

    # B. eICR 電子通報
    rbox(ax, 0.365, 0.32, 0.27, 0.285, INT_FILL, INT_STR, lw=2)
    rbox(ax, 0.365, 0.570, 0.27, 0.038, INT_STR, INT_STR, lw=0, r=0.01, z=4)
    txt(ax, 0.5, 0.589, "eICR 電子通報文件", size=11, color="white", bold=True)
    for i, line in enumerate([
        "HL7 eICR IG 標準格式",
        "FHIR R4 Document Bundle",
        "Condition (SNOMED-CT)",
        "Observation (LOINC)",
        "取代人工紙本通報",
    ]):
        txt(ax, 0.5, 0.545 - i*0.038, line, size=9.5, color=DGRAY)

    # C. 公衛儀表板
    rbox(ax, 0.69, 0.32, 0.27, 0.285, DASH_FILL, DASH_STR, lw=2)
    rbox(ax, 0.69, 0.570, 0.27, 0.038, DASH_STR, DASH_STR, lw=0, r=0.01, z=4)
    txt(ax, 0.825, 0.589, "公衛即時儀表板", size=11, color="white", bold=True)
    for i, line in enumerate([
        "Streamlit Web 介面",
        "KPI 即時計數",
        "台灣縣市地圖熱點",
        "時間趨勢分析",
        "eICR 通報單查閱 / PDF",
    ]):
        txt(ax, 0.825, 0.545 - i*0.038, line, size=9.5, color=DGRAY)

    # G5 內部流向
    arrow(ax, 0.04+0.27, 0.462, 0.365, 0.462,
          color=INT_STR, lw=2.2, label="案例資料")
    arrow(ax, 0.365+0.27, 0.462, 0.69, 0.462,
          color=DASH_STR, lw=2.2, label="通報記錄")

    # FHIR Server → G5 MedMorph
    arrow(ax, 0.855, 0.745, 0.175, 0.605,
          color=FHIR_STR, lw=2, label="GET /Condition\n(poll every 10s)", rad=0.15)

    # ────────────────────────────────────────────────────────────────────────
    # 6. 疾管署端點（外部系統）
    # ────────────────────────────────────────────────────────────────────────
    rbox(ax, 0.3, 0.065, 0.40, 0.185, CDC_FILL, CDC_STR, lw=2.5)
    rbox(ax, 0.3, 0.212, 0.40, 0.038, CDC_STR, CDC_STR, lw=0, r=0.01, z=4)
    txt(ax, 0.50, 0.231, "疾病管制署  通報端點  （外部系統）",
        size=12, color="white", bold=True)
    for i, line in enumerate([
        "衛生福利部疾病管制署 Taiwan CDC",
        "傳染病個案通報系統  /  NSSP 接收端",
        "接收 eICR FHIR Document Bundle",
    ]):
        txt(ax, 0.50, 0.193 - i*0.036, line, size=10, color=DGRAY)

    # G5 MedMorph → CDC
    arrow(ax, 0.175, 0.32, 0.37, 0.25,
          color=CDC_STR, lw=2.5,
          label="eICR Bundle  (POST)\nHL7 eICR IG 格式通報", lpos="top")

    # ────────────────────────────────────────────────────────────────────────
    # 7. 標準規範 badge（右下角）
    # ────────────────────────────────────────────────────────────────────────
    rbox(ax, 0.72, 0.065, 0.265, 0.185, "#FFFDE7", "#F57F17", lw=1.5, r=0.01)
    txt(ax, 0.852, 0.228, "適用標準規範", size=9.5, color="#E65100", bold=True)
    for i, line in enumerate([
        "HL7 FHIR R4",
        "HL7 MedMorph IG",
        "HL7 eICR IG",
        "SNOMED-CT  ·  LOINC",
        "NSSP Framework",
    ]):
        txt(ax, 0.852, 0.200 - i*0.026, line, size=9, color=DGRAY)

    # ────────────────────────────────────────────────────────────────────────
    # 8. 圖例
    # ────────────────────────────────────────────────────────────────────────
    legend = [
        (G_FILL,    G_STROKE,  "上游 G1/G3/G4"),
        (FHIR_FILL, FHIR_STR,  "FHIR 資料層（G2）"),
        (G5_FILL,   G5_STROKE, "G5 通報層（本組）"),
        (INT_FILL,  INT_STR,   "G5 內部模組"),
        (DASH_FILL, DASH_STR,  "公衛儀表板"),
        (CDC_FILL,  CDC_STR,   "外部通報端點"),
    ]
    lx = 0.01
    for i, (fill, stroke, lbl) in enumerate(legend):
        px = lx + i * 0.16
        p = FancyBboxPatch((px, 0.022), 0.018, 0.012,
                           boxstyle="round,pad=0,rounding_size=0.003",
                           lw=1.2, edgecolor=stroke, facecolor=fill, zorder=4)
        ax.add_patch(p)
        ax.text(px+0.022, 0.028, lbl, va="center",
                fontproperties=fp(8.5), color="#333", zorder=5)

    txt(ax, 0.99, 0.008,
        "NTU 智慧醫療期末專題 · 第五組 · 2026",
        size=8, color="#BDBDBD", ha="right", va="bottom")

    # ────────────────────────────────────────────────────────────────────────
    # 9. 儲存
    # ────────────────────────────────────────────────────────────────────────
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "G5_報告素材")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "architecture_diagram.png")

    fig.savefig(out, dpi=180, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"✅ 架構圖已儲存：{os.path.abspath(out)}")
    print(f"   大小：{os.path.getsize(out)//1024} KB")


if __name__ == "__main__":
    draw()
