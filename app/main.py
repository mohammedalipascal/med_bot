# app/main.py
import os
import requests
from fastapi import FastAPI, Request, Header, HTTPException
from app.db import init_db
from app import crud

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN", None)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "secretkey")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
ADMIN_USERNAME = "@Mgdad_Ali"  # حساب المطور

app = FastAPI(title="Med Faculty Bot")

@app.on_event("startup")
async def startup():
    init_db()

# --------- دوال مساعدة ----------
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

def send_file(chat_id, file_id):
    requests.post(f"{TELEGRAM_API}/sendDocument", json={"chat_id": chat_id, "document": file_id})

def is_admin(user):
    # نقدر نضيف لاحقاً أكثر من أدمن لو حبيت
    return user.get("username") == ADMIN_USERNAME.replace("@", "")

# --------- Webhook -------------
@app.post("/webhook")
async def webhook(update: dict, x_telegram_bot_api_secret_token: str = Header(None)):
    if WEBHOOK_SECRET_TOKEN and x_telegram_bot_api_secret_token != WEBHOOK_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid secret header")

    if "message" not in update:
        return {"ok": True}

    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")
    user = msg.get("from", {})

    # أوامر الأدمن لإضافة المحتويات
    if text.startswith("/add") and is_admin(user):
        # الصيغة: /add course type file_id
        parts = text.split()
        if len(parts) == 4:
            course, ctype, file_id = parts[1], parts[2], parts[3]
            crud.add_material(course, ctype, file_id)
            send_message(chat_id, f"✅ تمت إضافة {ctype} لمادة {course} بنجاح!")
        else:
            send_message(chat_id, "❌ الصيغة الصحيحة:\n`/add تشريح pdf <file_id>`")
        return {"ok": True}

    # أمر /start
    if text.startswith("/start"):
        buttons = {
            "keyboard": [
                [{"text": "ابدأ 🎓"}],
                [{"text": "تواصل مع المطور 👨‍💻"}]
            ],
            "resize_keyboard": True
        }
        send_message(chat_id, "مرحبًا بك في *بوت كلية الطب – جامعة المناقل!* 👋\nاختر من القائمة:", reply_markup=buttons)
        return {"ok": True}

    # تواصل مع المطور
    if text == "تواصل مع المطور 👨‍💻":
        send_message(chat_id, f"يمكنك التواصل مع المطور عبر الحساب التالي:\n{ADMIN_USERNAME}")
        return {"ok": True}

    # القائمة الرئيسية
    if text == "🏠 القائمة الرئيسية":
        buttons = {
            "keyboard": [
                [{"text": "ابدأ 🎓"}],
                [{"text": "تواصل مع المطور 👨‍💻"}]
            ],
            "resize_keyboard": True
        }
        send_message(chat_id, "عدت إلى القائمة الرئيسية 🏠", reply_markup=buttons)
        return {"ok": True}

    # بعد الضغط على ابدأ
    if text == "ابدأ 🎓":
        buttons = {
            "keyboard": [
                [{"text": "📘 التشريح"}, {"text": "🧠 الفسيولوجي"}],
                [{"text": "🏠 القائمة الرئيسية"}]
            ],
            "resize_keyboard": True
        }
        send_message(chat_id, "اختر المقرر الدراسي:", reply_markup=buttons)
        return {"ok": True}

    # اختيار مقرر
    if text in ["📘 التشريح", "🧠 الفسيولوجي"]:
        course = "تشريح" if "التشريح" in text else "فسيولوجي"
        buttons = {
            "keyboard": [
                [{"text": f"{course} 📄 PDF"}, {"text": f"{course} 🎥 فيديو"}, {"text": f"{course} 📚 مرجع"}],
                [{"text": "⬅️ رجوع"}, {"text": "🏠 القائمة الرئيسية"}]
            ],
            "resize_keyboard": True
        }
        send_message(chat_id, f"اختر نوع المحتوى لمقرر *{course}*:", reply_markup=buttons)
        return {"ok": True}

    # زر الرجوع
    if text == "⬅️ رجوع":
        buttons = {
            "keyboard": [
                [{"text": "📘 التشريح"}, {"text": "🧠 الفسيولوجي"}],
                [{"text": "🏠 القائمة الرئيسية"}]
            ],
            "resize_keyboard": True
        }
        send_message(chat_id, "رجعت لاختيار المقرر ⬅️", reply_markup=buttons)
        return {"ok": True}

    # اختيار نوع المحتوى
    if any(x in text for x in ["PDF", "فيديو", "مرجع"]):
        parts = text.split()
        course_name = parts[0]
        if "PDF" in text:
            content_type = "pdf"
        elif "فيديو" in text:
            content_type = "video"
        else:
            content_type = "reference"

        mat = crud.get_material(course_name, content_type)
        if mat and mat.file_id:
            send_message(chat_id, f"جارٍ إرسال {content_type} الخاص بمقرر {course_name}...")
            send_file(chat_id, mat.file_id)
        else:
            send_message(chat_id, "🚧 لم يتم العثور على هذا المحتوى بعد.")
        return {"ok": True}

    return {"ok": True}
