"""hwpx-parser-lib 테스트. 실제 HWPX 는 HWPX_TEST_SAMPLE 환경변수로 지정한다."""

from __future__ import annotations

import os

import pytest

import hwpx_parser
from hwpx_parser import DocIR, parse, parse_ir, render_compact

SAMPLE = os.getenv("HWPX_TEST_SAMPLE")
needs_sample = pytest.mark.skipif(not SAMPLE, reason="HWPX_TEST_SAMPLE 미설정")


def test_public_api_exists():
    assert callable(parse) and callable(parse_ir) and callable(render_compact)
    assert hwpx_parser.__version__


def test_rejects_non_hwpx_suffix(tmp_path):
    f = tmp_path / "x.hwp"
    f.write_bytes(b"stub")
    with pytest.raises(ValueError):
        parse_ir(str(f))


def test_hwp_and_docx_paths_are_stubbed():
    from hwpx_parser.core.docx_structured_exporter import DocxNotSupportedError, _load_docx_source
    from hwpx_parser.core.hwp_converter import HwpNotSupportedError, convert_hwp_to_hwpx_bytes

    with pytest.raises(HwpNotSupportedError):
        convert_hwp_to_hwpx_bytes(b"")
    with pytest.raises(DocxNotSupportedError):
        _load_docx_source("x.docx")


def test_render_compact_on_empty_doc():
    doc = DocIR()
    html, text = render_compact(doc)
    assert html.startswith("<!DOCTYPE html>") and text == ""


@needs_sample
def test_parse_real_sample():
    result = parse(SAMPLE)
    assert len(result.text) > 50
    assert "<p>" in result.html
    assert result.html.count("<table") == result.table_count
    # 압축 HTML 은 텍스트의 5배를 넘지 않아야 한다 (레이아웃 HTML 은 수십~수백 배)
    assert len(result.html) < len(result.text) * 5 + 2000


@needs_sample
def test_text_includes_table_cells():
    result = parse(SAMPLE)
    cells = [
        (c.text or "").strip()
        for p in result.doc.paragraphs
        for t in p.tables
        for row in t.cells
        for c in row
        if c and (c.text or "").strip()
    ]
    if cells:
        assert cells[0][:20] in result.text
