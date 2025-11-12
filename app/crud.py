# app/crud.py
import os
import json
import threading
import gspread
from google.oauth2.service_account import Credentials

LOCK = threading.Lock()  # لضمان التزامن عند الوصول للـ Google Sheet

# نطاقات الوصول المطلوبة
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# تحميل بيانات الخدمة من متغير البيئة
def _get_client():
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        raise RuntimeError("❌ متغير البيئة GOOGLE_SERVICE_ACCOUNT_JSON غير موجود.")
    info = json.loads(sa_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)

def _get_sheet(sheet_name=None):
    client = _get_client()
    sheet_name = sheet_name or os.getenv("GOOGLE_SHEET_NAME", "MedBot Files")
    return client.open(sheet_name).sheet1

# ========= مواد دائمة =========
def add_material(course, type_, file_id):
    """إضافة ملف دائم للمواد (سواء عادي أو forwarded)"""
    with LOCK:
        sheet = _get_sheet()
        records = sheet.get_all_records()
        # تحقق إن الملف غير موجود بنفس file_id
        for i, r in enumerate(records, start=2):  # الصف 1 عناوين
            if r.get("file_id") == file_id:
                # تحديث إذا موجود
                sheet.update(f"A{i}:C{i}", [[course, type_, file_id]])
                return
        # غير موجود → نضيف صف جديد
        sheet.append_row([course, type_, file_id])

def get_material(course, type_):
    """استرجاع ملف لمقرر معين ونوع محدد"""
    with LOCK:
        sheet = _get_sheet()
        records = sheet.get_all_records()
        for r in records:
            if r.get("course") == course and r.get("type") == type_:
                return {"course": r["course"], "type": r["type"], "file_id": r["file_id"]}
        return None

# ========= ملفات مؤقتة قبل تحديد المقرر =========
def set_waiting_file(chat_id, flag):
    """تعيين حالة انتظار رفع الملف"""
    with LOCK:
        sheet = _get_sheet("waiting_files")
        records = sheet.get_all_records()
        if not flag:
            # إزالة الملف المؤقت عند الانتهاء
            new_rows = [r for r in records if str(r.get("chat_id")) != str(chat_id)]
            # إعادة كتابة الجدول (مسح ثم كتابة رؤوس وأسطُر جديدة)
            sheet.clear()
            sheet.append_row(["chat_id", "file_id", "type"])
            for r in new_rows:
                sheet.append_row([r["chat_id"], r["file_id"], r["type"]])
        # لو flag=True نعمل nothing (تُستخدم عند بداية انتظار)

def set_waiting_file_fileid(chat_id, file_id, type_):
    """حفظ الملف المرفوع مؤقتًا (عادي أو forwarded)"""
    with LOCK:
        sheet = _get_sheet("waiting_files")
        records = sheet.get_all_records()
        for i, r in enumerate(records, start=2):
            if str(r.get("chat_id")) == str(chat_id):
                sheet.update(f"A{i}:C{i}", [[chat_id, file_id, type_]])
                return
        sheet.append_row([chat_id, file_id, type_])

def is_waiting_file(chat_id):
    """هل هذا الـ chat_id ينتظر رفع ملف؟"""
    with LOCK:
        sheet = _get_sheet("waiting_files")
        records = sheet.get_all_records()
        return any(str(r.get("chat_id")) == str(chat_id) for r in records)

def get_waiting_file(chat_id):
    """استرجاع الملف المرفوع مؤقتًا (عادي أو forwarded)"""
    with LOCK:
        sheet = _get_sheet("waiting_files")
        records = sheet.get_all_records()
        for r in records:
            if str(r.get("chat_id")) == str(chat_id):
                return {"file_id": r["file_id"], "type": r["type"]}
        return None

def init_db():
    """تهيئة الورقتين (materials + waiting_files)"""
    client = _get_client()
    main_name = os.getenv("GOOGLE_SHEET_NAME", "MedBot Files")

    try:
        spreadsheet = client.open(main_name)
    except gspread.SpreadsheetNotFound:
        # إنشاء جديد إذا لم يكن موجودًا
        spreadsheet = client.create(main_name)

    # التأكد من وجود الورقة الأساسية
    try:
        sheet = spreadsheet.worksheet("Sheet1")
        sheet.update("A1:C1", [["course", "type", "file_id"]])
    except gspread.WorksheetNotFound:
        spreadsheet.add_worksheet(title="Sheet1", rows="100", cols="3")
        sheet = spreadsheet.worksheet("Sheet1")
        sheet.update("A1:C1", [["course", "type", "file_id"]])

    # ورقة الملفات المؤقتة
    try:
        waiting = spreadsheet.worksheet("waiting_files")
    except gspread.WorksheetNotFound:
        spreadsheet.add_worksheet(title="waiting_files", rows="100", cols="3")
        waiting = spreadsheet.worksheet("waiting_files")
        waiting.update("A1:C1", [["chat_id", "file_id", "type"]])
