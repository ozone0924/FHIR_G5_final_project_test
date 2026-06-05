"""
pdf_report.py — eICR 通報單 PDF 產生器
字型：STHeiti Medium.ttc 提取繁體子字型，由 fpdf2 直接 Unicode 映射
格式：仿衛福部疾病管制署「傳染病個案通報單」，黑白正式版
"""

import io
import os
import tempfile
from datetime import datetime

from fpdf import FPDF

# ── 字型準備 ──────────────────────────────────────────────────────────────────
_TMP_FONT_PATH: str | None = None
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TTC_CANDIDATES = [
    (os.path.join(_BASE_DIR, "fonts", "NotoSansTC-Regular.ttf"), 0), 
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),   # macOS — 繁體確認可用
    ("/System/Library/Fonts/STHeiti Light.ttc",  0),   # macOS 備援
    ("/System/Library/Fonts/PingFang.ttc",       0),   # macOS PingFang
]


def _prepare_font() -> str | None:
    """從 TTC 提取第 idx 號子字型至暫存 TTF，供 fpdf2 使用。"""
    global _TMP_FONT_PATH
    if _TMP_FONT_PATH and os.path.exists(_TMP_FONT_PATH):
        return _TMP_FONT_PATH

    for path, idx in _TTC_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            from fontTools.ttLib import TTCollection
            ttc = TTCollection(path)
            font = ttc.fonts[idx]
            buf = io.BytesIO()
            font.save(buf)
            tmp = tempfile.NamedTemporaryFile(
                suffix=".ttf", prefix="eicr_font_", delete=False
            )
            tmp.write(buf.getvalue())
            tmp.close()
            _TMP_FONT_PATH = tmp.name
            return _TMP_FONT_PATH
        except Exception:
            continue
    return None


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def _fmt_dt(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return iso


# ── PDF 表單類別 ──────────────────────────────────────────────────────────────

class _NotificationForm(FPDF):
    F  = "CJK"
    PW = 170   # 可用寬度 mm（A4 210 - 左右各 20mm）
    LW = 35    # 標籤欄寬 mm
    RH = 7     # 列高 mm

    def __init__(self, font_path: str):
        super().__init__(format="A4")
        self.set_margins(20, 18, 20)
        self.set_auto_page_break(True, margin=20)
        self.add_font(self.F, style="", fname=font_path)
        self.add_page()

    def _f(self, sz: int):
        self.set_font(self.F, size=sz)

    def _gray(self, val: int = 235):
        self.set_fill_color(val, val, val)

    def _white(self):
        self.set_fill_color(255, 255, 255)
        self.set_text_color(0, 0, 0)

    def hr(self, thick: float = 0.5):
        self.set_line_width(thick)
        self.set_draw_color(0, 0, 0)
        self.line(self.l_margin, self.get_y(),
                  self.l_margin + self.PW, self.get_y())

    def section(self, title: str):
        self.ln(3)
        self._f(11)
        self._gray(220)
        self.set_text_color(0, 0, 0)
        self.cell(self.PW, 7, title, border=0, fill=True,
                  new_x="LMARGIN", new_y="NEXT")
        self.hr(0.5)
        self.ln(2)

    def row2(self, pairs: list[tuple[str, str]]):
        """1 或 2 組 label/value，平均分配 PW。"""
        n = len(pairs)
        col = self.PW / n
        val_w = col - self.LW
        y0 = self.get_y()
        for i, (lbl, val) in enumerate(pairs):
            x = self.l_margin + i * col
            self._f(9)
            self._gray()
            self.set_text_color(0, 0, 0)
            self.set_xy(x, y0)
            self.cell(self.LW, self.RH, str(lbl), border=1, fill=True)
            self._f(10)
            self._white()
            self.set_xy(x + self.LW, y0)
            self.cell(val_w, self.RH, str(val)[:40], border=1)
        self.set_xy(self.l_margin, y0 + self.RH)

    def wide_row(self, lbl: str, val: str):
        """全寬單行：標籤 + 可換行的值。"""
        val_w = self.PW - self.LW
        y0 = self.get_y()
        self._f(9)
        self._gray()
        self.set_text_color(0, 0, 0)
        self.set_xy(self.l_margin, y0)
        self.cell(self.LW, self.RH, lbl, border=1, fill=True)
        self._f(10)
        self._white()
        self.set_xy(self.l_margin + self.LW, y0)
        self.multi_cell(val_w, self.RH, str(val), border=1,
                        new_x="LMARGIN", new_y="NEXT")


# ── 主函式 ────────────────────────────────────────────────────────────────────

def generate_eicr_pdf(eicr: dict, hospital_name: str = "XX 醫院") -> bytes:
    """產生傳染病個案通報單 PDF（黑白正式格式，繁體中文完整支援）。"""
    font_path = _prepare_font()
    if not font_path:
        raise RuntimeError("找不到支援繁體中文的字型檔（STHeiti / PingFang）")

    pdf = _NotificationForm(font_path)
    W = pdf.PW

    # ── 頁首 ──────────────────────────────────────────────────────────────────
    pdf._f(9)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(45, 8, "衛生福利部疾病管制署", align="L")
    pdf._f(16)
    pdf.cell(85, 8, "傳  染  病  個  案  通  報  單", align="C")
    pdf._f(9)
    bundle_date = _fmt_dt(eicr.get("bundle_ts", ""))
    pdf.cell(40, 8, f"通報日期：{bundle_date}", align="R",
             new_x="LMARGIN", new_y="NEXT")

    pdf.hr(0.8)
    pdf.ln(2)

    pdf._f(10)
    cond = eicr.get("condition", {})
    pdf.cell(W / 2, 6, f"通報醫療院所：{hospital_name}", align="L")
    pdf.cell(
        W / 2, 6,
        f"疾病別：{cond.get('disease','—')}　通報流水號：{eicr.get('bundle_id','')[:8].upper()}",
        align="R", new_x="LMARGIN", new_y="NEXT",
    )
    pdf.hr(0.3)
    pdf.ln(2)

    # ── 壹、個案基本資料 ───────────────────────────────────────────────────────
    pdf.section("壹、個案基本資料")
    p = eicr.get("patient", {})
    g = {"male": "男", "female": "女", "unknown": "未知"}.get(
        p.get("gender", ""), p.get("gender", "—"))
    pdf.row2([("姓　　名", p.get("name", "—")),    ("性　　別", g)])
    pdf.row2([("出生日期", p.get("birthdate", "—")), ("居住地區", p.get("county", "—"))])
    pdf.row2([("聯絡電話", p.get("phone", "—")),   ("身分證號", "（個資保護，略）")])

    # ── 貳、通報疾病資訊 ───────────────────────────────────────────────────────
    pdf.section("貳、通報疾病資訊")
    clin_str = {
        "suspected": "■ 疑似  □ 確定",
        "confirmed": "□ 疑似  ■ 確定",
    }.get(cond.get("clinical_status", ""), cond.get("clinical_status", "—"))
    pdf.row2([("疾病名稱",   cond.get("disease", "—")),
              ("臨床分類",   clin_str)])
    pdf.row2([("SNOMED-CT", cond.get("snomed", "—")),
              ("發病日期",   _fmt_dt(cond.get("onset", "")))])
    pdf.row2([("確認狀態",   cond.get("ver_status", "—")),
              ("通報記錄時間", _fmt_dt(cond.get("recorded", "")))])
    pdf.wide_row("主訴症狀", eicr.get("symptoms", "") or "（未記載）")

    # ── 參、檢驗結果 ───────────────────────────────────────────────────────────
    pdf.section("參、檢驗結果")
    obs = eicr.get("observation", {})
    pdf.row2([("LOINC 面板", obs.get("loinc", "—")),
              ("面板說明",   obs.get("loinc_display", "—"))])
    pdf.row2([("檢驗結果", obs.get("result", "（待確認）") or "（待確認）"),
              ("結果判讀", "■ 陽性  □ 陰性  □ 未定")])

    # ── 肆、就診紀錄 ───────────────────────────────────────────────────────────
    pdf.section("肆、就診紀錄")
    enc = eicr.get("encounter", {})
    enc_zh = {"finished": "已完成", "in-progress": "進行中"}.get(
        enc.get("status", ""), enc.get("status", "—"))
    pdf.row2([("就診時間", _fmt_dt(enc.get("start", ""))),
              ("就診類型", enc.get("enc_class", "—"))])
    pdf.row2([("就診狀態", enc_zh), ("通報院所", hospital_name)])

    # ── 伍、通報醫療院所 ───────────────────────────────────────────────────────
    pdf.section("伍、通報醫療院所")
    org = eicr.get("organization", {})
    pdf.row2([("院所名稱", hospital_name),
              ("通報機構", org.get("name", "—"))])
    pdf.row2([("機構地址", org.get("address", "—")[:40]),
              ("機構網站", org.get("url", "—"))])
    pdf.row2([("通報醫師", "（請簽章）"),
              ("通報日期", datetime.now().strftime("%Y/%m/%d"))])

    # ── 簽章欄 ────────────────────────────────────────────────────────────────
    # 用 cell()（不換行），避免簽名底線文字超過 sign_w 發生多行偏位
    SIGN_H = 18
    pdf.ln(5)
    sign_w = W / 3
    y_sign = pdf.get_y()
    sign_texts = [
        "通報醫師簽章：______________",
        "院所主管簽章：______________",
        f"通報日期：{datetime.now().strftime('%Y/%m/%d')}",
    ]
    for i, txt in enumerate(sign_texts):
        pdf._f(10)
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(pdf.l_margin + i * sign_w, y_sign)
        pdf.cell(sign_w, SIGN_H, txt, border=1, align="L")
    pdf.set_xy(pdf.l_margin, y_sign + SIGN_H)

    # ── 頁尾 ──────────────────────────────────────────────────────────────────
    pdf.ln(5)
    pdf.hr(0.3)
    pdf.ln(2)
    pdf._f(7)
    pdf.set_text_color(130, 130, 130)
    bid    = eicr.get("bundle_id", "—")
    status = eicr.get("comp_status", "").upper()
    for line in [
        f"Bundle ID：{bid}",
        f"文件狀態：{status}",
        "本通報單由 MedMorph 自動通報引擎依據 HL7 FHIR R4 標準產生，格式參照衛生福利部傳染病個案通報單。",
        "NTU 智慧醫療期末專題 · 第五組 · MedMorph Reference Architecture · 僅供學術展示用途",
    ]:
        pdf.multi_cell(W, 4.5, line, align="L", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
