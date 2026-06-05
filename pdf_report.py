"""
pdf_report.py — eICR 通報單 PDF 產生器（黑白正式格式）
========================================================
採用 reportlab 內建 STSong-Light CID 字型，
無需外部字型檔，中文字完整顯示。

格式參照：衛生福利部疾病管制署 傳染病個案通報單（簡化版）
"""

import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle,
    Spacer, HRFlowable,
)
from reportlab.lib import colors

# ── 字型：STSong-Light 為 reportlab 內建 CJK CID 字型 ─────────────────────────
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

FONT  = "STSong-Light"
BLACK = colors.black
GRAY  = colors.HexColor("#444444")
LGRAY = colors.HexColor("#AAAAAA")
WHITE = colors.white

W = 170 * mm  # 頁面可用寬


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _fmt_dt(iso: str) -> str:
    if not iso:
        return "　"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return iso


def _p(text: str, size: int = 10, bold: bool = False,
       align: str = "LEFT") -> Paragraph:
    alignment = {"LEFT": 0, "CENTER": 1, "RIGHT": 2}.get(align, 0)
    style = ParagraphStyle(
        "p",
        fontName=FONT,
        fontSize=size,
        leading=size * 1.5,
        alignment=alignment,
        textColor=BLACK,
        wordWrap="CJK",
    )
    # bold 用底線模擬（CID 字型無粗體變體）
    txt = f"<u>{text}</u>" if bold else str(text)
    return Paragraph(txt, style)


def _section(title: str) -> list:
    """區段標題 + 分隔線"""
    return [
        Spacer(1, 4 * mm),
        _p(f"【{title}】", size=11, bold=True),
        HRFlowable(width=W, thickness=0.8, color=BLACK),
        Spacer(1, 1.5 * mm),
    ]


def _table(rows: list[list[str]], col_w: list[float]) -> Table:
    """欄位資料表（奇數欄位為 label，偶數為值）"""
    def cell(text: str, is_label: bool) -> Paragraph:
        return _p(text, size=9 if is_label else 10)

    data = [
        [cell(c, i % 2 == 0) for i, c in enumerate(row)]
        for row in rows
    ]
    tbl = Table(data, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.5, LGRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        # label 欄（0, 2, 4…）淺灰底
        ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
        ("BACKGROUND",    (2, 0), (2, -1), colors.HexColor("#F2F2F2")),
    ]))
    return tbl


# ── 主函式 ────────────────────────────────────────────────────────────────────

def generate_eicr_pdf(eicr: dict, hospital_name: str = "XX 醫院") -> bytes:
    """
    產生傳染病個案通報單 PDF（黑白正式格式）。

    Parameters
    ----------
    eicr          parse_eicr() 的回傳值
    hospital_name 通報醫院名稱
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=20 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )

    story = []
    col2 = [38 * mm, W / 2 - 38 * mm, 38 * mm, W / 2 - 38 * mm]

    # ── 表頭 ─────────────────────────────────────────────────────────────────
    header_data = [[
        _p("衛生福利部疾病管制署", size=9, align="LEFT"),
        _p("傳  染  病  個  案  通  報  單", size=16, bold=True, align="CENTER"),
        _p(f"通報日期：{_fmt_dt(eicr['bundle_ts'])}", size=9, align="RIGHT"),
    ]]
    hdr = Table(header_data, colWidths=[45 * mm, 85 * mm, 40 * mm])
    hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(hdr)
    story.append(HRFlowable(width=W, thickness=2, color=BLACK))

    # 副標題
    sub_data = [[
        _p(f"通報醫療院所：{hospital_name}", size=10),
        _p(
            f"疾病別：{eicr['condition']['disease']}　"
            f"通報流水號：{eicr['bundle_id'][:8].upper()}",
            size=10, align="RIGHT"
        ),
    ]]
    sub = Table(sub_data, colWidths=[W / 2, W / 2])
    sub.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sub)
    story.append(HRFlowable(width=W, thickness=0.5, color=LGRAY))

    # ── 壹、個案基本資料 ──────────────────────────────────────────────────────
    story.extend(_section("壹、個案基本資料"))
    p = eicr["patient"]
    gender_zh = {"male": "男", "female": "女", "unknown": "未知"}.get(p["gender"], p["gender"])
    story.append(_table([
        ["姓　　名", p["name"],       "性　　別", gender_zh],
        ["出生日期", p["birthdate"],  "居住地區", p["county"]],
        ["聯絡電話", p["phone"],      "身分證號", "（個資保護，略）"],
    ], col2))

    # ── 貳、通報疾病資訊 ──────────────────────────────────────────────────────
    story.extend(_section("貳、通報疾病資訊"))
    cond = eicr["condition"]
    clin_str = {
        "suspected": "■ 疑似  □ 確定",
        "confirmed": "□ 疑似  ■ 確定",
    }.get(cond["clinical_status"], cond["clinical_status"])
    story.append(_table([
        ["疾病名稱",   cond["disease"],      "臨床分類",   clin_str],
        ["SNOMED-CT", cond["snomed"],        "發病日期",   _fmt_dt(cond["onset"])],
        ["確認狀態",   cond["ver_status"],   "通報記錄時間", _fmt_dt(cond["recorded"])],
    ], col2))
    story.append(Spacer(1, 1.5 * mm))
    story.append(_table(
        [["主訴症狀", eicr["symptoms"] or "（未記載）"]],
        [38 * mm, W - 38 * mm],
    ))

    # ── 參、檢驗結果 ──────────────────────────────────────────────────────────
    story.extend(_section("參、檢驗結果"))
    obs = eicr["observation"]
    story.append(_table([
        ["LOINC 面板", obs["loinc"],       "面板說明",  obs["loinc_display"]],
        ["檢驗結果",   obs["result"] or "（待確認）",  "判讀", "■ 陽性  □ 陰性  □ 未定"],
    ], col2))

    # ── 肆、就診紀錄 ──────────────────────────────────────────────────────────
    story.extend(_section("肆、就診紀錄"))
    enc = eicr["encounter"]
    enc_status_zh = {"finished": "已完成", "in-progress": "進行中"}.get(enc["status"], enc["status"])
    story.append(_table([
        ["就診時間",  _fmt_dt(enc["start"]), "就診類型",  enc["enc_class"]],
        ["就診狀態",  enc_status_zh,         "通報院所",  hospital_name],
    ], col2))

    # ── 伍、通報醫療院所 ──────────────────────────────────────────────────────
    story.extend(_section("伍、通報醫療院所"))
    org = eicr["organization"]
    story.append(_table([
        ["院所名稱", hospital_name,   "通報機構",  org["name"]],
        ["機構地址", org["address"],  "機構網站",  org["url"]],
        ["通報醫師", "（請簽章）",     "通報日期",  datetime.now().strftime("%Y/%m/%d")],
    ], col2))

    # ── 簽章欄 ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    sign = Table(
        [[
            _p("通報醫師簽章：___________________________", size=10),
            _p("院所主管簽章：___________________________", size=10),
            _p(f"通報日期：{datetime.now().strftime('%Y/%m/%d')}", size=10),
        ]],
        colWidths=[W / 3, W / 3, W / 3],
    )
    sign.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.8, BLACK),
        ("GRID",          (0, 0), (-1, -1), 0.5, LGRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(sign)

    # ── 頁尾 ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width=W, thickness=0.5, color=LGRAY))
    story.append(Spacer(1, 2 * mm))
    footer_style = ParagraphStyle(
        "ft", fontName=FONT, fontSize=7, leading=10,
        textColor=LGRAY, wordWrap="CJK",
    )
    story.append(Paragraph(
        f"eICR Bundle ID：{eicr['bundle_id']}　文件狀態：{eicr.get('comp_status','').upper()}",
        footer_style,
    ))
    story.append(Paragraph(
        "本通報單由 MedMorph 自動通報引擎依據 HL7 FHIR R4 標準產生，格式參照衛生福利部傳染病個案通報單。",
        footer_style,
    ))
    story.append(Paragraph(
        "NTU 智慧醫療期末專題 · 第五組 · MedMorph Reference Architecture · 僅供學術展示用途",
        footer_style,
    ))

    doc.build(story)
    return buf.getvalue()
