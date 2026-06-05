"""
draw_architecture.py — G5 系統架構圖（乾淨版）
================================================
設計原則：
  • 僅用水平或垂直箭頭，禁止斜線穿越方塊
  • 標籤統一放在箭頭旁的空白區，不放在方塊內部
  • 移除 FHIR Server 獨立方塊（整合進 G2 / MedMorph 描述）

輸出：../G5_報告素材/architecture_diagram.png
執行：  uv run python draw_architecture.py
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.font_manager import FontProperties

# ── 字型 ─────────────────────────────────────────────────────────────────────
_FONTS = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]
_FONT = next((p for p in _FONTS if os.path.exists(p)), None)

def fp(size=10, bold=False):
    if _FONT:
        return FontProperties(fname=_FONT, size=size,
                              weight="bold" if bold else "normal")
    return FontProperties(size=size, weight="bold" if bold else "normal")

# ── 配色 ──────────────────────────────────────────────────────────────────────
BG        = "#F7F9FC"
BANNER    = "#003F87"
UP_BG     = "#EBF2FB"
G_FILL    = "#DDEAF8"
G_STR     = "#4472C4"
G2_FILL   = "#D6EAF8"
G2_STR    = "#1565C0"
G5_BG     = "#FFF8F0"
G5_HDR    = "#D84315"
G5_FILL   = "#FFF3E0"
ENG_FILL  = "#E8F5E9"
ENG_STR   = "#2E7D32"
DASH_FILL = "#FCE4EC"
DASH_STR  = "#880E4F"
CDC_FILL  = "#FFEBEE"
CDC_STR   = "#C62828"
STD_FILL  = "#FFFDE7"
STD_STR   = "#F57F17"
DGRAY     = "#333333"
MGRAY     = "#555555"
LGRAY     = "#888888"
WHITE     = "#FFFFFF"

# ── 繪圖工具 ─────────────────────────────────────────────────────────────────

def box(ax, x, y, w, h, fill, stroke, lw=1.8, r=0.012, alpha=1.0, z=3):
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle=f"round,pad=0,rounding_size={r}",
                       lw=lw, edgecolor=stroke, facecolor=fill,
                       alpha=alpha, zorder=z)
    ax.add_patch(p)

def t(ax, x, y, s, size=10, color=DGRAY, bold=False,
      ha="center", va="center", z=5):
    ax.text(x, y, s, ha=ha, va=va, zorder=z,
            fontproperties=fp(size, bold), color=color)

def hdr(ax, x, y, w, h, fill, txt, size=11):
    """有色標題帶"""
    box(ax, x, y, w, h, fill, fill, lw=0, r=0.010, z=4)
    t(ax, x + w/2, y + h/2, txt, size=size, color=WHITE, bold=True, z=5)

def body(ax, x, y, w, lines, size=9.2, gap=0.028):
    """方塊內文（由上往下排）"""
    for i, ln in enumerate(lines):
        t(ax, x + w/2, y - i * gap, ln, size=size, color=MGRAY)

def v_arrow(ax, x, y1, y2, color, lw=2.0, lbl="", lbl_x_off=0.012):
    """垂直箭頭（y1 → y2），標籤固定在箭頭右側"""
    ax.annotate("", xy=(x, y2), xytext=(x, y1),
                arrowprops=dict(
                    arrowstyle="->,head_width=0.020,head_length=0.022",
                    color=color, lw=lw,
                    connectionstyle="arc3,rad=0"),
                zorder=6)
    if lbl:
        lx = x + lbl_x_off
        ly = (y1 + y2) / 2
        t(ax, lx, ly, lbl, size=8.5, color=color, ha="left", z=7)

def h_arrow(ax, x1, x2, y, color, lw=2.0, lbl="", lbl_y_off=0.016):
    """水平箭頭（x1 → x2），標籤固定在箭頭上方"""
    ax.annotate("", xy=(x2, y), xytext=(x1, y),
                arrowprops=dict(
                    arrowstyle="->,head_width=0.018,head_length=0.020",
                    color=color, lw=lw,
                    connectionstyle="arc3,rad=0"),
                zorder=6)
    if lbl:
        lx = (x1 + x2) / 2
        ly = y + lbl_y_off
        ax.text(lx, ly, lbl, ha="center", va="center", zorder=7,
                fontproperties=fp(8.0), color=color,
                bbox=dict(boxstyle="round,pad=0.18", fc=WHITE, ec=color,
                          alpha=0.92, lw=0.8))

def step_arrow(ax, x1, y1, x2, y2, color, lw=2.0, lbl=""):
    """L 形箭頭：先水平再垂直（或相反），不穿越方塊"""
    # 畫兩段折線 + 最後一段有箭頭
    ax.plot([x1, x2, x2], [y1, y1, y2],
            color=color, lw=lw, zorder=6,
            solid_capstyle="round", solid_joinstyle="round")
    ax.annotate("", xy=(x2, y2), xytext=(x2, y2 + 0.001),
                arrowprops=dict(
                    arrowstyle="->,head_width=0.018,head_length=0.020",
                    color=color, lw=lw),
                zorder=6)
    if lbl:
        ax.text((x1 + x2) / 2, y1 + 0.015, lbl,
                ha="center", va="center", zorder=7,
                fontproperties=fp(8.0), color=color,
                bbox=dict(boxstyle="round,pad=0.18", fc=WHITE, ec=color,
                          alpha=0.92, lw=0.8))


# ── 主繪圖 ───────────────────────────────────────────────────────────────────

def draw():
    fig, ax = plt.subplots(figsize=(20, 13))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ─── 1. BANNER ───────────────────────────────────────────────────────────
    box(ax, 0.01, 0.925, 0.98, 0.062, BANNER, BANNER, lw=0, r=0.01)
    t(ax, 0.50, 0.962,
      "FHIR-Driven 傳染病自動通報與公衛監測系統  —  系統架構與組間對接",
      size=17, color=WHITE, bold=True)
    t(ax, 0.50, 0.937,
      "NTU 智慧醫療期末專題  ·  五組協作 Pipeline  ·  HL7 FHIR R4 / MedMorph / eICR",
      size=10, color="#BFD7FF")

    # ─── 2. 上游區域背景 ─────────────────────────────────────────────────────
    box(ax, 0.01, 0.735, 0.98, 0.175,
        UP_BG, "#90A4AE", lw=1, r=0.012, alpha=0.7, z=1)
    t(ax, 0.09, 0.902, "上游 Pipeline  G1 → G4",
      size=9, color="#37474F", bold=True, ha="center", va="top")

    # ─── 3. G1~G4 方塊 ───────────────────────────────────────────────────────
    gw, gh = 0.192, 0.115
    gy     = 0.753
    gxs    = [0.020, 0.222, 0.424, 0.626]
    HDR_H  = 0.040

    grps = [
        ("G1  病患問診層", G_FILL, G_STR,
         ["Rasa AI 對話機器人", "HL7 Questionnaire", "問診資料數位化收集"]),
        ("G2  FHIR 資料庫層", G2_FILL, G2_STR,
         ["HAPI FHIR Server (R4)", "Patient / Condition", "Observation 儲存 / API"]),
        ("G3  臨床決策層", G_FILL, G_STR,
         ["CQL 規則引擎", "PlanDefinition 觸發邏輯", "疑似病例判斷旗標"]),
        ("G4  群聚分析層", G_FILL, G_STR,
         ["Bulk FHIR Export / NDJSON", "NSSP 症候群分類", "時空異常偵測"]),
    ]
    for gx, (title, fill, stroke, lines) in zip(gxs, grps):
        box(ax, gx, gy, gw, gh, fill, stroke, lw=1.8)
        hdr(ax, gx, gy + gh - HDR_H, gw, HDR_H, stroke, title, size=10.5)
        body(ax, gx, gy + gh - HDR_H - 0.030, gw, lines, size=9.0, gap=0.026)

    # G1→G2→G3→G4 水平箭頭（箭頭在方塊之間的間隙中）
    data_lbl = [
        "QuestionnaireResponse",
        "Patient / Condition / Obs",
        "Condition (suspected)",
    ]
    for i in range(3):
        h_arrow(ax,
                gxs[i] + gw + 0.002, gxs[i+1] - 0.002,
                gy + gh / 2,
                color=G_STR, lw=2.0, lbl=data_lbl[i], lbl_y_off=0.020)

    # ─── 4. G5 核心區域（先定義以取得頂部 y） ───────────────────────────────
    G5_Y  = 0.330
    G5_H  = 0.370
    g5_top = G5_Y + G5_H

    box(ax, 0.01, G5_Y, 0.98, G5_H,
        G5_BG, G5_HDR, lw=2.5, r=0.015, alpha=0.7, z=2)
    hdr(ax, 0.01, G5_Y + G5_H - 0.048, 0.98, 0.048,
        G5_HDR, "G5  自動通報與公衛監測層  ——  本組負責範圍", size=12)

    # ─── 5. G4 → G5：L 形折線，繞出 G4 右側空白區再往下 ────────────────────
    # 路徑：G4 右邊中點 → 往右走到 x=0.845 → 垂直往下到 G5 頂部
    g4_right_x  = gxs[3] + gw          # G4 右邊界 = 0.818
    g4_mid_y    = gy + gh / 2           # G4 中高  ≈ 0.810
    turn_x      = 0.850                 # 折線轉折點 x（G4 右側空白）
    entry_x     = 0.200                 # 進入 G5 的 x（左半部空白，對應 MedMorph 正上方）

    # 畫折線：G4 右中 → 右側空白區 → 垂直往下 → 橫向進入 G5
    # 簡化：從 G4 底部中央往右到 turn_x，再垂直往下，再往左進入 G5 入口
    # 因 turn_x=0.850 在圖右空白區，不會穿越任何方塊

    # 線段
    ax.plot([g4_right_x, turn_x, turn_x, entry_x],
            [g4_mid_y, g4_mid_y, g5_top + 0.005, g5_top + 0.005],
            color=G2_STR, lw=2.5, zorder=6,
            solid_capstyle="round", solid_joinstyle="round")
    # 箭頭
    ax.annotate("", xy=(entry_x, g5_top), xytext=(entry_x, g5_top + 0.005),
                arrowprops=dict(
                    arrowstyle="->,head_width=0.020,head_length=0.022",
                    color=G2_STR, lw=2.5),
                zorder=6)
    # 標籤放在右側垂直段旁（turn_x 右邊空白處）
    ax.text(turn_x + 0.012, (g4_mid_y + g5_top) / 2,
            "Condition\n(clinicalStatus=suspected)\nHL7 FHIR R4",
            ha="left", va="center", zorder=7,
            fontproperties=fp(8.5), color=G2_STR,
            bbox=dict(boxstyle="round,pad=0.2", fc=WHITE,
                      ec=G2_STR, alpha=0.92, lw=0.8))

    # ─── 6. G5 三個子組件 ────────────────────────────────────────────────────
    IW = 0.270
    IH = 0.270
    IY = G5_Y + 0.025
    IHH = 0.042   # 子標題列高度
    ixs = [0.035, 0.360, 0.685]

    # MedMorph
    box(ax, ixs[0], IY, IW, IH, ENG_FILL, ENG_STR, lw=2)
    hdr(ax, ixs[0], IY + IH - IHH, IW, IHH, ENG_STR,
        "MedMorph 控制引擎", size=11)
    body(ax, ixs[0], IY + IH - IHH - 0.032, IW,
         ["自動通報控制中心",
          "輪詢 G2 FHIR Server",
          "偵測 suspected 案例",
          "觸發通報工作流程",
          "模擬送出至疾管署"],
         size=9.5, gap=0.040)

    # eICR
    box(ax, ixs[1], IY, IW, IH, ENG_FILL, ENG_STR, lw=2)
    hdr(ax, ixs[1], IY + IH - IHH, IW, IHH, ENG_STR,
        "eICR 電子通報文件", size=11)
    body(ax, ixs[1], IY + IH - IHH - 0.032, IW,
         ["HL7 eICR IG 標準格式",
          "FHIR R4 Document Bundle",
          "Condition  ( SNOMED-CT )",
          "Observation  ( LOINC )",
          "取代人工紙本通報"],
         size=9.5, gap=0.040)

    # Dashboard
    box(ax, ixs[2], IY, IW, IH, DASH_FILL, DASH_STR, lw=2)
    hdr(ax, ixs[2], IY + IH - IHH, IW, IHH, DASH_STR,
        "公衛即時儀表板", size=11)
    body(ax, ixs[2], IY + IH - IHH - 0.032, IW,
         ["Streamlit Web 介面",
          "KPI 即時計數",
          "台灣縣市地圖熱點",
          "時間趨勢分析",
          "eICR 通報單查閱 / PDF"],
         size=9.5, gap=0.040)

    # G5 內部水平箭頭（子組件之間，在方塊中間高度）
    arrow_y = IY + IH / 2
    h_arrow(ax,
            ixs[0] + IW + 0.002, ixs[1] - 0.002,
            arrow_y, color=ENG_STR, lw=2.0, lbl="案例資料")
    h_arrow(ax,
            ixs[1] + IW + 0.002, ixs[2] - 0.002,
            arrow_y, color=DASH_STR, lw=2.0, lbl="通報記錄")

    # ─── 7. G5 → 疾管署（垂直箭頭，從 G5 底部正中央往下） ───────────────────
    cdc_center_x = 0.40   # CDC 方塊中心 x（下方定義）
    # 使用 L 形：從 MedMorph 底部中央往下，再水平移到 CDC 中心上方
    medm_cx = ixs[0] + IW / 2
    v_arrow(ax, medm_cx, G5_Y, 0.250,      # G5 底部 → CDC 頂部
            color=CDC_STR, lw=2.5,
            lbl="eICR Bundle POST\n(HL7 eICR IG 格式)",
            lbl_x_off=0.014)

    # ─── 8. 疾管署方塊 ───────────────────────────────────────────────────────
    CDC_X, CDC_Y, CDC_W, CDC_H = 0.150, 0.055, 0.480, 0.185
    box(ax, CDC_X, CDC_Y, CDC_W, CDC_H, CDC_FILL, CDC_STR, lw=2.5)
    hdr(ax, CDC_X, CDC_Y + CDC_H - 0.040, CDC_W, 0.040,
        CDC_STR, "疾病管制署  通報端點  （外部系統）", size=11.5)
    body(ax, CDC_X, CDC_Y + CDC_H - 0.065, CDC_W,
         ["衛生福利部疾病管制署  Taiwan CDC",
          "傳染病個案通報系統  /  NSSP 接收端",
          "接收 eICR FHIR Document Bundle"],
         size=10.0, gap=0.038)

    # ─── 9. 適用標準方塊 ─────────────────────────────────────────────────────
    box(ax, 0.665, 0.055, 0.320, 0.185, STD_FILL, STD_STR, lw=1.5, r=0.010)
    hdr(ax, 0.665, 0.055 + 0.145, 0.320, 0.040,
        STD_STR, "適用標準規範", size=10.5)
    body(ax, 0.665, 0.055 + 0.120, 0.320,
         ["HL7 FHIR R4",
          "HL7 MedMorph IG",
          "HL7 eICR IG",
          "SNOMED-CT  ·  LOINC",
          "NSSP Framework"],
         size=9.2, gap=0.028)

    # ─── 10. 圖例 ────────────────────────────────────────────────────────────
    legend = [
        (G_FILL,    G_STR,    "上游 G1 / G3 / G4"),
        (G2_FILL,   G2_STR,   "G2 FHIR 資料層"),
        (G5_BG,     G5_HDR,   "G5 通報層（本組）"),
        (ENG_FILL,  ENG_STR,  "G5 內部模組"),
        (DASH_FILL, DASH_STR, "公衛儀表板"),
        (CDC_FILL,  CDC_STR,  "外部通報端點"),
    ]
    lx = 0.015
    for i, (fill, stroke, lbl) in enumerate(legend):
        px = lx + i * 0.160
        p = FancyBboxPatch((px, 0.018), 0.018, 0.012,
                           boxstyle="round,pad=0,rounding_size=0.003",
                           lw=1.2, edgecolor=stroke, facecolor=fill, zorder=4)
        ax.add_patch(p)
        ax.text(px + 0.022, 0.024, lbl, va="center",
                fontproperties=fp(8.5), color="#333", zorder=5)

    t(ax, 0.99, 0.006,
      "NTU 智慧醫療期末專題 · 第五組 · 2026",
      size=8, color="#BDBDBD", ha="right", va="bottom")

    # ─── 11. 儲存 ────────────────────────────────────────────────────────────
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "G5_報告素材")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "architecture_diagram.png")
    fig.savefig(out, dpi=180, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"✅  {os.path.abspath(out)}")
    print(f"   大小：{os.path.getsize(out)//1024} KB")


if __name__ == "__main__":
    draw()
