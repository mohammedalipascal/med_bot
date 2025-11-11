# app/crud.py
import sqlite3
from typing import Optional

DB_PATH = "medbot.db"  # قاعدة بيانات دائمة على القرص

# ========= تهيئة قاعدة البيانات =========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # جدول المواد
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course TEXT NOT NULL,
        type TEXT NOT NULL,
        file_id TEXT NOT NULL
    )
    """)
    
    # جدول حالة انتظار رفع الملفات
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS waiting_files (
        chat_id INTEGER PRIMARY KEY,
        waiting INTEGER DEFAULT 0
    )
    """)
    
    conn.commit()
    conn.close()

# ========= المواد =========
def add_material(course: str, content_type: str, file_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # تحقق إذا المادة موجودة لنقوم بالتحديث بدل الإضافة
    cursor.execute("SELECT id FROM materials WHERE course=? AND type=?", (course, content_type))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE materials SET file_id=? WHERE id=?", (file_id, row[0]))
    else:
        cursor.execute("INSERT INTO materials (course, type, file_id) VALUES (?, ?, ?)", (course, content_type, file_id))
    
    conn.commit()
    conn.close()

def get_material(course: str, content_type: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM materials WHERE course=? AND type=?", (course, content_type))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"file_id": row[0]}
    return None

# ========= انتظار رفع الملفات =========
def set_waiting_file(chat_id: int, waiting: bool):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO waiting_files (chat_id, waiting) VALUES (?, ?)", (chat_id, int(waiting)))
    conn.commit()
    conn.close()

def is_waiting_file(chat_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT waiting FROM waiting_files WHERE chat_id=?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False
