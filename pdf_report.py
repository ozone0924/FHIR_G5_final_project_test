"""
pdf_report.py — eICR 通報單 PDF 產生器
========================================
模擬衛生福利部疾病管制署「傳染病個案通報單」格式。
官方表單參考：https://www.cdc.gov.tw （衛福部疾管署通報系統）

使用：
    from pdf_report import generate_eicr_pdf
    pdf_bytes = generate_eicr_pdf(eicr_dict, hospital_name="台大醫院")
"""

import io
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ── 顏色定義（仿衛福部配色） ───────────────────────────────────────────────────
CDC_BLUE  = colors.HexColor("#003F87")
CDC_LIGHT = colors.HexColor("#E8F0F8")
GRAY_LINE = colors.HexColor("#CCCCCC")
DARK_GRAY = colors.HexColor("#333333")
MID_GRAY  = colors.HexColor("#666666")
WHITE     = colors.white

# ── 字型設定 ──────────────────────────────────────────────────────────────────
_FONT_NAME = "NotoTC"
_FONT_REGISTERED = False

_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Songti.ttc",    0),
    ("/System/Library/Fonts/STHeiti Light.ttc",           0),
    ("/System/Library/Fonts/STHeiti Medium.ttc",          0),
    ("/System/Library/Fonts/Supplemental/Kaiti.ttc",      0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("C:/Windows/Fonts/msyh.ttc",                         0),
    ("C:/Windows/Fonts/simsun.ttc",                       0),
]


def _ensure_font() -> str:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _FONT_NAME
    for path, idx in _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont(_FONT_NAME, path, subfontIndex=idx))
            # 讓 bold / italic 都指向同一字型（避免找不到 NotoTC-Bold 的錯誤）
            addMapping(_FONT_NAME, 0, 0, _FONT_NAME)
            addMapping(_FONT_NAME, 1, 0, _FONT_NAME)
            addMapping(_FONT_NAME, 0, 1, _FONT_NAME)
            addMapping(_FONT_NAME, 1, 1, _FONT_NAME)
            _FONT_REGISTERED = True
            return _FONT_NAME
        except Exception:
            continue
    _FONT_REGISTERED = True
    return "Helvetica"


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def _fmt_dt(iso: str) -> str:
    if not iso:
        return "未知"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return iso


def _para(text: str, font: str, size: int = 10,
          color=DARK_GRAY, align: str = "LEFT") -> Paragraph:
    alignment = {"LEFT": 0, "CENTER": 1, "RIGHT": 2}.get(align, 0)
    style = ParagraphStyle(
        "p",
        fontName=font,
        fontSize=size,
        textColor=color,
        alignment=alignment,
        leading=size * 1.45,
        wordWrap="CJK",
    )
    return Paragraph(str(text), style)


def _section_title(title: str, font: str, width: float) -> Table:
    data = [[_para(f"　{title}", font, 11, WHITE)]]
    tbl = Table(data, colWidths=[width])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CDC_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _data_table(rows: list[list[str]], font: str,
                col_widths: list[float]) -> Table:
    """label-value 交替底色欄位表"""
    def cell(text, is_label):
        return _para(text, font, 9 if is_label else 10,
                     MID_GRAY if is_label else DARK_GRAY)

    data = []
    for row in rows:
        data.append([cell(c, i % 2 == 0) for i, c in enumerate(row)])

    tbl = Table(data, colWidths=col_widths)
    styles = [
        ("GRID",          (0, 0), (-1, -1), 0.4, GRAY_LINE),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    for r in range(len(data)):
        styles.append(("BACKGROUND", (0, r), (-1, r),
                        CDC_LIGHT if r % 2 == 0 else WHITE))
    tbl.setStyle(TableStyle(styles))
    return tbl


# ── PDF 主函式 ────────────────────────────────────────────────────────────────

def generate_eicr_pdf(eicr: dict, hospital_name: str = "XX 醫院") -> bytes:
    """
    產生傳染病個案通報單 PDF。

    Parameters
    ----------
    eicr          parse_eicr() 的回傳值
    hospital_name 通報醫院名稱（顯示於通報單）
    """
    font = _ensure_font()
    buf  = io.BytesIO()
    W    = 170 * mm  # 可用頁寬（A4 扣邊距）

    col2 = [38 * mm, W / 2 - 38 * mm, 38 * mm, W / 2 - 38 * mm]

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=15 * mm, bottomMargin=20 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )

    story = []

    # ── 頁首 ─────────────────────────────────────────────────────────────────
    hdr = Table(
        [[
            _para("衛生福利部疾病管制署\nTaiwan CDC", font, 9, CDC_BLUE),
            _para("傳  染  病  個  案  通  報  單", font, 16, CDC_BLUE, "CENTER"),
            _para(f"通報日期\n{_fmt_dt(eicr['bundle_ts'])}", font, 9, MID_GRAY, "RIGHT"),
        ]],
        colWidths=[45 * mm, 85 * mm, 40 * mm],
    )
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(hdr)
    story.append(HRFlowable(width=W, thickness=2, color=CDC_BLUE))

    # 副標題列
    sub = Table(
        [[
            _para(f"通報醫療院所：{hospital_name}", font, 10, DARK_GRAY),
            _para(
                f"疾病別：{eicr['condition']['disease']}　　"
                f"通報流水號：{eicr['bundle_id'][:8].upper()}",
                font, 10, DARK_GRAY, "RIGHT",
            ),
        ]],
        colWidths=[W / 2, W / 2],
    )
    sub.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sub)
    story.append(HRFlowable(width=W, thickness=0.5, color=GRAY_LINE))
    story.append(Spacer(1, 4 * mm))

    # ── 壹、個案基本資料 ──────────────────────────────────────────────────────
    p = eicr["patient"]
    gender_zh = {"male": "男", "female": "女", "unknown": "未知"}.get(p["gender"], p["gender"])
    story.append(_section_title("壹、個案基本資料", font, W))
    story.append(_data_table([
        ["姓　　名", p["name"],       "性　　別", gender_zh],
        ["出生日期", p["birthdate"],  "居住地區", p["county"]],
        ["聯絡電話", p["phone"],      "身分證號", "（個資保護，略）"],
    ], font, col2))
    story.append(Spacer(1, 4 * mm))

    # ── 貳、疾病及臨床資訊 ────────────────────────────────────────────────────
    cond = eicr["condition"]
    clin_zh = {"suspected": "■ 疑似  □ 確定",
               "confirmed": "□ 疑似  ■ 確定"}.get(cond["clinical_status"], cond["clinical_status"])
    story.append(_section_title("貳、疾病及臨床資訊", font, W))
    story.append(_data_table([
        ["疾病名稱",   cond["disease"],       "臨床分類",   clin_zh],
        ["SNOMED-CT", cond["snomed"],         "發病日期",   _fmt_dt(cond["onset"])],
        ["確認狀態",   cond["ver_status"],    "通報記錄時間", _fmt_dt(cond["recorded"])],
    ], font, col2))
    # 症狀單行（整列寬）
    story.append(_data_table(
        [["主訴症狀", eicr["symptoms"] or "（未記載）"]],
        font, [38 * mm, W - 38 * mm],
    ))
    story.append(Spacer(1, 4 * mm))

    # ── 參、檢驗結果 ──────────────────────────────────────────────────────────
    obs = eicr["observation"]
    story.append(_section_title("參、檢驗結果", font, W))
    story.append(_data_table([
        ["LOINC 面板", obs["loinc"],       "面板說明",   obs["loinc_display"]],
        ["檢驗結果",   obs["result"] or "（待確認）", "結果判讀", "■ 陽性  □ 陰性  □ 未定"],
    ], font, col2))
    story.append(Spacer(1, 4 * mm))

    # ── 肆、就診紀錄 ──────────────────────────────────────────────────────────
    enc = eicr["encounter"]
    enc_status_zh = {"finished": "已完成", "in-progress": "進行中"}.get(enc["status"], enc["status"])
    story.append(_section_title("肆、就診紀錄", font, W))
    story.append(_data_table([
        ["就診時間",  _fmt_dt(enc["start"]),   "就診類型",  enc["enc_class"]],
        ["就診狀態",  enc_status_zh,           "通報院所",  hospital_name],
    ], font, col2))
    story.append(Spacer(1, 4 * mm))

    # ── 伍、通報醫療院所 ──────────────────────────────────────────────────────
    org = eicr["organization"]
    story.append(_section_title("伍、通報醫療院所", font, W))
    story.append(_data_table([
        ["院所名稱",  hospital_name,   "通報機構",  org["name"]],
        ["機構地址",  org["address"],  "機構網站",  org["url"]],
        ["通報醫師",  "（請簽章）",     "通報日期",  datetime.now().strftime("%Y/%m/%d")],
    ], font, col2))
    story.append(Spacer(1, 6 * mm))

    # ── 簽章欄 ────────────────────────────────────────────────────────────────
    sign = Table(
        [[
            _para("通報醫師簽章：________________________", font, 10, DARK_GRAY),
            _para("院所主管簽章：________________________", font, 10, DARK_GRAY),
            _para(f"通報日期：{datetime.now().strftime('%Y/%m/%d')}", font, 10, DARK_GRAY),
        ]],
        colWidths=[W / 3, W / 3, W / 3],
    )
    sign.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, GRAY_LINE),
        ("GRID",          (0, 0), (-1, -1), 0.5, GRAY_LINE),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(sign)
    story.append(Spacer(1, 4 * mm))

    # ── 頁尾 ─────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=0.5, color=GRAY_LINE))
    story.append(Spacer(1, 2 * mm))
    for line in [
        f"eICR Bundle ID：{eicr['bundle_id']}　　文件狀態：{eicr.get('comp_status','').upper()}",
        "本通報單由 MedMorph 自動通報引擎依據 HL7 FHIR R4 標準產生，格式參照衛生福利部傳染病個案通報單。",
        "NTU 智慧醫療期末專題 · 第五組 · MedMorph Reference Architecture · 僅供學術展示用途",
    ]:
        story.append(_para(line, font, 7, colors.HexColor("#999999")))

    doc.build(story)
    return buf.getvalue()
