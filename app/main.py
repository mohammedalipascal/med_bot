# app/main.py
import os
import requests
from fastapi import FastAPI, Request, Header, HTTPException
from app.db import init_db
from app import crud

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN", None)
ADMIN_USERNAME = "@Mgdad_Ali"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI(title="Med Faculty Bot")

@app.on_event("startup")
async def startup():
    init_db()

# ---------- دوال مساعدة ----------
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

def send_file(chat_id, file_id, content_type="pdf"):
    if content_type == "video":
        requests.post(f"{TELEGRAM_API}/sendVideo", json={"chat_id": chat_id, "video": file_id})
    else:
        requests.post(f"{TELEGRAM_API}/sendDocument", json={"chat_id": chat_id, "document": file_id})

def is_admin(user):
    return user.get("username") == ADMIN_USERNAME.replace("@", "")

# ---------- إنشاء Keyboards ----------
def get_main_keyboard(is_admin=False):
    buttons = [
        [{"text": "ابدأ 🎓"}],
        [{"text": "تواصل مع المطور 👨‍💻"}]
    ]
    if is_admin:
        buttons.append([{"text": "رفع ملف جديد 📤"}])
    return {"keyboard": buttons, "resize_keyboard": True}

def get_courses_keyboard():
    return {
        "keyboard": [
            [{"text": "📘 التشريح"}, {"text": "🧠 الفسيولوجي"}],
            [{"text": "🏠 القائمة الرئيسية"}]
        ],
        "resize_keyboard": True
    }

def get_types_keyboard(course):
    return {
        "keyboard": [
            [{"text": f"{course} 📄 PDF"}, {"text": f"{course} 🎥 فيديو"}, {"text": f"{course} 📚 مرجع"}],
            [{"text": "⬅️ رجوع"}, {"text": "🏠 القائمة الرئيسية"}]
        ],
        "resize_keyboard": True
    }

# ---------- Webhook ----------
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

    # ----------------- أوامر الأدمن -----------------
    # إضافة ملف جديد
    if text.startswith("/addfile") and is_admin(user):
        parts = text.split()
        if len(parts) == 4:
            course, ctype, file_id = parts[1], parts[2], parts[3]
            crud.add_material(course, ctype, file_id)
            send_message(chat_id, f"✅ تمت إضافة {ctype} لمادة {course} بنجاح!")
        else:
            send_message(chat_id, "❌ الصيغة الصحيحة:\n`/addfile <course> <type> <file_id>`")
        return {"ok": True}

    # رفع ملف جديد
    if text.strip() == "رفع ملف جديد 📤" and is_admin(user):
        send_message(chat_id, "📤 أرسل الآن الملف (PDF / فيديو) للبوت، وسأعطيك file_id مباشرة.")
        crud.set_waiting_file(chat_id, True)
        return {"ok": True}

    # استقبال الملف بعد /upload
    if "document" in msg or "video" in msg:
        if crud.is_waiting_file(chat_id):
            if "document" in msg:
                file_id = msg["document"]["file_id"]
                content_type = "pdf"
            else:
                file_id = msg["video"]["file_id"]
                content_type = "video"
            send_message(chat_id,
                f"✅ تم استلام الملف بنجاح!\nfile_id:\n`{file_id}`\nالآن أرسل الأمر التالي لإضافة الملف للمقرر:\n`/addfile <course> {content_type} {file_id}`"
            )
            crud.set_waiting_file(chat_id, False)
            return {"ok": True}

    # ----------------- أوامر المستخدم -----------------
    if text.startswith("/start"):
        send_message(chat_id, "مرحبًا بك في *بوت كلية الطب – جامعة المناقل!* 👋\nاختر من القائمة:",
                     reply_markup=get_main_keyboard(is_admin(user)))
        return {"ok": True}

    if text.strip() == "تواصل مع المطور 👨‍💻":
        send_message(chat_id, f"📩 يمكنك التواصل مع المطور عبر الحساب التالي:\n{ADMIN_USERNAME}")
        return {"ok": True}

    if text == "🏠 القائمة الرئيسية":
        send_message(chat_id, "عدت إلى القائمة الرئيسية 🏠", reply_markup=get_main_keyboard(is_admin(user)))
        return {"ok": True}

    if text == "ابدأ 🎓":
        send_message(chat_id, "اختر المقرر الدراسي:", reply_markup=get_courses_keyboard())
        return {"ok": True}

    if text in ["📘 التشريح", "🧠 الفسيولوجي"]:
        course = "تشريح" if "التشريح" in text else "فسيولوجي"
        send_message(chat_id, f"اختر نوع المحتوى لمقرر *{course}*:", reply_markup=get_types_keyboard(course))
        return {"ok": True}

    if text == "⬅️ رجوع":
        send_message(chat_id, "رجعت لاختيار المقرر ⬅️", reply_markup=get_courses_keyboard())
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
        if mat and mat["file_id"]:
            send_message(chat_id, f"جارٍ إرسال {content_type} الخاص بمقرر {course_name}...")
            send_file(chat_id, mat["file_id"], content_type)
        else:
            send_message(chat_id, "🚧 لم يتم العثور على هذا المحتوى بعد.")
        return {"ok": True}

    return {"ok": True}
