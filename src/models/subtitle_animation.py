"""자막 애니메이션 설정 데이터클래스 (per-segment)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SubtitleAnimation:
    """자막 진입·퇴출 애니메이션 설정 (per-segment)."""

    in_effect: str = "none"          # "none" | "fade" | "slide_up" | "slide_down" | "typewriter"
    out_effect: str = "none"         # "none" | "fade"
    in_duration_ms: int = 300        # 진입 효과 지속 시간 (ms)
    out_duration_ms: int = 300       # 퇴출 효과 지속 시간 (ms)
    slide_offset_px: int = 60        # 슬라이드 오프셋 (px)

    @property
    def is_active(self) -> bool:
        """in/out 효과 중 하나라도 설정되어 있으면 True."""
        return self.in_effect != "none" or self.out_effect != "none"

    def copy(self) -> SubtitleAnimation:
        """독립적인 복사본 반환."""
        return SubtitleAnimation(
            in_effect=self.in_effect,
            out_effect=self.out_effect,
            in_duration_ms=self.in_duration_ms,
            out_duration_ms=self.out_duration_ms,
            slide_offset_px=self.slide_offset_px,
        )
