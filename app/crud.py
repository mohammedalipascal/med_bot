import os
import threading
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# 🔒 قفل لتفادي التداخل بين الطلبات
LOCK = threading.Lock()

# ===== إعداد Google Sheets =====
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "MedBot Files")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

if not SERVICE_ACCOUNT_JSON:
    raise ValueError("❌ متغير البيئة GOOGLE_SERVICE_ACCOUNT_JSON غير موجود!")

creds_info = json.loads(SERVICE_ACCOUNT_JSON)
credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
client = gspread.authorize(credentials)

# ===== كاش داخلي لتقليل طلبات القراءة =====
_cache = {}
CACHE_TTL = 60  # ثواني

def _get_cache(key):
    if key in _cache and (time.time() - _cache[key]['time'] < CACHE_TTL):
        return _cache[key]['value']
    return None

def _set_cache(key, value):
    _cache[key] = {'value': value, 'time': time.time()}

# ===== تهيئة الورقة =====
def init_db():
    with LOCK:
        try:
            try:
                spreadsheet = client.open(GOOGLE_SHEET_NAME)
            except gspread.SpreadsheetNotFound:
                spreadsheet = client.create(GOOGLE_SHEET_NAME)

            sheet_titles = [s.title for s in spreadsheet.worksheets()]

            # materials
            if "materials" not in sheet_titles:
                spreadsheet.add_worksheet(title="materials", rows=5000, cols=6)
                sheet = spreadsheet.worksheet("materials")
                sheet.append_row(["course", "type", "file_id", "doctor", "created_at"])
            else:
                sheet = spreadsheet.worksheet("materials")
                header = sheet.row_values(1)
                expected = ["course", "type", "file_id", "doctor", "created_at"]
                if header[: len(expected)] != expected:
                    try:
                        sheet.delete_rows(1)
                    except Exception:
                        pass
                    sheet.insert_row(expected, 1)

            # waiting_files
            if "waiting_files" not in sheet_titles:
                spreadsheet.add_worksheet(title="waiting_files", rows=1000, cols=4)
                sheet2 = spreadsheet.worksheet("waiting_files")
                sheet2.append_row(["chat_id", "file_id", "type", "doctor"])
            else:
                sheet2 = spreadsheet.worksheet("waiting_files")
                header2 = sheet2.row_values(1)
                if header2[:4] != ["chat_id", "file_id", "type", "doctor"]:
                    try:
                        sheet2.delete_rows(1)
                    except Exception:
                        pass
                    sheet2.insert_row(["chat_id", "file_id", "type", "doctor"], 1)

            print("✅ Google Sheet جاهز للاستخدام")

        except Exception as e:
            print(f"❌ خطأ أثناء التهيئة: {e}")

# ========== مواد دائمة ==========
def add_material(course, type_, file_id, doctor=None):
    with LOCK:
        try:
            sheet = client.open(GOOGLE_SHEET_NAME).worksheet("materials")
            created_at = datetime.utcnow().isoformat()
            sheet.append_row([course, type_, file_id, doctor or "", created_at])
            # تحديث الكاش
            _cache.pop("materials", None)
        except Exception as e:
            print(f"❌ خطأ أثناء إضافة المادة: {e}")

def get_materials(course, type_, use_cache=False):
    key = "materials"
    if use_cache:
        cached = _get_cache(key)
        if cached:
            rows = cached
        else:
            rows = _fetch_materials_from_sheet()
            _set_cache(key, rows)
    else:
        rows = _fetch_materials_from_sheet()
    results = [
        {"course": row.get("course"), "type": row.get("type"),
         "file_id": row.get("file_id"), "doctor": row.get("doctor"),
         "created_at": row.get("created_at")}
        for row in rows
        if str(row.get("course")) == str(course) and str(row.get("type")) == str(type_)
    ]
    return results

def _fetch_materials_from_sheet():
    with LOCK:
        try:
            sheet = client.open(GOOGLE_SHEET_NAME).worksheet("materials")
            return sheet.get_all_records()
        except Exception as e:
            print(f"❌ خطأ أثناء جلب المواد: {e}")
            return []

def get_doctors_for_course_and_type(course, type_, use_cache=False):
    key = f"doctors_{course}_{type_}"
    if use_cache:
        cached = _get_cache(key)
        if cached:
            return cached
    rows = _fetch_materials_from_sheet()
    doctors = []
    for row in rows:
        if str(row.get("course")) == str(course) and str(row.get("type")) == str(type_):
            d = row.get("doctor") or ""
            if d and d not in doctors:
                doctors.append(d)
    if use_cache:
        _set_cache(key, doctors)
    return doctors

# ======= الملفات المؤقتة =======
def set_waiting_file(chat_id, flag):
    with LOCK:
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("waiting_files")
        all_rows = sheet.get_all_records()
        if not flag:
            new_rows = [r for r in all_rows if str(r.get("chat_id")) != str(chat_id)]
            sheet.clear()
            sheet.append_row(["chat_id", "file_id", "type", "doctor"])
            for row in new_rows:
                sheet.append_row([row.get("chat_id"), row.get("file_id"), row.get("type"), row.get("doctor") or ""])
        else:
            for r in all_rows:
                if str(r.get("chat_id")) == str(chat_id):
                    return
            sheet.append_row([chat_id, "", "", ""])
        _cache.pop(f"waiting_file_{chat_id}", None)
        _cache.pop(f"waiting_data_{chat_id}", None)

def set_waiting_file_fileid(chat_id, file_id, type_, doctor=None):
    with LOCK:
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("waiting_files")
        all_rows = sheet.get_all_records()
        for i, row in enumerate(all_rows, start=2):
            if str(row.get("chat_id")) == str(chat_id):
                sheet.update(f"A{i}:D{i}", [[chat_id, file_id, type_, doctor or ""]])
                _cache.pop(f"waiting_data_{chat_id}", None)
                return
        sheet.append_row([chat_id, file_id, type_, doctor or ""])
        _cache.pop(f"waiting_data_{chat_id}", None)

def set_waiting_file_doctor(chat_id, doctor):
    with LOCK:
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("waiting_files")
        all_rows = sheet.get_all_records()
        for i, row in enumerate(all_rows, start=2):
            if str(row.get("chat_id")) == str(chat_id):
                sheet.update(f"D{i}:D{i}", [[doctor]])
                _cache.pop(f"waiting_data_{chat_id}", None)
                return

def is_waiting_file(chat_id, use_cache=False):
    key = f"waiting_file_{chat_id}"
    if use_cache:
        cached = _get_cache(key)
        if cached is not None:
            return cached
    with LOCK:
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("waiting_files")
        rows = sheet.get_all_records()
        exists = any(str(r.get("chat_id")) == str(chat_id) for r in rows)
    if use_cache:
        _set_cache(key, exists)
    return exists

def get_waiting_file(chat_id, use_cache=False):
    key = f"waiting_data_{chat_id}"
    if use_cache:
        cached = _get_cache(key)
        if cached:
            return cached
    with LOCK:
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("waiting_files")
        rows = sheet.get_all_records()
        for r in rows:
            if str(r.get("chat_id")) == str(chat_id):
                result = {"file_id": r.get("file_id"), "type": r.get("type"), "doctor": r.get("doctor")}
                if use_cache:
                    _set_cache(key, result)
                return result
    return None
