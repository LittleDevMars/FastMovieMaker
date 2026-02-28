"""FFmpeg scdet 필터를 사용한 장면 감지 서비스."""

from __future__ import annotations

import re

from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner


class SceneDetectionService:
    """FFmpeg scdet 필터로 장면 경계를 감지하는 서비스."""

    @staticmethod
    def detect_scenes(
        video_path: str,
        threshold: float = 40.0,
        min_gap_ms: int = 500,
    ) -> list[int]:
        """FFmpeg scdet 필터로 장면 경계 ms 목록을 반환.

        Args:
            video_path: 분석할 비디오 파일 경로.
            threshold: 장면 감지 민감도 (0~100, 높을수록 덜 민감).
            min_gap_ms: 인접 경계 최소 간격 (ms).

        Returns:
            장면 전환 타임스탬프 목록 (ms 단위, 정렬됨).
        """
        runner = get_ffmpeg_runner()
        result = runner.run(
            ["-i", video_path,
             "-vf", f"scdet=threshold={threshold}",
             "-f", "null", "-"],
            capture_output=True,
            text=True,
        )
        raw = SceneDetectionService._parse_scdet_output(result.stderr)
        return SceneDetectionService._apply_min_gap(raw, min_gap_ms)

    @staticmethod
    def _parse_scdet_output(stderr: str) -> list[int]:
        """stderr에서 'pts_time:X.XXX' 또는 '@time:X.XXX' 패턴 → ms 목록."""
        times_ms: list[int] = []
        for m in re.finditer(r"(?:pts_time:|@time:)\s*([\d.]+)", stderr):
            times_ms.append(int(float(m.group(1)) * 1000))
        return sorted(set(times_ms))

    @staticmethod
    def _apply_min_gap(boundaries: list[int], min_gap_ms: int) -> list[int]:
        """인접 경계가 min_gap_ms 미만이면 후자를 제거."""
        if not boundaries:
            return []
        result = [boundaries[0]]
        for ms in boundaries[1:]:
            if ms - result[-1] >= min_gap_ms:
                result.append(ms)
        return result
