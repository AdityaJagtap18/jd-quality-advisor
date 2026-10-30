import pytest
from agents.jd_docx import _hex_to_rgb, extract_jd_text, build_docx
from models.context import JDDocument


_SAMPLE_DOC: JDDocument = {
    "role_title": "Senior ML Engineer",
    "about_company": "We build AI-powered hiring tools.",
    "about_role": "You will lead ML infrastructure.",
    "responsibilities": ["Design model pipelines", "Mentor junior engineers"],
    "required_skills": ["Python 3.11 (expert)", "PyTorch 2.x (advanced)"],
    "preferred_skills": ["Kubernetes", "MLflow"],
    "success_criteria": ["Ship v1 model pipeline within 90 days"],
    "reporting_structure": "Reports to VP of Engineering",
    "growth_path": "Path to Staff Engineer within 18 months",
    "compensation": "₹40–55 LPA + equity",
    "equal_opportunity": "We are an equal opportunity employer.",
}


def test_hex_to_rgb_navy():
    assert _hex_to_rgb("#1D3557") == (29, 53, 87)


def test_hex_to_rgb_red():
    assert _hex_to_rgb("#C8102E") == (200, 16, 46)


def test_hex_to_rgb_without_hash():
    assert _hex_to_rgb("2D2D2D") == (45, 45, 45)


def test_extract_jd_text_contains_key_fields():
    text = extract_jd_text(_SAMPLE_DOC)
    assert "Senior ML Engineer" in text
    assert "AI-powered hiring tools" in text
    assert "PyTorch 2.x" in text
    assert "equal opportunity" in text


def test_extract_jd_text_excludes_none_fields():
    doc: JDDocument = {
        "role_title": "Engineer",
        "about_company": "Acme Corp",
        "about_role": "Build things",
        "responsibilities": ["Do work"],
        "required_skills": ["Python"],
        "preferred_skills": [],
        "success_criteria": [],
        "equal_opportunity": "EOE",
    }
    text = extract_jd_text(doc)
    assert text
    assert "None" not in text


def test_build_docx_returns_bytes():
    result = build_docx(_SAMPLE_DOC, "#1D3557", None)
    assert isinstance(result, bytes)
    assert len(result) > 1000


def test_build_docx_with_invalid_color_falls_back():
    result = build_docx(_SAMPLE_DOC, "not-a-color", None)
    assert isinstance(result, bytes)
