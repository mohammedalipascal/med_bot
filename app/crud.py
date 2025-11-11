# app/crud.py
from .db import SessionLocal, Material

def get_material(course_name, content_type):
    db = SessionLocal()
    result = db.query(Material).filter_by(course_name=course_name, content_type=content_type).first()
    db.close()
    return result

def add_material(course_name, content_type, file_id):
    db = SessionLocal()
    m = Material(course_name=course_name, content_type=content_type, file_id=file_id)
    db.add(m)
    db.commit()
    db.close()
