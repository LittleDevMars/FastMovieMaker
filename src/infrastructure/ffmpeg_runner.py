"""FFmpeg 실행 추상화. 모든 FFmpeg subprocess 호출은 이 클래스를 통해 수행.

Application 계층이 subprocess에 직접 의존하지 않도록 하여,
테스트 시 Mock으로 교체하거나 향후 Rust 구현체로 전환 가능하게 함.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from src.utils.ffmpeg_utils import find_ffmpeg, find_ffprobe


class FFmpegRunner:
    """FFmpeg/FFprobe 실행을 담당하는 인프라 클래스."""

    def __init__(self, ffmpeg_path: str | None = None, ffprobe_path: str | None = None):
        """경로를 지정하지 않으면 자동 탐색 (config → PATH → bundled)."""
        self._ffmpeg = ffmpeg_path or find_ffmpeg()
        self._ffprobe = ffprobe_path or find_ffprobe()

    @property
    def ffmpeg_path(self) -> str | None:
        return self._ffmpeg

    @property
    def ffprobe_path(self) -> str | None:
        return self._ffprobe

    def is_available(self) -> bool:
        """FFmpeg 실행 파일이 존재하는지."""
        return self._ffmpeg is not None and Path(self._ffmpeg).is_file()

    def run(
        self,
        args: list[str],
        *,
        check: bool = False,
        capture_output: bool = True,
        text: bool = True,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess:
        """FFmpeg를 동기 실행. args에는 ffmpeg 바이너리 경로를 제외한 인자만 전달."""
        if not self._ffmpeg:
            raise FileNotFoundError("FFmpeg not found. Please install FFmpeg.")
        cmd = [self._ffmpeg] + args
        run_kwargs = dict(capture_output=capture_output, text=text, **kwargs)
        if sys.platform == "win32":
            run_kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        return subprocess.run(cmd, check=check, **run_kwargs)

    def run_async(
        self,
        args: list[str],
        **kwargs: Any,
    ) -> subprocess.Popen:
        """FFmpeg를 비동기 실행 (Popen). 진행률 스트리밍 등에 사용."""
        if not self._ffmpeg:
            raise FileNotFoundError("FFmpeg not found. Please install FFmpeg.")
        cmd = [self._ffmpeg] + args
        if sys.platform == "win32":
            kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        return subprocess.Popen(cmd, **kwargs)

    def run_ffprobe(
        self,
        args: list[str],
        *,
        check: bool = False,
        capture_output: bool = True,
        text: bool = True,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess:
        """FFprobe를 동기 실행."""
        if not self._ffprobe:
            raise FileNotFoundError("FFprobe not found. Please install FFmpeg.")
        cmd = [self._ffprobe] + args
        run_kwargs = dict(capture_output=capture_output, text=text, **kwargs)
        if timeout is not None:
            run_kwargs["timeout"] = timeout
        return subprocess.run(cmd, check=check, **run_kwargs)


# 싱글톤 인스턴스 (대부분의 서비스에서 공유)
_default_runner: FFmpegRunner | None = None


def get_ffmpeg_runner() -> FFmpegRunner:
    """기본 FFmpegRunner 인스턴스 반환."""
    global _default_runner
    if _default_runner is None:
        _default_runner = FFmpegRunner()
    return _default_runner
