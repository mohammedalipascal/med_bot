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

# ===== كاش داخلي =====
CACHE = {
    "materials": {"data": [], "last_update": 0},
    "waiting_files": {"data": [], "last_update": 0},
}
CACHE_TTL = 10  # ثواني: مدة صلاحية الكاش

def refresh_cache(sheet_name):
    now = time.time()
    if now - CACHE[sheet_name]["last_update"] > CACHE_TTL:
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet(sheet_name)
        CACHE[sheet_name]["data"] = sheet.get_all_records()
        CACHE[sheet_name]["last_update"] = now

def get_materials_cached(course, type_):
    refresh_cache("materials")
    return [
        row for row in CACHE["materials"]["data"]
        if str(row.get("course")) == str(course) and str(row.get("type")) == str(type_)
    ]

def get_waiting_files_cached():
    refresh_cache("waiting_files")
    return CACHE["waiting_files"]["data"]

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

# ========== مواد دائمة =========
def add_material(course, type_, file_id, doctor=None):
    with LOCK:
        try:
            sheet = client.open(GOOGLE_SHEET_NAME).worksheet("materials")
            created_at = datetime.utcnow().isoformat()
            sheet.append_row([course, type_, file_id, doctor or "", created_at])
            # تحديث الكاش بعد الإضافة
            CACHE["materials"]["data"].append({
                "course": course,
                "type": type_,
                "file_id": file_id,
                "doctor": doctor or "",
                "created_at": created_at
            })
        except Exception as e:
            print(f"❌ خطأ أثناء إضافة المادة: {e}")

def get_materials(course, type_):
    return get_materials_cached(course, type_)

def get_doctors_for_course_and_type(course, type_):
    refresh_cache("materials")
    doctors = []
    for row in CACHE["materials"]["data"]:
        if str(row.get("course")) == str(course) and str(row.get("type")) == str(type_):
            d = row.get("doctor") or ""
            if d and d not in doctors:
                doctors.append(d)
    return doctors

# ======= الملفات المؤقتة (قبل تحديد المقرر) =======
def set_waiting_file(chat_id, flag):
    with LOCK:
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("waiting_files")
        if not flag:
            # إعادة كتابة جميع الصفوف بدون هذا chat_id
            all_rows = get_waiting_files_cached()
            new_rows = [r for r in all_rows if str(r.get("chat_id")) != str(chat_id)]
            sheet.clear()
            sheet.append_row(["chat_id", "file_id", "type", "doctor"])
            for row in new_rows:
                sheet.append_row([row.get("chat_id"), row.get("file_id"), row.get("type"), row.get("doctor") or ""])
            # تحديث الكاش
            CACHE["waiting_files"]["data"] = new_rows
            CACHE["waiting_files"]["last_update"] = time.time()
        else:
            # إضافة صف مؤقت إذا لم يكن موجود
            all_rows = get_waiting_files_cached()
            for r in all_rows:
                if str(r.get("chat_id")) == str(chat_id):
                    return
            sheet.append_row([chat_id, "", "", ""])
            CACHE["waiting_files"]["data"].append({"chat_id": chat_id, "file_id": "", "type": "", "doctor": ""})

def set_waiting_file_fileid(chat_id, file_id, type_, doctor=None):
    with LOCK:
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("waiting_files")
        all_rows = get_waiting_files_cached()
        for i, row in enumerate(all_rows, start=2):
            if str(row.get("chat_id")) == str(chat_id):
                sheet.update(f"A{i}:D{i}", [[chat_id, file_id, type_, doctor or ""]])
                # تحديث الكاش
                row.update({"file_id": file_id, "type": type_, "doctor": doctor or ""})
                return
        # إذا لم يوجد، أضف صف جديد
        sheet.append_row([chat_id, file_id, type_, doctor or ""])
        CACHE["waiting_files"]["data"].append({"chat_id": chat_id, "file_id": file_id, "type": type_, "doctor": doctor or ""})

def set_waiting_file_doctor(chat_id, doctor):
    with LOCK:
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("waiting_files")
        all_rows = get_waiting_files_cached()
        for i, row in enumerate(all_rows, start=2):
            if str(row.get("chat_id")) == str(chat_id):
                sheet.update(f"D{i}:D{i}", [[doctor]])
                row["doctor"] = doctor
                return

def is_waiting_file(chat_id):
    rows = get_waiting_files_cached()
    return any(str(r.get("chat_id")) == str(chat_id) for r in rows)

def get_waiting_file(chat_id):
    rows = get_waiting_files_cached()
    for r in rows:
        if str(r.get("chat_id")) == str(chat_id):
            return {"file_id": r.get("file_id"), "type": r.get("type"), "doctor": r.get("doctor")}
    return None
