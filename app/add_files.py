from app import crud, db

db.init_db()

crud.add_material("تشريح", "pdf", "BAACAgQAAxkBAAECzFRpE0WDefraOSSkW4uh2omrvf-aVQACUxcAAlkmmVM9LgefiEH1ZzYE")
crud.add_material("فسيولوجي", "video", "BQACAgQAAxkBA...")
crud.add_material("تشريح", "reference", "BQACAgQAAxkBA...")

print("✅ تم إضافة الملفات بنجاح!")
