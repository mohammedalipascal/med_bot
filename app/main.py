# app/main.py
import os
import requests
import logging
from fastapi import FastAPI, Header, HTTPException
from app import crud  # CRUD للتعامل مع SQLite

# ========= Logging مفصل =========
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ========= الإعدادات الأساسية =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN", None)
ADMIN_USERNAME = "@Mgdad_Ali"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI(title="Med Faculty Bot")

@app.on_event("startup")
async def startup():
    crud.init_db()
    logger.info("Database initialized successfully.")

# ========= دوال مساعدة =========
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        logger.info(f"Send message status: {r.status_code}, response: {r.text}")
    except Exception as e:
        logger.exception(f"Failed to send message: {e}")

def send_file(chat_id, file_id, content_type="pdf"):
    try:
        if content_type == "video":
            r = requests.post(f"{TELEGRAM_API}/sendVideo", json={"chat_id": chat_id, "video": file_id})
        else:
            r = requests.post(f"{TELEGRAM_API}/sendDocument", json={"chat_id": chat_id, "document": file_id})
        logger.info(f"Send file status: {r.status_code}, response: {r.text}")
    except Exception as e:
        logger.exception(f"Failed to send file: {e}")

def is_admin(user):
    return user.get("username") == ADMIN_USERNAME.replace("@", "")

# ========= الكيبوردات =========
def get_main_keyboard(is_admin=False):
    buttons = [[{"text": "ابدأ 🎓"}], [{"text": "تواصل مع المطور 👨‍💻"}]]
    if is_admin:
        buttons.append([{"text": "رفع ملف جديد 📤"}])
    return {"keyboard": buttons, "resize_keyboard": True}

def get_courses_keyboard():
    return {
        "keyboard": [[{"text": "📘 التشريح"}, {"text": "🧠 الفسيولوجي"}], [{"text": "🏠 القائمة الرئيسية"}]],
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

# ========= Webhook الرئيسي =========
@app.post("/webhook")
async def webhook(update: dict, x_telegram_bot_api_secret_token: str = Header(None)):
    try:
        if WEBHOOK_SECRET_TOKEN and x_telegram_bot_api_secret_token != WEBHOOK_SECRET_TOKEN:
            logger.warning("Invalid secret token received.")
            raise HTTPException(status_code=401, detail="Invalid secret header")

        logger.debug(f"Received update: {update}")
        msg = update.get("message")
        if not msg:
            return {"ok": True}

        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user = msg.get("from", {})

        # ========= التعامل مع الملفات (عادية أو forwarded) =========
        file_info = None
        content_type = None

        if "document" in msg:
            file_info = msg["document"]
            content_type = "pdf"
        elif "video" in msg:
            file_info = msg["video"]
            content_type = "video"

        # تحقق من الملفات الموجهة (forwarded)
        elif "forward_from_message_id" in msg or "forward_from_chat" in msg:
            if "document" in msg:
                file_info = msg["document"]
                content_type = "pdf"
            elif "video" in msg:
                file_info = msg["video"]
                content_type = "video"

        if file_info and crud.is_waiting_file(chat_id):
            file_id = file_info["file_id"]

            # حفظ الملف تلقائيًا في قاعدة البيانات
            crud.add_material("unknown_course", content_type, file_id)  # يمكن تعديل course لاحقًا

            send_message(
                chat_id,
                f"✅ تم استلام الملف بنجاح!\n"
                f"file_id:\n{file_id}\n"
                f"الآن أرسل الأمر التالي لإضافته:\n"
                f"/addfile <course> {content_type} {file_id}"
            )
            crud.set_waiting_file(chat_id, False)
            logger.info(f"Received file from admin: {file_id} (type={content_type})")
            return {"ok": True}

        # ========= أوامر الأدمن =========
        if text.startswith("/addfile") and is_admin(user):
            parts = text.split()
            if len(parts) == 4:
                course, ctype, file_id = parts[1], parts[2], parts[3]
                crud.add_material(course, ctype, file_id)
                send_message(chat_id, f"✅ تمت إضافة {ctype} لمادة {course} بنجاح!")
                logger.info(f"Admin added file: course={course}, type={ctype}, file_id={file_id}")
            else:
                send_message(chat_id, "❌ الصيغة الصحيحة:\n/addfile <course> <type> <file_id>")
            return {"ok": True}

        if text == "رفع ملف جديد 📤" and is_admin(user):
            send_message(chat_id,
                         "📤 أرسل الآن الملف (PDF / فيديو) للبوت، وسأعطيك file_id مباشرة.")
            crud.set_waiting_file(chat_id, True)
            logger.info(f"Admin {user.get('username')} is uploading a file.")
            return {"ok": True}

        # ========= أوامر المستخدم =========
        if text.startswith("/start"):
            send_message(chat_id, "👋 مرحبًا بك في بوت كلية الطب – جامعة المناقل\n\n"
    "📚 هذا البوت صُمم لمساعدتك في الوصول إلى كل محتوى ومقررات الطب بسهولة:\n"
    "📝 فيديوهات تعليمية\n"
    "📄 ملفات PDF\n"
    "📚 مراجع علمية\n\n"
    "⚠️ *تنويه:* البوت حالياً في مراحل الصيانة والتجهيز لتوفير كل المواد بأداء مستقر.\n\n"
  ",
                         reply_markup=get_main_keyboard(is_admin(user)))
            return {"ok": True}

        if text == "تواصل مع المطور 👨‍💻":
            send_message(chat_id, f"📩 يمكنك التواصل مع المطور عبر الحساب التالي:\n{ADMIN_USERNAME}")
            return {"ok": True}

        if text == "🏠 القائمة الرئيسية":
            send_message(chat_id, "🏠 عدت إلى القائمة الرئيسية",
                         reply_markup=get_main_keyboard(is_admin(user)))
            return {"ok": True}

        if text == "ابدأ 🎓":
            send_message(chat_id, "📚 اختر المقرر الدراسي:", reply_markup=get_courses_keyboard())
            return {"ok": True}

        if text in ["📘 التشريح", "🧠 الفسيولوجي"]:
            course = "تشريح" if "التشريح" in text else "فسيولوجي"
            send_message(chat_id, f"📂 اختر نوع المحتوى لمقرر {course}:", reply_markup=get_types_keyboard(course))
            return {"ok": True}

        if text == "⬅️ رجوع":
            send_message(chat_id, "⬅️ رجعت لاختيار المقرر:", reply_markup=get_courses_keyboard())
            return {"ok": True}

        # ========= اختيار نوع المحتوى =========
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
            if mat and mat.get("file_id"):
                send_message(chat_id, f"📨 جارٍ إرسال {content_type} الخاص بمقرر {course_name}...")
                send_file(chat_id, mat["file_id"], content_type)
            else:
                send_message(chat_id, "🚧 لم يتم العثور على هذا المحتوى بعد.")
            return {"ok": True}

        send_message(chat_id, "🤔 لم أفهم الأمر، يرجى اختيار من القائمة.")
        return {"ok": True}

    except Exception as e:
        logger.exception(f"Exception in webhook processing: {e}")
        return {"ok": True}
