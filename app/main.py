from fastapi import FastAPI, Request
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from app import crud
import os

app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(BOT_TOKEN)


@app.post("/webhook")
async def webhook(request: Request):
    update = await request.json()
    print("🔹 Received update:", update)

    # حالة الرسائل النصية (للتعامل مع /start أو رفع ملف)
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        # أمر /start
        if text == "/start":
            keyboard = [
                [InlineKeyboardButton("📚 ابدأ", callback_data="start")],
                [InlineKeyboardButton("📞 تواصل مع المطور", callback_data="contact_dev")],
                [InlineKeyboardButton("📤 رفع ملف جديد", callback_data="upload_file")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            bot.send_message(chat_id, "أهلاً بك في بوت كلية الطب 👨‍⚕️\nاختر من القائمة:", reply_markup=reply_markup)

        # استقبال ملف أثناء الرفع
        elif crud.is_waiting_file(chat_id):
            if "document" in update["message"]:
                file_id = update["message"]["document"]["file_id"]
                crud.set_waiting_file(chat_id, False)
                bot.send_message(chat_id, f"✅ تم استلام الملف بنجاح!\n📄 file_id الخاص به:\n`{file_id}`", parse_mode="Markdown")
            else:
                bot.send_message(chat_id, "❌ أرسل ملف PDF أو مستند فقط، وليس نصاً.")
        else:
            bot.send_message(chat_id, "استخدم الأزرار أدناه 👇")

    # حالة الضغط على الأزرار (callback)
    elif "callback_query" in update:
        query = update["callback_query"]
        data = query["data"]
        chat_id = query["message"]["chat"]["id"]

        # زر ابدأ
        if data == "start":
            keyboard = [
                [InlineKeyboardButton("📖 المواد الدراسية", callback_data="materials")],
                [InlineKeyboardButton("📞 تواصل مع المطور", callback_data="contact_dev")],
                [InlineKeyboardButton("📤 رفع ملف جديد", callback_data="upload_file")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            bot.send_message(chat_id, "اختر من القائمة التالية 👇", reply_markup=reply_markup)

        # زر تواصل مع المطور
        elif data == "contact_dev":
            bot.send_message(chat_id, "📞 للتواصل مع المطور:\n@Mgdad_Ali")

        # زر رفع ملف
        elif data == "upload_file":
            bot.send_message(chat_id, "📤 أرسل الآن الملف الذي تريد رفعه (PDF أو مرجع).")
            crud.set_waiting_file(chat_id, True)

        # زر رجوع
        elif data == "back":
            keyboard = [
                [InlineKeyboardButton("📚 ابدأ", callback_data="start")],
                [InlineKeyboardButton("📞 تواصل مع المطور", callback_data="contact_dev")],
                [InlineKeyboardButton("📤 رفع ملف جديد", callback_data="upload_file")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            bot.send_message(chat_id, "⬅️ عدت إلى القائمة الرئيسية:", reply_markup=reply_markup)

        else:
            bot.send_message(chat_id, "❓ لم أفهم هذا الخيار، حاول مجددًا.")

    return {"ok": True}
