# app/crud.py
import sqlite3
import os
import threading

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")
lock = threading.Lock()  # لتجنب التعارض عند عدة طلبات

# ========= تهيئة قاعدة البيانات والجداول =========
def init_db():
    with lock:
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
        # جدول متابعة رفع الملفات
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS waiting_files (
                chat_id INTEGER PRIMARY KEY,
                waiting INTEGER NOT NULL
            )
        """)
        conn.commit()
        conn.close()

# ========= إضافة مادة =========
def add_material(course, content_type, file_id):
    with lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO materials (course, type, file_id)
            VALUES (?, ?, ?)
        """, (course, content_type, file_id))
        conn.commit()
        conn.close()

# ========= جلب مادة =========
def get_material(course, content_type):
    with lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT file_id FROM materials
            WHERE course = ? AND type = ?
            ORDER BY id DESC LIMIT 1
        """, (course, content_type))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"file_id": row[0]}
        return None

# ========= متابعة رفع الملفات =========
def set_waiting_file(chat_id, waiting=True):
    with lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO waiting_files (chat_id, waiting)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET waiting=excluded.waiting
        """, (chat_id, int(waiting)))
        conn.commit()
        conn.close()

def is_waiting_file(chat_id):
    with lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT waiting FROM waiting_files WHERE chat_id=?
        """, (chat_id,))
        row = cursor.fetchone()
        conn.close()
        return bool(row[0]) if row else False
