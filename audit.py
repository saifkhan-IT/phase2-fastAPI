"""Academic degree-audit calculations: chronology, cross-lists and credits."""

import re

from catalog import display_code, normalize_code

SEASONS = {"W": 0, "SP": 1, "S": 2, "F": 3}
GRADUATION_CREDITS = 120


def term_key(term: str) -> tuple[int, int]:
    """24W < 24SP < 24S < 24F; invalid terms never satisfy chronology."""
    match = re.fullmatch(r"\s*(\d{2})(W|SP|S|F)\s*", str(term).upper())
    if not match:
        return (-1, -1)
    return int(match.group(1)), SEASONS[match.group(2)]


def _is_completed(attempt: dict) -> bool:
    return str(attempt.get("status", "")).strip().lower() == "completed"


def _related_codes(catalog_record: dict, field: str) -> set[str]:
    """Normalize the catalog's lists defensively."""
    return {normalize_code(code) for code in catalog_record.get(field, [])}


def build_audit(
    student_id: str,
    history: list[dict],
    plan: list[dict],
    catalog: dict[str, dict],
    strict: bool = False,
) -> dict:
    """Build the public report without mutating student or catalog data."""
    # Choose the latest completed attempt for each course. Failed/in-progress
    # attempts cannot replace a pass or earn any credits.
    completed = {}
    passed_terms = {}
    for position, attempt in enumerate(history):
        if not _is_completed(attempt):
            continue
        code = normalize_code(attempt["course_code"])
        passed_terms.setdefault(code, []).append(term_key(attempt.get("term", "")))
        score = (term_key(attempt.get("term", "")), position)
        if code not in completed or score > completed[code][0]:
            completed[code] = (score, attempt)

    earned = sum(
        max(0, float(record.get("credits_earned", 0)))
        for _, record in completed.values()
    )
    planned_total = 0
    error_groups: dict[str, list[dict]] = {}
    cross_conflicts = []
    seen_conflicts = set()

    for planned in plan:
        planned_code = normalize_code(planned["course_code"])
        planned_name = display_code(planned["course_code"])
        planned_term = str(planned["term"]).strip().upper()
        course = catalog.get(planned_code, {})
        planned_total += float(course.get("credits", 0))

        for prereq in course.get("prerequisites", []):
            prereq_code = normalize_code(prereq)
            plan_term_key = term_key(planned_term)
            had_earlier_pass = any(
                passed_term != (-1, -1) and passed_term < plan_term_key
                for passed_term in passed_terms.get(prereq_code, [])
            )
            if not had_earlier_pass:
                error_groups.setdefault(planned_term, []).append(
                    {
                        "course_code": planned_name,
                        "type": "MISSING_PREREQUISITE",
                        "message": f"Missing prerequisite: {display_code(prereq)}",
                    }
                )

        # Check cross-list data in BOTH directions: some catalogs only list a
        # relationship under one of the two course entries.
        cross_listed = _related_codes(course, "cross_listed")
        for finished_code, (_, finished) in completed.items():
            finished_course = catalog.get(finished_code, {})
            if (
                finished_code in cross_listed
                or planned_code in _related_codes(finished_course, "cross_listed")
            ):
                conflict_key = (planned_code, finished_code)
                if conflict_key not in seen_conflicts:
                    seen_conflicts.add(conflict_key)
                    cross_conflicts.append(
                        {
                            "course_code": planned_name,
                            "type": "CROSS_LIST_CONFLICT",
                            "message": (
                                "Cross-listed with completed course "
                                f"{display_code(finished['course_code'])}"
                            ),
                        }
                    )

    timeline = [
        {"term": term, "errors": error_groups[term]}
        for term in sorted(error_groups, key=term_key)
    ]
    any_issues = bool(timeline or cross_conflicts)
    status = "failed" if strict and any_issues else "warning" if any_issues else "ok"

    def number(value: float) -> int | float:
        return int(value) if float(value).is_integer() else value

    return {
        "student_id": student_id,
        "status": status,
        "timeline_validation": timeline,
        "cross_list_violations": cross_conflicts,
        "credit_summary": {
            "total_earned": number(earned),
            "total_planned": number(planned_total),
            "total_remaining_for_graduation": number(
                max(0, GRADUATION_CREDITS - earned - planned_total)
            ),
        },
    }
