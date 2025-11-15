import os
import requests
import logging
from fastapi import FastAPI, Header, HTTPException
from app import crud  # CRUD يتعامل مع Google Sheets وفق التعديل الأخير

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

# ========= حالة المستخدم (حل المشكلة) =========
USER_STATE = {}

@app.on_event("startup")
async def startup():
    crud.init_db()
    logger.info("✅ Database initialized successfully.")

# ========= دوال مساعدة =========
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
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

# ========= القوائم =========
def get_main_keyboard(is_admin=False):
    buttons = [[{"text": "ابدأ 🎓"}], [{"text": "تواصل مع المطور 👨‍💻"}]]
    if is_admin:
        buttons.append([{"text": "رفع ملف جديد 📤"}])
    return {"keyboard": buttons, "resize_keyboard": True}

def get_courses_keyboard():
    return {
        "keyboard": [
            [{"text": "Anatomy"}, {"text": "Pathology"}],
            [{"text": "Histology"}, {"text": "Parasitology"}],
            [{"text": "Physiology"}, {"text": "Biochemistry"}],
            [{"text": "Embryology"}, {"text": "Microbiology"}],
            [{"text": "Pharmacology"}, {"text": "🏠 القائمة الرئيسية"}],
            [{"text": "⬅️ رجوع"}]
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

def make_doctors_keyboard(doctors):
    kb = []
    row = []
    for i, d in enumerate(doctors, start=1):
        row.append({"text": d})
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([{"text": "🏠 القائمة الرئيسية"}])
    return {"keyboard": kb, "resize_keyboard": True}

# ========= Webhook =========
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

        # التقاط الملفات
        file_info = None
        content_type = None
        if "document" in msg:
            file_info = msg["document"]
            content_type = "pdf"
        elif "video" in msg:
            file_info = msg["video"]
            content_type = "video"

        # ===== إدارة الملفات المؤقتة للأدمن =====
        if file_info and is_admin(user):
            file_id = file_info.get("file_id")
            if crud.is_waiting_file(chat_id, use_cache=True):
                crud.set_waiting_file_fileid(chat_id, file_id, content_type, doctor="")
            else:
                crud.set_waiting_file(chat_id, True)
                crud.set_waiting_file_fileid(chat_id, file_id, content_type, doctor="")
            send_message(chat_id, "✅ تم استلام الملف. الآن *اكتب اسم الدكتور* لهذا الملف.")
            return {"ok": True}

        if text and crud.is_waiting_file(chat_id, use_cache=True) and is_admin(user):
            waiting = crud.get_waiting_file(chat_id, use_cache=True)
            if not waiting or not waiting.get("file_id"):
                send_message(chat_id, "❌ لم يتم استلام ملف بعد.")
                return {"ok": True}

            if not waiting.get("doctor"):
                doctor_name = text.strip()
                crud.set_waiting_file_doctor(chat_id, doctor_name)
                send_message(chat_id, f"✅ تم تسجيل دكتور: *{doctor_name}*.\nاختر المقرر:", reply_markup=get_courses_keyboard())
                return {"ok": True}

        # ===== أوامر الأدمن =====
        if text == "رفع ملف جديد 📤" and is_admin(user):
            crud.set_waiting_file(chat_id, True)
            send_message(chat_id, "📤 أرسل الملف الآن.")
            return {"ok": True}

        # ===== المستخدم =====
        if text == "/start":
            USER_STATE.pop(chat_id, None)
            send_message(chat_id, "👋 أهلاً!", reply_markup=get_main_keyboard(is_admin(user)))
            return {"ok": True}

        if text == "ابدأ 🎓":
            send_message(chat_id, "📚 اختر المقرر:", reply_markup=get_courses_keyboard())
            return {"ok": True}

        if text == "⬅️ رجوع":
            send_message(chat_id, "رجعت لاختيار المقرر:", reply_markup=get_courses_keyboard())
            return {"ok": True}

        if text == "🏠 القائمة الرئيسية":
            USER_STATE.pop(chat_id, None)
            send_message(chat_id, "🏠 القائمة الرئيسية", reply_markup=get_main_keyboard(is_admin(user)))
            return {"ok": True}

        # ===== اختيار المقرر =====
        course_names = [
            "Anatomy", "Pathology", "Histology", "Parasitology",
            "Physiology", "Biochemistry", "Embryology",
            "Microbiology", "Pharmacology"
        ]

        if text in course_names:
            send_message(chat_id, f"📂 اختر نوع المحتوى لمقرر {text}:", reply_markup=get_types_keyboard(text))
            return {"ok": True}

        # ===== اختيار نوع المادة =====
        if any(x in text for x in ["PDF", "فيديو", "مرجع"]):
            course_name = text.split()[0]
            ctype = "pdf" if "PDF" in text else "video" if "فيديو" in text else "reference"

            # تخزين الوضع الحالي للمستخدم
            USER_STATE[chat_id] = {
                "course": course_name,
                "type": ctype
            }

            doctors = crud.get_doctors_for_course_and_type(course_name, ctype, use_cache=True)
            if not doctors:
                send_message(chat_id, "🚧 لا توجد ملفات بعد.")
                return {"ok": True}

            send_message(chat_id, f"👨‍🏫 اختر الدكتور ({ctype}):", reply_markup=make_doctors_keyboard(doctors))
            return {"ok": True}

        # ===== اختيار الدكتور =====
        if text:
            doctor = text.strip()
            state = USER_STATE.get(chat_id)

            if state:
                course = state["course"]
                ctype = state["type"]

                mats = crud.get_materials(course, ctype, use_cache=True)
                files = [m for m in mats if m.get("doctor") == doctor]

                if files:
                    send_message(chat_id, f"📤 ملفات الدكتور {doctor} ({ctype}):")
                    for m in files:
                        send_file(chat_id, m["file_id"], content_type=ctype)
                    return {"ok": True}

        # ===== Default =====
        send_message(chat_id, "🤔 لم أفهم الأمر.")
        return {"ok": True}

    except Exception as e:
        logger.exception(f"Exception in webhook: {e}")
        return {"ok": True}
