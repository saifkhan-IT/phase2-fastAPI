"""Real TCP/HTTP integration test, invoked after GitHub Actions starts uvicorn."""

import os

import httpx
import pytest


@pytest.mark.skipif(not os.getenv("LIVE_BASE_URL"), reason="Requires running uvicorn")
def test_real_http_import_history_plan_audit():
    base = os.environ["LIVE_BASE_URL"].rstrip("/")
    student = "ci-phase3-check"
    catalog = b"""<table><tr><th>Course Code</th><th>Title</th>
    <th>Credits</th><th>Prerequisites</th><th>Cross-listed</th></tr>
    <tr><td>COSC1000</td><td>Intro</td><td>3</td><td></td><td></td></tr>
    <tr><td>COSC2000</td><td>Advanced</td><td>3</td>
    <td>COSC1000</td><td></td></tr></table>"""
    history = b"""<table><tr><th>Status</th><th>Course</th><th>Grade</th>
    <th>Term</th><th>Credits</th></tr>
    <tr><td>Completed</td><td>COSC1000</td><td>90</td><td>24W</td>
    <td>3</td></tr></table>"""
    with httpx.Client(timeout=10) as client:
        r = client.post(
            f"{base}/api/v1/admin/catalog/import",
            files={"file": ("catalog.html", catalog, "text/html")},
        )
        assert r.status_code == 201, r.text
        r = client.post(
            f"{base}/api/v1/students/{student}/history/import",
            files={"file": ("history.html", history, "text/html")},
        )
        assert r.status_code == 201, r.text
        r = client.post(
            f"{base}/api/v1/students/{student}/plan",
            json={"planned_courses": [{"course_code": "COSC-2000", "term": "26F"}]},
        )
        assert r.status_code == 200, r.text
        report = client.get(
            f"{base}/api/v1/students/{student}/audit-report?strict=true"
        )
        assert report.status_code == 200, report.text
        assert report.json()["status"] == "ok"
        assert report.json()["credit_summary"] == {
            "total_earned": 3,
            "total_planned": 3,
            "total_remaining_for_graduation": 114,
        }
