"""신구조문대비표 구조화 추출.

법령·고시 개정안 첨부의 "현행 | 개정안" 표를 행 단위 구조로 바꾼다.

    DocIR ──(grids_from_doc)──▶ Grid(셀 격자) ──(extract_from_grids)──▶ SynTable

- 추출 로직은 DocIR 에 묶이지 않은 `Grid` 위에서 동작한다 (합성 데이터로 테스트 가능).
- 열 매핑: 헤더 행에서 '현행' / '개정(안)' / '비고·사유' / '구분' 열을 찾는다. colspan 헤더는 하위 열 전체를 포함한다.
- 행 정렬: rowspan 으로 이어지는 행은 앞 행에 합친다.
- 생략 표기: 개정안 셀의 `-----` 구간을 현행 텍스트로 복원한다 (실패 시 None).
- diff: 어절 단위 (difflib).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

__all__ = [
    "Cell",
    "Grid",
    "Columns",
    "SynRow",
    "SynTable",
    "extract_from_grids",
    "extract_syn_tables",
    "grids_from_doc",
    "expand_ellipsis",
    "restore_revised",
    "word_diff",
]

# ----------------------------------------------------------------------------- 격자 모델


@dataclass
class Cell:
    text: str = ""
    rowspan: int = 1
    colspan: int = 1


@dataclass
class Grid:
    """표 하나. rows[i] 는 그 행에서 *시작하는* 셀들의 목록(HTML <tr> 과 같은 의미).
    rowspan 으로 덮이는 위치는 생략하거나 None 으로 둔다."""

    rows: list[list[Optional[Cell]]]
    title: Optional[str] = None
    table_index: int = 0


@dataclass
class Columns:
    current: list[int]
    revised: list[int]
    note: Optional[list[int]] = None
    key: Optional[list[int]] = None

    def to_dict(self) -> dict[str, Any]:
        return {"current": self.current, "revised": self.revised, "note": self.note}


@dataclass
class SynRow:
    current: str
    revised: str
    note: str = ""
    key: Optional[str] = None
    revised_expanded: Optional[str] = None
    restore_complete: bool = True
    changed: bool = False
    diff: list[tuple[str, str]] = field(default_factory=list)
    row_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "key": self.key,
            "current": self.current,
            "revised": self.revised,
            "revised_expanded": self.revised_expanded,
            "restore_complete": self.restore_complete,
            "note": self.note,
            "changed": self.changed,
            "diff": [list(d) for d in self.diff],
        }


@dataclass
class SynTable:
    columns: Columns
    header: list[str]
    rows: list[SynRow]
    title: Optional[str] = None
    table_index: int = 0

    @property
    def changed_count(self) -> int:
        return sum(1 for r in self.rows if r.changed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "syn_table",
            "title": self.title,
            "columns": self.columns.to_dict(),
            "header": self.header,
            "row_count": len(self.rows),
            "changed_count": self.changed_count,
            "rows": [r.to_dict() for r in self.rows],
            "source": {"table_index": self.table_index},
        }


# ----------------------------------------------------------------------------- 유틸

_WS_RE = re.compile(r"\s+")
_DASH_RE = re.compile(r"[-‐–—─]{2,}")
_SAME_RE = re.compile(r"[\(（]?(현행과같음|현행과동일|좌동|생략)[\)）]?\.?$")
_KEY_RE = re.compile(
    r"^\s*(제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*\([^)]*\))?|\[\s*별표\s*\d*\s*\]|별표\s*\d+|제\s*\d+\s*항|[가-힣]\.|\d+\.)"
)
_CAPTION_RE = re.compile(r"신\s*[·ㆍ・]?\s*구\s*조문|대비표|신\s*구\s*대조")

_CURRENT_RE = re.compile(r"^현행$|^현행\(?[^)]*\)?$")
_REVISED_RE = re.compile(r"^(개정|개정안|개정\(안\)|개정후|개선안|신설|변경|변경안|개정내용)$|^개정")
_NOTE_RE = re.compile(r"^(비고|사유|개정사유|변경사유|비\s*고)$")
_KEYCOL_RE = re.compile(r"^(구분|조문|항목|구\s*분)$")


def _norm(text: str) -> str:
    return _WS_RE.sub("", text or "")


def _first_line(text: str) -> str:
    return (text or "").strip().splitlines()[0] if (text or "").strip() else ""


# ----------------------------------------------------------------------------- 격자 → 물리 좌표

_CONT = object()  # rowspan/colspan 으로 덮인 위치 표식


def _layout(grid: Grid) -> list[list[Any]]:
    """HTML 표 배치 규칙으로 각 행의 물리 열 위치를 계산한다.
    반환: rows × cols 행렬. 원소는 Cell(시작 위치) 또는 _CONT(덮인 위치) 또는 None."""
    occupied: dict[tuple[int, int], Any] = {}
    n_rows = len(grid.rows)
    for r, row in enumerate(grid.rows):
        c = 0
        for cell in row:
            if cell is None:
                # 자리표시자: 병합으로 덮인 위치면 그 칸을 건너뛰고, 아니면 빈 셀로 취급
                if (r, c) not in occupied:
                    occupied[(r, c)] = Cell("")
                c += 1
                continue
            while (r, c) in occupied:
                c += 1
            occupied[(r, c)] = cell
            for dr in range(cell.rowspan):
                for dc in range(cell.colspan):
                    if dr == 0 and dc == 0:
                        continue
                    occupied.setdefault((r + dr, c + dc), _CONT)
            c += cell.colspan
    n_cols = max((c for (_, c) in occupied), default=-1) + 1
    n_rows = max(n_rows, max((r for (r, _) in occupied), default=-1) + 1)
    return [[occupied.get((r, c)) for c in range(n_cols)] for r in range(n_rows)]


def _row_texts(layout_row: list[Any]) -> list[str]:
    return [(x.text if isinstance(x, Cell) else "") for x in layout_row]


# ----------------------------------------------------------------------------- 헤더 탐지


def _detect_columns(layout: list[list[Any]], title: Optional[str]) -> tuple[Optional[Columns], int, list[str]]:
    """헤더 행(최대 3행)에서 열 역할을 찾는다. 반환: (Columns, 본문 시작 행, 헤더 텍스트)."""
    n_cols = len(layout[0]) if layout else 0
    for depth in range(1, min(3, len(layout)) + 1):
        current: list[int] = []
        revised: list[int] = []
        note: list[int] = []
        keycol: list[int] = []
        # 각 열의 헤더 텍스트 = depth 행 동안 그 열을 덮는 셀 텍스트들의 연결
        col_labels: list[list[str]] = [[] for _ in range(n_cols)]
        for r in range(depth):
            for c in range(n_cols):
                x = layout[r][c]
                if isinstance(x, Cell):
                    for dc in range(x.colspan):
                        if c + dc < n_cols:
                            col_labels[c + dc].append(_norm(x.text))
        for c, labels in enumerate(col_labels):
            joined = "".join(labels)
            if any(_CURRENT_RE.match(lbl) for lbl in labels) or joined.startswith("현행"):
                current.append(c)
            elif any(_REVISED_RE.match(lbl) for lbl in labels) or joined.startswith("개정"):
                revised.append(c)
            elif any(_NOTE_RE.match(lbl) for lbl in labels):
                note.append(c)
            elif any(_KEYCOL_RE.match(lbl) for lbl in labels):
                keycol.append(c)
        if current and revised:
            # 하위 헤더 행: 현행/개정안 쪽 셀이 모두 짧고 양쪽 라벨이 같으면(예: 항목|세부인정사항) 헤더에 포함
            while depth < len(layout) - 1 and _is_subheader(layout[depth], current, revised):
                depth += 1
            header = _row_texts(layout[0])
            if depth > 1:
                header = [
                    " / ".join(t for t in (_row_texts(layout[r])[c] for r in range(depth)) if t) for c in range(n_cols)
                ]
            return Columns(current=current, revised=revised, note=note or None, key=keycol or None), depth, header
    # 헤더 없음: 캡션이 대비표이고 2열이면 좌=현행, 우=개정안
    if title and _CAPTION_RE.search(_norm(title)) and n_cols == 2:
        return Columns(current=[0], revised=[1]), 0, []
    return None, 0, []


def _is_subheader(row: list[Any], current: list[int], revised: list[int]) -> bool:
    def labels(cols: list[int]) -> list[str]:
        out = []
        for c in cols:
            x = row[c] if c < len(row) else None
            if not isinstance(x, Cell):
                return []
            t = _norm(x.text)
            if not t or len(t) > 12:
                return []
            out.append(t)
        return out

    cur, rev = labels(current), labels(revised)
    return bool(cur) and cur == rev


# ----------------------------------------------------------------------------- 행 정렬


def _logical_rows(layout: list[list[Any]], start: int, cols: Columns) -> list[dict[str, str]]:
    """본문 행을 논리 행으로 묶는다. 현행/개정안 열 중 하나라도 rowspan 연속(_CONT)이면 앞 행에 합친다."""
    watched = list(cols.current) + list(cols.revised)
    out: list[dict[str, str]] = []
    for r in range(start, len(layout)):
        row = layout[r]
        cont = any(row[c] is _CONT for c in watched if c < len(row))
        texts = {
            "current": "\n".join(t for t in (_cell_text(row, c) for c in cols.current) if t),
            "revised": "\n".join(t for t in (_cell_text(row, c) for c in cols.revised) if t),
            "note": "\n".join(t for t in (_cell_text(row, c) for c in (cols.note or [])) if t),
            "key": "\n".join(t for t in (_cell_text(row, c) for c in (cols.key or [])) if t),
        }
        if cont and out:
            prev = out[-1]
            for k, v in texts.items():
                if v:
                    prev[k] = (prev[k] + "\n" + v) if prev[k] else v
            continue
        if not texts["current"] and not texts["revised"]:
            continue
        out.append(texts)
    return out


def _cell_text(row: list[Any], c: int) -> str:
    if c >= len(row):
        return ""
    x = row[c]
    return (x.text or "").strip() if isinstance(x, Cell) else ""


# ----------------------------------------------------------------------------- 생략 표기 복원 / diff


def expand_ellipsis(current: str, revised: str) -> Optional[str]:
    """개정안의 `---` 구간을 현행 텍스트로 채운다. 하나라도 복원 못 하면 None.
    (부분 복원이 필요하면 `restore_revised` 를 사용한다.)"""
    text, complete = restore_revised(current, revised)
    return text if complete else None


def restore_revised(current: str, revised: str) -> tuple[str, bool]:
    """개정안의 `---` 구간을 현행 텍스트로 채운다. 반환: (복원 텍스트, 완전 복원 여부).

    개정안을 [리터럴, 생략, 리터럴, ...] 로 나눈다. 생략 구간은 "현행과 동일한 부분", 리터럴은 바뀐(또는
    유지된) 부분이다. 각 리터럴을 현행에서 찾아 그 앞 구간을 생략 자리에 넣는다.
    - 리터럴이 현행에 그대로 있으면 그 위치를 앵커로 쓴다.
    - 없으면(내용이 바뀐 경우) 리터럴과 현행의 최장 공통 부분(2자 이상)으로 위치를 추정한다.
    - 둘 다 실패한 생략 구간은 원문 대시를 남기고 완전 복원 실패로 표시한다. 공백 차이는 무시한다."""
    if not _DASH_RE.search(revised or ""):
        return revised, True
    cur_norm, cur_map = _norm_with_map(current)
    parts = _DASH_RE.split(revised)  # seg0 (dash) seg1 (dash) ... segN
    dashes = _DASH_RE.findall(revised)
    out: list[str] = []
    pos = 0
    complete = True
    for i, seg in enumerate(parts):
        seg_norm = _norm(seg)
        preceded_by_dash = i > 0
        if not seg_norm:
            if preceded_by_dash and i == len(parts) - 1:
                out.append(_slice_orig(current, cur_map, pos, len(cur_norm)))
                pos = len(cur_norm)
            elif preceded_by_dash:
                # 연속 생략(대시 사이에 공백만): 그대로 두고 다음 리터럴에서 채움
                out.append(seg)
            else:
                out.append(seg)
            continue
        idx = cur_norm.find(seg_norm, pos)
        if idx >= 0:
            anchor, new_pos = idx, idx + len(seg_norm)
        else:
            m = SequenceMatcher(None, cur_norm[pos:], seg_norm, autojunk=False).find_longest_match(
                0, len(cur_norm) - pos, 0, len(seg_norm)
            )
            if m.size < 2:
                # 앵커 없음: 이 생략 구간은 복원 불가 → 대시 원문 유지
                if preceded_by_dash:
                    out.append(dashes[i - 1])
                    complete = False
                out.append(seg)
                continue
            match_start = pos + m.a
            match_end = match_start + m.size
            prefix = seg_norm[: m.b]
            before = cur_norm[max(pos, match_start - len(prefix)) : match_start]
            anchor = match_start - len(before) if prefix and _looks_replaced(before, prefix) else match_start
            suffix = seg_norm[m.b + m.size :]
            after = cur_norm[match_end : match_end + len(suffix)]
            new_pos = match_end + (len(after) if suffix and _looks_replaced(after, suffix) else 0)
        if preceded_by_dash:
            out.append(_slice_orig(current, cur_map, pos, anchor))
        out.append(seg)
        pos = new_pos
    return "".join(out), complete


def _looks_replaced(original: str, replacement: str) -> bool:
    """`original`(현행 구간)이 `replacement`(개정안 리터럴 조각)로 대체된 것으로 볼지.
    숫자↔숫자이거나 문자 유사도가 충분하면 대체, 아니면 삽입으로 본다."""
    if not original or not replacement:
        return False
    if any(ch.isdigit() for ch in original) and any(ch.isdigit() for ch in replacement):
        return True
    return SequenceMatcher(None, original, replacement, autojunk=False).ratio() >= 0.34


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    norm_chars: list[str] = []
    mapping: list[int] = []
    for i, ch in enumerate(text or ""):
        if not ch.isspace():
            norm_chars.append(ch)
            mapping.append(i)
    return "".join(norm_chars), mapping


def _slice_orig(text: str, mapping: list[int], a: int, b: int) -> str:
    if a >= b or not mapping:
        return ""
    start = mapping[a] if a < len(mapping) else len(text)
    end = mapping[b - 1] + 1 if b - 1 < len(mapping) else len(text)
    return text[start:end]


_TOKEN_RE = re.compile(r"\S+")


def word_diff(a: str, b: str) -> list[tuple[str, str]]:
    """어절 단위 diff. [(op, text)] — op ∈ equal|delete|insert."""
    ta = _TOKEN_RE.findall(a or "")
    tb = _TOKEN_RE.findall(b or "")
    out: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag == "equal":
            out.append(("equal", " ".join(ta[i1:i2])))
        else:
            if i2 > i1:
                out.append(("delete", " ".join(ta[i1:i2])))
            if j2 > j1:
                out.append(("insert", " ".join(tb[j1:j2])))
    return out


# ----------------------------------------------------------------------------- 추출 본체


def _extract_key(row: dict[str, str]) -> Optional[str]:
    if row.get("key"):
        return _first_line(row["key"])
    for side in ("current", "revised"):
        m = _KEY_RE.match(_first_line(row.get(side, "")))
        if m:
            return m.group(1).strip()
    return None


def _is_same_marker(current: str, revised: str) -> bool:
    """개정안 셀이 "(현행과 같음)" 류로 끝나고, 그 앞부분(조문 번호 등)이 현행에 그대로 있으면 변경 없음."""
    body = _norm(revised or "")
    m = _SAME_RE.search(body)
    if not m:
        return False
    prefix = body[: m.start()].strip("(（")
    return prefix == "" or prefix in _norm(current or "")


def extract_from_grids(grids: Iterable[Grid]) -> list[SynTable]:
    tables: list[SynTable] = []
    for grid in grids:
        if not grid.rows:
            continue
        layout = _layout(grid)
        if not layout or not layout[0]:
            continue
        cols, body_start, header = _detect_columns(layout, grid.title)
        if cols is None:
            continue
        rows: list[SynRow] = []
        for i, lr in enumerate(_logical_rows(layout, body_start, cols)):
            cur, rev = lr["current"], lr["revised"]
            key = _extract_key(lr)
            if _is_same_marker(cur, rev):
                # "(현행과 같음)" 류 — 변경 없음
                rows.append(
                    SynRow(current=cur, revised=rev, note=lr["note"], key=key, revised_expanded=cur, row_index=i)
                )
                continue
            has_dash = bool(_DASH_RE.search(rev or ""))
            expanded, complete = restore_revised(cur, rev) if has_dash else (rev, True)
            diff = word_diff(cur, expanded)
            changed = any(op != "equal" for op, _ in diff)
            rows.append(
                SynRow(
                    current=cur,
                    revised=rev,
                    note=lr["note"],
                    key=key,
                    revised_expanded=expanded if has_dash else None,
                    restore_complete=complete,
                    changed=changed,
                    diff=diff,
                    row_index=i,
                )
            )
        if not rows:
            continue
        tables.append(SynTable(columns=cols, header=header, rows=rows, title=grid.title, table_index=grid.table_index))
    return tables


# ----------------------------------------------------------------------------- DocIR 어댑터


def grids_from_doc(doc: Any) -> list[Grid]:
    """DocIR → Grid 목록. 표 직전 문단(최대 3개) 중 대비표 캡션을 title 로 붙인다."""
    grids: list[Grid] = []
    recent: list[str] = []
    index = 0
    for para in doc.paragraphs:
        txt = (para.text or "").strip()
        for table in getattr(para, "tables", None) or []:
            title = next((t for t in reversed(recent) if _CAPTION_RE.search(_norm(t))), None)
            rows: list[list[Optional[Cell]]] = []
            seen: set[int] = set()
            for row in table.cells:
                out_row: list[Optional[Cell]] = []
                for cell in row:
                    if cell is None:
                        out_row.append(None)
                        continue
                    ident = id(cell)
                    if ident in seen:  # 병합으로 같은 셀 객체가 반복 배치된 경우
                        out_row.append(None)
                        continue
                    seen.add(ident)
                    style = getattr(cell, "cell_style", None)
                    paras = [(p.text or "").strip() for p in (getattr(cell, "paragraphs", None) or [])]
                    text = "\n".join(p for p in paras if p) or (getattr(cell, "text", "") or "").strip()
                    out_row.append(
                        Cell(
                            text=text,
                            rowspan=int(getattr(style, "rowspan", None) or 1),
                            colspan=int(getattr(style, "colspan", None) or 1),
                        )
                    )
                rows.append(out_row)
            grids.append(Grid(rows=rows, title=title, table_index=index))
            index += 1
        if txt:
            recent.append(txt)
            recent = recent[-3:]
    return grids


def extract_syn_tables(doc: Any) -> list[SynTable]:
    return extract_from_grids(grids_from_doc(doc))
