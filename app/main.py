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

@app.on_event("startup")
async def startup():
    crud.init_db()
    logger.info("✅ Database initialized successfully.")

# ========= إدارة انتظار رفع الملف داخل الذاكرة =========
# هذا يسمح بتفادي قراءات خاطئة من الكاش أو Google Sheet خلال عملية رفع الملف
WAITING_STATE = {}  # keyed by chat_id -> {"file_id":..., "doctor":..., "course":..., "type":...}

# ========= حالة المستخدم لاختيار النوع والمقرر (حتى لا نرسل PDF + Video مع بعض) =========
USER_STATE = {}  # keyed by chat_id -> {"course": ..., "type": ...}

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

        # ===== إدارة الملفات المؤقتة من الأدمن باستخدام WAITING_STATE (ذاكرة) =====
        # استقبال ملف جديد من الأدمن -> نخزن داخليًا في WAITING_STATE فقط
        if file_info and is_admin(user):
            file_id = file_info.get("file_id")
            WAITING_STATE[chat_id] = {
                "file_id": file_id,
                "doctor": None,
                "course": None,
                "type": content_type
            }
            # رسالة كما في الأصل (لم أغير النص)
            send_message(chat_id, "✅ تم استلام الملف. الآن *اكتب اسم الدكتور* لهذا الملف (أرسله كرسالة نصية).")
            return {"ok": True}

        # لو الأدمن كتب اسم الدكتور أثناء وجود حالة انتظار داخل الذاكرة
        if text and is_admin(user) and chat_id in WAITING_STATE:
            waiting_local = WAITING_STATE[chat_id]
            # لو الدكتور ليس مسجل بعد، اعتبر الرسالة اسم الدكتور
            if not waiting_local.get("doctor"):
                doctor_name = text.strip()
                waiting_local["doctor"] = doctor_name
                # نرسل نفس الرسالة الأصلية لاختيار المقرر
                send_message(chat_id, f"✅ تم تسجيل دكتور: *{doctor_name}*.\nاختر المقرر الذي تريد ربط الملف به:", reply_markup=get_courses_keyboard())
                return {"ok": True}

        # ===== أوامر الأدمن (زر بدء رفع ملف جديد) =====
        if text == "رفع ملف جديد 📤" and is_admin(user):
            # نحتفظ بالسلوك الأصلي هنا (هذا يسجل حالة انتظار في الورقة إذا أردت)
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
            # امسح حالة المستخدم القديمة لو كانت موجودة
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
            # امسح حالة المستخدم عند العودة للقائمة الرئيسية
            USER_STATE.pop(chat_id, None)
            send_message(chat_id, "🏠 عدت إلى القائمة الرئيسية", reply_markup=get_main_keyboard(is_admin(user)))
            return {"ok": True}

        if text == "ابدأ 🎓":
            send_message(chat_id, "📚 اختر المقرر الدراسي:", reply_markup=get_courses_keyboard())
            return {"ok": True}

        if text == "⬅️ رجوع":
            # رجوع: نمسح حالة الاختيار للمستخدم
            USER_STATE.pop(chat_id, None)
            send_message(chat_id, "⬅️ رجعت لاختيار المقرر:", reply_markup=get_courses_keyboard())
            return {"ok": True}

        # ===== اختيار المقرر والنوع والدكتور مع الكاش =====
        course_names = [
            "Anatomy", "Pathology", "Histology", "Parasitology",
            "Physiology", "Biochemistry", "Embryology",
            "Microbiology", "Pharmacology"
        ]

        # ===== إذا الأدمن في وضع انتظار واختر المقرر، نسجل المقرر في الذاكرة =====
        if text and text in course_names and is_admin(user) and chat_id in WAITING_STATE:
            WAITING_STATE[chat_id]["course"] = text
            # نرسل واجهة اختيار النوع كما في الأصل
            send_message(chat_id, f"📂 اختر نوع المحتوى لمقرر {text}:", reply_markup=get_types_keyboard(text))
            return {"ok": True}

        # اختيار المقرر الدراسي (للمستخدمين العاديين)
        if text and text in course_names:
            # نمسح حالة سابقة ثم نعرض أنواع الملف (سيتم وضع النوع عند اختياره)
            USER_STATE.pop(chat_id, None)
            send_message(chat_id, f"📂 اختر نوع المحتوى لمقرر {text}:", reply_markup=get_types_keyboard(text))
            return {"ok": True}

        # اختيار نوع الملف (PDF / فيديو / مرجع)
        if text and any(x in text for x in ["PDF", "فيديو", "مرجع"]):
            course_name = text.split()[0]
            ctype = "pdf" if "PDF" in text else "video" if "فيديو" in text else "reference"

            # أولاً: إذا الأدمن في WAITING_STATE محليًا، نستخدم البيانات المحفوظة ونضيف المادة
            if is_admin(user) and chat_id in WAITING_STATE:
                waiting_local = WAITING_STATE.get(chat_id, {})
                file_id = waiting_local.get("file_id")
                doctor = waiting_local.get("doctor") or None
                # استخدم المقرر المحفوظ بالذاكرة إن وجد، وإلا استخدم course_name المستخرج
                course_used = waiting_local.get("course") or course_name

                if not file_id:
                    send_message(chat_id, "❌ لم يتم العثور على الملف المؤقت. أعد العملية.")
                    return {"ok": True}

                # حفظ المادة في Google Sheet عبر CRUD (واحد write هنا مطلوب)
                crud.add_material(course_used, ctype, file_id, doctor=doctor)
                # نحاول إزالة حالة الانتظار من الـ sheet إذا كانت مسجلة هناك (حتى لو لم نستخدمها للقراءة)
                try:
                    crud.set_waiting_file(chat_id, False)
                except Exception:
                    # لا نوقف التدفق في حال فشل مسح الانتظار في الورقة
                    logger.exception("Failed to clear waiting_file in sheet (ignored).")

                # نحذف الحالة المحلية
                WAITING_STATE.pop(chat_id, None)

                # رسالة كما في الأصل (نفس النص)
                send_message(chat_id, f"✅ تم حفظ الملف للمقرر *{course_used}* (type={ctype}) تحت الدكتور: {doctor or 'غير محدد'}")
                return {"ok": True}

            # ثانيًا: المسار الطبيعي للمستخدم لعرض الدكاترة حسب النوع
            # نسجل حالة المستخدم الحالية حتى نعرف النوع عند اختيار اسم الدكتور
            USER_STATE[chat_id] = {"course": course_name, "type": ctype}

            doctors = crud.get_doctors_for_course_and_type(course_name, ctype, use_cache=True)
            if not doctors:
                send_message(chat_id, "🚧 لم يتم العثور على دكاترة أو ملفات لهذا الاختيار بعد.")
                return {"ok": True}
            send_message(chat_id, f"👨‍🏫 اختر الدكتور لعرض ملفاته في {course_name} ({ctype}):", reply_markup=make_doctors_keyboard(doctors))
            return {"ok": True}

        # اختيار اسم الدكتور (للمستخدمين العاديين) — الآن نحترم النوع الذي اختاره المستخدم سابقاً
        if text:
            # إذا الأدمن يرسل اسم الدكتور أثناء الانتظار، تعاملنا مع الحالة أعلاه؛ هنا المسار العام لباقي المستخدمين
            doctor_name = text.strip()

            # أولًا: هل لدى المستخدم حالة مختارة (course + type)؟
            state = USER_STATE.get(chat_id)
            found_any = False

            if state:
                # جلب المواد للمقرر والنوع المحددين فقط
                course = state.get("course")
                ctype = state.get("type")
                if course and ctype:
                    mats = crud.get_materials(course, ctype, use_cache=True)
                    for m in mats:
                        if m.get("doctor") == doctor_name:
                            if not found_any:
                                send_message(chat_id, f"📤 ملفات الدكتور {doctor_name}:")
                                found_any = True
                            send_file(chat_id, m.get("file_id"), content_type=ctype)
                    if found_any:
                        return {"ok": True}

            # لو لا يوجد state أو لم نجد ملفات بالنوع المحدد، نرجع للسلوك القديم (نبحث في كل المقررات والأنواع)
            for course in course_names:
                for ctype in ["pdf", "video", "reference"]:
                    mats = crud.get_materials(course, ctype, use_cache=True)
                    for m in mats:
                        if m.get("doctor") == doctor_name:
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
