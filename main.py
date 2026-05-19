"""
╔══════════════════════════════════════════════════════════════════════════╗
║  🏥 سيها Backend — FastAPI + SQLite                                     ║
║  نظام إدارة التقارير الطبية — ملف واحد شامل                            ║
╚══════════════════════════════════════════════════════════════════════════╝

تشغيل:
    pip install fastapi uvicorn python-jose[cryptography] passlib[bcrypt]
    uvicorn main:app --reload --port 8000

Swagger UI:
    http://localhost:8000/docs
"""

from __future__ import annotations
import sqlite3, json, os, hashlib, secrets, random, string
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Depends, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import io

# ══════════════════════════════════════════════════════
#  ⚙️ الإعدادات
# ══════════════════════════════════════════════════════

DB_PATH      = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "seha.db"))
# إنشاء مجلد data إذا لم يكن موجوداً
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
SECRET_KEY   = os.environ.get("SECRET_KEY", "seha-secret-key-change-in-prod-2025")
REPORT_PRICE = 10.0   # سعر التقرير الافتراضي بالريال

# ══════════════════════════════════════════════════════
#  🗄️ قاعدة البيانات — SQLite
# ══════════════════════════════════════════════════════

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def db_ctx():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """إنشاء الجداول وتعبئة البيانات الأولية"""
    with db_ctx() as conn:
        cur = conn.cursor()
        cur.executescript("""
        -- ══ المستخدمون ══
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id   INTEGER UNIQUE,
            name          TEXT    DEFAULT '',
            username      TEXT    DEFAULT '',
            balance       REAL    DEFAULT 0,
            reports_count INTEGER DEFAULT 0,
            role          TEXT    DEFAULT 'user',   -- user | admin | agent
            status        TEXT    DEFAULT 'active', -- active | banned | suspended
            date_pref     TEXT    DEFAULT 'gregorian',
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- ══ المستشفيات ══
        CREATE TABLE IF NOT EXISTS hospitals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ar       TEXT    NOT NULL,
            name_en       TEXT    DEFAULT '',
            city          TEXT    DEFAULT '',
            type          TEXT    DEFAULT 'مستشفى',   -- مستشفى | مركز صحي | عيادة
            logo_b64      TEXT    DEFAULT '',
            is_government INTEGER DEFAULT 1,
            entity_id     INTEGER DEFAULT NULL,
            status        TEXT    DEFAULT 'active',   -- active | inactive
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- ══ الأطباء ══
        CREATE TABLE IF NOT EXISTS doctors (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id   INTEGER NOT NULL REFERENCES hospitals(id),
            name_ar       TEXT    NOT NULL,
            name_en       TEXT    DEFAULT '',
            specialty     TEXT    DEFAULT 'طب عام',
            license_no    TEXT    DEFAULT '',
            status        TEXT    DEFAULT 'active',
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- ══ التقارير ══
        CREATE TABLE IF NOT EXISTS reports (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL REFERENCES users(id),
            hospital_id       INTEGER REFERENCES hospitals(id),
            doctor_id         INTEGER REFERENCES doctors(id),
            report_type       TEXT    DEFAULT 'sick_leave',
            patient_data_json TEXT    DEFAULT '{}',
            rnum              TEXT    UNIQUE,
            pdf_path          TEXT    DEFAULT '',
            created_at        TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- ══ الباقات ══
        CREATE TABLE IF NOT EXISTS packages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            price         REAL    NOT NULL,
            reports_count INTEGER NOT NULL,
            is_active     INTEGER DEFAULT 1,
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- ══ المعاملات المالية ══
        CREATE TABLE IF NOT EXISTS transactions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            type       TEXT    NOT NULL, -- charge | deduct | refund | bonus
            amount     REAL    NOT NULL,
            note       TEXT    DEFAULT '',
            created_at TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- ══ الإعدادات ══
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );

        -- ══ المرضى المحفوظون ══
        CREATE TABLE IF NOT EXISTS saved_patients (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id),
            patient_name TEXT    NOT NULL,
            patient_id   TEXT    NOT NULL,
            birth_date   TEXT    DEFAULT '',
            phone        TEXT    DEFAULT '',
            employer     TEXT    DEFAULT '',
            nationality  TEXT    DEFAULT 'سعودي',
            created_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, patient_id)
        );
        """)

        # ══ الإعدادات الافتراضية ══
        defaults = [
            ('report_price',        str(REPORT_PRICE)),
            ('report_counter',      '0'),
            ('support_whatsapp',    '966501234567'),
            ('bot_maintenance',     '0'),
            ('web_url',             'https://seha.sh'),
            ('date_format',         'gregorian'),
            ('app_name',            'سيها'),
            ('version',             '2.0.0'),
        ]
        for k, v in defaults:
            cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))

        # ══ seed: المستشفيات ══
        hospitals_seed = [
            ("مستشفى الملك فهد التخصصي",       "King Fahad Specialist Hospital",   "الرياض",   "مستشفى",     1),
            ("مستشفى الملك فيصل التخصصي",       "King Faisal Specialist Hospital",  "الرياض",   "مستشفى",     1),
            ("مستشفى الملك عبدالعزيز",          "King Abdulaziz Hospital",          "جدة",      "مستشفى",     1),
            ("مستشفى الملك خالد التخصصي",       "King Khaled Specialist Hospital",  "الرياض",   "مستشفى",     1),
            ("مستشفى الملك سلمان",              "King Salman Hospital",             "الرياض",   "مستشفى",     1),
            ("مستشفى الأمير محمد بن عبدالعزيز", "Prince Mohammed bin Abdulaziz Hospital","المدينة","مستشفى",   1),
            ("مستشفى قوى الأمن",               "Security Forces Hospital",          "الرياض",   "مستشفى",     1),
            ("المجمع الطبي الأول",              "Al Awal Medical Complex",          "الرياض",   "عيادة",      0),
            ("مستشفى السعودي الألماني",         "Saudi German Hospital",             "جدة",      "مستشفى",     0),
            ("مستشفى الحمادي",                 "Al Hamadi Hospital",                "الرياض",   "مستشفى",     0),
            ("مركز الرعاية الأولية الشمال",    "North Primary Care Center",        "الرياض",   "مركز صحي",   1),
            ("مركز طب الأسرة",                "Family Medicine Center",            "جدة",      "مركز صحي",   1),
        ]
        for (name_ar, name_en, city, htype, is_gov) in hospitals_seed:
            cur.execute("""
                INSERT OR IGNORE INTO hospitals(name_ar, name_en, city, type, is_government)
                VALUES (?,?,?,?,?)
            """, (name_ar, name_en, city, htype, is_gov))

        # ══ seed: الأطباء ══
        doctors_seed = [
            (1, "د. أحمد بن محمد الغامدي",  "Dr. Ahmed Al-Ghamdi",   "طب داخلي",    "SAU-12345"),
            (1, "د. سارة بنت علي العمري",    "Dr. Sara Al-Omari",     "طب أطفال",    "SAU-12346"),
            (1, "د. خالد بن عبدالله القحطاني","Dr. Khalid Al-Qahtani", "طب طوارئ",   "SAU-12347"),
            (2, "د. فهد بن سعد الدوسري",    "Dr. Fahad Al-Dosari",   "جراحة عامة",  "SAU-22348"),
            (2, "د. نورة بنت محمد الشهراني", "Dr. Noura Al-Shahrani",  "طب عيون",    "SAU-22349"),
            (3, "د. عبدالرحمن بن يوسف الزهراني","Dr. Abdulrahman Al-Zahrani","طب عام","SAU-32350"),
            (3, "د. منى بنت سالم البقمي",    "Dr. Mona Al-Baqmi",    "أمراض نساء",  "SAU-32351"),
            (4, "د. محمد بن إبراهيم العصيمي","Dr. Mohammed Al-Otaibi","أمراض قلب",   "SAU-42352"),
            (5, "د. ريم بنت عبدالله السبيعي","Dr. Reem Al-Subaie",    "طب أطفال",    "SAU-52353"),
            (6, "د. طارق بن حمد الحربي",    "Dr. Tariq Al-Harbi",    "طب طوارئ",   "SAU-62354"),
            (7, "د. هند بنت عمر المطيري",    "Dr. Hind Al-Mutairi",   "طب عام",     "SAU-72355"),
            (8, "د. بدر بن سليمان الرشيدي",  "Dr. Badr Al-Rashidi",   "طب عائلة",   "SAU-82356"),
        ]
        for (hid, name_ar, name_en, spec, lic) in doctors_seed:
            cur.execute("""
                INSERT OR IGNORE INTO doctors(hospital_id, name_ar, name_en, specialty, license_no)
                VALUES (?,?,?,?,?)
            """, (hid, name_ar, name_en, spec, lic))

        # ══ seed: الباقات ══
        packages_seed = [
            ("باقة المبتدئ",   50,   5),
            ("باقة الأساسية",  90,   10),
            ("باقة الاحترافية",150,  20),
            ("باقة الذهبية",   250,  40),
            ("باقة البلاتينية",400,  75),
        ]
        for (name, price, count) in packages_seed:
            cur.execute("""
                INSERT OR IGNORE INTO packages(name, price, reports_count)
                VALUES (?,?,?)
            """, (name, price, count))

        # ══ seed: مستخدم admin ══
        cur.execute("""
            INSERT OR IGNORE INTO users(telegram_id, name, username, balance, role, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (5562670260, "المدير", "admin", 1000.0, "admin", "active"))


# ══════════════════════════════════════════════════════
#  🔑 المصادقة — Token بسيط
# ══════════════════════════════════════════════════════

security = HTTPBearer(auto_error=False)

def _make_token(telegram_id: int) -> str:
    payload = f"{telegram_id}:{SECRET_KEY}"
    return hashlib.sha256(payload.encode()).hexdigest()

def _verify_token(token: str) -> Optional[dict]:
    with db_ctx() as conn:
        users = conn.execute(
            "SELECT * FROM users WHERE status != 'banned'", ()
        ).fetchall()
        for u in users:
            if _make_token(u["telegram_id"]) == token:
                return dict(u)
    return None

def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    if not creds:
        raise HTTPException(401, "مطلوب تسجيل الدخول")
    user = _verify_token(creds.credentials)
    if not user:
        raise HTTPException(401, "رمز غير صالح أو منتهي")
    return user

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "صلاحية المسؤول مطلوبة")
    return user

# ══════════════════════════════════════════════════════
#  📐 نماذج Pydantic
# ══════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    telegram_id: int
    name: Optional[str] = ""
    username: Optional[str] = ""

class HospitalCreate(BaseModel):
    name_ar:       str
    name_en:       str   = ""
    city:          str   = ""
    type:          str   = "مستشفى"
    logo_b64:      str   = ""
    is_government: int   = 1
    status:        str   = "active"

class HospitalUpdate(BaseModel):
    name_ar:       Optional[str] = None
    name_en:       Optional[str] = None
    city:          Optional[str] = None
    type:          Optional[str] = None
    logo_b64:      Optional[str] = None
    is_government: Optional[int] = None
    status:        Optional[str] = None

class DoctorCreate(BaseModel):
    name_ar:    str
    name_en:    str = ""
    specialty:  str = "طب عام"
    license_no: str = ""
    status:     str = "active"

class ReportCreate(BaseModel):
    hospital_id:       int
    doctor_id:         int
    report_type:       str = "sick_leave"
    patient_data_json: dict = Field(default_factory=dict)

class WalletCharge(BaseModel):
    user_id:    int
    amount:     float
    note:       str   = "شحن رصيد"
    package_id: Optional[int] = None

class UserUpdate(BaseModel):
    name:    Optional[str]   = None
    role:    Optional[str]   = None
    status:  Optional[str]   = None
    balance: Optional[float] = None

class SettingUpdate(BaseModel):
    value: str

# ══════════════════════════════════════════════════════
#  🚀 التطبيق
# ══════════════════════════════════════════════════════

app = FastAPI(
    title="🏥 سيها API",
    description="نظام إدارة التقارير الطبية — Backend كامل",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()
    print("✅ سيها Backend جاهز")

# ══════════════════════════════════════════════════════
#  🔐 المصادقة
# ══════════════════════════════════════════════════════

@app.post("/auth/login", tags=["Auth"])
def login(req: LoginRequest):
    """
    تسجيل الدخول / إنشاء حساب تلقائي بـ telegram_id.
    يُرجع token + بيانات المستخدم.
    """
    with db_ctx() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (req.telegram_id,)
        ).fetchone()

        if not user:
            conn.execute("""
                INSERT INTO users(telegram_id, name, username, balance, role, status)
                VALUES (?, ?, ?, 0, 'user', 'active')
            """, (req.telegram_id, req.name or "", req.username or ""))
            conn.commit()
            user = conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (req.telegram_id,)
            ).fetchone()

        if user["status"] == "banned":
            raise HTTPException(403, "هذا الحساب محظور")

        # تحديث الاسم إذا تغيّر
        if req.name and req.name != user["name"]:
            conn.execute(
                "UPDATE users SET name=?, username=? WHERE id=?",
                (req.name, req.username or "", user["id"])
            )

    token = _make_token(req.telegram_id)
    return {
        "token":   token,
        "user":    dict(user),
        "message": "مرحباً بك في سيها",
    }

# ══════════════════════════════════════════════════════
#  🏥 المستشفيات
# ══════════════════════════════════════════════════════

@app.get("/hospitals", tags=["Hospitals"])
def list_hospitals(
    city:   Optional[str] = Query(None, description="فلترة بالمدينة"),
    type:   Optional[str] = Query(None, description="فلترة بالنوع"),
    search: Optional[str] = Query(None, description="بحث بالاسم"),
    status: str           = Query("active"),
    user:   dict          = Depends(get_current_user),
):
    """قائمة المستشفيات مع فلترة اختيارية"""
    sql    = "SELECT * FROM hospitals WHERE status = ?"
    params: list[Any] = [status]

    if city:
        sql += " AND city = ?"
        params.append(city)
    if type:
        sql += " AND type = ?"
        params.append(type)
    if search:
        sql += " AND (name_ar LIKE ? OR name_en LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    sql += " ORDER BY name_ar"

    with db_ctx() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"hospitals": [dict(r) for r in rows], "count": len(rows)}

@app.post("/hospitals", tags=["Hospitals"])
def create_hospital(data: HospitalCreate, admin: dict = Depends(require_admin)):
    """إضافة مستشفى جديد (مسؤول فقط)"""
    with db_ctx() as conn:
        cur = conn.execute("""
            INSERT INTO hospitals(name_ar, name_en, city, type, logo_b64, is_government, status)
            VALUES (?,?,?,?,?,?,?)
        """, (data.name_ar, data.name_en, data.city, data.type,
              data.logo_b64, data.is_government, data.status))
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM hospitals WHERE id=?", (new_id,)).fetchone()
    return {"hospital": dict(row), "message": "تم إضافة المستشفى"}

@app.get("/hospitals/{hospital_id}", tags=["Hospitals"])
def get_hospital(hospital_id: int, user: dict = Depends(get_current_user)):
    with db_ctx() as conn:
        row = conn.execute(
            "SELECT * FROM hospitals WHERE id=?", (hospital_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "المستشفى غير موجود")
    return dict(row)

@app.patch("/hospitals/{hospital_id}", tags=["Hospitals"])
def update_hospital(
    hospital_id: int,
    data: HospitalUpdate,
    admin: dict = Depends(require_admin),
):
    """تعديل بيانات مستشفى"""
    updates = {k: v for k, v in data.dict().items() if v is not None}
    if not updates:
        raise HTTPException(400, "لا توجد بيانات للتحديث")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [hospital_id]
    with db_ctx() as conn:
        conn.execute(f"UPDATE hospitals SET {set_clause} WHERE id=?", vals)
        row = conn.execute("SELECT * FROM hospitals WHERE id=?", (hospital_id,)).fetchone()
    return {"hospital": dict(row), "message": "تم التحديث"}

@app.delete("/hospitals/{hospital_id}", tags=["Hospitals"])
def deactivate_hospital(hospital_id: int, admin: dict = Depends(require_admin)):
    with db_ctx() as conn:
        conn.execute("UPDATE hospitals SET status='inactive' WHERE id=?", (hospital_id,))
    return {"message": "تم إيقاف المستشفى"}

# ══════════════════════════════════════════════════════
#  👨‍⚕️ الأطباء
# ══════════════════════════════════════════════════════

@app.get("/hospitals/{hospital_id}/doctors", tags=["Doctors"])
def get_doctors(
    hospital_id: int,
    status: str = Query("active"),
    user:   dict = Depends(get_current_user),
):
    """قائمة أطباء مستشفى معين"""
    with db_ctx() as conn:
        # التحقق من وجود المستشفى
        hosp = conn.execute(
            "SELECT id FROM hospitals WHERE id=?", (hospital_id,)
        ).fetchone()
        if not hosp:
            raise HTTPException(404, "المستشفى غير موجود")

        rows = conn.execute("""
            SELECT * FROM doctors
            WHERE hospital_id=? AND status=?
            ORDER BY name_ar
        """, (hospital_id, status)).fetchall()

    return {"doctors": [dict(r) for r in rows], "count": len(rows)}

@app.post("/hospitals/{hospital_id}/doctors", tags=["Doctors"])
def add_doctor(
    hospital_id: int,
    data: DoctorCreate,
    admin: dict = Depends(require_admin),
):
    with db_ctx() as conn:
        cur = conn.execute("""
            INSERT INTO doctors(hospital_id, name_ar, name_en, specialty, license_no, status)
            VALUES (?,?,?,?,?,?)
        """, (hospital_id, data.name_ar, data.name_en,
              data.specialty, data.license_no, data.status))
        row = conn.execute("SELECT * FROM doctors WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"doctor": dict(row), "message": "تم إضافة الطبيب"}

# ══════════════════════════════════════════════════════
#  📋 التقارير
# ══════════════════════════════════════════════════════

def _gen_rnum() -> str:
    """توليد رقم تقرير فريد"""
    with db_ctx() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='report_counter'").fetchone()
        counter = int(row["value"]) + 1 if row else 1
        conn.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES('report_counter',?)",
            (str(counter),)
        )
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"SH{counter:06d}{suffix}"

@app.post("/reports", tags=["Reports"])
def create_report(data: ReportCreate, user: dict = Depends(get_current_user)):
    """
    إنشاء تقرير جديد.
    يخصم رصيد المستخدم تلقائياً بسعر التقرير.
    """
    with db_ctx() as conn:
        # جلب سعر التقرير
        price_row = conn.execute(
            "SELECT value FROM settings WHERE key='report_price'"
        ).fetchone()
        price = float(price_row["value"]) if price_row else REPORT_PRICE

        # التحقق من الرصيد
        u = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if u["balance"] < price:
            raise HTTPException(402, f"رصيدك غير كافٍ. المطلوب: {price} ريال، رصيدك: {u['balance']:.2f} ريال")

        # التحقق من المستشفى والطبيب
        hosp = conn.execute(
            "SELECT id FROM hospitals WHERE id=? AND status='active'", (data.hospital_id,)
        ).fetchone()
        if not hosp:
            raise HTTPException(404, "المستشفى غير موجود أو غير نشط")

        doc = conn.execute(
            "SELECT id FROM doctors WHERE id=? AND hospital_id=? AND status='active'",
            (data.doctor_id, data.hospital_id)
        ).fetchone()
        if not doc:
            raise HTTPException(404, "الطبيب غير موجود في هذا المستشفى")

        # توليد رقم التقرير
        rnum = _gen_rnum()

        # إنشاء التقرير
        cur = conn.execute("""
            INSERT INTO reports(user_id, hospital_id, doctor_id, report_type,
                                patient_data_json, rnum)
            VALUES (?,?,?,?,?,?)
        """, (user["id"], data.hospital_id, data.doctor_id, data.report_type,
              json.dumps(data.patient_data_json, ensure_ascii=False), rnum))
        report_id = cur.lastrowid

        # خصم الرصيد
        conn.execute(
            "UPDATE users SET balance = balance - ?, reports_count = reports_count + 1 WHERE id=?",
            (price, user["id"])
        )

        # تسجيل المعاملة
        conn.execute("""
            INSERT INTO transactions(user_id, type, amount, note)
            VALUES (?,?,?,?)
        """, (user["id"], "deduct", price, f"إصدار تقرير {rnum}"))

        # جلب التقرير الكامل مع التفاصيل
        report = conn.execute("""
            SELECT r.*,
                   h.name_ar AS hospital_name_ar, h.name_en AS hospital_name_en,
                   d.name_ar AS doctor_name_ar,   d.name_en AS doctor_name_en,
                   d.specialty AS doctor_specialty
            FROM reports r
            LEFT JOIN hospitals h ON r.hospital_id = h.id
            LEFT JOIN doctors   d ON r.doctor_id   = d.id
            WHERE r.id = ?
        """, (report_id,)).fetchone()

    return {
        "report":  dict(report),
        "rnum":    rnum,
        "charged": price,
        "message": "تم إصدار التقرير بنجاح",
    }

@app.get("/reports", tags=["Reports"])
def list_reports(
    user_id:     Optional[int] = Query(None),
    report_type: Optional[str] = Query(None),
    limit:       int           = Query(50, le=200),
    offset:      int           = Query(0),
    user:        dict          = Depends(get_current_user),
):
    """
    قائمة التقارير.
    المستخدم العادي يرى تقاريره فقط.
    المسؤول يرى الكل أو يفلتر بـ user_id.
    """
    is_admin = user["role"] == "admin"

    sql = """
        SELECT r.*,
               h.name_ar AS hospital_name_ar, h.name_en AS hospital_name_en,
               d.name_ar AS doctor_name_ar,   d.specialty AS doctor_specialty,
               u.name    AS user_name
        FROM reports r
        LEFT JOIN hospitals h ON r.hospital_id = h.id
        LEFT JOIN doctors   d ON r.doctor_id   = d.id
        LEFT JOIN users     u ON r.user_id     = u.id
        WHERE 1=1
    """
    params: list[Any] = []

    if not is_admin:
        sql += " AND r.user_id = ?"
        params.append(user["id"])
    elif user_id:
        sql += " AND r.user_id = ?"
        params.append(user_id)

    if report_type:
        sql += " AND r.report_type = ?"
        params.append(report_type)

    sql += " ORDER BY r.created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    with db_ctx() as conn:
        rows  = conn.execute(sql, params).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM reports WHERE user_id = ?" if not is_admin
            else "SELECT COUNT(*) FROM reports",
            [user["id"]] if not is_admin else []
        ).fetchone()[0]

    reports = []
    for r in rows:
        d = dict(r)
        # Parse patient_data_json
        try:
            d["patient_data"] = json.loads(d.get("patient_data_json") or "{}")
        except Exception:
            d["patient_data"] = {}
        reports.append(d)

    return {"reports": reports, "total": total, "limit": limit, "offset": offset}

@app.get("/reports/{rnum}", tags=["Reports"])
def get_report(rnum: str, user: dict = Depends(get_current_user)):
    """جلب تقرير واحد بالرقم"""
    with db_ctx() as conn:
        row = conn.execute("""
            SELECT r.*,
                   h.name_ar AS hospital_name_ar, h.name_en AS hospital_name_en,
                   h.logo_b64 AS hospital_logo,
                   d.name_ar AS doctor_name_ar,   d.name_en AS doctor_name_en,
                   d.specialty AS doctor_specialty, d.license_no
            FROM reports r
            LEFT JOIN hospitals h ON r.hospital_id = h.id
            LEFT JOIN doctors   d ON r.doctor_id   = d.id
            WHERE r.rnum = ?
        """, (rnum,)).fetchone()

    if not row:
        raise HTTPException(404, "التقرير غير موجود")

    r = dict(row)
    if user["role"] != "admin" and r["user_id"] != user["id"]:
        raise HTTPException(403, "لا تملك صلاحية الوصول لهذا التقرير")

    try:
        r["patient_data"] = json.loads(r.get("patient_data_json") or "{}")
    except Exception:
        r["patient_data"] = {}
    return r

# ══════════════════════════════════════════════════════
#  👥 المرضى المحفوظون
# ══════════════════════════════════════════════════════

@app.get("/patients", tags=["Patients"])
def list_patients(
    user_id: Optional[int] = Query(None),
    search:  Optional[str] = Query(None),
    user:    dict          = Depends(get_current_user),
):
    """قائمة المرضى المحفوظين"""
    target_id = user_id if (user["role"] == "admin" and user_id) else user["id"]

    sql    = "SELECT * FROM saved_patients WHERE user_id=?"
    params: list[Any] = [target_id]

    if search:
        sql += " AND (patient_name LIKE ? OR patient_id LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    sql += " ORDER BY created_at DESC"

    with db_ctx() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"patients": [dict(r) for r in rows], "count": len(rows)}

@app.post("/patients", tags=["Patients"])
def save_patient(data: dict = Body(...), user: dict = Depends(get_current_user)):
    """حفظ مريض للاستخدام المستقبلي"""
    required = ["patient_name", "patient_id"]
    for f in required:
        if f not in data:
            raise HTTPException(400, f"الحقل '{f}' مطلوب")

    with db_ctx() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO saved_patients
                (user_id, patient_name, patient_id, birth_date, phone, employer, nationality)
            VALUES (?,?,?,?,?,?,?)
        """, (
            user["id"],
            data["patient_name"], data["patient_id"],
            data.get("birth_date", ""), data.get("phone", ""),
            data.get("employer", ""), data.get("nationality", "سعودي"),
        ))
    return {"message": "تم حفظ بيانات المريض"}

@app.delete("/patients/{patient_id_val}", tags=["Patients"])
def delete_patient(patient_id_val: str, user: dict = Depends(get_current_user)):
    with db_ctx() as conn:
        conn.execute(
            "DELETE FROM saved_patients WHERE user_id=? AND patient_id=?",
            (user["id"], patient_id_val)
        )
    return {"message": "تم حذف المريض"}

# ══════════════════════════════════════════════════════
#  💰 المحفظة
# ══════════════════════════════════════════════════════

@app.get("/wallet", tags=["Wallet"])
def get_wallet(
    user_id: Optional[int] = Query(None),
    limit:   int           = Query(20, le=100),
    user:    dict          = Depends(get_current_user),
):
    """بيانات المحفظة والمعاملات"""
    target_id = user_id if (user["role"] == "admin" and user_id) else user["id"]

    with db_ctx() as conn:
        u = conn.execute(
            "SELECT id, name, balance, reports_count FROM users WHERE id=?",
            (target_id,)
        ).fetchone()
        if not u:
            raise HTTPException(404, "المستخدم غير موجود")

        txns = conn.execute("""
            SELECT * FROM transactions
            WHERE user_id=?
            ORDER BY created_at DESC
            LIMIT ?
        """, (target_id, limit)).fetchall()

        # إجماليات
        stats = conn.execute("""
            SELECT
                SUM(CASE WHEN type IN ('charge','bonus','refund') THEN amount ELSE 0 END) AS total_charged,
                SUM(CASE WHEN type = 'deduct' THEN amount ELSE 0 END)                     AS total_spent
            FROM transactions WHERE user_id=?
        """, (target_id,)).fetchone()

    return {
        "user":          dict(u),
        "balance":       u["balance"],
        "transactions":  [dict(t) for t in txns],
        "total_charged": stats["total_charged"] or 0,
        "total_spent":   stats["total_spent"]   or 0,
    }

@app.post("/wallet/charge", tags=["Wallet"])
def charge_wallet(data: WalletCharge, admin: dict = Depends(require_admin)):
    """شحن رصيد مستخدم (مسؤول فقط)"""
    if data.amount <= 0:
        raise HTTPException(400, "المبلغ يجب أن يكون أكبر من صفر")

    with db_ctx() as conn:
        u = conn.execute(
            "SELECT id, balance FROM users WHERE id=?", (data.user_id,)
        ).fetchone()
        if not u:
            raise HTTPException(404, "المستخدم غير موجود")

        note = data.note
        if data.package_id:
            pkg = conn.execute(
                "SELECT * FROM packages WHERE id=?", (data.package_id,)
            ).fetchone()
            if pkg:
                note = f"شراء باقة: {pkg['name']} ({pkg['reports_count']} تقرير)"

        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE id=?",
            (data.amount, data.user_id)
        )
        conn.execute("""
            INSERT INTO transactions(user_id, type, amount, note)
            VALUES (?,?,?,?)
        """, (data.user_id, "charge", data.amount, note))

        new_balance = conn.execute(
            "SELECT balance FROM users WHERE id=?", (data.user_id,)
        ).fetchone()["balance"]

    return {
        "message":     f"تم شحن {data.amount} ريال بنجاح",
        "new_balance": new_balance,
        "user_id":     data.user_id,
    }

@app.post("/wallet/deduct", tags=["Wallet"])
def deduct_wallet(data: WalletCharge, admin: dict = Depends(require_admin)):
    """خصم رصيد من مستخدم (مسؤول فقط)"""
    with db_ctx() as conn:
        u = conn.execute(
            "SELECT id, balance FROM users WHERE id=?", (data.user_id,)
        ).fetchone()
        if not u:
            raise HTTPException(404, "المستخدم غير موجود")
        if u["balance"] < data.amount:
            raise HTTPException(400, "الرصيد غير كافٍ للخصم")

        conn.execute(
            "UPDATE users SET balance = balance - ? WHERE id=?",
            (data.amount, data.user_id)
        )
        conn.execute("""
            INSERT INTO transactions(user_id, type, amount, note)
            VALUES (?,?,?,?)
        """, (data.user_id, "deduct", data.amount, data.note or "خصم رصيد"))

        new_balance = conn.execute(
            "SELECT balance FROM users WHERE id=?", (data.user_id,)
        ).fetchone()["balance"]

    return {
        "message":     f"تم خصم {data.amount} ريال",
        "new_balance": new_balance,
    }

# ══════════════════════════════════════════════════════
#  📦 الباقات
# ══════════════════════════════════════════════════════

@app.get("/packages", tags=["Packages"])
def list_packages(user: dict = Depends(get_current_user)):
    with db_ctx() as conn:
        rows = conn.execute(
            "SELECT * FROM packages WHERE is_active=1 ORDER BY price"
        ).fetchall()
    return {"packages": [dict(r) for r in rows]}

# ══════════════════════════════════════════════════════
#  🛡️ لوحة المسؤول
# ══════════════════════════════════════════════════════

@app.get("/admin/stats", tags=["Admin"])
def admin_stats(admin: dict = Depends(require_admin)):
    """إحصاءات شاملة للوحة التحكم"""
    with db_ctx() as conn:
        total_users    = conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]
        active_users   = conn.execute("SELECT COUNT(*) FROM users WHERE status='active'").fetchone()[0]
        banned_users   = conn.execute("SELECT COUNT(*) FROM users WHERE status='banned'").fetchone()[0]
        total_reports  = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        today          = datetime.now().strftime("%Y-%m-%d")
        today_reports  = conn.execute(
            "SELECT COUNT(*) FROM reports WHERE created_at LIKE ?", (f"{today}%",)
        ).fetchone()[0]

        total_revenue = conn.execute(
            "SELECT SUM(amount) FROM transactions WHERE type='deduct'"
        ).fetchone()[0] or 0

        total_charged = conn.execute(
            "SELECT SUM(amount) FROM transactions WHERE type IN ('charge','bonus')"
        ).fetchone()[0] or 0

        total_balance = conn.execute(
            "SELECT SUM(balance) FROM users"
        ).fetchone()[0] or 0

        hospitals_count = conn.execute(
            "SELECT COUNT(*) FROM hospitals WHERE status='active'"
        ).fetchone()[0]

        doctors_count = conn.execute(
            "SELECT COUNT(*) FROM doctors WHERE status='active'"
        ).fetchone()[0]

        # أكثر مستخدمين تقارير
        top_users = conn.execute("""
            SELECT name, telegram_id, reports_count, balance
            FROM users
            ORDER BY reports_count DESC
            LIMIT 5
        """).fetchall()

        # آخر 7 أيام
        weekly = conn.execute("""
            SELECT DATE(created_at) AS day, COUNT(*) AS count
            FROM reports
            WHERE created_at >= DATE('now', '-7 days')
            GROUP BY day
            ORDER BY day
        """).fetchall()

    return {
        "users": {
            "total":   total_users,
            "active":  active_users,
            "banned":  banned_users,
        },
        "reports": {
            "total":   total_reports,
            "today":   today_reports,
            "weekly":  [dict(r) for r in weekly],
        },
        "financial": {
            "total_revenue": round(total_revenue, 2),
            "total_charged": round(total_charged, 2),
            "total_balance": round(total_balance, 2),
        },
        "hospitals": {"total": hospitals_count},
        "doctors":   {"total": doctors_count},
        "top_users": [dict(u) for u in top_users],
    }

@app.get("/admin/users", tags=["Admin"])
def admin_list_users(
    search:  Optional[str] = Query(None),
    role:    Optional[str] = Query(None),
    status:  Optional[str] = Query(None),
    limit:   int           = Query(50, le=200),
    offset:  int           = Query(0),
    admin:   dict          = Depends(require_admin),
):
    """قائمة المستخدمين مع فلترة"""
    sql    = "SELECT * FROM users WHERE 1=1"
    params: list[Any] = []

    if search:
        sql += " AND (name LIKE ? OR username LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if role:
        sql += " AND role = ?"
        params.append(role)
    if status:
        sql += " AND status = ?"
        params.append(status)

    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    with db_ctx() as conn:
        rows  = conn.execute(sql, params).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    return {"users": [dict(r) for r in rows], "total": total}

@app.post("/admin/users", tags=["Admin"])
def admin_create_user(data: dict = Body(...), admin: dict = Depends(require_admin)):
    """إنشاء مستخدم يدوياً"""
    if "telegram_id" not in data:
        raise HTTPException(400, "telegram_id مطلوب")
    with db_ctx() as conn:
        try:
            cur = conn.execute("""
                INSERT INTO users(telegram_id, name, username, balance, role, status)
                VALUES (?,?,?,?,?,?)
            """, (
                data["telegram_id"],
                data.get("name", ""),
                data.get("username", ""),
                data.get("balance", 0),
                data.get("role", "user"),
                data.get("status", "active"),
            ))
            row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "المستخدم موجود مسبقاً بهذا telegram_id")
    return {"user": dict(row), "message": "تم إنشاء المستخدم"}

@app.get("/admin/users/{user_id}", tags=["Admin"])
def admin_get_user(user_id: int, admin: dict = Depends(require_admin)):
    with db_ctx() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "المستخدم غير موجود")
    return dict(row)

@app.patch("/admin/users/{user_id}", tags=["Admin"])
def admin_update_user(
    user_id: int,
    data: UserUpdate,
    admin: dict = Depends(require_admin),
):
    """تعديل بيانات مستخدم"""
    updates = {k: v for k, v in data.dict().items() if v is not None}
    if not updates:
        raise HTTPException(400, "لا توجد بيانات للتحديث")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [user_id]
    with db_ctx() as conn:
        conn.execute(f"UPDATE users SET {set_clause} WHERE id=?", vals)
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return {"user": dict(row), "message": "تم التحديث"}

@app.post("/admin/users/{user_id}/ban", tags=["Admin"])
def ban_user(user_id: int, admin: dict = Depends(require_admin)):
    with db_ctx() as conn:
        conn.execute("UPDATE users SET status='banned' WHERE id=?", (user_id,))
    return {"message": "تم حظر المستخدم"}

@app.post("/admin/users/{user_id}/unban", tags=["Admin"])
def unban_user(user_id: int, admin: dict = Depends(require_admin)):
    with db_ctx() as conn:
        conn.execute("UPDATE users SET status='active' WHERE id=?", (user_id,))
    return {"message": "تم رفع الحظر عن المستخدم"}

# ══════════════════════════════════════════════════════
#  ⚙️ الإعدادات
# ══════════════════════════════════════════════════════

@app.get("/admin/settings", tags=["Admin"])
def get_settings(admin: dict = Depends(require_admin)):
    with db_ctx() as conn:
        rows = conn.execute("SELECT * FROM settings ORDER BY key").fetchall()
    return {"settings": {r["key"]: r["value"] for r in rows}}

@app.put("/admin/settings/{key}", tags=["Admin"])
def update_setting(key: str, data: SettingUpdate, admin: dict = Depends(require_admin)):
    with db_ctx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
            (key, data.value)
        )
    return {"message": f"تم تحديث الإعداد '{key}'", "key": key, "value": data.value}

# ══════════════════════════════════════════════════════
#  🏠 الصفحة الرئيسية
# ══════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════
#  📄 توليد PDF
# ══════════════════════════════════════════════════════

@app.get("/reports/{rnum}/pdf", tags=["Reports"])
def download_report_pdf(rnum: str, user: dict = Depends(get_current_user)):
    """تحميل PDF التقرير"""
    with db_ctx() as conn:
        row = conn.execute("""
            SELECT r.*,
                   h.name_ar AS hospital_name_ar, h.name_en AS hospital_name_en,
                   h.city AS hospital_city, h.type AS hospital_type,
                   h.logo_b64 AS hospital_logo,
                   '' AS hospital_license,
                   d.name_ar AS doctor_name_ar, d.name_en AS doctor_name_en,
                   d.specialty AS doctor_specialty, d.license_no AS doctor_license
            FROM reports r
            LEFT JOIN hospitals h ON r.hospital_id = h.id
            LEFT JOIN doctors   d ON r.doctor_id   = d.id
            WHERE r.rnum = ?
        """, (rnum,)).fetchone()

    if not row:
        raise HTTPException(404, "التقرير غير موجود")

    if row["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "غير مصرح")

    r = dict(row)
    patient = json.loads(r.get("patient_data_json") or "{}")

    # بناء المعاملات بالشكل الصحيح لـ generate_pdf
    report_type = r["report_type"]
    # normalize report_type
    type_map = {"official": "report", "sick_leave": "report", "visit": "mashad", "companion": "companion"}
    report_type = type_map.get(report_type, report_type)

    hospital_data = {
        "name_ar":       r.get("hospital_name_ar") or "",
        "name_en":       r.get("hospital_name_en") or "",
        "city":          r.get("hospital_city") or "",
        "type":          r.get("hospital_type") or "",
        "logo_b64":      r.get("hospital_logo") or "",
        "is_government": 1 if r.get("hospital_type") in ("مستشفى", "مركز صحي") else 0,
    }

    doctor_data = {
        "name_ar":   r.get("doctor_name_ar") or "",
        "name_en":   r.get("doctor_name_en") or "",
        "specialty": r.get("doctor_specialty") or "",
        "license_no": r.get("doctor_license") or "",
    }

    # تحويل أسماء الحقول من HTML إلى ما يتوقعه pdf_gen.py
    def _norm_patient(p, rtype):
        if rtype == "report":
            return {
                "full_name":   p.get("name") or p.get("full_name") or "",
                "id_number":   p.get("national_id") or p.get("id_number") or "",
                "nationality": p.get("nationality") or "",
                "workplace":   p.get("employer") or p.get("workplace") or "",
                "excuse_date": p.get("leave_from") or p.get("excuse_date") or "",
                "days_count":  int(p.get("days") or p.get("days_count") or 1),
                "diagnosis":   p.get("diagnosis") or "",
            }
        elif rtype == "mashad":
            return {
                "full_name":   p.get("name") or p.get("full_name") or "",
                "id_number":   p.get("national_id") or p.get("id_number") or "",
                "nationality": p.get("nationality") or "",
                "workplace":   p.get("employer") or p.get("workplace") or "",
                "visit_type":  p.get("visit_type") or "طوارئ",
                "adm_date":    p.get("adm_date") or "",
                "adm_time":    p.get("adm_time") or "",
                "dis_date":    p.get("dis_date") or "",
                "dis_time":    p.get("dis_time") or "",
            }
        else:  # companion
            return {
                "full_name":   p.get("companion_name") or p.get("name") or p.get("full_name") or "",
                "id_number":   p.get("national_id") or p.get("id_number") or "",
                "nationality": p.get("nationality") or "",
                "workplace":   p.get("employer") or p.get("workplace") or "",
                "relation":    p.get("relation") or "",
                "adm_date":    p.get("adm_date") or "",
                "dis_date":    p.get("dis_date") or "",
                "patient_name": p.get("patient_name") or "",
            }

    patient_normalized = _norm_patient(patient, report_type)

    try:
        from pdf_generator import generate_pdf
        pdf_bytes = generate_pdf(
            report_type  = report_type,
            patient_data = patient_normalized,
            hospital_data= hospital_data,
            doctor_data  = doctor_data,
            rnum         = rnum,
        )
    except Exception as e:
        raise HTTPException(500, f"خطأ في توليد PDF: {e}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={rnum}.pdf"}
    )


@app.get("/app", tags=["General"])
def serve_app():
    """فتح تطبيق الويب"""
    from fastapi.responses import FileResponse
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seha_mini_app_v6.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    raise HTTPException(404, "ملف HTML غير موجود")

@app.get("/", tags=["General"])
def root():
    return {
        "app":     "🏥 سيها — نظام التقارير الطبية",
        "version": "2.0.0",
        "docs":    "/docs",
        "status":  "running",
    }

@app.get("/health", tags=["General"])
def health():
    try:
        with db_ctx() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "healthy", "db": "connected"}
    except Exception as e:
        raise HTTPException(500, f"Database error: {e}")


# ══════════════════════════════════════════════════════
#  ▶️ التشغيل المباشر
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
