"""Student Academic Profile API — Phases 1, 2 and 3."""

import re
from threading import RLock

from bs4 import BeautifulSoup
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from audit import build_audit
from catalog import normalize_code, parse_catalog

app = FastAPI(title="Student Academic Profile API")
app.state.students = {}
app.state.catalog = {}
app.state.lock = RLock()


class HistoryCourse(BaseModel):
    course_code: str
    term: str
    credits_earned: int
    status: str


class PlannedCourse(BaseModel):
    course_code: str
    term: str


class HistoryRequest(BaseModel):
    history: list[HistoryCourse]


class PlanRequest(BaseModel):
    planned_courses: list[PlannedCourse]


def get_student(student_id: str):
    student = app.state.students.get(student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


def grade_rank(grade: str):
    grade = grade.strip().upper()
    if re.fullmatch(r"\d+(?:\.\d+)?%?", grade):
        return 2
    if grade and grade not in {"P", "PASS", "-", "N/A"}:
        return 1
    return 0


def parse_transcript(html: bytes):
    """Original Phase 2 transcript parser retained for compatibility."""
    soup = BeautifulSoup(html, "html.parser")
    courses = {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_index = None
        columns = None
        for index, row in enumerate(rows):
            headers = row.find_all("th")
            if not headers:
                continue
            labels = [
                cell.get_text(" ", strip=True).lower() for cell in headers
            ]
            required = ["status", "course", "grade", "term", "credits"]
            if all(name in labels for name in required):
                columns = {name: labels.index(name) for name in required}
                header_index = index
                break
        if columns is None:
            continue
        for row in rows[header_index + 1:]:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) <= max(columns.values()):
                continue

            def cell_value(name):
                return cells[columns[name]].get_text(" ", strip=True)

            status = cell_value("status")
            course_code = cell_value("course")
            grade = cell_value("grade")
            term = cell_value("term")
            credits_text = cell_value("credits")
            if status not in {"Completed", "In-Progress", "Attempted"}:
                continue
            if not term or not course_code:
                continue
            try:
                credits = int(credits_text)
            except (ValueError, TypeError):
                credits = 0
            record = {
                "course_code": course_code,
                "term": term,
                "credits_earned": credits,
                "status": status,
            }
            key = (course_code, term)
            score = (grade_rank(grade), credits)
            if key not in courses or score > courses[key][0]:
                courses[key] = (score, record)
    return [item[1] for item in courses.values()]


@app.post("/api/v1/admin/catalog/import", status_code=201)
async def import_catalog(file: UploadFile = File(...)):
    courses = parse_catalog(await file.read())
    if not courses:
        raise HTTPException(status_code=422, detail="No catalog courses found")
    with app.state.lock:
        # Replacement prevents hidden test data leaking across successive imports.
        app.state.catalog = courses
    return {"status": "success", "courses_imported": len(courses)}


@app.get("/api/v1/catalog/courses/{course_code}")
def get_catalog_course(course_code: str):
    with app.state.lock:
        course = app.state.catalog.get(normalize_code(course_code))
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        return course.copy()


@app.post("/api/v1/students/{student_id}/history/import", status_code=201)
async def import_history(student_id: str, file: UploadFile = File(...)):
    history = parse_transcript(await file.read())
    with app.state.lock:
        student = app.state.students.setdefault(student_id, {"history": [], "plan": []})
        student["history"] = history
    return {"status": "success", "past_courses_imported": len(history)}


@app.put("/api/v1/students/{student_id}/history")
def update_history(student_id: str, body: HistoryRequest):
    with app.state.lock:
        student = get_student(student_id)
        student["history"] = [course.model_dump() for course in body.history]
    return {"status": "success", "message": "Academic history updated successfully"}


@app.delete("/api/v1/students/{student_id}/history")
def delete_history(student_id: str):
    with app.state.lock:
        student = get_student(student_id)
        student["history"] = []
    return {"status": "success"}


@app.post("/api/v1/students/{student_id}/plan")
def create_plan(student_id: str, body: PlanRequest):
    with app.state.lock:
        student = get_student(student_id)
        student["plan"] = [course.model_dump() for course in body.planned_courses]
    return {"status": "success", "planned_courses_saved": len(body.planned_courses)}


@app.put("/api/v1/students/{student_id}/plan")
def update_plan(student_id: str, body: PlanRequest):
    with app.state.lock:
        student = get_student(student_id)
        student["plan"] = [course.model_dump() for course in body.planned_courses]
    return {"status": "success", "planned_courses_saved": len(body.planned_courses)}


@app.delete("/api/v1/students/{student_id}/plan")
def delete_plan(student_id: str):
    with app.state.lock:
        student = get_student(student_id)
        student["plan"] = []
    return {"status": "success"}


@app.get("/api/v1/students/{student_id}/profile")
def get_profile(student_id: str):
    with app.state.lock:
        student = get_student(student_id)
        return {
            "student_id": student_id,
            "history": [course.copy() for course in student["history"]],
            "plan": [course.copy() for course in student["plan"]],
        }


@app.get("/api/v1/students/{student_id}/audit-report")
def audit_report(student_id: str, strict: bool = False):
    with app.state.lock:
        student = get_student(student_id)
        return build_audit(
            student_id,
            student["history"],
            student["plan"],
            app.state.catalog,
            strict=strict,
        )
