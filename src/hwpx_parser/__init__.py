"""hwpx-parser-lib — HWPX 구조 파서 (파싱 전용).

document-processor(jimin-1216/document-processor)에서 HWPX 파싱 경로만 발라낸 경량 라이브러리.
레이아웃 렌더링·편집·주석·PDF·DOCX·HWP(Java) 경로는 포함하지 않는다.

공개 API
    parse_ir(source)            -> DocIR           문서 구조(IR). 문단·표·셀·병합 정보
    render_compact(doc)         -> (html, text)    저장/후속처리용 압축 HTML(<p>/<table>) 과 표 셀 포함 텍스트
    parse(source)               -> ParseResult     위 두 가지를 한 번에
    extract_syn_tables(doc)     -> [SynTable]      신구조문대비표 구조화 (hwpx_parser.syn_table)

내부 모듈(models, core/*)은 원본 document-processor 와 파일 단위로 동일하게 유지하여
원본의 HWPX 파싱 수정을 그대로 가져올 수 있게 한다.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import BinaryIO

from .models import DocIR
from .syn_table import SynTable, extract_syn_tables

__version__ = "0.2.0"
__all__ = [
    "DocIR",
    "ParseResult",
    "SynTable",
    "extract_syn_tables",
    "parse",
    "parse_ir",
    "render_compact",
    "__version__",
]

Source = str | PathLike[str] | bytes | BinaryIO


@dataclass(frozen=True)
class ParseResult:
    html: str
    text: str
    doc: DocIR

    @property
    def table_count(self) -> int:
        return sum(len(p.tables) for p in self.doc.paragraphs)


def parse_ir(source: Source) -> DocIR:
    """HWPX → DocIR. 경로·바이트·파일객체 모두 허용. HWPX 가 아니면 ValueError."""
    if isinstance(source, (str, PathLike)):
        suffix = Path(source).suffix.lower()
        if suffix and suffix != ".hwpx":
            raise ValueError(f"hwpx-parser-lib 는 HWPX 전용입니다: {suffix}")
    return DocIR.from_file(source, doc_type="hwpx")


def _wrap(body: str) -> str:
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{body}</body></html>"


def _esc(text: str) -> str:
    return _html.escape(text).replace("\n", "<br/>")


def render_compact(doc: DocIR) -> tuple[str, str]:
    """DocIR → (압축 HTML, 텍스트).

    - HTML: 문단은 <p>, 표는 <table>/<tr>/<td>(rowspan·colspan 유지)만 사용. 스타일 없음
    - 텍스트: 문단 텍스트 + 표 행(셀을 ' | ' 로 연결)
    원본 DocIR.to_html() 은 화면 재현용이라 텍스트 대비 수십~수백 배로 커지므로 저장·후속처리에는 이 출력을 쓴다.
    """
    html_parts: list[str] = []
    text_parts: list[str] = []

    def cell_text(cell) -> str:
        paras = [(p.text or "").strip() for p in (getattr(cell, "paragraphs", None) or [])]
        paras = [p for p in paras if p]
        return "\n".join(paras) if paras else (getattr(cell, "text", "") or "").strip()

    for para in doc.paragraphs:
        txt = (para.text or "").strip()
        if txt:
            html_parts.append(f"<p>{_esc(txt)}</p>")
            text_parts.append(txt)
        for table in para.tables:
            rows_html: list[str] = []
            for row in table.cells:
                tds: list[str] = []
                row_text: list[str] = []
                for cell in row:
                    if cell is None:
                        continue
                    style = getattr(cell, "cell_style", None)
                    attrs = ""
                    rs = getattr(style, "rowspan", None) or 1
                    cs = getattr(style, "colspan", None) or 1
                    if rs > 1:
                        attrs += f' rowspan="{rs}"'
                    if cs > 1:
                        attrs += f' colspan="{cs}"'
                    ct = cell_text(cell)
                    tds.append(f"<td{attrs}>{_esc(ct)}</td>")
                    if ct:
                        row_text.append(ct.replace("\n", " "))
                if tds:
                    rows_html.append("<tr>" + "".join(tds) + "</tr>")
                if row_text:
                    text_parts.append(" | ".join(row_text))
            if rows_html:
                html_parts.append("<table>" + "".join(rows_html) + "</table>")

    return _wrap("\n".join(html_parts)), "\n".join(text_parts)


def parse(source: Source) -> ParseResult:
    doc = parse_ir(source)
    html, text = render_compact(doc)
    return ParseResult(html=html, text=text, doc=doc)
