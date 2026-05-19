# ============================================================
#  arabic_transliterate.py
#  نظام تحويل الأسماء العربية → إنجليزية
#  معتمد على نظام الجوازات السعودية (ALA-LC)
#  يمكن ربطه مباشرة ببوت التيليغرام
# ============================================================

import re
import unicodedata

# ─────────────────────────────────────────────
#  1) جدول الحروف (نظام الجوازات السعودية)
# ─────────────────────────────────────────────
CHAR_MAP = {
    # حروف أساسية
    "ا": "A",  "أ": "A",  "إ": "I",  "آ": "AA",
    "ب": "B",  "ت": "T",  "ث": "TH",
    "ج": "J",  "ح": "H",  "خ": "KH",
    "د": "D",  "ذ": "TH", "ر": "R",  "ز": "Z",
    "س": "S",  "ش": "SH", "ص": "S",  "ض": "D",
    "ط": "T",  "ظ": "TH", "ع": "A",  "غ": "GH",
    "ف": "F",  "ق": "Q",  "ك": "K",  "ل": "L",
    "م": "M",  "ن": "N",  "ه": "H",  "و": "W",
    "ي": "Y",  "ى": "A",  "ة": "H",
    # همزات
    "ء": "",   "ئ": "Y",  "ؤ": "W",
    # حروف خاصة
    "لا": "LA", "لأ": "LA", "لإ": "LI", "لآ": "LAA",
    # تنوين وحركات (تُحذف)
    "\u064b": "", "\u064c": "", "\u064d": "",
    "\u064e": "", "\u064f": "", "\u0650": "",
    "\u0651": "", "\u0652": "", "\u0670": "",
    # أل التعريف
    "ال": "AL-",
}

# ─────────────────────────────────────────────
#  2) قاموس الأسماء الشائعة (مطابق للجوازات)
#     الأكثر شيوعاً في السعودية
# ─────────────────────────────────────────────
NAMES_DICT = {
    # أسماء ذكور
    "محمد": "MOHAMMED",    "أحمد": "AHMED",       "عبدالله": "ABDULLAH",
    "عبدالرحمن": "ABDULRAHMAN", "عمر": "OMAR",    "علي": "ALI",
    "إبراهيم": "IBRAHIM",  "خالد": "KHALID",      "يوسف": "YOUSUF",
    "عبدالعزيز": "ABDULAZIZ", "سعد": "SAAD",      "فهد": "FAHAD",
    "سلطان": "SULTAN",     "نايف": "NAIF",        "فيصل": "FAISAL",
    "تركي": "TURKI",       "سلمان": "SALMAN",     "بندر": "BANDAR",
    "ماجد": "MAJED",       "وليد": "WALEED",      "هاني": "HANI",
    "زياد": "ZIYAD",       "رامي": "RAMI",        "باسم": "BASIM",
    "عصام": "ESSAM",       "طارق": "TARIQ",       "هشام": "HISHAM",
    "كريم": "KARIM",       "ياسر": "YASSER",      "أسامة": "OSAMA",
    "راشد": "RASHED",      "حمد": "HAMAD",        "ناصر": "NASSER",
    "حسن": "HASSAN",       "حسين": "HUSSAIN",     "جاسم": "JASIM",
    "منصور": "MANSOUR",    "صالح": "SALEH",       "عادل": "ADEL",
    "وائل": "WAEL",        "بلال": "BILAL",       "مشعل": "MISHAL",
    "سامي": "SAMI",        "معاذ": "MUATH",       "جابر": "JABER",
    "عمر": "OMAR",         "أنس": "ANAS",         "شريف": "SHERIF",
    "ممدوح": "MAMDOUH",    "وسيم": "WASEEM",      "أيمن": "AYMAN",
    "حازم": "HAZEM",       "كامل": "KAMEL",       "رياض": "RIYAD",
    "عبدالمجيد": "ABDULMAJEED", "عبدالله": "ABDULLAH", "عبدالكريم": "ABDULKARIM",
    "عبدالحميد": "ABDULHAMID", "عبدالواحد": "ABDULWAHID",
    "عبدالرحيم": "ABDULRAHIM", "عبدالقادر": "ABDULQADER",
    "عبدالمالك": "ABDULMALIK", "عبدالسلام": "ABDULSALAM",
    "محمود": "MAHMOUD",    "جمال": "JAMAL",       "نواف": "NAWAF",
    "ثامر": "THAMER",      "غازي": "GHAZI",       "مبارك": "MUBARAK",
    "ضياء": "DIAA",        "لؤي": "LUAY",         "رفيق": "RAFIQ",
    "شهاب": "SHIHAB",      "مصطفى": "MUSTAFA",    "مازن": "MAZEN",
    "داود": "DAWOOD",      "عيسى": "ESSA",        "موسى": "MUSA",
    "يحيى": "YAHYA",       "زكريا": "ZAKARIA",    "إسماعيل": "ISMAIL",
    "صلاح": "SALAH",       "قاسم": "QASIM",       "لطيف": "LATIF",
    "رضا": "RIDA",         "عمار": "AMMAR",       "قيس": "QAIS",
    "ريان": "RYAN",        "آدم": "ADAM",

    # أسماء إناث
    "فاطمة": "FATIMAH",    "نورة": "NOURA",       "سارة": "SARAH",
    "منى": "MONA",         "هند": "HIND",         "ريم": "REEM",
    "لينا": "LINA",        "مريم": "MARYAM",      "أميرة": "AMIRA",
    "دانا": "DANA",        "رنا": "RANA",         "ليلى": "LAYLA",
    "سلمى": "SALMA",       "شيماء": "SHAIMAA",    "غادة": "GHADA",
    "أسماء": "ASMA",       "رهف": "RAHAF",        "بشرى": "BUSHRA",
    "حنان": "HANAN",       "إيمان": "IMAN",       "وفاء": "WAFA",
    "نادية": "NADIA",      "سوسن": "SAWSAN",      "أمل": "AMAL",
    "هيفاء": "HAIFA",      "ميساء": "MAISA",      "أريج": "AREEJ",
    "رغد": "RAGHAD",       "ديمة": "DIMA",        "شذى": "SHATHA",
    "نجلاء": "NAJLA",      "ابتسام": "IBTISAM",   "عبير": "ABEER",
    "سمر": "SAMAR",        "ولاء": "WALAA",       "تهاني": "TAHANI",
    "جواهر": "JAWAHER",    "نوف": "NOUF",         "زينب": "ZAINAB",
    "خديجة": "KHADIJAH",   "عائشة": "AISHA",      "رقية": "RUQAYA",
    "أروى": "ARWA",        "وجدان": "WIJDAN",     "مها": "MAHA",
    "يارا": "YARA",        "لمى": "LAMA",         "روان": "RAWAN",
    "جنى": "JANA",         "سدرة": "SIDRA",       "هلا": "HALA",
    "نغم": "NAGHAM",       "شروق": "SHUROUQ",     "إشراق": "ISHRAQ",

    # ألقاب / كُنى شائعة
    "ابن": "IBN",          "بنت": "BINT",         "ام": "UMM",
    "ابو": "ABU",          "أبو": "ABU",

    # أسماء قبائل / عائلات شائعة
    "الغامدي": "AL-GHAMDI",     "الزهراني": "AL-ZAHRANI",
    "الشهري": "AL-SHAHRI",      "القحطاني": "AL-QAHTANI",
    "العتيبي": "AL-OTAIBI",     "الشمري": "AL-SHAMMARI",
    "الحربي": "AL-HARBI",       "الدوسري": "AL-DOSARI",
    "المطيري": "AL-MUTAIRI",    "السبيعي": "AL-SUBAIE",
    "البقمي": "AL-BAQAMI",      "الرشيدي": "AL-RASHIDI",
    "العنزي": "AL-ANZI",        "الرويلي": "AL-RUWAILI",
    "البلوي": "AL-BALAWI",      "الجهني": "AL-JOHANI",
    "السلمي": "AL-SALMI",       "الأسمري": "AL-ASMARI",
    "الثقفي": "AL-THAQAFI",     "الغريبي": "AL-GHARIBI",
    "العمري": "AL-OMARI",       "الخثعمي": "AL-KHATHAMI",
    "الحازمي": "AL-HAZMI",      "السهلي": "AL-SAHLI",
    "الأحمدي": "AL-AHMADI",     "المالكي": "AL-MALIKI",
    "الزيدي": "AL-ZAIDI",       "اليامي": "AL-YAMI",
    "العمراني": "AL-OMRANI",    "الصاعدي": "AL-SAEDI",
    "السيد": "AL-SAYED",        "آل سعود": "AL SAUD",
    "الخالدي": "AL-KHALIDI",    "العبدلي": "AL-ABDALI",
    "الصبحي": "AL-SOBHI",       "الحمدان": "AL-HAMDAN",
    "الشيخ": "AL-SHEIKH",       "الأمير": "AL-AMIR",
}

# ─────────────────────────────────────────────
#  3) دالة التطبيع (تنظيف النص)
# ─────────────────────────────────────────────
def _normalize(text: str) -> str:
    """تنظيف النص من التشكيل والمسافات الزائدة"""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)  # حذف التشكيل
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ─────────────────────────────────────────────
#  4) الدالة الرئيسية للتحويل
# ─────────────────────────────────────────────
def transliterate_name(arabic_name: str) -> str:
    """
    تحويل الاسم العربي → إنجليزي بنظام الجوازات السعودية
    
    المنطق:
    1. بحث مباشر في القاموس (أدق)
    2. تحويل كلمة بكلمة من القاموس
    3. تحويل حرف بحرف (ALA-LC)
    
    مثال:
        transliterate_name("محمد أحمد الغامدي")
        → "MOHAMMED AHMED AL-GHAMDI"
    """
    if not arabic_name:
        return ""
    
    # إذا كان النص إنجليزي أصلاً
    if not any("\u0600" <= c <= "\u06FF" for c in arabic_name):
        return arabic_name.upper()
    
    name = _normalize(arabic_name)
    
    # ── البحث في القاموس الكامل أولاً ──
    if name in NAMES_DICT:
        return NAMES_DICT[name]
    
    # ── تحويل كلمة بكلمة ──
    parts = name.split()
    result_parts = []
    
    for part in parts:
        if part in NAMES_DICT:
            result_parts.append(NAMES_DICT[part])
        else:
            result_parts.append(_char_transliterate(part))
    
    return " ".join(result_parts)


def _char_transliterate(word: str) -> str:
    """تحويل حرف بحرف باستخدام جدول ALA-LC"""
    # معالجة "ال" التعريف
    if word.startswith("ال"):
        rest = word[2:]
        # شمسية أم قمرية؟
        solar = "تثدذرزسشصضطظلن"
        if rest and rest[0] in solar:
            prefix = "AL-" + CHAR_MAP.get(rest[0], rest[0])
            rest = rest[1:]
        else:
            prefix = "AL-"
        return prefix + _letters_to_en(rest)
    
    return _letters_to_en(word)


def _letters_to_en(word: str) -> str:
    """تحويل حروف الكلمة"""
    result = []
    i = 0
    while i < len(word):
        # فحص مجموعات من حرفين أولاً (لا، لأ...)
        two = word[i:i+2]
        if two in CHAR_MAP:
            result.append(CHAR_MAP[two])
            i += 2
            continue
        ch = word[i]
        result.append(CHAR_MAP.get(ch, ch))
        i += 1
    return "".join(result).upper()


# ─────────────────────────────────────────────
#  5) دالة مساعدة لتنسيق الاسم الكامل
# ─────────────────────────────────────────────
def format_patient_name(arabic_name: str) -> str:
    """
    تنسيق اسم المريض للتقرير الطبي
    يُرجع الاسم بحروف كبيرة ومنسق
    """
    en = transliterate_name(arabic_name)
    # إزالة المسافات المتكررة وتنظيف
    en = re.sub(r"\s+", " ", en).strip()
    return en


# ─────────────────────────────────────────────
#  6) كيفية ربطه بالبوت (استبدال _translate_sync)
# ─────────────────────────────────────────────
"""
في ملف bot.py استبدل دالة _translate_sync بهذا الكود:

from arabic_transliterate import transliterate_name

def _translate_sync(text: str) -> str:
    if not text: return ""
    text = text.strip()
    
    # إذا لا يحتوي على عربي
    if not any('\u0600' <= c <= '\u06FF' for c in text):
        return text.upper()
    
    # ── 1) القاموس المحلي (أسرع وأدق) ──
    local = transliterate_name(text)
    if local and local != text.upper():
        return local
    
    # ── 2) Cerebras AI ──
    # ... (الكود الحالي)
    
    # ── 3) Groq AI ──
    # ... (الكود الحالي)
    
    # ── 4) Google Translate ──
    # ... (الكود الحالي)
    
    return text.upper()
"""


# ─────────────────────────────────────────────
#  7) اختبار سريع
# ─────────────────────────────────────────────
if __name__ == "__main__":
    test_names = [
        "محمد أحمد الغامدي",
        "فاطمة علي الزهراني",
        "عبدالرحمن خالد القحطاني",
        "نورة سعد العتيبي",
        "إبراهيم محمود الشمري",
        "مريم عبدالله الحربي",
        "خالد ناصر الدوسري",
        "سارة محمد الشهري",
        "عمر فهد المطيري",
        "هند يوسف السبيعي",
    ]
    
    print("=" * 55)
    print(f"{'الاسم العربي':<30} {'الاسم الإنجليزي'}")
    print("=" * 55)
    for name in test_names:
        en = transliterate_name(name)
        print(f"{name:<30} {en}")
    print("=" * 55)
