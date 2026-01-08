import os
import requests
import logging
from fastapi import FastAPI, Header, HTTPException
from app import crud

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
    logger.info("✅ Database initialized successfully.")

# ========= إدارة انتظار رفع الملف داخل الذاكرة =========
WAITING_STATE = {}  # keyed by chat_id -> {"file_id":..., "semester":..., "course":..., "type":...}

# ========= حالة المستخدم لاختيار السمستر والمقرر والنوع =========
USER_STATE = {}  # keyed by chat_id -> {"semester": ..., "course": ..., "type": ...}

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

def get_semesters_keyboard():
    return {
        "keyboard": [
            [{"text": "الفصل الأول 1️⃣"}, {"text": "الفصل الثاني 2️⃣"}],
            [{"text": "الفصل الثالث 3️⃣"}, {"text": "الفصل الرابع 4️⃣"}],
            [{"text": "الفصل الخامس 5️⃣"}],
            [{"text": "🏠 القائمة الرئيسية"}]
        ],
        "resize_keyboard": True
    }

def get_courses_keyboard(semester):
    # تحديد المقررات حسب كل سمستر
    courses_map = {
        "1": [["Anatomy"], ["Histology"], ["Embryology"]],
        "2": [["Anatomy"], ["Physiology"], ["Biochemistry"]],
        "3": [["Pathology"], ["Pharmacology"], ["Microbiology"]],
        "4": [["Pathology"], ["Pharmacology"], ["Parasitology"]],
        "5": [["Medicine"], ["Surgery"], ["Pediatrics"]],
    }
    
    course_buttons = courses_map.get(semester, [[{"text": "لا توجد مقررات"}]])
    course_buttons.append([{"text": "⬅️ رجوع"}, {"text": "🏠 القائمة الرئيسية"}])
    
    return {"keyboard": course_buttons, "resize_keyboard": True}

def get_types_keyboard(course):
    return {
        "keyboard": [
            [{"text": f"{course} 📄 PDF"}, {"text": f"{course} 🎥 فيديو"}],
            [{"text": f"{course} 📚 مرجع"}],
            [{"text": "⬅️ رجوع"}, {"text": "🏠 القائمة الرئيسية"}]
        ],
        "resize_keyboard": True
    }

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

        # ===== إدارة الملفات من الأدمن =====
        if file_info and is_admin(user):
            file_id = file_info.get("file_id")
            WAITING_STATE[chat_id] = {
                "file_id": file_id,
                "semester": None,
                "course": None,
                "type": content_type
            }
            send_message(chat_id, "✅ تم استلام الملف. الآن اختر السمستر:", reply_markup=get_semesters_keyboard())
            return {"ok": True}

        # ===== أوامر الأدمن =====
        if text == "رفع ملف جديد 📤" and is_admin(user):
            crud.set_waiting_file(chat_id, True)
            send_message(chat_id, "📤 الآن أرسل الملف (PDF / فيديو) وسأطلب اختيار السمستر بعد الاستلام.")
            return {"ok": True}

        if text and text.startswith("/addfile") and is_admin(user):
            parts = text.split()
            if len(parts) == 5:
                semester, course, ctype, file_id = parts[1], parts[2], parts[3], parts[4]
                crud.add_material(semester, course, ctype, file_id)
                send_message(chat_id, f"✅ تمت إضافة {ctype} لمادة {course} (سمستر {semester}) بنجاح!")
            else:
                send_message(chat_id, "❌ الصيغة الصحيحة:\n/addfile <semester> <course> <type> <file_id>")
            return {"ok": True}

        # ===== أوامر المستخدم =====
        if text == "/start":
            USER_STATE.pop(chat_id, None)
            welcome_text = (
                "👋 مرحبًا بك في بوت كلية الطب – جامعة المناقل!\n\n"
                "📚 هذا البوت يساعدك للوصول إلى محتوى المقررات بسهولة.\n"
                "⚠️ تنويه: البوت في مراحل الصيانة لرفع كميات كبيرة من المواد.\n"
            )
            send_message(chat_id, welcome_text, reply_markup=get_main_keyboard(is_admin(user)))
            return {"ok": True}

        if text == "تواصل مع المطور 👨‍💻":
            send_message(chat_id, f"📩 تواصل مع المطور: {ADMIN_USERNAME}")
            return {"ok": True}

        if text == "🏠 القائمة الرئيسية":
            USER_STATE.pop(chat_id, None)
            WAITING_STATE.pop(chat_id, None)
            send_message(chat_id, "🏠 عدت إلى القائمة الرئيسية", reply_markup=get_main_keyboard(is_admin(user)))
            return {"ok": True}

        if text == "ابدأ 🎓":
            USER_STATE.pop(chat_id, None)
            send_message(chat_id, "📚 اختر الفصل الدراسي:", reply_markup=get_semesters_keyboard())
            return {"ok": True}

        if text == "⬅️ رجوع":
            state = USER_STATE.get(chat_id, {})
            
            # إذا كان عند اختيار النوع، نرجع لاختيار المقرر
            if state.get("course") and state.get("semester"):
                state.pop("type", None)
                state.pop("course", None)
                send_message(chat_id, f"⬅️ اختر المقرر:", reply_markup=get_courses_keyboard(state.get("semester")))
                return {"ok": True}
            
            # إذا كان عند اختيار المقرر، نرجع لاختيار السمستر
            if state.get("semester"):
                USER_STATE.pop(chat_id, None)
                send_message(chat_id, "⬅️ اختر الفصل الدراسي:", reply_markup=get_semesters_keyboard())
                return {"ok": True}
            
            # افتراضي: رجوع للسمسترات
            send_message(chat_id, "⬅️ اختر الفصل الدراسي:", reply_markup=get_semesters_keyboard())
            return {"ok": True}

        # ===== اختيار السمستر =====
        semester_map = {
            "الفصل الأول 1️⃣": "1",
            "الفصل الثاني 2️⃣": "2",
            "الفصل الثالث 3️⃣": "3",
            "الفصل الرابع 4️⃣": "4",
            "الفصل الخامس 5️⃣": "5"
        }
        
        if text in semester_map:
            semester = semester_map[text]
            
            # للأدمن: حفظ السمستر في WAITING_STATE
            if is_admin(user) and chat_id in WAITING_STATE:
                WAITING_STATE[chat_id]["semester"] = semester
                send_message(chat_id, f"✅ تم اختيار {text}. الآن اختر المقرر:", reply_markup=get_courses_keyboard(semester))
                return {"ok": True}
            
            # للمستخدم العادي: حفظ في USER_STATE
            USER_STATE[chat_id] = {"semester": semester}
            send_message(chat_id, f"📖 اختر المقرر من {text}:", reply_markup=get_courses_keyboard(semester))
            return {"ok": True}

        # ===== اختيار المقرر =====
        course_names = [
            "Anatomy", "Pathology", "Histology", "Parasitology",
            "Physiology", "Biochemistry", "Embryology",
            "Microbiology", "Pharmacology", "Medicine", "Surgery", "Pediatrics"
        ]

        if text in course_names:
            # للأدمن: حفظ المقرر في WAITING_STATE
            if is_admin(user) and chat_id in WAITING_STATE:
                WAITING_STATE[chat_id]["course"] = text
                send_message(chat_id, f"📂 اختر نوع المحتوى لمقرر {text}:", reply_markup=get_types_keyboard(text))
                return {"ok": True}
            
            # للمستخدم: حفظ المقرر
            state = USER_STATE.get(chat_id, {})
            if not state.get("semester"):
                send_message(chat_id, "⚠️ يرجى اختيار السمستر أولاً")
                return {"ok": True}
            
            state["course"] = text
            USER_STATE[chat_id] = state
            send_message(chat_id, f"📂 اختر نوع المحتوى لمقرر {text}:", reply_markup=get_types_keyboard(text))
            return {"ok": True}

        # ===== اختيار نوع الملف =====
        if text and any(x in text for x in ["PDF", "فيديو", "مرجع"]):
            course_name = text.split()[0]
            ctype = "pdf" if "PDF" in text else "video" if "فيديو" in text else "reference"

            # للأدمن: حفظ الملف نهائياً
            if is_admin(user) and chat_id in WAITING_STATE:
                waiting_local = WAITING_STATE.get(chat_id, {})
                file_id = waiting_local.get("file_id")
                semester = waiting_local.get("semester")
                course = waiting_local.get("course") or course_name

                if not file_id or not semester:
                    send_message(chat_id, "❌ بيانات غير مكتملة. أعد العملية.")
                    return {"ok": True}

                crud.add_material(semester, course, ctype, file_id)
                
                try:
                    crud.set_waiting_file(chat_id, False)
                except Exception:
                    logger.exception("Failed to clear waiting_file in sheet (ignored).")

                WAITING_STATE.pop(chat_id, None)
                send_message(chat_id, f"✅ تم حفظ الملف للسمستر {semester} - مقرر {course} ({ctype})")
                return {"ok": True}

            # للمستخدم: عرض الملفات مباشرة
            state = USER_STATE.get(chat_id, {})
            semester = state.get("semester")
            course = state.get("course")
            
            if not semester or not course:
                send_message(chat_id, "⚠️ يرجى اختيار السمستر والمقرر أولاً")
                return {"ok": True}

            # جلب الملفات من قاعدة البيانات
            mats = crud.get_materials(semester, course, ctype, use_cache=True)
            
            if not mats:
                send_message(chat_id, f"🚧 لا توجد ملفات متاحة حالياً لـ {course} ({ctype})")
                return {"ok": True}
            
            send_message(chat_id, f"📤 جاري إرسال ملفات {course} ({ctype})...")
            for m in mats:
                send_file(chat_id, m.get("file_id"), content_type=ctype)
            
            return {"ok": True}

        # افتراضي
        send_message(chat_id, "🤔 لم أفهم الأمر، يرجى اختيار من القائمة.")
        return {"ok": True}

    except Exception as e:
        logger.exception(f"Exception in webhook processing: {e}")
        return {"ok": True}
