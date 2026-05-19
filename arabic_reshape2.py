"""
Arabic Reshaper using Unicode Presentation Forms (FE70-FEFF)
هذا الأسلوب يستخدم نماذج العرض العربية في Unicode مباشرة
"""

# جدول الحروف: معزول، أول، وسط، آخر
# القيم من Unicode Arabic Presentation Forms-A/B
ARABIC_CHAR_TABLE = {
    'ء': ('\uFE80', None,     None,     None    ),
    'آ': ('\uFE81', None,     None,     '\uFE82'),
    'أ': ('\uFE83', None,     None,     '\uFE84'),
    'ؤ': ('\uFE85', None,     None,     '\uFE86'),
    'إ': ('\uFE87', None,     None,     '\uFE88'),
    'ئ': ('\uFE89', '\uFE8B', '\uFE8C', '\uFE8A'),
    'ا': ('\uFE8D', None,     None,     '\uFE8E'),
    'ب': ('\uFE8F', '\uFE91', '\uFE92', '\uFE90'),
    'ة': ('\uFE93', None,     None,     '\uFE94'),
    'ت': ('\uFE95', '\uFE97', '\uFE98', '\uFE96'),
    'ث': ('\uFE99', '\uFE9B', '\uFE9C', '\uFE9A'),
    'ج': ('\uFE9D', '\uFE9F', '\uFEA0', '\uFE9E'),
    'ح': ('\uFEA1', '\uFEA3', '\uFEA4', '\uFEA2'),
    'خ': ('\uFEA5', '\uFEA7', '\uFEA8', '\uFEA6'),
    'د': ('\uFEA9', None,     None,     '\uFEAA'),
    'ذ': ('\uFEAB', None,     None,     '\uFEAC'),
    'ر': ('\uFEAD', None,     None,     '\uFEAE'),
    'ز': ('\uFEAF', None,     None,     '\uFEB0'),
    'س': ('\uFEB1', '\uFEB3', '\uFEB4', '\uFEB2'),
    'ش': ('\uFEB5', '\uFEB7', '\uFEB8', '\uFEB6'),
    'ص': ('\uFEB9', '\uFEBB', '\uFEBC', '\uFEBA'),
    'ض': ('\uFEBD', '\uFEBF', '\uFEC0', '\uFEBE'),
    'ط': ('\uFEC1', '\uFEC3', '\uFEC4', '\uFEC2'),
    'ظ': ('\uFEC5', '\uFEC7', '\uFEC8', '\uFEC6'),
    'ع': ('\uFEC9', '\uFECB', '\uFECC', '\uFECA'),
    'غ': ('\uFECD', '\uFECF', '\uFED0', '\uFECE'),
    'ف': ('\uFED1', '\uFED3', '\uFED4', '\uFED2'),
    'ق': ('\uFED5', '\uFED7', '\uFED8', '\uFED6'),
    'ك': ('\uFED9', '\uFEDB', '\uFEDC', '\uFEDA'),
    'ل': ('\uFEDD', '\uFEDF', '\uFEE0', '\uFEDE'),
    'م': ('\uFEE1', '\uFEE3', '\uFEE4', '\uFEE2'),
    'ن': ('\uFEE5', '\uFEE7', '\uFEE8', '\uFEE6'),
    'ه': ('\uFEE9', '\uFEEB', '\uFEEC', '\uFEEA'),
    'و': ('\uFEED', None,     None,     '\uFEEE'),
    'ى': ('\uFEEF', None,     None,     '\uFEF0'),
    'ي': ('\uFEF1', '\uFEF3', '\uFEF4', '\uFEF2'),
    # لام-ألف ligatures
    'لأ': ('\uFEF3', None, None, '\uFEF6'),  # handled separately
    'لآ': ('\uFEF5', None, None, '\uFEF6'),
    'لإ': ('\uFEF7', None, None, '\uFEF8'),
    'لا': ('\uFEFB', None, None, '\uFEFC'),
}

# الحروف غير المتصلة من اليسار
NON_JOINING_LEFT = set('ءآأؤإادذرزوةى\uFE80\uFE81\uFE82\uFE83\uFE84\uFE85\uFE86\uFE87\uFE88\uFE8D\uFE8E\uFEA9\uFEAA\uFEAB\uFEAC\uFEAD\uFEAE\uFEAF\uFEB0\uFEED\uFEEE\uFEEF\uFEF0\uFE93\uFE94')

def is_arabic_char(ch):
    cp = ord(ch)
    return (0x0600 <= cp <= 0x06FF) or (0xFE70 <= cp <= 0xFEFF)

def connects_left(ch):
    """هل يتصل الحرف من اليسار؟"""
    return is_arabic_char(ch) and ch not in NON_JOINING_LEFT and ch != 'ـ'

def connects_right(ch):
    """هل يتصل الحرف من اليمين؟"""
    return is_arabic_char(ch) and ch != 'ـ'

def reshape_word(word):
    """يُشكّل كلمة عربية واحدة ويعكسها"""
    chars = list(word)
    n = len(chars)
    result = []
    
    i = 0
    while i < n:
        ch = chars[i]
        
        # لام + ألف ligature
        if ch == 'ل' and i + 1 < n and chars[i+1] in 'اأإآ':
            next_ch = chars[i+1]
            lig_key = 'ل' + next_ch
            if lig_key in ARABIC_CHAR_TABLE:
                forms = ARABIC_CHAR_TABLE[lig_key]
                # هل الـ ligature في آخر الكلمة؟
                prev_conn = (i > 0 and connects_left(chars[i-1]))
                if prev_conn:
                    result.append(forms[3])  # آخر
                else:
                    result.append(forms[0])  # معزول
                i += 2
                continue
        
        if not is_arabic_char(ch) or ch == 'ـ':
            result.append(ch)
            i += 1
            continue
        
        if ch not in ARABIC_CHAR_TABLE:
            result.append(ch)
            i += 1
            continue
        
        forms = ARABIC_CHAR_TABLE[ch]
        
        prev_conn = (i > 0 and connects_left(chars[i-1]))
        next_conn = (i < n-1 and connects_right(ch) and is_arabic_char(chars[i+1]))
        
        if prev_conn and next_conn and forms[2]:
            result.append(forms[2])   # وسط
        elif prev_conn and forms[3]:
            result.append(forms[3])   # آخر
        elif next_conn and forms[1]:
            result.append(forms[1])   # أول
        else:
            result.append(forms[0])   # معزول
        
        i += 1
    
    return ''.join(reversed(result))


def shape_arabic_text(text):
    """
    يُعالج نصاً عربياً كاملاً:
    1. يُشكّل كل كلمة عربية
    2. يعكس ترتيب الكلمات (RTL)
    3. يحافظ على الأرقام والرموز في مكانها
    """
    import re
    
    # قسّم النص إلى أجزاء عربية وغير عربية
    segments = re.split(r'(\s+)', text)
    
    arabic_segments = []
    other_segments = []
    result_parts = []
    
    for seg in segments:
        if not seg:
            continue
        if seg.strip() == '':
            result_parts.append(('space', seg))
        elif any(is_arabic_char(c) for c in seg):
            result_parts.append(('arabic', reshape_word(seg)))
        else:
            result_parts.append(('other', seg))
    
    # عكس ترتيب الأجزاء كلها (RTL) مع الحفاظ على المسافات
    # الطريقة: عكس العناصر غير المسافات
    non_spaces = [(t, v) for t, v in result_parts if t != 'space']
    spaces = [(t, v) for t, v in result_parts if t == 'space']
    
    non_spaces.reverse()
    
    # إعادة الدمج بنفس بنية المسافات
    final = []
    ni = 0
    for t, v in result_parts:
        if t == 'space':
            final.append(v)
        else:
            final.append(non_spaces[ni][1])
            ni += 1
    
    return ''.join(final)


# اختبار
tests = [
    "غازي علي صالح الغامدي",
    "السعودية",
    "اسامه صادق محمد",
    "الى من يهمه الامر",
    "طبيب عام",
    "عيادات",
    "ساعة و 15 دقيقة",
    "مستشفى الملك فهد بالباحة",
    "07:45 - 1447-11-09 مساءً",
]

for t in tests:
    shaped = shape_arabic_text(t)
    print(f"IN:  {t}")
    print(f"OUT: {shaped}")
    print()
