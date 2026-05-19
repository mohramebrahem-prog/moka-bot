"""
╔══════════════════════════════════════════════════════════════════════════╗
║  visit_pdf_gen.py — مولد PDF مشهد المراجعة (Statement of Visit)        ║
║  يعتمد على: ReportLab + pypdf + arabic_reshape2.py                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

# ── استيراد تشكيل النص العربي ──
try:
    from arabic_reshape2 import shape_arabic_text
except ImportError:
    def shape_arabic_text(t): return t

# ══════════════════════════════════════════════════════════════
#  ثوابت الصفحة
# ══════════════════════════════════════════════════════════════
PAGE_W = 595.5
PAGE_H = 842.25

# ألوان
DARK_BLUE = (0.1725, 0.2431, 0.4667)  # #2C3E77
WHITE     = (1.0,    1.0,    1.0)
BLACK     = (0.0,    0.0,    0.0)

# مركز عمود البيانات العربية
AR_CX = 392.5

# ══════════════════════════════════════════════════════════════
#  مسارات الخطوط
# ══════════════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_FONTS_REGISTERED = False
_times_ok         = False   # Times New Roman TTF محمل
_noto_ok          = False   # NotoSansArabic TTF محمل
_open_sans_ok     = False   # Open Sans TTF محمل

# مسارات بحث الخطوط — مطابقة لـ pdf_gen.py
_TIMES_PATHS = [
    os.path.join(BASE_DIR, "fonts", "times.ttf"),
    os.path.join(BASE_DIR, "times.ttf"),
    "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
    "/Library/Fonts/Times New Roman.ttf",
    "C:/Windows/Fonts/times.ttf",
]
_NOTO_REG_PATHS = [
    os.path.join(BASE_DIR, "NotoSansArabic-Regular.ttf"),
    os.path.join(BASE_DIR, "fonts", "NotoSansArabic-Regular.ttf"),
]
_NOTO_BOLD_PATHS = [
    os.path.join(BASE_DIR, "NotoSansArabic-Bold.ttf"),
    os.path.join(BASE_DIR, "fonts", "NotoSansArabic-Bold.ttf"),
]
_OPEN_SANS_REG_PATHS = [
    os.path.join(BASE_DIR, "OpenSans-Regular.ttf"),
    os.path.join(BASE_DIR, "fonts", "OpenSans-Regular.ttf"),
]
_OPEN_SANS_BOLD_PATHS = [
    os.path.join(BASE_DIR, "OpenSans-Bold.ttf"),
    os.path.join(BASE_DIR, "fonts", "OpenSans-Bold.ttf"),
]


def _register_fonts():
    global _FONTS_REGISTERED, _times_ok, _noto_ok, _open_sans_ok
    if _FONTS_REGISTERED:
        return

    # تسجيل Times New Roman (للنصوص الإنجليزية)
    for path in _TIMES_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("TimesNewRoman", path))
                _times_ok = True
                break
            except Exception:
                pass

    # تسجيل NotoSansArabic (للنصوص العربية)
    for path in _NOTO_REG_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("NotoSansArabic", path))
                _noto_ok = True
                break
            except Exception:
                pass
    for path in _NOTO_BOLD_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("NotoSansArabic-Bold", path))
            except Exception:
                pass

    # تسجيل Open Sans
    for path in _OPEN_SANS_REG_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("OpenSans", path))
                _open_sans_ok = True
                break
            except Exception:
                pass
    for path in _OPEN_SANS_BOLD_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("OpenSans-Bold", path))
            except Exception:
                pass

    _FONTS_REGISTERED = True


# ══════════════════════════════════════════════════════════════
#  دالة رسم النص المركزية
# ══════════════════════════════════════════════════════════════

def _get_fonts():
    """يُعيد أسماء الخطوط المناسبة حسب ما هو مسجَّل — مطابق لـ pdf_gen.py"""
    FONT_AR_REG  = "NotoSansArabic"      if _noto_ok  else ("TimesNewRoman" if _times_ok else "Times-Roman")
    FONT_AR_BOLD = "NotoSansArabic-Bold" if _noto_ok  else ("TimesNewRoman" if _times_ok else "Times-Bold")
    FONT_REG     = "TimesNewRoman"       if _times_ok else "Times-Roman"
    FONT_BOLD    = "TimesNewRoman"       if _times_ok else "Times-Bold"
    return FONT_AR_REG, FONT_AR_BOLD, FONT_REG, FONT_BOLD


# الحقول التي تدعم السطر الثاني مع أقصى عرض لكل منها (بالـ pt)
MAX_WIDTHS = {
    "name_en":          170,
    "name_ar":          160,
    "employer_ar":      160,
    "practitioner_en":  170,
    "practitioner_ar":  160,
    "position_en":      170,
    "position_ar":      160,
    "nationality_en":   170,
    "nationality_ar":   160,
    "visit_type_en":    170,
    "visit_type_ar":    160,
    "waiting_period_en":170,
    "waiting_period_ar":160,
    "hospital_ar":      0,
    "hospital_en":      0,
}


def _draw_two_lines(c: canvas.Canvas, text: str, font: str, font_size: float,
                    x: float, mid_y: float, max_width: float, align: str):
    """
    يرسم النص بحجم خط ثابت.
    - سطر واحد إن كان يسع.
    - سطرين إن كان طويلاً — يكسر عند آخر مسافة.
    - السطر الثاني يُقطع إن تجاوز العرض (لا يوجد سطر ثالث).
    """
    line_height = font_size * 1.2

    try:
        total_w = pdfmetrics.stringWidth(text, font, font_size)
    except Exception:
        total_w = max_width + 1

    def _draw_line(txt, y):
        c.setFont(font, font_size)
        if align == "center":
            c.drawCentredString(x, y, txt)
        elif align == "right":
            c.drawRightString(x, y, txt)
        else:
            c.drawString(x, y, txt)

    if total_w <= max_width:
        _draw_line(text, mid_y)
        return

    # كسر عند المسافات
    words = text.split(" ")
    line1 = ""
    for i, word in enumerate(words):
        test = (line1 + " " + word).strip()
        try:
            w = pdfmetrics.stringWidth(test, font, font_size)
        except Exception:
            w = max_width + 1
        if w <= max_width:
            line1 = test
        else:
            line2 = " ".join(words[i:])
            # قطع السطر الثاني إن تجاوز العرض
            try:
                w2 = pdfmetrics.stringWidth(line2, font, font_size)
            except Exception:
                w2 = max_width + 1
            if w2 > max_width:
                trimmed = ""
                for ch in line2:
                    try:
                        tw = pdfmetrics.stringWidth(trimmed + ch, font, font_size)
                    except Exception:
                        tw = max_width + 1
                    if tw <= max_width:
                        trimmed += ch
                    else:
                        break
                line2 = trimmed.rstrip()

            y1 = mid_y + line_height * 0.5
            y2 = mid_y - line_height * 0.5
            for line, y in [(line1, y1), (line2, y2)]:
                if line:
                    _draw_line(line, y)
            return

    # كل الكلمات تسع في سطر واحد
    _draw_line(line1, mid_y)


def draw(c: canvas.Canvas, text: str, x: float, top: float, bottom: float,
         color: tuple, font: str, align: str = "left", arabic: bool = False,
         field_key: str = ""):
    """
    ترسم نصاً على الـ canvas مع دعم السطر الثاني للحقول الطويلة.
    top/bottom: إحداثيات PDF من الأعلى (0 = رأس الصفحة).
    """
    if not text:
        return

    FONT_AR_REG, FONT_AR_BOLD, FONT_REG, FONT_BOLD = _get_fonts()

    if arabic:
        text = shape_arabic_text(str(text))
        resolved_font = FONT_AR_BOLD if "Bold" in font else FONT_AR_REG
    else:
        text = str(text)
        resolved_font = FONT_BOLD if "Bold" in font else FONT_REG

    font_size = bottom - top
    mid_y = (PAGE_H - ((top + bottom) / 2)) - font_size * 0.35

    c.setFillColorRGB(*color)

    max_w = MAX_WIDTHS.get(field_key, 0)
    if max_w > 0:
        _draw_two_lines(c, text, resolved_font, font_size, x, mid_y, max_w, align)
    else:
        try:
            c.setFont(resolved_font, font_size)
        except Exception:
            c.setFont("Helvetica", font_size)
        if align == "center":
            c.drawCentredString(x, mid_y, text)
        elif align == "right":
            c.drawRightString(x, mid_y, text)
        else:
            c.drawString(x, mid_y, text)


# ══════════════════════════════════════════════════════════════
#  الدالة الرئيسية
# ══════════════════════════════════════════════════════════════

def generate_visit_pdf(
    data: dict,
    output_path: str,
    template_path: str | None = None,
    website_url: str = "https://sehaseinquiresslendquiry.com",
) -> str:
    """
    يولّد ملف PDF لمشهد المراجعة (Statement of Visit).

    data: dict يحتوي على المفاتيح التالية:
        leave_id, admission_date_en, admission_date_ar,
        discharge_date_en, discharge_date_ar,
        waiting_period_en, waiting_period_ar,
        issue_date, name_en, name_ar, national_id,
        nationality_en, nationality_ar, employer_ar,
        practitioner_en, practitioner_ar,
        position_en, position_ar,
        visit_type_en, visit_type_ar,
        hospital_ar, hospital_en,
        issue_time, issue_weekday_date

    يُرجع مسار الملف الناتج.
    """
    _register_fonts()

    # ── القالب ──
    if not template_path:
        template_path = os.path.join(BASE_DIR, "visit_template.pdf")

    # ── إنشاء طبقة النصوص ──
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(PAGE_W, PAGE_H))

    # ── جدول الحقول ──
    # (مفتاح_data, x, top, bottom, color, font, align, arabic)
    FIELDS = [
        ("leave_id",          297.75, 184.4, 193.0, DARK_BLUE, "TimesNewRoman",    "center", False),
        ("admission_date_en", 163.3,  213.7, 222.3, WHITE,     "TimesNewRoman",    "left",   False),
        ("admission_date_ar", AR_CX,  213.7, 222.3, WHITE,     "NotoSansArabic",   "center", True ),
        ("discharge_date_en", 163.3,  244.6, 253.1, WHITE,     "TimesNewRoman",    "left",   False),
        ("discharge_date_ar", AR_CX,  244.6, 253.1, WHITE,     "NotoSansArabic",   "center", True ),
        ("waiting_period_en", 165.6,  275.5, 284.0, WHITE,     "TimesNewRoman",    "left",   False),
        ("waiting_period_ar", AR_CX,  275.5, 284.0, WHITE,     "NotoSansArabic",   "center", True ),
        ("issue_date",        297.75, 306.8, 315.4, DARK_BLUE, "TimesNewRoman",    "center", False),
        ("name_en",           200.0,  334.5, 343.5, DARK_BLUE, "TimesNewRoman",    "center", False),
        ("name_ar",           AR_CX,  334.5, 343.5, DARK_BLUE, "NotoSansArabic",   "center", True ),
        ("national_id",       297.75, 366.2, 374.7, DARK_BLUE, "TimesNewRoman",    "center", False),
        ("nationality_en",    200.0,  395.5, 404.0, DARK_BLUE, "TimesNewRoman",    "center", False),
        ("nationality_ar",    AR_CX,  395.5, 404.0, DARK_BLUE, "NotoSansArabic",   "center", True ),
        ("employer_ar",       AR_CX,  425.1, 433.7, DARK_BLUE, "NotoSansArabic",   "center", True ),
        ("practitioner_en",   200.0,  455.9, 464.7, DARK_BLUE, "TimesNewRoman",    "center", False),
        ("practitioner_ar",   AR_CX,  455.9, 464.7, DARK_BLUE, "NotoSansArabic",   "center", True ),
        ("position_en",       200.0,  487.2, 495.9, DARK_BLUE, "TimesNewRoman",    "center", False),
        ("position_ar",       AR_CX,  487.2, 495.9, DARK_BLUE, "NotoSansArabic",   "center", True ),
        ("visit_type_en",     200.0,  517.4, 525.9, DARK_BLUE, "TimesNewRoman",    "center", False),
        ("visit_type_ar",     AR_CX,  517.4, 525.9, DARK_BLUE, "NotoSansArabic",   "center", True ),
        ("hospital_ar",       431.0,  641.0, 650.0, BLACK,     "NotoSansArabic-Bold","center",True),
        ("hospital_en",       431.0,  653.5, 661.5, BLACK,     "TimesNewRoman",    "center", False),
        ("issue_time",        21.9,   683.6, 691.7, BLACK,     "TimesNewRoman",    "left",   False),
        ("issue_weekday_date",21.9,   698.6, 706.7, BLACK,     "TimesNewRoman",    "left",   False),
    ]

    for fkey, x, top, bottom, color, font, align, arabic in FIELDS:
        val = data.get(fkey, "")
        if not val:
            continue
        draw(c, str(val), x, top, bottom, color, font, align, arabic, field_key=fkey)

    # ── رسم الشعار (logo_data: base64 PNG/JPEG) — نفس طريقة pdf_gen.py ──
    logo_b64 = data.get("logo_data", "")
    if logo_b64:
        _tmp_logo_path = ""
        try:
            import base64 as _b64
            import tempfile as _tmpfile
            raw = logo_b64
            if "," in raw:
                raw = raw.split(",", 1)[1]
            img_data = _b64.b64decode(raw + "==")
            fd, _tmp_logo_path = _tmpfile.mkstemp(suffix=".png")
            with os.fdopen(fd, "wb") as _f:
                _f.write(img_data)
            # ── منطقة الشعار: يمين الصفحة، أسفل الجدول وفوق اسم المستشفى ──
            LOGO_MAX_W = 90.0
            LOGO_MAX_H = 70.0
            LOGO_CX    = 431.0   # نفس مركز اسم المستشفى
            LOGO_RL_Y  = 215.2   # من أسفل الصفحة (ReportLab)
            from reportlab.lib.utils import ImageReader as _IR
            _ir = _IR(_tmp_logo_path)
            iw, ih = _ir.getSize()
            scale = min(LOGO_MAX_W / iw, LOGO_MAX_H / ih)
            nw, nh = iw * scale, ih * scale
            logo_x = LOGO_CX - nw / 2   # توسيط أفقي
            logo_y = LOGO_RL_Y + (LOGO_MAX_H - nh) / 2   # توسيط رأسي
            c.drawImage(_ir, logo_x, logo_y, width=nw, height=nh,
                        preserveAspectRatio=True, mask="auto")
        except Exception as _logo_err:
            import logging as _logging
            _logging.getLogger(__name__).warning(f"visit_pdf logo: {_logo_err}")
        finally:
            if _tmp_logo_path and os.path.exists(_tmp_logo_path):
                try:
                    os.unlink(_tmp_logo_path)
                except Exception:
                    pass

    # ── رسم QR Code مضمن — نفس أسلوب pdf_gen.py تماماً ──────────
    # الموضع: يسار الصفحة، أسفل الجدول وفوق الرابط
    # إحداثيات ReportLab: x=21.9, rl_y=185.0, width=108, height=101
    SEHA_URL = str(website_url or "https://sehaseinquiresslendquiry.com").strip()
    if SEHA_URL and not SEHA_URL.startswith(("https://", "http://")):
        SEHA_URL = "https://" + SEHA_URL

    _qr_x  = 108.0
    _qr_y  = 224.0   # rl_y (من أسفل الصفحة)
    _qr_w  = 68.0
    _qr_h  = 63.0

    try:
        import qrcode as _qrcode
        from io import BytesIO as _BytesIO
        from reportlab.lib.utils import ImageReader as _IRqr
        _qr = _qrcode.QRCode(version=2, box_size=6, border=1,
                             error_correction=_qrcode.constants.ERROR_CORRECT_M)
        _qr.add_data(SEHA_URL)
        _qr.make(fit=True)
        _qr_img = _qr.make_image(fill_color="black", back_color="white")
        _buf = _BytesIO()
        _qr_img.save(_buf, "PNG")
        _buf.seek(0)
        c.drawImage(_IRqr(_buf), _qr_x, _qr_y, width=_qr_w, height=_qr_h, mask="auto")
    except Exception:
        # fallback: مستطيل أبيض إن فشل توليد QR
        c.setFillColorRGB(1, 1, 1)
        c.setStrokeColorRGB(1, 1, 1)
        c.setLineWidth(0)
        c.rect(_qr_x, _qr_y, _qr_w, _qr_h, stroke=0, fill=1)

    # ── رسم نص الرابط الشكلي (شكلي فقط — لا يعمل) + annotation مخفي برابط الأدمن ──
    # الرابط المرئي: نص أزرق شكلي فوق الخط الأزرق في القالب — ثابت لا يتغير
    # الرابط المخفي: annotation غير مرئي يحمل web_url الحقيقي — يُفتح عند الضغط
    _display_url = "www.seha.sa/#/inquiries/slenquiry"   # نص شكلي ثابت
    _font_size   = 6.5
    _, _, FONT_REG, _ = _get_fonts()
    try:
        c.setFont(FONT_REG, _font_size)
    except Exception:
        c.setFont("Times-Roman", _font_size)
    c.setFillColorRGB(0.0, 0.0, 1.0)   # أزرق نقي
    c.drawCentredString(141.10, 162.15, _display_url)

    # annotation مخفي — عند الضغط يفتح SEHA_URL الحقيقي (web_url من قاعدة البيانات)
    c.linkURL(SEHA_URL, (95.3, 153.15, 186.9, 173.15), relative=0)

    c.save()
    packet.seek(0)

    # ── دمج مع القالب ──
    overlay_pdf = PdfReader(packet)
    overlay_page = overlay_pdf.pages[0]

    writer = PdfWriter()

    if os.path.exists(template_path):
        template_pdf = PdfReader(template_path)
        base_page = template_pdf.pages[0]
        # حذف روابط القالب القديمة (رابط خاطئ في visit_template)
        if '/Annots' in base_page:
            del base_page['/Annots']
        base_page.merge_page(overlay_page)
        writer.add_page(base_page)
    else:
        # بدون قالب — الطبقة فقط
        writer.add_page(overlay_page)

    with open(output_path, "wb") as f:
        writer.write(f)

    return output_path
