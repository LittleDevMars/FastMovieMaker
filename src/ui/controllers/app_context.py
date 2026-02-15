"""AppContext — Controller 간 공유 상태 및 위젯 참조.

MainWindow가 초기화 후 이 객체를 생성하여 모든 Controller에 주입한다.
Controller는 self.ctx 로 접근.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from pathlib import Path

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QUndoStack
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtWidgets import QMainWindow, QStatusBar

    from src.models.project import ProjectState
    from src.services.autosave import AutoSaveManager
    from src.services.frame_cache_service import FrameCacheService
    from src.ui.media_library_panel import MediaLibraryPanel
    from src.ui.playback_controls import PlaybackControls
    from src.ui.subtitle_panel import SubtitlePanel
    from src.ui.templates_panel import TemplatesPanel
    from src.ui.timeline_widget import TimelineWidget
    from src.ui.track_header_panel import TrackHeaderPanel
    from src.ui.track_selector import TrackSelector
    from src.ui.video_player_widget import VideoPlayerWidget


class AppContext:
    """Controller들이 공유하는 상태 및 위젯 참조 컨테이너.

    모든 필드는 MainWindow.__init__ 이후 설정됨.
    """

    def __init__(self) -> None:
        # ---- Core state ----
        self.project: ProjectState = None  # type: ignore[assignment]
        self.undo_stack: QUndoStack = None  # type: ignore[assignment]
        self.window: QMainWindow = None  # type: ignore[assignment]

        # ---- Media players ----
        self.player: QMediaPlayer = None  # type: ignore[assignment]
        self.audio_output: QAudioOutput = None  # type: ignore[assignment]
        self.tts_player: QMediaPlayer = None  # type: ignore[assignment]
        self.tts_audio_output: QAudioOutput = None  # type: ignore[assignment]

        # ---- UI Widgets ----
        self.video_widget: VideoPlayerWidget = None  # type: ignore[assignment]
        self.timeline: TimelineWidget = None  # type: ignore[assignment]
        self.subtitle_panel: SubtitlePanel = None  # type: ignore[assignment]
        self.controls: PlaybackControls = None  # type: ignore[assignment]
        self.track_selector: TrackSelector = None  # type: ignore[assignment]
        self.media_panel: MediaLibraryPanel = None  # type: ignore[assignment]
        self.templates_panel: TemplatesPanel = None  # type: ignore[assignment]
        self.track_header: TrackHeaderPanel = None  # type: ignore[assignment]

        # ---- Services ----
        self.autosave: AutoSaveManager = None  # type: ignore[assignment]
        self.frame_cache_service: FrameCacheService | None = None

        # ---- Timers (생성은 MainWindow) ----
        self.pending_seek_timer: QTimer = None  # type: ignore[assignment]
        self.render_pause_timer: QTimer = None  # type: ignore[assignment]

        # ---- 재생 공유 상태 ----
        self.current_clip_index: int = 0
        self.current_track_index: int = 0
        self.current_playback_source: str | None = None
        self.pending_seek_ms: int | None = None
        self.pending_auto_play: bool = False
        self.play_intent: bool = False
        self.showing_cached_frame: bool = False

        # ---- 프로젝트 경로 ----
        self.current_project_path: Path | None = None
        self.temp_video_path: Path | None = None

        # ---- 프록시 ----
        self.use_proxies: bool = False
        self.proxy_map: dict[str, str] = {}

        # ---- Controller 참조 (MainWindow가 설정) ----
        self.playback_ctrl: Any = None
        self.subtitle_ctrl: Any = None
        self.clip_ctrl: Any = None
        self.overlay_ctrl: Any = None
        self.project_ctrl: Any = None
        self.media_ctrl: Any = None

        # ---- MainWindow 콜백 (Controller에서 호출) ----
        self.refresh_all: Callable[[], None] = lambda: None
        self.ensure_timeline_duration: Callable[[], None] = lambda: None
        self.refresh_track_selector: Callable[[], None] = lambda: None

    def status_bar(self) -> QStatusBar:
        """편의 메서드: MainWindow의 상태바 접근."""
        return self.window.statusBar()

    def active_track(self):
        """현재 활성 자막 트랙 반환."""
        idx = self.project.active_track_index
        tracks = self.project.subtitle_tracks
        if 0 <= idx < len(tracks):
            return tracks[idx]
        return None
