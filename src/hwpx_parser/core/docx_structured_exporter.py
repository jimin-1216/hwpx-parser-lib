"""DOCX 지원 스텁. 이 라이브러리는 HWPX 전용이다."""

from __future__ import annotations


class DocxNotSupportedError(NotImplementedError):
    pass


def _not_supported(*args, **kwargs):
    raise DocxNotSupportedError("hwpx-parser-lib 는 HWPX 전용입니다. DOCX 는 지원하지 않습니다.")


_iter_blocks = _not_supported
_iter_blocks_from_element = _not_supported
_load_docx_source = _not_supported
export_docx_structured_mapping = _not_supported
