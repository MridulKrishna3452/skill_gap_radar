from app.services.extraction.requirement import RequirementLocator, segment, strongest


def label_of(text: str, needle: str) -> str:
    return RequirementLocator(text).label_at(text.index(needle))


def test_section_headers() -> None:
    text = "About us\nWe build Python tools.\nMust have:\nSQL\nPreferred qualifications\nScala"
    assert label_of(text, "Python") == "unspecified"
    assert label_of(text, "SQL") == "required"
    assert label_of(text, "Scala") == "nice_to_have"


def test_inline_header_with_content() -> None:
    text = "Good to have: Kafka, Airflow"
    assert label_of(text, "Kafka") == "nice_to_have"


def test_sentence_cue_overrides_section() -> None:
    text = "Requirements:\nPython is mandatory. Exposure to Rust would be a plus."
    assert label_of(text, "Python") == "required"
    assert label_of(text, "Rust") == "nice_to_have"


def test_responsibilities_section_resets_label() -> None:
    text = "Requirements:\nJava\nResponsibilities:\nMaintain Jenkins pipelines"
    assert label_of(text, "Jenkins") == "unspecified"


def test_mixed_sentence_leans_to_weaker_claim() -> None:
    assert label_of("Strong SQL required, Spark preferred", "Spark") == "nice_to_have"


def test_segments_cover_text_in_order() -> None:
    segs = segment("A. B.\nC")
    assert [s.start for s in segs] == sorted(s.start for s in segs)


def test_strongest() -> None:
    assert strongest(["nice_to_have", "required"]) == "required"
    assert strongest([]) == "unspecified"
