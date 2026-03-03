"""TimelineMarker — 타임라인 마커 데이터클래스."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TimelineMarker:
    """타임라인의 특정 위치를 표시하는 마커."""

    ms: int               # 위치 (ms)
    name: str = ""        # 마커 이름 (기본 빈 문자열)
    color: str = "yellow" # yellow/red/green/blue/white

    def to_dict(self) -> dict:
        d: dict = {"ms": self.ms}
        if self.name:
            d["name"] = self.name
        if self.color != "yellow":
            d["color"] = self.color
        return d

    @classmethod
    def from_dict(cls, data: dict) -> TimelineMarker:
        return cls(
            ms=data["ms"],
            name=data.get("name", ""),
            color=data.get("color", "yellow"),
        )
