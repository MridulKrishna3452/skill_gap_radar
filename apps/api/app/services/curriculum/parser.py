"""Syllabus PDF parsing into courses and units.

Two strategies, tried in order:
- "regex": v1's line parser (legacy/app/curriculum/parser.py) generalised. Course headings
  ("Course: ...", "Subject: ...", or a course code like "CS 301 ..."), unit headings
  ("Unit 1", "Unit IV", "Module 2", "Chapter 3"), and outcome lines. Unlike v1, every line
  under a unit is kept as its content, not only lines starting with "Topics:".
- "layout": for PDFs without textual unit markers. Uses font size and weight from PyMuPDF to
  find headings: the larger heading level becomes courses, the smaller one units.

If neither finds a unit, parsing fails with a clear message. Nothing is invented: v1's
"paragraph scanner" fallback, which stored arbitrary text as topics, is not ported.
"""

import re
import statistics
from dataclasses import dataclass, field
from pathlib import PurePath

import pymupdf

MAX_TITLE = 500


class CurriculumParseError(Exception):
    pass


@dataclass
class ParsedUnit:
    title: str
    content_lines: list[str] = field(default_factory=list)
    outcome_lines: list[str] = field(default_factory=list)

    @property
    def content(self) -> str:
        return "\n".join(self.content_lines).strip()

    @property
    def learning_outcomes(self) -> str | None:
        text = "\n".join(self.outcome_lines).strip()
        return text or None


@dataclass
class ParsedCourse:
    title: str
    code: str | None = None
    units: list[ParsedUnit] = field(default_factory=list)


@dataclass
class ParseResult:
    strategy: str
    page_count: int
    courses: list[ParsedCourse]

    @property
    def unit_count(self) -> int:
        return sum(len(c.units) for c in self.courses)


@dataclass(frozen=True)
class Line:
    text: str
    size: float
    bold: bool


_COURSE_LABEL = re.compile(
    r"^(?:course|subject|paper)(?:\s+(?:title|name))?\s*[:\-–]\s*(?P<rest>.{3,})$", re.I
)
# Two-digit codes occur too ("CSH01" honours, "CSM03" minor courses). Outcome labels
# ("CO 12", "PO1") look like codes and are excluded.
_COURSE_CODE = re.compile(
    r"^(?:course\s+code\s*[:\-–]?\s*)?(?!(?:CO|PO|PSO)[\s\-]?\d)"
    r"(?P<code>[A-Z]{2,6}[\s\-]?\d{2,4}[A-Z]?)\b\s*[:\-–.)]?\s*"
    r"(?P<title>[A-Za-z][^\n]{2,150})?$"
)
# Sections that follow a course's last unit. Book and course titles listed there ("Computer
# Networking: A Top-Down Approach") are not syllabus content, so a unit ends at them.
_UNIT_END = re.compile(
    r"^(?:text\s*books?|text|references?|reference\s+books?|suggested\s+readings?|"
    r"further\s+readings?|bibliography|online(?:\s*/\s*nptel)?(?:\s+courses?)?|nptel|"
    r"web\s*(?:resources|references|links)|e-?\s*resources)\s*(?P<colon>:)?\s*(?P<rest>.*)$",
    re.I,
)
_UNIT = re.compile(
    r"^(?P<kind>unit|module|chapter|block)\s*[-–:]?\s*(?P<num>\d{1,2}|[ivxlc]{1,6})\b"
    r"\s*[:.\-–)]?\s*(?P<rest>.*)$",
    re.I,
)
_OUTCOMES = re.compile(
    r"^(?:(?:course|learning|unit)\s+)?outcomes?\s*[:\-–]?\s*(?P<rest>.*)$|^(?P<co>CO\s?\d+\b.*)$",
    re.I,
)
_TOPICS = re.compile(r"^(?:topics?|contents?|syllabus)\s*[:\-–]\s*", re.I)
_NOISE = re.compile(r"^(?:page\s*\d+(\s*of\s*\d+)?|\d{1,3}|[-–_=\s.]+)$", re.I)


def read_lines(data: bytes, max_pages: int) -> tuple[list[Line], int]:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as exc:  # pymupdf raises several types for corrupt files
        raise CurriculumParseError("The file is not a readable PDF") from exc
    with doc:
        if doc.needs_pass:
            raise CurriculumParseError("The PDF is password protected")
        page_count = doc.page_count
        if page_count > max_pages:
            raise CurriculumParseError(f"The PDF has {page_count} pages; the limit is {max_pages}")
        lines: list[Line] = []
        for page_no in range(page_count):
            page = doc.load_page(page_no)  # type: ignore[no-untyped-call]
            for block in page.get_text("dict")["blocks"]:
                for raw_line in block.get("lines", []):
                    spans = [s for s in raw_line["spans"] if s["text"].strip()]
                    if not spans:
                        continue
                    text = " ".join(" ".join(s["text"].split()) for s in spans).strip()
                    size = max(s["size"] for s in spans)
                    bold = all(s["flags"] & 16 or "bold" in s["font"].lower() for s in spans)
                    lines.append(Line(text, round(size, 1), bool(bold)))
    if not lines:
        raise CurriculumParseError(
            "No text found in the PDF. Scanned syllabi need OCR before upload."
        )
    return lines, page_count


def _split_code(title: str) -> tuple[str | None, str]:
    m = _COURSE_CODE.match(title)
    if m and m.group("title"):
        return " ".join(m.group("code").split()), m.group("title").strip(" :-–")
    return None, title


def _add_unit_line(unit: ParsedUnit, text: str, in_outcomes: bool) -> bool:
    """Append a body line to the unit; returns whether we are inside an outcomes block."""
    m = _OUTCOMES.match(text)
    if m:
        rest = (m.group("rest") or m.group("co") or "").strip()
        if rest:
            unit.outcome_lines.append(rest)
        return True
    topics = _TOPICS.sub("", text)
    if in_outcomes and topics == text:
        unit.outcome_lines.append(text)
        return True
    unit.content_lines.append(topics)
    return False


def _ends_unit(text: str, heading_like: bool) -> bool:
    """A "Text Books" / "References" / "Online courses" label: followed by a colon, or alone
    on a heading-styled line ("Text Mining" or a plain "References to ..." sentence is not)."""
    m = _UNIT_END.match(text)
    if m is None:
        return False
    return bool(m.group("colon")) or (heading_like and not m.group("rest"))


def _body_size(lines: list[Line]) -> float:
    """Median font size weighted by characters: the size of ordinary body text."""
    weights: list[float] = []
    for line in lines:
        weights.extend([line.size] * min(len(line.text), 200))
    return statistics.median(weights)


def parse_regex(lines: list[Line], fallback_title: str) -> list[ParsedCourse]:
    body = _body_size(lines)
    courses: list[ParsedCourse] = []
    course: ParsedCourse | None = None
    unit: ParsedUnit | None = None
    in_outcomes = False
    for line in lines:
        text = line.text
        if _NOISE.match(text):
            continue
        label = _COURSE_LABEL.match(text)
        # A bare course code ("CS 301 Data Engineering") only counts as a heading when set
        # in bold or a larger font; otherwise body text like "ISO 9001 standards" would match.
        heading_like = line.bold or line.size >= body * 1.1
        code = _COURSE_CODE.match(text) if heading_like and len(text) <= 160 else None
        if label or (code and code.group("title")):
            title = label.group("rest").strip() if label else text
            code_value, title = _split_code(title)
            course = ParsedCourse(title=title[:MAX_TITLE], code=code_value)
            courses.append(course)
            unit, in_outcomes = None, False
            continue
        m = _UNIT.match(text)
        if m:
            if course is None:
                course = ParsedCourse(title=fallback_title)
                courses.append(course)
            unit = ParsedUnit(title=text[:MAX_TITLE])
            course.units.append(unit)
            in_outcomes = False
            continue
        if unit is not None and _ends_unit(text, heading_like):
            unit, in_outcomes = None, False
            continue
        if unit is not None:
            in_outcomes = _add_unit_line(unit, text, in_outcomes)
    return [c for c in courses if c.units]


def parse_layout(lines: list[Line], fallback_title: str) -> list[ParsedCourse]:
    body = _body_size(lines)

    def is_heading(line: Line) -> bool:
        short = len(line.text) <= 120 and not line.text.endswith((".", ","))
        return short and (line.size >= body * 1.15 or (line.bold and line.size >= body))

    heading_sizes = sorted({line.size for line in lines if is_heading(line)}, reverse=True)
    if not heading_sizes:
        return []
    # Two heading levels: the largest is the document title or course level. Use the two
    # most common heading sizes as course and unit levels.
    counts = {s: sum(1 for ln in lines if is_heading(ln) and ln.size == s) for s in heading_sizes}
    common = sorted(heading_sizes, key=lambda s: (-counts[s], -s))[:2]
    course_size = max(common) if len(common) == 2 else None
    unit_size = min(common)

    courses: list[ParsedCourse] = []
    course: ParsedCourse | None = None
    unit: ParsedUnit | None = None
    in_outcomes = False
    for line in lines:
        if _NOISE.match(line.text):
            continue
        if _ends_unit(line.text, is_heading(line)):
            unit, in_outcomes = None, False
            continue
        if is_heading(line) and course_size is not None and line.size == course_size:
            code_value, title = _split_code(line.text)
            course = ParsedCourse(title=title[:MAX_TITLE], code=code_value)
            courses.append(course)
            unit = None
            continue
        if is_heading(line) and line.size == unit_size:
            if course is None:
                course = ParsedCourse(title=fallback_title)
                courses.append(course)
            unit = ParsedUnit(title=line.text[:MAX_TITLE])
            course.units.append(unit)
            in_outcomes = False
            continue
        if unit is not None:
            in_outcomes = _add_unit_line(unit, line.text, in_outcomes)
    return [c for c in courses if any(u.content for u in c.units)]


def parse_pdf(data: bytes, filename: str, max_pages: int) -> ParseResult:
    lines, page_count = read_lines(data, max_pages)
    fallback = PurePath(filename).stem.replace("_", " ").strip() or "Untitled course"
    for strategy, fn in (("regex", parse_regex), ("layout", parse_layout)):
        courses = fn(lines, fallback)
        if courses:
            return ParseResult(strategy, page_count, courses)
    raise CurriculumParseError(
        "Could not find course units in this PDF. Expected headings such as 'Unit 1' / "
        "'Module 2', or headings set in a larger or bold font."
    )
