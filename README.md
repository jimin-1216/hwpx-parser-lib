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
