import os
import requests
import logging
import time
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

# ========= جلسات مؤقتة لتذكر اختيار المستخدم (course + ctype) =========
SESSIONS = {}  # chat_id -> {"course": str, "ctype": str, "time": timestamp}
SESSION_TTL = 300  # ثانية (5 دقائق)

def _cleanup_sessions():
    now = time.time()
    to_delete = [cid for cid, s in SESSIONS.items() if now - s.get("time", 0) > SESSION_TTL]
    for cid in to_delete:
        SESSIONS.pop(cid, None)

def set_session(chat_id, course, ctype):
    SESSIONS[chat_id] = {"course": course, "ctype": ctype, "time": time.time()}

def get_session(chat_id):
    _cleanup_sessions()
    return SESSIONS.get(chat_id)

def clear_session(chat_id):
    SESSIONS.pop(chat_id, None)


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

        # ===== إدارة الملفات المؤقتة من الأدمن مع الكاش =====
        if file_info and is_admin(user):
            file_id = file_info.get("file_id")
            if crud.is_waiting_file(chat_id, use_cache=True):
                crud.set_waiting_file_fileid(chat_id, file_id, content_type, doctor="")
                send_message(chat_id, "✅ تم استلام الملف. الآن *اكتب اسم الدكتور* لهذا الملف (أرسله كرسالة نصية).")
            else:
                crud.set_waiting_file(chat_id, True)
                crud.set_waiting_file_fileid(chat_id, file_id, content_type, doctor="")
                send_message(chat_id, "✅ تم استلام الملف. الآن *اكتب اسم الدكتور* لهذا الملف (أرسله كرسالة نصية).")
            return {"ok": True}

        if text and crud.is_waiting_file(chat_id, use_cache=True) and is_admin(user):
            waiting = crud.get_waiting_file(chat_id, use_cache=True)
            if not waiting or not waiting.get("file_id"):
                send_message(chat_id, "❌ لم يتم استلام ملف بعد. أرسل الملف أولًا ثم اسم الدكتور.")
                return {"ok": True}
            if not waiting.get("doctor"):
                doctor_name = text.strip()
                crud.set_waiting_file_doctor(chat_id, doctor_name)
                send_message(chat_id, f"✅ تم تسجيل دكتور: *{doctor_name}*.\nاختر المقرر الذي تريد ربط الملف به:", reply_markup=get_courses_keyboard())
                return {"ok": True}

        # ===== أوامر الأدمن =====
        if text == "رفع ملف جديد 📤" and is_admin(user):
            crud.set_waiting_file(chat_id, True)
            send_message(chat_id, "📤 الآن أرسل الملف (PDF / فيديو) وسأطلب اسم الدكتور بعد الاستلام.")
            return {"ok": True}

        if text and text.startswith("/addfile") and is_admin(user):
            parts = text.split()
            if len(parts) == 4:
                course, ctype, file_id = parts[1], parts[2], parts[3]
                crud.add_material(course, ctype, file_id, doctor=None)
                send_message(chat_id, f"✅ تمت إضافة {ctype} لمادة {course} بنجاح!")
            else:
                send_message(chat_id, "❌ الصيغة الصحيحة:\n/addfile <course> <type> <file_id>")
            return {"ok": True}

        # ===== أوامر المستخدم =====
        if text == "/start":
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
            send_message(chat_id, "🏠 عدت إلى القائمة الرئيسية", reply_markup=get_main_keyboard(is_admin(user)))
            return {"ok": True}

        if text == "ابدأ 🎓":
            send_message(chat_id, "📚 اختر المقرر الدراسي:", reply_markup=get_courses_keyboard())
            return {"ok": True}

        if text == "⬅️ رجوع":
            send_message(chat_id, "⬅️ رجعت لاختيار المقرر:", reply_markup=get_courses_keyboard())
            return {"ok": True}

        # ===== اختيار المقرر والنوع والدكتور مع الكاش =====
        course_names = [
            "Anatomy", "Pathology", "Histology", "Parasitology",
            "Physiology", "Biochemistry", "Embryology",
            "Microbiology", "Pharmacology"
        ]

        # المستخدم اختار مقرر أثناء وضع waiting_file (admin flow)
        if text and any(c == text for c in course_names) and crud.is_waiting_file(chat_id, use_cache=True) and is_admin(user):
            selected_course = text
            send_message(chat_id, f"📂 اختر نوع المحتوى لمقرر {selected_course}:", reply_markup=get_types_keyboard(selected_course))
            return {"ok": True}

        # المستخدم اختار نوع محتوى أثناء وجود waiting_file (admin completes upload)
        if text and any(x in text for x in ["PDF", "فيديو", "مرجع"]) and crud.is_waiting_file(chat_id, use_cache=True) and is_admin(user):
            course_name = text.split()[0]
            ctype = "pdf" if "PDF" in text else "video" if "فيديو" in text else "reference"
            waiting = crud.get_waiting_file(chat_id, use_cache=True)
            if not waiting or not waiting.get("file_id"):
                send_message(chat_id, "❌ لم يتم العثور على الملف المؤقت. أعد العملية.")
                return {"ok": True}
            file_id = waiting.get("file_id")
            doctor = waiting.get("doctor") or None
            crud.add_material(course_name, ctype, file_id, doctor=doctor)
            crud.set_waiting_file(chat_id, False)
            send_message(chat_id, f"✅ تم حفظ الملف للمقرر *{course_name}* (type={ctype}) تحت الدكتور: {doctor or 'غير محدد'}")
            return {"ok": True}

        # طلب الملفات من المستخدم بدون تجاوز الحصة: عرض كيبورد الدكاترة + حفظ session
        if text and any(x in text for x in ["PDF", "فيديو", "مرجع"]) and not crud.is_waiting_file(chat_id, use_cache=True):
            parts = text.split()
            course_name = parts[0]
            ctype = "pdf" if "PDF" in text else "video" if "فيديو" in text else "reference"
            doctors = crud.get_doctors_for_course_and_type(course_name, ctype, use_cache=True)
            if not doctors:
                send_message(chat_id, "🚧 لم يتم العثور على دكاترة أو ملفات لهذا الاختيار بعد.")
                return {"ok": True}
            # حفظ الجلسة حتى يضغط المستخدم اسم الدكتور
            set_session(chat_id, course_name, ctype)
            send_message(chat_id, f"👨‍🏫 اختر الدكتور لعرض ملفاته في {course_name} ({ctype}):", reply_markup=make_doctors_keyboard(doctors))
            return {"ok": True}

        # اختيار اسم الدكتور
        if text:
            doctor_name = text.strip()
            # أولًا: نتحقق إن في جلسة سابقة (يعني المستخدم سبق واختار course+type)
            sess = get_session(chat_id)
            if sess:
                # نستخدم السياق المضمون لإرسال ملفات نفس النوع فقط
                course = sess.get("course")
                ctype = sess.get("ctype")
                mats = crud.get_materials(course, ctype, use_cache=True)
                found_any = False
                for m in mats:
                    if m.get("doctor") and m.get("doctor") == doctor_name:
                        if not found_any:
                            send_message(chat_id, f"📤 ملفات الدكتور {doctor_name} في {course} ({ctype}):")
                            found_any = True
                        send_file(chat_id, m.get("file_id"), content_type=ctype)
                clear_session(chat_id)
                if found_any:
                    return {"ok": True}
                else:
                    send_message(chat_id, "🚧 لم يتم العثور على ملفات لهذا الدكتور ضمن هذا النوع/المقرر.")
                    return {"ok": True}

            # إذا ما كانت هناك جلسة، نعود لطريقة البحث العامة (البحث عبر كل المقررات والنوع)
            found_any = False
            for course in course_names:
                for ctype in ["pdf", "video", "reference"]:
                    mats = crud.get_materials(course, ctype, use_cache=True)
                    for m in mats:
                        if m.get("doctor") and m.get("doctor") == doctor_name:
                            if not found_any:
                                send_message(chat_id, f"📤 ملفات الدكتور {doctor_name}:")
                                found_any = True
                            send_file(chat_id, m.get("file_id"), content_type=ctype)
            if found_any:
                return {"ok": True}

        # افتراضي
        send_message(chat_id, "🤔 لم أفهم الأمر، يرجى اختيار من القائمة.")
        return {"ok": True}

    except Exception as e:
        logger.exception(f"Exception in webhook processing: {e}")
        return {"ok": True}
