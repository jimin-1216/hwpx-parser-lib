# hwpx-parser-lib

HWPX 문서를 **파싱만** 하는 경량 라이브러리. [document-processor](https://github.com/jimin-1216/document-processor)에서
HWPX 파싱 경로(문서 IR 생성 + 스타일 추출)만 발라냈다.

- 순수 Python. 의존성은 `pydantic` 하나. Java·JAR 없음
- 표를 페이지 단위로 쪼개지 않고 문서 구조 그대로(셀 병합 rowspan/colspan 포함) 제공
- 저장·후속처리용 **압축 HTML**(`<p>`/`<table>`)과 **표 셀 포함 텍스트** 출력
- 포함하지 않는 것: 레이아웃 HTML 렌더링, 편집, 주석, PDF, DOCX, HWP(구 바이너리 — rhwp 등 사용)

## 설치

```bash
pip install "hwpx-parser-lib @ git+https://github.com/jimin-1216/hwpx-parser-lib.git@<commit>"
```

## 사용

```python
from hwpx_parser import parse, parse_ir, render_compact

result = parse("문서.hwpx")
result.html          # 압축 HTML
result.text          # 문단 + 표 행 텍스트
result.table_count

doc = parse_ir("문서.hwpx")      # DocIR — 문단(paragraphs) / 표(paragraph.tables) / 셀(table.cells)
for para in doc.paragraphs:
    for table in para.tables:
        for row in table.cells:
            print([c.text for c in row if c])
```

## 신구조문대비표 구조화 (`hwpx_parser.syn_table`)

법령·고시 개정안 첨부의 "현행 | 개정안" 표를 행 단위 구조로 바꾼다.

```python
from hwpx_parser import parse_ir, extract_syn_tables

for t in extract_syn_tables(parse_ir("개정안.hwpx")):
    print(t.title, t.header, t.columns.to_dict(), len(t.rows), t.changed_count)
    for row in t.rows:
        row.key               # "제3조(…)", "[별표 2]", "가." 등
        row.current           # 현행 셀 텍스트
        row.revised           # 개정안 셀 텍스트 (생략 표기 `-----` 포함)
        row.revised_expanded  # 생략 표기를 현행으로 채운 복원본 (없으면 None)
        row.restore_complete  # 모든 생략 구간을 복원했는지
        row.changed           # 어절 diff 상 변경 여부 ("(현행과 같음)" 은 변경 없음)
        row.diff              # [("equal"|"delete"|"insert", 텍스트), ...]
    t.to_dict()               # JSON 직렬화용
```

- 헤더 인식: `현행` / `개정(안)` / `비고·사유` / `구분`. colspan 헤더는 하위 열 전체를 묶고, 하위 헤더 행(항목|세부인정사항)은 자동 포함
- rowspan 으로 이어지는 행은 앞 행에 합친다
- 헤더 없는 2열 표는 직전 문단이 "신구조문대비표" 류 캡션일 때만 인정
- PDF 는 표 구조가 없으므로 대상 아님

## 원본과의 관계

`src/hwpx_parser/` 아래 `models.py`, `style_types.py`, `io_utils.py`, `logging_config.py`, `builder.py`, `hwpx.py`,
`core/document_ir_parser.py`, `core/hwpx_structured_exporter.py`, `core/style_extractor.py` 는
document-processor 의 동일 파일을 **수정 없이** 복사한 것이다. 원본에서 HWPX 파싱이 개선되면 파일을 그대로 덮어쓴다.

`core/hwp_converter.py`, `core/docx_structured_exporter.py` 는 원본의 Java/DOCX 경로를 막는 스텁이다.

| 원본 커밋 | 동기화일 |
|---|---|
| a416f6a434679019e1e26659e39a190ed36a0118 | 2026-09-04 |

## 테스트

```bash
uv venv && uv pip install -e ".[dev]"
HWPX_TEST_SAMPLE=/path/to/sample.hwpx uv run pytest
```
