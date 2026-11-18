"""Required vs nice-to-have detection for skill mentions in a job description.

The description is split into lines and sentences. Each sentence gets a label from, in order:
1. a cue inside the sentence ("... is a plus", "must have ..."). When a sentence has both
   kinds, the nice-to-have cue wins: we would rather under-state a requirement than invent one;
2. the section it sits in, set by the last header line ("Nice to have:", "Requirements");
3. otherwise "unspecified".
"""

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Literal

Requirement = Literal["required", "nice_to_have", "unspecified"]

_HEADER_NICE = re.compile(
    r"^\W*(nice[\s-]to[\s-]have|good[\s-]to[\s-]have|preferred(\s+(qualifications|skills|"
    r"experience|requirements))?|bonus(\s+points)?|plus\s+points?|desirable(\s+skills)?|"
    r"added\s+advantage|brownie\s+points|optional(\s+skills)?|it\s+would\s+be\s+(great|nice)|"
    r"what\s+would\s+be\s+a\s+plus)\b",
    re.IGNORECASE,
)
_HEADER_REQUIRED = re.compile(
    r"^\W*(requirements?|required(\s+(skills|qualifications|experience))?|must[\s-]haves?|"
    r"mandatory(\s+skills)?|minimum\s+qualifications|basic\s+qualifications|qualifications|"
    r"skills\s+required|key\s+skills|technical\s+skills|skills?\s*(&|and)\s*experience|"
    r"what\s+you('ll|\s+will)?\s+need|what\s+we('re|\s+are)\s+looking\s+for|who\s+you\s+are|"
    r"you\s+(have|bring)|eligibility(\s+criteria)?|desired\s+candidate\s+profile|"
    r"skills?\s+needed)\b",
    re.IGNORECASE,
)
_HEADER_OTHER = re.compile(
    r"^\W*(responsibilities|key\s+responsibilities|roles?\s+(and|&)\s+responsibilities|"
    r"what\s+you('ll|\s+will)\s+do|about\s+(us|the\s+(role|company|team|job))|benefits|perks|"
    r"why\s+join|role\s+overview|job\s+description|the\s+role|duties|what\s+we\s+offer)\b",
    re.IGNORECASE,
)

_CUE_NICE = re.compile(
    r"\b(nice[\s-]to[\s-]have|good[\s-]to[\s-]have|(is|are|would\s+be|will\s+be)\s+a\s+plus|"
    r"a\s+big\s+plus|added\s+advantage|an\s+advantage|advantageous|preferred|preferably|"
    r"desirable|bonus|not\s+mandatory|not\s+required|optional)\b",
    re.IGNORECASE,
)
_CUE_REQUIRED = re.compile(
    r"\b(must|required|requirement|mandatory|essential|need\s+to\s+have|should\s+have|"
    r"strong\s+(knowledge|experience|understanding|proficiency|skills?|background)|"
    r"proficien(t|cy)|expert(ise)?|hands[\s-]on|solid\s+(experience|understanding|knowledge)|"
    r"\d+\+?\s*(years|yrs))\b",
    re.IGNORECASE,
)

_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")
_MAX_HEADER_LEN = 60


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    label: Requirement


def _header_label(line: str) -> Requirement | Literal["other"] | None:
    """Return the section a header line opens, or None if the line is not a header."""
    head = line
    if len(line) > _MAX_HEADER_LEN:
        # Long lines count only as "Header: inline content".
        colon = line.find(":")
        if colon == -1 or colon > 40:
            return None
        head = line[:colon]
    if _HEADER_NICE.match(head):
        return "nice_to_have"
    if _HEADER_REQUIRED.match(head):
        return "required"
    if _HEADER_OTHER.match(head):
        return "other"
    return None


def _sentence_label(sentence: str) -> Requirement | None:
    if _CUE_NICE.search(sentence):
        return "nice_to_have"
    if _CUE_REQUIRED.search(sentence):
        return "required"
    return None


def segment(text: str) -> list[Segment]:
    """Label every sentence of the text. Segments are ordered and cover each line."""
    segments: list[Segment] = []
    section: Requirement = "unspecified"
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line_start = offset
        offset += len(raw_line)
        line = raw_line.strip()
        if not line:
            continue
        header = _header_label(line)
        if header is not None:
            section = "unspecified" if header == "other" else header
        pos = line_start + (len(raw_line) - len(raw_line.lstrip()))
        for part in _SENTENCE_END.split(line):
            idx = text.find(part, pos)
            if idx == -1:  # pragma: no cover - split parts always occur in order
                continue
            label = _sentence_label(part) or section
            segments.append(Segment(idx, idx + len(part), label))
            pos = idx + len(part)
    return segments


class RequirementLocator:
    """Answers "which requirement label applies at character offset X?" for one text."""

    def __init__(self, text: str) -> None:
        self._segments = segment(text)
        self._starts = [s.start for s in self._segments]

    def label_at(self, char_offset: int) -> Requirement:
        i = bisect_right(self._starts, char_offset) - 1
        if i >= 0 and char_offset < self._segments[i].end:
            return self._segments[i].label
        return "unspecified"


_RANK: dict[Requirement, int] = {"required": 2, "nice_to_have": 1, "unspecified": 0}


def strongest(labels: list[Requirement]) -> Requirement:
    """A skill required anywhere in the posting is required overall."""
    return max(labels, key=_RANK.__getitem__, default="unspecified")
