"""Builds small syllabus PDFs for tests (test fixtures only; never used by the app)."""

import pymupdf


def make_pdf(lines: list[tuple[str, float, bool]]) -> bytes:
    """lines: (text, font size, bold). One line per row, new page when full."""
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page()
    y = 50.0
    for text, size, bold in lines:
        if y > 780:
            page = doc.new_page()
            y = 50.0
        page.insert_text((50, y), text, fontsize=size, fontname="hebo" if bold else "helv")
        y += size + 8
    data: bytes = doc.tobytes()
    doc.close()
    return data


# The layout v1 generated for its own sample syllabus (legacy/app/curriculum/parser.py),
# used to show the regex strategy still reads that format.
V1_STYLE = [
    ("UNIVERSITY OF TESTING", 16, False),
    ("Course: CS 301: Advanced Data Engineering", 14, False),
    ("Unit 1: Relational Data Processing", 11, False),
    ("Topics: SQL databases, indexing, PostgreSQL, normalization, transactions.", 10, False),
    ("Outcomes: Write complex SQL queries.", 10, False),
    ("Unit 2: Distributed Systems Foundations", 11, False),
    (
        "Topics: Apache Hadoop, HDFS architecture, MapReduce, Linux shell, Git version control.",
        10,
        False,
    ),
    ("Outcomes: Deploy simple Hadoop jobs.", 10, False),
    ("Course: CS 302: Machine Learning", 14, False),
    ("Unit 1: Supervised learning", 11, False),
    ("Topics: regression, classification, scikit-learn, Python.", 10, False),
]

# No "Unit"/"Module" markers: headings are only distinguishable by font size.
LAYOUT_ONLY = [
    ("Department of Computing", 20, True),
    ("Cloud Computing", 16, True),
    ("Virtualisation Basics", 13, True),
    ("Hypervisors, virtual machines and containers with Docker.", 10, False),
    ("Kubernetes Orchestration", 13, True),
    ("Pods, deployments and services on Kubernetes clusters.", 10, False),
    ("Web Development", 16, True),
    ("Frontend Engineering", 13, True),
    ("HTML, CSS and JavaScript fundamentals; building components in React.", 10, False),
]
