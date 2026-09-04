"""HWP(구 바이너리) → HWPX 변환 스텁.

원본 document-processor 는 Java(jpype + hwp2hwpx JAR)로 변환하지만, 이 라이브러리는 HWPX 전용이다.
HWP 파일은 rhwp 등 별도 도구로 처리한다.
"""

from __future__ import annotations

from pathlib import Path


class HwpNotSupportedError(NotImplementedError):
    pass


def convert_hwp_to_hwpx_bytes(*args, **kwargs) -> bytes:  # noqa: D401
    raise HwpNotSupportedError("hwpx-parser-lib 는 HWPX 전용입니다. HWP(구 바이너리)는 rhwp 등으로 변환/파싱하세요.")


def patch_hwpx_container(hwpx_path: str | Path) -> None:
    """원본은 손상된 컨테이너 rootfile 항목을 정리한다. HWPX 전용 경로에서는 no-op."""
    return None
