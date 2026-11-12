"""HTML course-catalog import with format-insensitive course-code matching."""

import re

from bs4 import BeautifulSoup


CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z]{2,8})[\s-]*([0-9]{3,5}[A-Za-z]?)\b",
    re.IGNORECASE,
)


def normalize_code(code: str) -> str:
    return re.sub(r"[\s-]+", "", str(code)).upper()


def display_code(code: str) -> str:
    normalized = normalize_code(code)
    match = re.fullmatch(r"([A-Z]{2,8})(\d{3,5}[A-Z]?)", normalized)
    return f"{match.group(1)}-{match.group(2)}" if match else normalized


def extract_codes(value: str) -> list[str]:
    """Return distinct course codes in order of first appearance."""
    found = []
    seen = set()
    for match in CODE_PATTERN.finditer(str(value)):
        code = display_code(match.group())
        key = normalize_code(code)
        if key not in seen:
            seen.add(key)
            found.append(code)
    return found


def _column_name(label: str) -> str | None:
    key = re.sub(r"[^a-z]", "", label.lower())
    if key in {"code", "course", "coursecode", "courseid", "coursenumber"}:
        return "course_code"
    if key in {"title", "coursetitle", "coursename", "name"}:
        return "title"
    if "credit" in key:
        return "credits"
    if "prereq" in key:
        return "prerequisites"
    if "crosslist" in key or key in {"equivalent", "equivalents"}:
        return "cross_listed"
    return None


def parse_catalog(html: bytes) -> dict[str, dict]:
    """Parse table(s) with labeled columns, independent of course identities."""
    soup = BeautifulSoup(html, "html.parser")
    courses = {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        columns = {}
        header_row_index = None
        for index, row in enumerate(rows):
            headers = row.find_all("th")
            if not headers:
                continue
            candidate = {}
            for position, cell in enumerate(headers):
                name = _column_name(cell.get_text(" ", strip=True))
                if name is not None:
                    candidate[name] = position
            if {"course_code", "credits"}.issubset(candidate):
                columns = candidate
                header_row_index = index
                break
        if header_row_index is None:
            # Support a five-column catalog even if the header uses <td>.
            for index, row in enumerate(rows):
                cells = row.find_all(["td", "th"], recursive=False)
                candidate = {}
                for position, cell in enumerate(cells):
                    name = _column_name(cell.get_text(" ", strip=True))
                    if name is not None:
                        candidate[name] = position
                if {"course_code", "credits"}.issubset(candidate):
                    columns = candidate
                    header_row_index = index
                    break
        if header_row_index is None:
            continue
        for row in rows[header_row_index + 1:]:
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells or max(columns.values()) >= len(cells):
                continue

            def cell_text(field: str) -> str:
                at = columns.get(field)
                return cells[at].get_text(" ", strip=True) if at is not None else ""

            raw_code = cell_text("course_code")
            code_matches = extract_codes(raw_code)
            if not code_matches:
                continue
            canonical_code = code_matches[0]
            credit_match = re.search(r"\d+(?:\.\d+)?", cell_text("credits"))
            credits = float(credit_match.group()) if credit_match else 0
            if credits.is_integer():
                credits = int(credits)
            courses[normalize_code(canonical_code)] = {
                "course_code": canonical_code,
                "title": cell_text("title"),
                "credits": credits,
                "prerequisites": extract_codes(cell_text("prerequisites")),
                "cross_listed": [
                    related
                    for related in extract_codes(cell_text("cross_listed"))
                    if normalize_code(related) != normalize_code(canonical_code)
                ],
            }
    return courses
