"""
╔══════════════════════════════════════════════════════════════════════════╗
║  📄 سيها — pdf_generator.py                                             ║
║  واجهة موحّدة لتوليد 3 أنواع PDF                                       ║
║                                                                          ║
║  report    → إجازة مرضية      (templates_NEE.pdf)                      ║
║  mashad    → مشهد مراجعة      (visit_template.pdf)                      ║
║  companion → مرافقة مريض      (companion_template.pdf)                  ║
║                                                                          ║
║  الاستخدام:                                                              ║
║    from pdf_generator import generate_pdf                               ║
║    pdf_bytes = generate_pdf("report", patient_data,                     ║
║                             hospital_data, doctor_data, rnum)           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import io
import os
import uuid
import tempfile
from datetime import datetime, timedelta
from typing import Any

# ── الاستيراد من الملفات الأصلية ──────────────────────────────────────────
from pdf_gen import (
    generate_excuse_pdf,
    to_hijri,
    to_hijri_duration,
    _to_en,
    nat_en,
    normalize_nat_ar,
    format_weekday_date,
)
from visit_pdf_gen import generate_visit_pdf
from companion_pdf_gen import generate_companion_pdf

TEMP_DIR = tempfile.gettempdir()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_REPORT    = os.path.join(BASE_DIR, "templates_NEE.pdf")
TEMPLATE_MASHAD    = os.path.join(BASE_DIR, "visit_template.pdf")
TEMPLATE_COMPANION = os.path.join(BASE_DIR, "companion_template.pdf")


# ════════════════════════════════════════════════════════════════════════════
#  🔧 دوال مساعدة مشتركة
# ════════════════════════════════════════════════════════════════════════════

def _cleanup(path: str | None) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def _logo_b64_to_tmp(logo_b64: str) -> str | None:
    """يحوّل base64 شعار إلى ملف PNG مؤقت — يُرجع المسار أو None."""
    if not logo_b64:
        return None
    try:
        import base64
        raw = logo_b64.split(",", 1)[1] if "," in logo_b64 else logo_b64
        img_data = base64.b64decode(raw + "==")
        fd, tmp = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, "wb") as f:
            f.write(img_data)
        return tmp
    except Exception:
        return None


def _fmt_date(val: str) -> str:
    """يُعيد التاريخ بصيغة DD-MM-YYYY."""
    if not val:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val.strip(), fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return val


# ════════════════════════════════════════════════════════════════════════════
#  1️⃣  إجازة مرضية — report
# ════════════════════════════════════════════════════════════════════════════
#
#  patient_data المتوقعة:
#    full_name / patient_name   — اسم المريض
#    id_number / patient_id     — رقم الهوية
#    nationality                — الجنسية
#    workplace / employer       — جهة العمل
#    excuse_date / leave_from   — تاريخ بداية الإجازة (DD-MM-YYYY أو YYYY-MM-DD)
#    days_count / leave_days    — عدد الأيام
#    exit_date / leave_to       — تاريخ نهاية الإجازة (اختياري)
#    issue_time                 — وقت الإصدار (اختياري)
#    issue_date / issue_date_input — تاريخ الإصدار (اختياري)
#    full_name_en               — الاسم الإنجليزي (اختياري)
#    doctor_name_en             — اسم الطبيب إنجليزي (اختياري)
#
#  hospital_data المتوقعة:
#    name_ar / hospital_name    — اسم المستشفى عربي
#    name_en / hospital_name_en — اسم المستشفى إنجليزي (اختياري)
#    logo_b64                   — شعار base64 (اختياري)
#    is_government              — 1 = حكومي، 0 = خاص
#    type / hospital_type       — 'خاص' | 'حكومي' | 'مجمعات' (اختياري)
#
#  doctor_data المتوقعة:
#    name_ar / doctor_name      — اسم الطبيب عربي
#    name_en / doctor_name_en   — اسم الطبيب إنجليزي (اختياري)
#    specialty                  — التخصص
#    license_no / license_number — رقم الترخيص (اختياري)
#
# ════════════════════════════════════════════════════════════════════════════

def _generate_report(
    patient_data: dict,
    hospital_data: dict,
    doctor_data: dict,
    rnum: str,
    website_url: str = "https://seha.sh",
) -> bytes:
    pd, hd, dd = patient_data, hospital_data, doctor_data

    order_data = {
        "full_name":        pd.get("full_name")       or pd.get("patient_name", ""),
        "id_number":        pd.get("id_number")        or pd.get("patient_id", ""),
        "nationality":      pd.get("nationality", ""),
        "workplace":        pd.get("workplace")        or pd.get("employer", ""),
        "excuse_date":      pd.get("excuse_date")      or pd.get("leave_from", ""),
        "days_count":       pd.get("days_count")       or pd.get("leave_days", 1),
        "exit_date":        pd.get("exit_date")        or pd.get("leave_to", ""),
        "issue_time":       pd.get("issue_time", ""),
        "issue_date_input": pd.get("issue_date_input") or pd.get("issue_date", ""),
        "full_name_en":     pd.get("full_name_en", ""),
        "doctor_name_en":   pd.get("doctor_name_en", ""),
    }

    hospital_name    = hd.get("name_ar")  or hd.get("hospital_name", "")
    hospital_name_en = hd.get("name_en")  or hd.get("hospital_name_en", "")
    logo_b64         = hd.get("logo_b64", "")

    hospital_type = hd.get("type") or hd.get("hospital_type")
    if hospital_type is None:
        hospital_type = "حكومي" if hd.get("is_government", 1) else "خاص"

    doctor_name    = dd.get("name_ar")   or dd.get("doctor_name", "")
    specialty      = dd.get("specialty", "")
    license_number = dd.get("license_no") or dd.get("license_number")

    issue_time = order_data["issue_time"] or datetime.now().strftime("%I:%M %p")

    tmp_logo = _logo_b64_to_tmp(logo_b64)
    out_path = os.path.join(TEMP_DIR, f"report_{uuid.uuid4().hex[:8]}.pdf")

    try:
        generate_excuse_pdf(
            order_data        = order_data,
            hospital          = hospital_name,
            doctor            = doctor_name,
            specialty         = specialty,
            issue_time        = issue_time,
            output_path       = out_path,
            logo_path         = tmp_logo,
            gsl_code          = rnum,
            license_number    = license_number,
            hospital_type     = hospital_type,
            website_url       = website_url,
            template_path     = TEMPLATE_REPORT,
            same_day_discharge = False,
            hospital_name_en  = hospital_name_en,
        )
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        _cleanup(tmp_logo)
        _cleanup(out_path)


# ════════════════════════════════════════════════════════════════════════════
#  2️⃣  مشهد مراجعة — mashad
# ════════════════════════════════════════════════════════════════════════════
#
#  patient_data المتوقعة:
#    patient_name / full_name   — اسم المريض
#    patient_id / id_number     — رقم الهوية
#    nationality                — الجنسية
#    employer / workplace       — جهة العمل
#    admission_date             — تاريخ الدخول
#    admission_time             — وقت الدخول  (اختياري)
#    discharge_date             — تاريخ الخروج
#    discharge_time             — وقت الخروج  (اختياري)
#    visit_type                 — نوع الزيارة: طوارئ/عيادة خارجية/مراجعة
#    issue_time                 — وقت الإصدار (اختياري)
#    issue_date                 — تاريخ الإصدار (اختياري)
#
# ════════════════════════════════════════════════════════════════════════════

_VTYPE_EN = {
    "طوارئ":         "Emergency",
    "عيادة خارجية": "Outpatient",
    "مراجعة":        "Follow-up",
    "إسعاف":         "Ambulance",
    "عيادة":         "Clinic",
    "إسعافي":        "Emergency",
}


def _calc_waiting(adm_date: str, adm_time: str,
                  dis_date: str, dis_time: str) -> tuple[str, str]:
    """يُرجع (waiting_ar, waiting_en)."""
    try:
        fmt = "%d-%m-%Y %H:%M" if adm_time else "%d-%m-%Y"
        adm_str = f"{adm_date} {adm_time}".strip() if adm_time else adm_date
        dis_str = f"{dis_date} {dis_time}".strip() if dis_time else dis_date
        adm_dt  = datetime.strptime(adm_str, fmt)
        dis_dt  = datetime.strptime(dis_str, fmt)
        delta   = dis_dt - adm_dt
        total_m = max(0, int(delta.total_seconds() / 60))
        h, m    = total_m // 60, total_m % 60
        d       = delta.days
        if d >= 1:
            return f"{d} يوم {h % 24} ساعة", f"{d} day{'s' if d>1 else ''} {h%24} hr"
        elif h > 0:
            ar = f"{h} ساعة {m} دقيقة" if m else f"{h} ساعة"
            en = f"{h} hr {m} min" if m else f"{h} hr"
            return ar, en
        return f"{total_m} دقيقة", f"{total_m} min"
    except Exception:
        return "—", "—"


def _generate_mashad(
    patient_data: dict,
    hospital_data: dict,
    doctor_data: dict,
    rnum: str,
    website_url: str = "https://seha.sh",
) -> bytes:
    pd, hd, dd = patient_data, hospital_data, doctor_data

    full_name    = pd.get("patient_name")  or pd.get("full_name", "")
    id_number    = pd.get("patient_id")    or pd.get("id_number", "")
    nationality  = pd.get("nationality", "")
    employer     = pd.get("employer")      or pd.get("workplace", "")
    adm_date     = _fmt_date(pd.get("admission_date", ""))
    adm_time     = pd.get("admission_time", "")
    dis_date     = _fmt_date(pd.get("discharge_date") or adm_date)
    dis_time     = pd.get("discharge_time", "")
    visit_type_ar = pd.get("visit_type", "مراجعة")
    visit_type_en = _VTYPE_EN.get(visit_type_ar, visit_type_ar)
    issue_time   = pd.get("issue_time", "") or datetime.now().strftime("%I:%M %p")
    issue_date   = _fmt_date(pd.get("issue_date") or dis_date) or dis_date

    try:
        issue_dt = datetime.strptime(issue_date, "%d-%m-%Y")
    except Exception:
        issue_dt = datetime.now()

    wait_ar, wait_en = _calc_waiting(adm_date, adm_time, dis_date, dis_time)

    hijri_adm = to_hijri(adm_date)
    hijri_dis = to_hijri(dis_date)

    name_en = pd.get("full_name_en", "") or _to_en(full_name)
    nat_en_ = nat_en(nationality)
    doc_ar  = dd.get("name_ar")   or dd.get("doctor_name", "")
    doc_en  = dd.get("name_en")   or dd.get("doctor_name_en", "") or _to_en(doc_ar)
    spec    = dd.get("specialty", "")
    spec_en = _to_en(spec) if spec else ""
    hosp_ar = hd.get("name_ar")  or hd.get("hospital_name", "")
    hosp_en = hd.get("name_en")  or hd.get("hospital_name_en", "") or _to_en(hosp_ar)

    def _disp(d: str, t: str = "") -> str:
        return f"{d} {t}".strip() if t else d

    data = {
        "leave_id":           rnum,
        "admission_date_en":  _disp(adm_date, adm_time),
        "admission_date_ar":  _disp(hijri_adm, adm_time),
        "discharge_date_en":  _disp(dis_date, dis_time),
        "discharge_date_ar":  _disp(hijri_dis, dis_time),
        "waiting_period_en":  wait_en,
        "waiting_period_ar":  wait_ar,
        "issue_date":         issue_date,
        "name_en":            (name_en or full_name).upper(),
        "name_ar":            full_name,
        "national_id":        id_number,
        "nationality_en":     nat_en_,
        "nationality_ar":     normalize_nat_ar(nationality),
        "employer_ar":        employer,
        "practitioner_en":    (doc_en or doc_ar).upper(),
        "practitioner_ar":    doc_ar,
        "position_en":        spec_en or spec,
        "position_ar":        spec,
        "visit_type_en":      visit_type_en,
        "visit_type_ar":      visit_type_ar,
        "hospital_ar":        hosp_ar,
        "hospital_en":        hosp_en if hosp_en and not any('\u0600'<=c<='\u06FF' for c in hosp_en) else "",
        "logo_data":          hd.get("logo_b64", ""),
        "issue_time":         issue_time,
        "issue_weekday_date": format_weekday_date(issue_dt),
    }

    out_path = os.path.join(TEMP_DIR, f"mashad_{uuid.uuid4().hex[:8]}.pdf")
    try:
        generate_visit_pdf(
            data          = data,
            output_path   = out_path,
            template_path = TEMPLATE_MASHAD,
            website_url   = website_url,
        )
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        _cleanup(out_path)


# ════════════════════════════════════════════════════════════════════════════
#  3️⃣  مرافقة مريض — companion
# ════════════════════════════════════════════════════════════════════════════
#
#  patient_data المتوقعة:
#    companion_name             — اسم المرافق
#    national_id / patient_id   — رقم هوية المرافق
#    nationality                — جنسية المرافق
#    relation                   — صلة القرابة (زوج/ابن/أخ/والد...)
#    employer / workplace       — جهة عمل المرافق
#    admission_date             — تاريخ الدخول
#    discharge_date             — تاريخ الخروج
#    issue_date                 — تاريخ الإصدار (اختياري)
#    issue_time                 — وقت الإصدار   (اختياري)
#
# ════════════════════════════════════════════════════════════════════════════

_RELATION_EN = {
    "زوج": "Husband", "زوجة": "Wife",
    "ابن": "Son",     "ابنة": "Daughter",
    "أخ":  "Brother", "أخت":  "Sister",
    "والد": "Father",  "والدة": "Mother",
    "أب":  "Father",  "أم":   "Mother",
}


def _generate_companion(
    patient_data: dict,
    hospital_data: dict,
    doctor_data: dict,
    rnum: str,
    website_url: str = "https://seha.sh",
) -> bytes:
    pd, hd, dd = patient_data, hospital_data, doctor_data

    comp_name   = pd.get("companion_name", "")
    national_id = pd.get("national_id")   or pd.get("patient_id", "")
    nationality = pd.get("nationality", "")
    relation_ar = pd.get("relation", "")
    relation_en = _RELATION_EN.get(relation_ar) or _to_en(relation_ar) or relation_ar
    employer    = pd.get("employer")      or pd.get("workplace", "")
    adm_date    = _fmt_date(pd.get("admission_date", ""))
    dis_date    = _fmt_date(pd.get("discharge_date") or adm_date)
    issue_date  = _fmt_date(pd.get("issue_date") or dis_date) or dis_date
    issue_time  = pd.get("issue_time", "") or datetime.now().strftime("%I:%M %p")

    try:
        issue_dt = datetime.strptime(issue_date, "%d-%m-%Y")
    except Exception:
        issue_dt = datetime.now()

    # مدة المرافقة
    try:
        d1   = datetime.strptime(adm_date, "%d-%m-%Y")
        d2   = datetime.strptime(dis_date, "%d-%m-%Y")
        days = max(1, (d2 - d1).days + 1)
    except Exception:
        days = 1

    hijri_adm = to_hijri(adm_date)
    hijri_dis = to_hijri(dis_date)
    dur_en    = f"{days} {'day' if days==1 else 'days'} ( {adm_date} to {dis_date} )"
    dur_ar    = to_hijri_duration(days, hijri_adm, hijri_dis)

    comp_name_en = _to_en(comp_name)
    nat_en_      = nat_en(nationality)
    doc_ar  = dd.get("name_ar")  or dd.get("doctor_name", "")
    doc_en  = dd.get("name_en")  or dd.get("doctor_name_en", "") or _to_en(doc_ar)
    spec    = dd.get("specialty", "")
    spec_en = _to_en(spec) if spec else ""
    hosp_ar = hd.get("name_ar") or hd.get("hospital_name", "")
    hosp_en = hd.get("name_en") or hd.get("hospital_name_en", "") or _to_en(hosp_ar)

    data = {
        "leave_id":           rnum,
        "leave_duration_en":  dur_en,
        "leave_duration_ar":  dur_ar,
        "admission_date_en":  adm_date,
        "admission_date_ar":  hijri_adm,
        "discharge_date_en":  dis_date,
        "discharge_date_ar":  hijri_dis,
        "issue_date":         issue_date,
        "companion_name_en":  (comp_name_en or comp_name).upper(),
        "companion_name_ar":  comp_name,
        "national_id":        national_id,
        "nationality_en":     nat_en_,
        "nationality_ar":     normalize_nat_ar(nationality),
        "relation_en":        relation_en,
        "relation_ar":        relation_ar,
        "employer_ar":        employer,
        "physician_name_en":  (doc_en or doc_ar).upper(),
        "physician_name_ar":  doc_ar,
        "position_en":        spec_en or spec,
        "position_ar":        spec,
        "hospital_ar":        hosp_ar,
        "hospital_en":        hosp_en if hosp_en and not any('\u0600'<=c<='\u06FF' for c in hosp_en) else "",
        "logo_data":          hd.get("logo_b64", ""),
        "issue_time":         issue_time,
        "issue_weekday_date": format_weekday_date(issue_dt),
    }

    out_path = os.path.join(TEMP_DIR, f"companion_{uuid.uuid4().hex[:8]}.pdf")
    try:
        generate_companion_pdf(
            data          = data,
            output_path   = out_path,
            template_path = TEMPLATE_COMPANION,
            website_url   = website_url,
        )
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        _cleanup(out_path)


# ════════════════════════════════════════════════════════════════════════════
#  🚀 الواجهة العامة الموحّدة
# ════════════════════════════════════════════════════════════════════════════

_GENERATORS = {
    "report":     _generate_report,
    "sick_leave": _generate_report,    # alias
    "mashad":     _generate_mashad,
    "visit":      _generate_mashad,    # alias
    "companion":  _generate_companion,
}


def generate_pdf(
    report_type: str,
    patient_data: dict[str, Any],
    hospital_data: dict[str, Any],
    doctor_data: dict[str, Any],
    rnum: str,
    website_url: str = "https://seha.sh",
) -> bytes:
    """
    يولّد PDF ويُرجع bytes جاهزة للإرسال أو الحفظ.

    المعاملات:
        report_type   — "report" | "mashad" | "companion"
                        ("sick_leave" و"visit" أسماء بديلة مقبولة)
        patient_data  — بيانات المريض/المرافق
        hospital_data — بيانات المستشفى من DB
        doctor_data   — بيانات الطبيب من DB
        rnum          — رقم التقرير الفريد
        website_url   — رابط موقع سيها للـ QR Code (اختياري)

    مثال:
        pdf = generate_pdf(
            "report",
            {"patient_name": "أحمد الغامدي", "patient_id": "1054823917",
             "nationality": "سعودي", "employer": "أرامكو",
             "excuse_date": "20-04-2026", "days_count": 3},
            {"name_ar": "مستشفى الملك فهد", "is_government": 1, "logo_b64": ""},
            {"name_ar": "د. خالد العمري", "specialty": "طب عام"},
            rnum="SH000001ABCD",
        )
        await message.reply_document(io.BytesIO(pdf), filename=f"{rnum}.pdf")
    """
    key = report_type.strip().lower()
    if key not in _GENERATORS:
        raise ValueError(
            f"نوع تقرير غير معروف: '{report_type}'. "
            "الأنواع المتاحة: report, mashad, companion"
        )
    return _GENERATORS[key](patient_data, hospital_data, doctor_data, rnum, website_url)


# ════════════════════════════════════════════════════════════════════════════
#  🧪 اختبار: python pdf_generator.py [report|mashad|companion]
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    SAMPLE_PATIENT = {
        # report
        "patient_name": "أحمد محمد الغامدي",
        "patient_id":   "1054823917",
        "nationality":  "سعودي",
        "employer":     "أرامكو السعودية",
        "excuse_date":  "20-04-2026",
        "days_count":   3,
        "issue_time":   "10:30 AM",
        # mashad
        "admission_date": "20-04-2026",
        "admission_time": "08:00",
        "discharge_date": "20-04-2026",
        "discharge_time": "10:15",
        "visit_type":     "طوارئ",
        # companion
        "companion_name": "محمد عبدالله العمري",
        "national_id":    "1057834629",
        "relation":       "زوج",
    }
    SAMPLE_HOSPITAL = {
        "name_ar":       "مستشفى الملك فهد التخصصي",
        "name_en":       "King Fahad Specialist Hospital",
        "is_government": 1,
        "logo_b64":      "",
    }
    SAMPLE_DOCTOR = {
        "name_ar":    "د. أحمد بن محمد الغامدي",
        "name_en":    "Dr. Ahmed Al-Ghamdi",
        "specialty":  "طب داخلي",
        "license_no": "SAU-12345",
    }

    types = sys.argv[1:] or ["report", "mashad", "companion"]
    for t in types:
        try:
            pdf = generate_pdf(t, SAMPLE_PATIENT, SAMPLE_HOSPITAL, SAMPLE_DOCTOR, "SH000001TEST")
            out = f"test_{t}.pdf"
            with open(out, "wb") as f:
                f.write(pdf)
            print(f"✅ {t:12s} → {out}  ({len(pdf):,} bytes)")
        except FileNotFoundError as e:
            print(f"⚠️  {t:12s} → {e}")
        except Exception as e:
            import traceback
            print(f"❌ {t:12s} → {e}")
            traceback.print_exc()
