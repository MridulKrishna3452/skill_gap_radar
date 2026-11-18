"""Text normalizers for job postings.

Ported from v1 (legacy/app/scraper/cleaning.py and legacy/app/utils/helpers.py).

Behaviour changes from v1, each covered by a test:
- An empty company or location returns None. v1 returned "Unknown Company" and "Remote", which
  invented facts: a posting with no location is not a remote job.
- Company names keep their casing unless the source is all upper or all lower case. v1 always
  title-cased, turning "IBM" into "Ibm".
- clean_html uses the standard library parser instead of BeautifulSoup and also decodes
  entities such as &amp;.
- v1's standardize_skills_string is not ported: raw skill lists now go through the taxonomy
  alias table (services/extraction), which covers every mapping it had.
"""

import hashlib
import re
from html import unescape
from html.parser import HTMLParser

_COMPANY_SUFFIX = re.compile(
    r"\b(private\s+limited|pvt\.?\s*ltd\.?|pvt|limited|ltd|inc|corp|llc|llp|"
    r"incorporation|incorporated|corporation)\b\.?",
    re.IGNORECASE,
)
_WS = re.compile(r"\s+")

# Order matters: the first matching rule wins (v1 order, plus Chennai/Kolkata/Gurugram).
_LOCATION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("bangalore", "bengaluru"), "Bengaluru"),
    (("noida",), "Noida"),
    (("gurgaon", "gurugram"), "Gurugram"),
    (("delhi", "ncr"), "Delhi NCR"),
    (("mumbai", "bombay"), "Mumbai"),
    (("hyderabad", "secunderabad"), "Hyderabad"),
    (("pune",), "Pune"),
    (("chennai", "madras"), "Chennai"),
    (("kolkata", "calcutta"), "Kolkata"),
    (("remote", "work from home", "wfh"), "Remote"),
)


class _TextExtractor(HTMLParser):
    _BLOCK = frozenset({"p", "br", "li", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_html(text: str | None, *, keep_lines: bool = False) -> str:
    """Strip tags and decode entities. keep_lines preserves block breaks as newlines."""
    if not text:
        return ""
    parser = _TextExtractor()
    parser.feed(text)
    parser.close()
    raw = unescape("".join(parser.parts))
    if keep_lines:
        lines = (_WS.sub(" ", line).strip() for line in raw.splitlines())
        return "\n".join(line for line in lines if line)
    return _WS.sub(" ", raw).strip()


def normalize_company(name: str | None) -> str | None:
    """Strip legal suffixes ("Pvt Ltd", "Inc.") and tidy whitespace and casing."""
    if not name or not name.strip():
        return None
    cleaned = _COMPANY_SUFFIX.sub("", name)
    cleaned = _WS.sub(" ", cleaned).strip(" ,.-")
    if not cleaned:
        return None
    # Short all-caps names are usually acronyms (IBM, TCS) and stay as they are.
    if (cleaned.isupper() and len(cleaned) > 4) or cleaned.islower():
        cleaned = cleaned.title()
    return cleaned


def company_key(name: str) -> str:
    """Case- and punctuation-insensitive key used to deduplicate companies."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def normalize_location(loc: str | None) -> str | None:
    """Map common spellings of Indian metros (and remote work) to one canonical name."""
    if not loc or not loc.strip():
        return None
    lower = loc.lower().strip()
    for needles, canonical in _LOCATION_RULES:
        if any(n in lower for n in needles):
            return canonical
    return _WS.sub(" ", loc).strip().title()


def normalize_title(title: str) -> str:
    return _WS.sub(" ", clean_html(title)).strip()


def content_hash(title: str, company: str | None, location: str | None, description: str) -> str:
    """Stable fingerprint of a posting's content, insensitive to case and whitespace."""
    parts = [title, company or "", location or "", description]
    canonical = "\x1f".join(_WS.sub(" ", p).strip().lower() for p in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
