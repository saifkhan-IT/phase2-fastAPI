# Student Academic Profile API — Phase 3

Built from the existing `phase2-fastAPI` codebase, with Phase 1 catalog endpoints
and Phase 3 degree audit added.

## Local setup (Windows PowerShell)

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest -q tests/test_api.py --cov=main --cov=catalog --cov=audit --cov-report=term-missing --cov-fail-under=80
uvicorn main:app --reload
```

API docs: http://127.0.0.1:8000/docs

## Required API calls

1. `POST /api/v1/admin/catalog/import`: multipart upload `file` = catalog HTML.
2. `POST /api/v1/students/770001/history/import`: multipart upload `file` = transcript HTML.
3. `POST /api/v1/students/770001/plan`: JSON `{"planned_courses":[{"course_code":"COSC4426","term":"26F"}]}`.
4. `GET /api/v1/students/770001/audit-report?strict=false`
5. `GET /api/v1/students/770001/audit-report?strict=true`

The existing Phase 2 `/history`, `/plan` and `/profile` APIs are retained.

## GitHub Actions

Push `.github/workflows/ci.yml`, `tests/`, and all application files to the
same GitHub repository. Open **Actions > Phase 3 Quality Gate > newest run**.
It should show green checks for **Lint**, **Pytest (minimum 80% coverage)**,
and **Live API integration**. Screenshot these checks and the coverage summary
as `ci_proof.png`; copy the run logs to `ci_logs.txt`. Never fabricate results.

## Render

Keep the existing Render service pointing at this GitHub repository:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`

After deployment, wake the service before submitting. Create `api_url.txt`
containing ONLY your actual Render base URL with no trailing slash.

## Practice self-test

Download the assignment's `selftest.zip` from Moodle and extract it. Start
`uvicorn main:app --host 0.0.0.0 --port 8000` in terminal one, then run
`bash selftest/run_selftest.sh` in terminal two (Git Bash/WSL on Windows).
The hidden grader uses different data, so locally passing tests do not
fully guarantee the hidden grade.

## Notes

- Catalog records are in memory and are replaced by every successful catalog import.
- Student records are in memory and keyed by student ID.
- The assignment's exact sample `Course Catalog.html` was unavailable when
  creating this code. Please verify its HTML against the parser, and run the
  official Moodle self-test before spending a graded attempt.
