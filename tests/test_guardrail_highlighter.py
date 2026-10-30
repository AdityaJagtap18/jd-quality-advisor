import pytest
from unittest.mock import MagicMock
from agents.guardrails import scan_jd_for_violations
from app import _build_highlighted_html


def _make_client(response_text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def test_scan_returns_phrases_from_valid_json():
    client = _make_client('["young and energetic", "candidates aged 25-35"]')
    result = scan_jd_for_violations(
        "We want young and energetic candidates aged 25-35.",
        "Topic blocked: Discriminatory_Hiring_Criteria (DENY)",
        client,
    )
    assert result == ["young and energetic", "candidates aged 25-35"]


def test_scan_handles_text_around_json():
    client = _make_client('Here are the phrases: ["male preferred"]\nDone.')
    result = scan_jd_for_violations("male preferred applicants only.", "Topic blocked: X", client)
    assert result == ["male preferred"]


def test_scan_returns_empty_list_on_json_parse_failure():
    client = _make_client("Sorry, I cannot identify any phrases.")
    result = scan_jd_for_violations("Some JD text.", "Topic blocked: X", client)
    assert result == []


def test_scan_returns_empty_list_on_api_exception():
    client = MagicMock()
    client.messages.create.side_effect = Exception("API error")
    result = scan_jd_for_violations("Some JD text.", "Topic blocked: X", client)
    assert result == []


def test_scan_returns_empty_list_for_empty_jd():
    client = _make_client('["phrase"]')
    result = scan_jd_for_violations("", "Topic blocked: X", client)
    assert result == []
    client.messages.create.assert_not_called()


def test_scan_returns_empty_list_for_empty_array_response():
    client = _make_client("[]")
    result = scan_jd_for_violations("Normal JD text.", "Topic blocked: X", client)
    assert result == []


def test_build_html_highlights_phrase():
    html = _build_highlighted_html(
        "We want young professionals only.", ["young professionals only"]
    )
    assert "<mark" in html
    assert "young professionals only" in html


def test_build_html_highlights_all_occurrences():
    html = _build_highlighted_html(
        "male preferred, yes male preferred.", ["male preferred"]
    )
    assert html.count("<mark") == 2


def test_build_html_no_highlights_for_empty_phrases():
    html = _build_highlighted_html("Normal JD text.", [])
    assert "<mark" not in html
    assert "Normal JD text." in html


def test_build_html_escapes_html_chars_in_jd():
    html = _build_highlighted_html("JD with <b>bold</b> & symbols.", [])
    assert "<b>" not in html
    assert "&lt;b&gt;" in html
    assert "&amp;" in html


def test_build_html_phrase_not_in_jd_is_skipped():
    html = _build_highlighted_html("Normal JD text.", ["phrase not present"])
    assert "<mark" not in html


def test_build_html_highlights_case_insensitive():
    html = _build_highlighted_html(
        "We want Young Professionals only.", ["young professionals"]
    )
    assert "<mark" in html
    assert "Young Professionals" in html  # original JD casing preserved


def test_scan_filters_non_string_items():
    client = _make_client('[{"phrase": "young and energetic"}, "candidates aged 25-35"]')
    result = scan_jd_for_violations("Some JD text.", "Topic blocked: X", client)
    assert result == ["candidates aged 25-35"]


def test_build_html_deduplicates_overlapping_phrases():
    html = _build_highlighted_html(
        "young professionals only.", ["young professionals only", "young professionals"]
    )
    # Longer phrase absorbs shorter; exactly one mark, no nesting
    assert html.count("<mark") == 1
