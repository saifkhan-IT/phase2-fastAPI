"""Phase 1/2 compatibility and Phase 3 rule regression tests."""

import pytest
from fastapi.testclient import TestClient

from audit import build_audit, term_key
from catalog import display_code, extract_codes, normalize_code, parse_catalog
from main import app, grade_rank, parse_transcript

client = TestClient(app)

CATALOG_HTML = b"""
<html><body><table id="catalog">
<tr><th>Course Code</th><th>Title</th><th>Credits</th>
<th>Prerequisites</th><th>Cross-listed</th></tr>
<tr><td>COSC 3127</td><td>Intermediate Python</td><td>3</td>
<td>None</td><td></td></tr>
<tr><td>COSC-4426</td><td>AI</td><td>3</td>
<td>Requires COSC 3127</td><td></td></tr>
<tr><td>ITEC3506</td><td>Information Systems</td><td>3</td>
<td>N/A</td><td>COSC 3506</td></tr>
<tr><td>COSC-3506</td><td>Databases</td><td>3</td>
<td></td><td></td></tr>
<tr><td> MATH-1200 </td><td>Calculus</td><td>6</td>
<td>Requires COSC-3127 and either ITEC 3506 or COSC3506</td><td></td></tr>
</table></body></html>
"""

TRANSCRIPT_HTML = b"""
<table><tr><th>Status</th><th>Course</th><th>Grade</th><th>Term</th>
<th>Credits</th></tr>
<tr><td>Attempted</td><td>COSC 3127</td><td>F</td><td>23F</td><td>0</td></tr>
<tr><td>Completed</td><td>COSC-3127</td><td>88%</td><td>24W</td><td>3</td></tr>
<tr><td>Completed</td><td>COSC3506</td><td>75</td><td>24F</td><td>3</td></tr>
<tr><td>In-Progress</td><td>MATH1200</td><td>-</td><td>26F</td><td>0</td></tr>
</table>
"""


@pytest.fixture(autouse=True)
def clean_app_state():
    app.state.students.clear()
    app.state.catalog.clear()
    yield
    app.state.students.clear()
    app.state.catalog.clear()


def load_catalog():
    response = client.post(
        "/api/v1/admin/catalog/import",
        files={"file": ("catalog.html", CATALOG_HTML, "text/html")},
    )
    assert response.status_code == 201
    assert response.json()["courses_imported"] == 5


def load_history(student="770001"):
    response = client.post(
        f"/api/v1/students/{student}/history/import",
        files={"file": ("history.html", TRANSCRIPT_HTML, "text/html")},
    )
    assert response.status_code == 201
    assert response.json()["past_courses_imported"] == 4


def set_plan(courses, student="770001", method="post"):
    return getattr(client, method)(
        f"/api/v1/students/{student}/plan",
        json={"planned_courses": courses},
    )


def set_history(courses, student="770001"):
    return client.put(
        f"/api/v1/students/{student}/history",
        json={"history": courses},
    )


def audit(strict=False, student="770001"):
    return client.get(
        f"/api/v1/students/{student}/audit-report",
        params={"strict": str(strict).lower()},
    )


def test_normalize_code_and_display():
    assert normalize_code("cosc - 3506") == "COSC3506"
    assert normalize_code("ITEC 3506") == "ITEC3506"
    assert display_code("cosc3506") == "COSC-3506"
    assert display_code("SOMETHING") == "SOMETHING"
    assert extract_codes("Requires COSC 1046 and COSC1046 or ITEC-1047") == [
        "COSC-1046", "ITEC-1047"
    ]


def test_catalog_import_lookup_and_normalized_routes():
    load_catalog()
    course = client.get("/api/v1/catalog/courses/cosc3506")
    assert course.status_code == 200
    assert course.json()["credits"] == 3
    assert client.get("/api/v1/catalog/courses/COSC-3506").status_code == 200
    math = client.get("/api/v1/catalog/courses/math1200").json()
    assert math["prerequisites"] == ["COSC-3127", "ITEC-3506", "COSC-3506"]
    assert client.get("/api/v1/catalog/courses/X999").status_code == 404


def test_catalog_import_replaces_previous_and_rejects_empty():
    load_catalog()
    response = client.post(
        "/api/v1/admin/catalog/import",
        files={"file": ("empty.html", b"<html></html>", "text/html")},
    )
    assert response.status_code == 422
    assert client.get("/api/v1/catalog/courses/COSC3506").status_code == 200
    replacement = b"""<table><tr><th>Code</th><th>Credits</th></tr>
    <tr><td>PHYS1000</td><td>4</td></tr></table>"""
    response = client.post(
        "/api/v1/admin/catalog/import",
        files={"file": ("next.html", replacement, "text/html")},
    )
    assert response.json()["courses_imported"] == 1
    assert client.get("/api/v1/catalog/courses/COSC3506").status_code == 404


def test_catalog_header_td_and_invalid_rows():
    html = b"""<table>
    <tr><td>Course</td><td>Title</td><td>Credits</td><td>Cross-listed courses</td></tr>
    <tr><td>???</td><td>Bad</td><td>three</td><td></td></tr>
    <tr><td>CHEM 1100</td><td>Good</td><td>3.5 credits</td><td>CHEM1100, BIOL-1100</td></tr>
    </table>"""
    records = parse_catalog(html)
    assert records["CHEM1100"]["credits"] == 3.5
    assert records["CHEM1100"]["cross_listed"] == ["BIOL-1100"]
    assert parse_catalog(b"<table><tr><td>Bad</td></tr></table>") == {}


def test_timeline_order_and_invalid_term():
    assert [term_key(term) for term in ["23F", "24W", "24SP", "24S", "24F"]] == sorted(
        [term_key(term) for term in ["23F", "24W", "24SP", "24S", "24F"]]
    )
    assert term_key("xx") == (-1, -1)
    assert term_key(" 26sp ") == (26, 1)


def test_grade_rank_and_transcript_malformed():
    assert grade_rank("81%") == 2
    assert grade_rank("F") == 1
    assert grade_rank("Pass") == 0
    assert parse_transcript(b"<html></html>") == []
    assert parse_transcript(b"<table><tr><th>Random</th></tr></table>") == []


def test_history_import_profile_and_retake():
    load_history()
    profile = client.get("/api/v1/students/770001/profile")
    assert profile.status_code == 200
    assert len(profile.json()["history"]) == 4
    report = audit().json()
    assert report["status"] == "ok"
    assert report["credit_summary"]["total_earned"] == 6
    assert report["credit_summary"]["total_remaining_for_graduation"] == 114


def test_missing_prior_prerequisite_and_strict_behavior():
    load_catalog()
    load_history()
    set_plan([{"course_code": "cosc4426", "term": "24W"}])
    normal = audit().json()
    assert normal["status"] == "warning"
    assert normal["timeline_validation"] == [
        {
            "term": "24W",
            "errors": [
                {
                    "course_code": "COSC-4426",
                    "type": "MISSING_PREREQUISITE",
                    "message": "Missing prerequisite: COSC-3127",
                }
            ],
        }
    ]
    assert audit(strict=True).json()["status"] == "failed"
    assert normal["credit_summary"] == {
        "total_earned": 6,
        "total_planned": 3,
        "total_remaining_for_graduation": 111,
    }


def test_prior_term_pass_satisfies_prerequisite():
    load_catalog()
    load_history()
    set_plan([{"course_code": "COSC 4426", "term": "24F"}])
    assert audit(strict=True).json()["status"] == "ok"


def test_cross_list_warning_strict_and_symmetric():
    load_catalog()
    load_history()
    set_plan([{"course_code": "ITEC-3506", "term": "26F"}])
    report = audit().json()
    assert report["cross_list_violations"] == [
        {
            "course_code": "ITEC-3506",
            "type": "CROSS_LIST_CONFLICT",
            "message": "Cross-listed with completed course COSC-3506",
        }
    ]
    assert audit(strict=True).json()["status"] == "failed"
    # Data is only declared on ITEC's side: reverse lookup still detects it.
    set_history(
        [{"course_code": "ITEC3506", "term": "23F", "credits_earned": 3,
          "status": "Completed"}]
    )
    set_plan([{"course_code": "COSC3506", "term": "26F"}], method="put")
    assert audit().json()["cross_list_violations"][0]["type"] == "CROSS_LIST_CONFLICT"


def test_only_completed_cross_list_violates():
    load_catalog()
    load_history()
    set_history(
        [{"course_code": "COSC3506", "term": "24W", "credits_earned": 0,
          "status": "Attempted"}]
    )
    set_plan([{"course_code": "ITEC3506", "term": "26F"}])
    assert audit().json()["cross_list_violations"] == []


def test_no_double_count_three_passes_and_failed_attempts():
    load_history()
    set_history(
        [
            {"course_code": "COSC 3127", "term": "22F", "credits_earned": 0,
             "status": "Attempted"},
            {"course_code": "COSC-3127", "term": "23W", "credits_earned": 3,
             "status": "Completed"},
            {"course_code": "cosc3127", "term": "25F", "credits_earned": 3,
             "status": "Completed"},
            {"course_code": "COSC3127", "term": "26W", "credits_earned": 0,
             "status": "Attempted"},
        ]
    )
    assert audit().json()["credit_summary"]["total_earned"] == 3


def test_latest_completed_credit_override_and_remaining_floor():
    catalog = {"MATH1200": {"credits": 10, "prerequisites": [], "cross_listed": []}}
    report = build_audit(
        "a",
        [
            {"course_code": "ENG1000", "term": "22F", "status": "Completed",
             "credits_earned": 100},
            {"course_code": "ENG1000", "term": "25F", "status": "Completed",
             "credits_earned": 115},
        ],
        [{"course_code": "MATH1200", "term": "26F"}],
        catalog,
    )
    assert report["credit_summary"] == {
        "total_earned": 115,
        "total_planned": 10,
        "total_remaining_for_graduation": 0,
    }


def test_all_term_violations_chronologically_sorted():
    load_catalog()
    load_history()
    set_history([])
    set_plan(
        [
            {"course_code": "COSC-4426", "term": "26F"},
            {"course_code": "COSC-4426", "term": "24W"},
            {"course_code": "COSC-4426", "term": "26SP"},
        ]
    )
    result = audit().json()
    assert [entry["term"] for entry in result["timeline_validation"]] == [
        "24W", "26SP", "26F"
    ]


def test_prerequisites_multiple_missing_and_same_term():
    load_catalog()
    load_history()
    set_history(
        [{"course_code": "COSC3127", "term": "25S", "credits_earned": 3,
          "status": "Completed"}]
    )
    set_plan([{"course_code": "MATH1200", "term": "25S"}])
    report = audit().json()
    missing = [entry["message"] for entry in report["timeline_validation"][0]["errors"]]
    assert missing == [
        "Missing prerequisite: COSC-3127",
        "Missing prerequisite: ITEC-3506",
        "Missing prerequisite: COSC-3506",
    ]


def test_nonexistent_student_status_codes():
    assert client.get("/api/v1/students/notfound/audit-report").status_code == 404
    assert client.get("/api/v1/students/notfound/profile").status_code == 404
    assert client.put("/api/v1/students/notfound/history", json={"history": []}).status_code == 404
    assert client.post(
        "/api/v1/students/notfound/plan", json={"planned_courses": []}
    ).status_code == 404


def test_student_isolation_and_plan_crud():
    load_history("one")
    load_history("two")
    set_plan([{"course_code": "MATH1200", "term": "26F"}], "one")
    assert client.get("/api/v1/students/two/profile").json()["plan"] == []
    assert set_plan([{"course_code": "COSC4426", "term": "27W"}], "one", "put").status_code == 200
    assert client.delete("/api/v1/students/one/plan").status_code == 200
    assert client.get("/api/v1/students/one/profile").json()["plan"] == []
    assert client.delete("/api/v1/students/one/history").status_code == 200
    assert client.get("/api/v1/students/one/profile").json()["history"] == []


def test_transcript_import_deduplicates_same_course_term():
    html = b"""<table><tr><th>Status</th><th>Course</th><th>Grade</th>
    <th>Term</th><th>Credits</th></tr>
    <tr><td>Attempted</td><td>COSC1000</td><td>F</td><td>23F</td><td>0</td></tr>
    <tr><td>Completed</td><td>COSC1000</td><td>90%</td><td>23F</td><td>3</td></tr>
    <tr><td>Completed</td><td>COSC 1001</td><td>P</td><td>24W</td><td>bad</td></tr>
    <tr><td>Completed</td><td></td><td>P</td><td>24W</td><td>3</td></tr>
    <tr><td>Other</td><td>COSC1002</td><td>P</td><td>24W</td><td>3</td></tr>
    <tr><td>Completed</td><td>COSC1003</td><td>P</td><td></td><td>3</td></tr>
    <tr><td>Completed</td><td>COSC1003</td></tr>
    </table>"""
    rows = parse_transcript(html)
    assert len(rows) == 2
    assert rows[0]["credits_earned"] == 3
    assert rows[1]["credits_earned"] == 0


def test_report_for_empty_history_and_plan():
    load_history()
    set_history([])
    set_plan([])
    result = audit(strict=True)
    assert result.status_code == 200
    assert result.json() == {
        "student_id": "770001",
        "status": "ok",
        "timeline_validation": [],
        "cross_list_violations": [],
        "credit_summary": {
            "total_earned": 0,
            "total_planned": 0,
            "total_remaining_for_graduation": 120,
        },
    }


def test_invalid_strict_param_gives_422():
    load_history()
    assert client.get(
        "/api/v1/students/770001/audit-report?strict=possibly"
    ).status_code == 422


def test_unlisted_plan_course_counts_as_zero_credits():
    load_history()
    set_plan([{"course_code": "XXXX7777", "term": "26F"}])
    assert audit().json()["credit_summary"]["total_planned"] == 0


def test_duplicate_cross_list_conflict_reports_only_once():
    load_catalog()
    load_history()
    set_plan(
        [
            {"course_code": "ITEC3506", "term": "25F"},
            {"course_code": "ITEC 3506", "term": "26F"},
        ]
    )
    assert len(audit().json()["cross_list_violations"]) == 1


def test_empty_and_malformed_catalog_tables_ignored():
    assert parse_catalog(b"<table></table>") == {}
    assert parse_catalog(b"""<table><tr><th>Course Code</th><th>Credits</th></tr>
    <tr><td>COSC1000</td></tr></table>""") == {}


def test_bad_terms_do_not_satisfy_prerequisites():
    report = build_audit(
        "x",
        [{"course_code": "COSC1000", "term": "UNKNOWN", "status": "Completed",
          "credits_earned": 3}],
        [{"course_code": "COSC2000", "term": "26F"}],
        {"COSC2000": {"credits": 3, "prerequisites": ["COSC1000"],
                      "cross_listed": []}},
    )
    assert report["timeline_validation"][0]["errors"][0]["type"] == "MISSING_PREREQUISITE"


def test_an_earlier_pass_still_qualifies_after_later_retake():
    load_catalog()
    load_history()
    set_history(
        [
            {"course_code": "COSC3127", "term": "23F", "credits_earned": 3,
             "status": "Completed"},
            {"course_code": "COSC-3127", "term": "26F", "credits_earned": 3,
             "status": "Completed"},
        ]
    )
    set_plan([{"course_code": "COSC4426", "term": "24W"}])
    report = audit().json()
    assert report["status"] == "ok"
    assert report["credit_summary"]["total_earned"] == 3


def test_empty_student_audit_uses_zero_credit_totals():
    response = client.post(
        "/api/v1/students/empty-student/history/import",
        files={"file": ("empty.html", b"<html></html>", "text/html")},
    )
    assert response.status_code == 201
    response = client.post(
        "/api/v1/students/empty-student/plan",
        json={"planned_courses": []},
    )
    assert response.status_code == 200
    response = client.get(
        "/api/v1/students/empty-student/audit-report?strict=true"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["credit_summary"] == {
        "total_earned": 0,
        "total_planned": 0,
        "total_remaining_for_graduation": 120,
    }
