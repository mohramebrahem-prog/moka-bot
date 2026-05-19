from __future__ import annotations
"""
companion_pdf_gen.py — توليد PDF مرافق مريض
أبعاد القالب: 842.25 × 1190.25 pt (A3)
نظام الخطوط والرسم مطابق لـ pdf_gen.py
"""
import os, tempfile, base64
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# ── BiDi + arabic_reshaper (نفس نظام pdf_gen.py) ──
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _BIDI_OK = True
except ImportError:
    _BIDI_OK = False

# ── arabic_reshape2 المحلي كـ fallback ──
try:
    from arabic_reshape2 import shape_arabic_text as _shape_local
except ImportError:
    def _shape_local(t): return t

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PAGE_W    = 842.25
PAGE_H    = 1190.25
DARK_BLUE = (0.17255, 0.24314, 0.46667)
WHITE     = (1.0, 1.0, 1.0)
BLACK     = (0.0, 0.0, 0.0)

# ══════════════════════════════════════════════════════════════
# DRAW_SLOTS
# ══════════════════════════════════════════════════════════════
DRAW_SLOTS = {
    'leave_id':             {'x': 432.0, 'rl_y': 933.0, 'size': 13.5, 'color': DARK_BLUE},
    'leave_duration_en':    {'x': 318.0, 'rl_y': 892.0, 'size': 13.5, 'color': WHITE},
    'leave_duration_ar':    {'x': 557.0, 'rl_y': 893.0, 'size': 13.5, 'color': WHITE,
                             'skip_arabic_processing': True},
    'admission_date_en':    {'x': 324.0, 'rl_y': 851.0, 'size': 13.5, 'color': DARK_BLUE},
    'admission_date_ar':    {'x': 557.0, 'rl_y': 851.0, 'size': 13.5, 'color': DARK_BLUE},
    'discharge_date_en':    {'x': 324.0, 'rl_y': 809.0, 'size': 13.5, 'color': DARK_BLUE},
    'discharge_date_ar':    {'x': 559.0, 'rl_y': 809.0, 'size': 13.5, 'color': DARK_BLUE},
    'issue_date':           {'x': 442.0, 'rl_y': 767.0, 'size': 13.5, 'color': DARK_BLUE},
    'companion_name_en':    {'x': 318.0, 'rl_y': 723.0, 'size': 13.5, 'color': DARK_BLUE},
    'companion_name_ar':    {'x': 558.0, 'rl_y': 723.0, 'size': 13.5, 'color': DARK_BLUE},
    'national_id':          {'x': 439.0, 'rl_y': 680.0, 'size': 13.5, 'color': DARK_BLUE},
    'nationality_en':       {'x': 316.0, 'rl_y': 638.0, 'size': 13.5, 'color': DARK_BLUE},
    'nationality_ar':       {'x': 557.0, 'rl_y': 642.0, 'size': 13.5, 'color': DARK_BLUE},
    'relation_en':          {'x': 318.0, 'rl_y': 596.0, 'size': 13.5, 'color': DARK_BLUE},
    'relation_ar':          {'x': 559.0, 'rl_y': 596.0, 'size': 13.5, 'color': DARK_BLUE},
    'employer_ar':          {'x': 559.0, 'rl_y': 554.0, 'size': 13.5, 'color': DARK_BLUE},
    'physician_name_en':    {'x': 318.0, 'rl_y': 510.0, 'size': 13.5, 'color': DARK_BLUE},
    'physician_name_ar':    {'x': 557.0, 'rl_y': 512.0, 'size': 13.5, 'color': DARK_BLUE},
    'position_en':          {'x': 316.0, 'rl_y': 466.0, 'size': 13.5, 'color': DARK_BLUE},
    'position_ar':          {'x': 558.0, 'rl_y': 469.0, 'size': 13.5, 'color': DARK_BLUE},
    'hospital_ar':          {'x': 634.0, 'rl_y': 279.0, 'size': 13.5, 'color': BLACK, 'bold': True},
    'hospital_en':          {'x': 634.0, 'rl_y': 260.0, 'size': 13.5, 'color': BLACK, 'bold': True},
    'issue_time':           {'x': 60.0,  'rl_y': 193.0, 'size': 13.5, 'color': BLACK, 'align': 'left'},
    'issue_weekday_date':   {'x': 60.0,  'rl_y': 166.0, 'size': 13.5, 'color': BLACK, 'align': 'left'},
}

MAX_WIDTHS = {
    'companion_name_en': 230, 'companion_name_ar': 220,
    'physician_name_en': 230, 'physician_name_ar': 220,
    'employer_ar':       220,
    'nationality_en':    230, 'nationality_ar':    220,
    'relation_en':       230, 'relation_ar':       220,
    'position_en':       230, 'position_ar':       220,
    'leave_duration_en': 230, 'leave_duration_ar': 220,
}

# ══════════════════════════════════════════════════════════════
# تسجيل الخطوط — مطابق لـ pdf_gen.py
# ══════════════════════════════════════════════════════════════
_fonts_registered = False
_times_ok     = False
_noto_ok      = False
_open_sans_ok = False

_TIMES_PATHS = [
    os.path.join(BASE_DIR, 'times.ttf'),
    os.path.join(BASE_DIR, 'fonts', 'times.ttf'),
    os.path.join(BASE_DIR, 'Times New Roman MT Std Regular.otf'),
    '/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
    '/Library/Fonts/Times New Roman.ttf',
    'C:/Windows/Fonts/times.ttf',
]
_TIMES_BOLD_PATHS = [
    os.path.join(BASE_DIR, 'timesbd.ttf'),
    os.path.join(BASE_DIR, 'fonts', 'timesbd.ttf'),
    os.path.join(BASE_DIR, 'Times New Roman MT Std Bold.otf'),
    '/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf',
    '/Library/Fonts/Times New Roman Bold.ttf',
    'C:/Windows/Fonts/timesbd.ttf',
]
_NOTO_REG_PATHS = [
    os.path.join(BASE_DIR, 'NotoSansArabic-Regular.ttf'),
    os.path.join(BASE_DIR, 'fonts', 'NotoSansArabic-Regular.ttf'),
]
_NOTO_BOLD_PATHS = [
    os.path.join(BASE_DIR, 'NotoSansArabic-Bold.ttf'),
    os.path.join(BASE_DIR, 'fonts', 'NotoSansArabic-Bold.ttf'),
]
_OPEN_SANS_REG_PATHS = [
    os.path.join(BASE_DIR, 'OpenSans-Regular.ttf'),
    os.path.join(BASE_DIR, 'fonts', 'OpenSans-Regular.ttf'),
]
_OPEN_SANS_BOLD_PATHS = [
    os.path.join(BASE_DIR, 'OpenSans-Bold.ttf'),
    os.path.join(BASE_DIR, 'fonts', 'OpenSans-Bold.ttf'),
]


def _register_fonts():
    global _fonts_registered, _times_ok, _noto_ok, _open_sans_ok
    if _fonts_registered: return

    for path in _TIMES_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('TimesNewRoman', path))
                _times_ok = True
                break
            except: pass

    _times_bold_ok = False
    for path in _TIMES_BOLD_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('TimesNewRoman-Bold', path))
                _times_bold_ok = True
                break
            except: pass
    if not _times_bold_ok and _times_ok:
        for path in _TIMES_PATHS:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont('TimesNewRoman-Bold', path))
                    break
                except: pass

    for path in _NOTO_REG_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('NotoSansArabic', path))
                _noto_ok = True
                break
            except: pass
    for path in _NOTO_BOLD_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('NotoSansArabic-Bold', path))
                break
            except: pass

    for path in _OPEN_SANS_REG_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('OpenSans', path))
                _open_sans_ok = True
                break
            except: pass
    for path in _OPEN_SANS_BOLD_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('OpenSans-Bold', path))
                break
            except: pass

    _fonts_registered = True


# ══════════════════════════════════════════════════════════════
# دوال مساعدة
# ══════════════════════════════════════════════════════════════

def _has_arabic(t):
    return any('\u0600' <= c <= '\u06FF' for c in str(t))


def _shape_ar(text: str) -> str:
    """تشكيل النص العربي — arabic_reshaper + BiDi أولاً، ثم arabic_reshape2 كـ fallback"""
    if not _has_arabic(text):
        return text
    if _BIDI_OK:
        try:
            return get_display(arabic_reshaper.reshape(text), base_dir='R')
        except Exception:
            pass
    return _shape_local(text)


def _draw_two_lines(c, text, font, size, x, rl_y, max_w, align='center'):
    lh = size * 1.2
    try:    tw = pdfmetrics.stringWidth(text, font, size)
    except: tw = max_w + 1

    def _dl(line, y):
        c.setFont(font, size)
        if align == 'left':    c.drawString(x, y, line)
        elif align == 'right': c.drawRightString(x, y, line)
        else:                  c.drawCentredString(x, y, line)

    if tw <= max_w:
        _dl(text, rl_y); return

    words, line1 = text.split(' '), ''
    for i, w in enumerate(words):
        test = (line1 + ' ' + w).strip()
        try:    ww = pdfmetrics.stringWidth(test, font, size)
        except: ww = max_w + 1
        if ww <= max_w:
            line1 = test
        else:
            line2 = ' '.join(words[i:])
            try:
                if pdfmetrics.stringWidth(line2, font, size) > max_w:
                    trimmed = ''
                    for ch in line2:
                        if pdfmetrics.stringWidth(trimmed+ch, font, size) <= max_w: trimmed += ch
                        else: break
                    line2 = trimmed.rstrip()
            except: pass
            _dl(line1, rl_y + lh*0.5)
            if line2: _dl(line2, rl_y - lh*0.5)
            return
    _dl(line1, rl_y)


def _draw_duration_ar(c, text_str, font_ar, font_en, size, x, rl_y, color):
    """
    رسم مدة الإجازة العربية — مطابق تماماً لـ pdf_gen.py:
    - كلمات عربية  → NotoSansArabic + BiDi/reshape
    - أرقام وأقواس → Times-Roman
    - عكس الترتيب + قلب الأقواس (RTL)
    - تمركز يدوي حول x
    """
    c.setFillColorRGB(*color)
    segments = []
    for token in text_str.split(' '):
        if not token:
            continue
        if _has_arabic(token):
            if _BIDI_OK:
                try:
                    shaped_tok = get_display(arabic_reshaper.reshape(token), base_dir='R')
                except Exception:
                    shaped_tok = _shape_local(token)
            else:
                shaped_tok = _shape_local(token)
            segments.append((shaped_tok, font_ar))
        else:
            segments.append((token, font_en))

    # عكس الترتيب + قلب الأقواس — خلية RTL
    segments = [(')' if t == '(' else '(' if t == ')' else t, f)
                for t, f in reversed(segments)]

    space_w = pdfmetrics.stringWidth(' ', font_en, size)
    total_w = sum(pdfmetrics.stringWidth(t, f, size) for t, f in segments)
    total_w += space_w * (len(segments) - 1)

    cur_x = x - total_w / 2
    for i, (tok, fnt) in enumerate(segments):
        c.setFont(fnt, size)
        c.drawString(cur_x, rl_y, tok)
        cur_x += pdfmetrics.stringWidth(tok, fnt, size)
        if i < len(segments) - 1:
            cur_x += space_w


# ══════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ══════════════════════════════════════════════════════════════

def generate_companion_pdf(data: dict, output_path: str,
                           template_path: str | None = None,
                           website_url: str = 'https://seha.sh') -> str:
    _register_fonts()
    if not template_path:
        template_path = os.path.join(BASE_DIR, 'companion_template.pdf')

    FONT_AR_REG  = 'NotoSansArabic'      if _noto_ok  else 'Times-Roman'
    FONT_AR_BOLD = 'NotoSansArabic-Bold' if _noto_ok  else 'Times-Bold'
    FONT_EN_REG  = 'TimesNewRoman'       if _times_ok else 'Times-Roman'
    FONT_EN_BOLD = 'TimesNewRoman-Bold'  if _times_ok else 'Times-Bold'
    FONT_REG     = 'Times-Roman'
    FONT_BOLD    = 'Times-Bold'

    packet = BytesIO()
    c = rl_canvas.Canvas(packet, pagesize=(PAGE_W, PAGE_H))

    for slot_id, slot in DRAW_SLOTS.items():
        value = data.get(slot_id)
        if not value: continue
        text_str = str(value).strip()
        if not text_str: continue

        x       = slot['x']
        rl_y    = slot['rl_y']
        size    = slot['size']
        color   = slot.get('color', BLACK)
        align   = slot.get('align', 'center')
        is_bold = slot.get('bold', False)
        c.setFillColorRGB(*color)

        # ── leave_duration_ar: رسم مقطعي مطابق لـ pdf_gen.py ──
        if slot.get('skip_arabic_processing'):
            _draw_duration_ar(c, text_str, FONT_AR_REG, FONT_REG, size, x, rl_y, color)
            continue

        is_ar = _has_arabic(text_str)
        if is_ar:
            font     = FONT_AR_BOLD if is_bold else FONT_AR_REG
            text_str = _shape_ar(text_str)
        else:
            font = FONT_EN_BOLD if is_bold else FONT_EN_REG
        c.setFillColorRGB(*color)

        max_w = MAX_WIDTHS.get(slot_id)
        if max_w:
            _draw_two_lines(c, text_str, font, size, x, rl_y, max_w, align)
        else:
            try:    c.setFont(font, size)
            except: c.setFont('Helvetica', size)
            if align == 'left':    c.drawString(x, rl_y, text_str)
            elif align == 'right': c.drawRightString(x, rl_y, text_str)
            else:                  c.drawCentredString(x, rl_y, text_str)

    # ── شعار المستشفى ──
    logo_b64 = data.get('logo_data', '')
    if logo_b64:
        _tmp = ''
        try:
            raw = logo_b64
            if ',' in raw: raw = raw.split(',', 1)[1]
            img_data = base64.b64decode(raw + '==')
            fd, _tmp = tempfile.mkstemp(suffix='.png')
            with os.fdopen(fd, 'wb') as f: f.write(img_data)
            ir = ImageReader(_tmp)
            iw, ih = ir.getSize()
            LOGO_MAX_W, LOGO_MAX_H = 120.0, 90.0
            LOGO_CX,    LOGO_RL_Y  = 634.0, 340.0
            scale  = min(LOGO_MAX_W / iw, LOGO_MAX_H / ih)
            nw, nh = iw * scale, ih * scale
            logo_x = LOGO_CX - nw / 2
            logo_y = LOGO_RL_Y + (LOGO_MAX_H - nh) / 2
            c.drawImage(ir, logo_x, logo_y, width=nw, height=nh,
                        preserveAspectRatio=True, mask='auto')
        except Exception as e:
            import logging; logging.getLogger(__name__).warning(f'logo: {e}')
        finally:
            if _tmp and os.path.exists(_tmp):
                try: os.unlink(_tmp)
                except: pass

    # ── QR Code ──
    _SEHA_URL = str(website_url or 'https://seha.sh').strip()
    if _SEHA_URL and not _SEHA_URL.startswith(('https://', 'http://')):
        _SEHA_URL = 'https://' + _SEHA_URL
    try:
        import qrcode as _qrcode
        _qr = _qrcode.QRCode(version=2, box_size=6, border=1,
                              error_correction=_qrcode.constants.ERROR_CORRECT_M)
        _qr.add_data(_SEHA_URL)
        _qr.make(fit=True)
        _qr_img = _qr.make_image(fill_color='black', back_color='white')
        _qr_buf = BytesIO()
        _qr_img.save(_qr_buf, 'PNG')
        _qr_buf.seek(0)
        QR_X, QR_Y, QR_W, QR_H = 171.6, 323.0, 98.3, 98.3
        c.drawImage(ImageReader(_qr_buf), QR_X, QR_Y, width=QR_W, height=QR_H, mask='auto')
    except Exception as _qe:
        import logging; logging.getLogger(__name__).warning(f'QR: {_qe}')

    # ── رابط الموقع ──
    _display_url = 'www.seha.sa/#/inquiries/slenquiry'
    _url_font_sz = 12.5
    try:    c.setFont(FONT_EN_REG, _url_font_sz)
    except: c.setFont('Times-Roman', _url_font_sz)
    c.setFillColorRGB(0.0, 0.0, 1.0)
    c.drawCentredString(226.6, 221.0, _display_url)
    c.linkURL(_SEHA_URL, (105.0, 210.0, 348.0, 236.0), relative=0)

    c.save(); packet.seek(0)
    overlay_page = PdfReader(packet).pages[0]
    writer = PdfWriter()
    if os.path.exists(template_path):
        base_page = PdfReader(template_path).pages[0]
        base_page.merge_page(overlay_page)
        writer.add_page(base_page)
    else:
        writer.add_page(overlay_page)
    with open(output_path, 'wb') as f: writer.write(f)
    return output_path
