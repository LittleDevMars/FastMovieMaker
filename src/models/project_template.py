"""프로젝트 템플릿 모델.

미리 정의된 해상도/fps/자막 스타일 설정을 프로젝트에 일괄 적용한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd

from src.models.style import SubtitleStyle


@dataclass(slots=True)
class ProjectTemplate:
    """단일 프로젝트 템플릿."""

    name: str             # 식별자 (e.g. "yt_shorts")
    display_name: str     # UI 표시 이름
    width: int            # 출력 영상 너비
    height: int           # 출력 영상 높이
    fps: float            # 출력 영상 FPS
    subtitle_style: SubtitleStyle   # 기본 자막 스타일
    is_builtin: bool = True         # False = 사용자 정의
    description: str = ""           # 간단한 설명

    @property
    def aspect_label(self) -> str:
        """해상도 및 비율 레이블 (e.g. '1080×1920 (9:16)')."""
        g = gcd(self.width, self.height)
        w_ratio = self.width // g
        h_ratio = self.height // g
        return f"{self.width}×{self.height} ({w_ratio}:{h_ratio})"
