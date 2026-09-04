"""신구조문대비표 구조화 추출기 테스트 (합성 셀 격자 기반)."""

from __future__ import annotations

import os

import pytest

from hwpx_parser.syn_table import (
    Cell,
    Grid,
    expand_ellipsis,
    extract_from_grids,
    word_diff,
)


def g(rows, title=None, index=0) -> Grid:
    """[[str|Cell, ...], ...] → Grid. 문자열은 span 1 셀."""
    norm = [[c if (c is None or isinstance(c, Cell)) else Cell(c) for c in row] for row in rows]
    return Grid(rows=norm, title=title, table_index=index)


# ------------------------------------------------------------------ 헤더/열 매핑
def test_two_column_header_detected():
    grid = g([["현 행", "개 정 안"], ["제1조(목적) 이 규정은 30일", "제1조(목적) ---- 60일"]])

    tables = extract_from_grids([grid])

    assert len(tables) == 1
    t = tables[0]
    assert t.columns.current == [0] and t.columns.revised == [1] and t.columns.note is None
    assert t.header == ["현 행", "개 정 안"]
    assert len(t.rows) == 1


def test_four_column_header_with_note():
    grid = g([["구분", "현행", "개정", "비고"], ["가", "A 30일", "A 60일", "기간 연장"]])

    t = extract_from_grids([grid])[0]

    assert t.columns.current == [1] and t.columns.revised == [2] and t.columns.note == [3]
    assert t.rows[0].note == "기간 연장"
    assert t.rows[0].key == "가"


def test_colspan_header_maps_sub_columns():
    grid = g(
        [
            [Cell("현 행", colspan=2), Cell("개 정", colspan=2), Cell("비고", rowspan=2)],
            ["항목", "세부인정사항", "항목", "세부인정사항"],
            ["가-1", "30일 이내", "가-1", "60일 이내", "연장"],
        ]
    )

    t = extract_from_grids([grid])[0]

    assert t.columns.current == [0, 1] and t.columns.revised == [2, 3] and t.columns.note == [4]
    assert t.rows[0].current == "가-1\n30일 이내"
    assert t.rows[0].revised == "가-1\n60일 이내"
    assert t.rows[0].note == "연장"


def test_table_without_header_is_ignored():
    grid = g([["품목", "시행일"], ["냉장고", "6개월"]])

    assert extract_from_grids([grid]) == []


def test_two_column_table_after_caption_is_accepted():
    grid = g([["제2조 …", "제2조 ----"]], title="신·구조문 대비표")

    t = extract_from_grids([grid])[0]

    assert t.columns.current == [0] and t.columns.revised == [1]


# ------------------------------------------------------------------ 행 정렬
def test_rowspan_merges_continuation_rows():
    grid = g(
        [
            ["현행", "개정안"],
            [Cell("제3조 ① 가", rowspan=2), "제3조 ① 가'"],
            [None, "② 신설"],
            ["제4조", "제4조"],
        ]
    )

    t = extract_from_grids([grid])[0]

    assert [r.current for r in t.rows] == ["제3조 ① 가", "제4조"]
    assert t.rows[0].revised == "제3조 ① 가'\n② 신설"


def test_empty_rows_are_skipped():
    grid = g([["현행", "개정안"], ["", ""], ["A", "A"]])

    t = extract_from_grids([grid])[0]

    assert len(t.rows) == 1


# ------------------------------------------------------------------ 생략 표기 복원
def test_expand_ellipsis_basic():
    cur = "보건복지부장관은 신청일부터 30일 이내에 결정한다."
    rev = "-------------------------- 60일 이내에 결정한다."

    assert expand_ellipsis(cur, rev) == "보건복지부장관은 신청일부터 60일 이내에 결정한다."


def test_expand_ellipsis_middle_and_trailing():
    cur = "제1조(목적) 이 규정은 종합상황실의 설치에 필요한 사항을 규정한다."
    rev = "제1조(목적) ------- 상시 종합상황실의 ------------------------."

    assert expand_ellipsis(cur, rev) == "제1조(목적) 이 규정은 상시 종합상황실의 설치에 필요한 사항을 규정한다."


def test_expand_ellipsis_returns_none_when_literal_not_found():
    assert expand_ellipsis("가나다", "---- 완전히 다른 문장") is None


def test_expand_without_dashes_returns_revised_unchanged():
    assert expand_ellipsis("가나다", "라마바") == "라마바"


def test_two_dash_run_counts_as_ellipsis():
    assert (
        expand_ellipsis("투자하는 기업을 말한다.", "5억원 이상을 투자하는 --.")
        == "5억원 이상을 투자하는 기업을 말한다."
    )


def test_restore_partial_keeps_unresolved_dashes():
    from hwpx_parser.syn_table import restore_revised

    text, complete = restore_revised("가나다 라마바 사아자", "가나다 ---- 완전히다른말 ---- 사아자")
    assert complete is False
    assert text.endswith("사아자") and "완전히다른말" in text


def test_same_marker_row_is_unchanged():
    grid = g([["현행", "개정안"], ["가. ∼ 카. (생  략)", "가. ∼ 카. (현행과 같음)"], ["나. 본문", "(현행과 같음)"]])

    t = extract_from_grids([grid])[0]

    assert [r.changed for r in t.rows] == [False, False]
    assert t.rows[1].revised_expanded == "나. 본문"


# ------------------------------------------------------------------ diff / changed
def test_word_diff_marks_changed_tokens():
    d = word_diff("신청일부터 30일 이내에", "신청일부터 60일 이내에")

    ops = [op for op, _ in d]
    assert "delete" in ops and "insert" in ops
    assert ("delete", "30일") in d and ("insert", "60일") in d


def test_row_changed_flag_and_expanded():
    grid = g(
        [
            ["현행", "개정안"],
            ["제3조 신청일부터 30일 이내", "제3조 ------- 60일 이내"],
            ["제4조 그대로", "제4조 그대로"],
        ]
    )

    t = extract_from_grids([grid])[0]

    assert t.rows[0].changed is True
    assert t.rows[0].revised_expanded == "제3조 신청일부터 60일 이내"
    assert t.rows[0].key == "제3조"
    assert t.rows[1].changed is False
    assert t.changed_count == 1


def test_to_dict_shape():
    t = extract_from_grids([g([["현행", "개정안"], ["제1조 가", "제1조 나"]], title="대비표", index=7)])[0]

    d = t.to_dict()
    assert d["kind"] == "syn_table" and d["title"] == "대비표"
    assert d["columns"] == {"current": [0], "revised": [1], "note": None}
    assert d["rows"][0]["diff"] and d["source"]["table_index"] == 7


# ------------------------------------------------------------------ 실파일
@pytest.mark.skipif(not os.getenv("HWPX_SYN_SAMPLE"), reason="HWPX_SYN_SAMPLE 미설정")
def test_extract_from_real_hwpx():
    from hwpx_parser import parse_ir
    from hwpx_parser.syn_table import extract_syn_tables

    tables = extract_syn_tables(parse_ir(os.environ["HWPX_SYN_SAMPLE"]))

    assert tables, "대비표를 찾지 못함"
    assert any(r.changed for t in tables for r in t.rows)


# ------------------------------------------------------------------ 물리 격자 / 블록 분할
def test_physical_grid_with_colspan_headers():
    rows = [
        [Cell("현행", colspan=2), None, Cell("개정안", colspan=2), None, Cell("비고", rowspan=2)],
        [Cell("항목"), Cell("세부인정사항"), Cell("항목"), Cell("세부인정사항"), None],
        [Cell("가-1"), Cell("30일 이내"), Cell("가-1"), Cell("60일 이내"), Cell("연장")],
    ]
    t = extract_from_grids([Grid(rows=rows, physical=True)])[0]

    assert t.columns.current == [0, 1] and t.columns.revised == [2, 3] and t.columns.note == [4]
    assert t.rows[0].current == "가-1\n30일 이내" and t.rows[0].note == "연장"


def test_colspan_in_body_rows_does_not_merge_rows():
    rows = [
        [Cell("현행"), Cell("개정안", colspan=2), None],
        [Cell("제1조 가"), Cell("제1조 나", colspan=2), None],
        [Cell("제2조 가"), Cell("제2조 나", colspan=2), None],
    ]
    t = extract_from_grids([Grid(rows=rows, physical=True)])[0]

    assert len(t.rows) == 2


def test_single_cell_table_is_split_by_article():
    cur = "제1조(목적) 이 규정은 A를 정한다.\n제2조(정의) 용어는 B이다.\n제3조(적용) C에 적용한다."
    rev = "제1조(목적) 이 규정은 A를 정한다.\n제2조(정의) 용어는 B'이다.\n제3조(적용) C에 적용한다."
    t = extract_from_grids([g([["현행", "개정안"], [cur, rev]])])[0]

    assert len(t.rows) == 3
    assert [r.key for r in t.rows] == ["제1조(목적)", "제2조(정의)", "제3조(적용)"]
    assert [r.changed for r in t.rows] == [False, True, False]


def test_split_handles_new_and_deleted_articles():
    cur = "제1조 A\n제2조 B"
    rev = "제1조 A\n제2조의2 신설\n제2조 B"
    t = extract_from_grids([g([["현행", "개정안"], [cur, rev]])])[0]

    keys = [(r.current[:3], r.revised[:5]) for r in t.rows]
    assert ("", "제2조의2") in keys
