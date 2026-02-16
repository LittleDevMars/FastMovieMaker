"""MainWindow UI 구성. 초기화 + 시그널 배선은 main_window.py에서 담당."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.media_library_panel import MediaLibraryPanel
from src.ui.playback_controls import PlaybackControls
from src.ui.subtitle_panel import SubtitlePanel
from src.ui.timeline_widget import TimelineWidget
from src.ui.track_header_panel import TrackHeaderPanel
from src.ui.track_selector import TrackSelector
from src.ui.video_player_widget import VideoPlayerWidget
from src.ui.templates_panel import TemplatesPanel
from src.utils.i18n import tr


def build_main_window_ui(window, player, audio_output, tts_audio_output, waveform_service) -> None:
    """window에 중앙 위젯·레이아웃·타임라인 툴바를 구성하고 필요한 속성을 설정한다.
    Controller 생성 전에 호출하며, window._toggle_magnetic_snap, _toggle_ripple_mode는 MainWindow에 있어야 한다.
    """
    central = QWidget()
    window.setCentralWidget(central)

    window._video_widget = VideoPlayerWidget(player)
    window._track_selector = TrackSelector()
    window._subtitle_panel = SubtitlePanel()

    subtitle_tab = QWidget()
    subtitle_layout = QVBoxLayout(subtitle_tab)
    subtitle_layout.setContentsMargins(0, 0, 0, 0)
    subtitle_layout.setSpacing(0)
    subtitle_layout.addWidget(window._track_selector)
    subtitle_layout.addWidget(window._subtitle_panel, 1)

    window._media_panel = MediaLibraryPanel()
    window._templates_panel = TemplatesPanel()
    window._overlay_template = None

    window._right_tabs = QTabWidget()
    window._right_tabs.addTab(subtitle_tab, tr("Subtitles"))
    window._right_tabs.addTab(window._media_panel, tr("Media"))
    window._right_tabs.addTab(window._templates_panel, tr("Templates"))

    window._top_splitter = QSplitter(Qt.Orientation.Horizontal)
    window._top_splitter.addWidget(window._video_widget)
    window._top_splitter.addWidget(window._right_tabs)
    window._top_splitter.setStretchFactor(0, 3)
    window._top_splitter.setStretchFactor(1, 1)
    window._top_splitter.setSizes([1050, 390])

    window._controls = PlaybackControls(player, audio_output)
    window._controls.set_tts_audio_output(tts_audio_output)

    window._timeline = TimelineWidget()
    window._timeline.set_waveform_service(waveform_service)
    window._track_headers = TrackHeaderPanel()
    window._track_headers.state_changed.connect(window._on_track_state_changed)

    window._timeline_container = QWidget()
    timeline_outer_layout = QHBoxLayout(window._timeline_container)
    timeline_outer_layout.setContentsMargins(0, 0, 0, 0)
    timeline_outer_layout.setSpacing(0)
    timeline_outer_layout.addWidget(window._track_headers)
    timeline_outer_layout.addWidget(window._timeline, 1)

    window._zoom_toolbar = QWidget()
    window._zoom_toolbar.setFixedHeight(28)
    window._zoom_toolbar.setStyleSheet(
        "background-color: rgb(40, 40, 40); border-top: 1px solid rgb(60, 60, 60);"
    )
    zoom_layout = QHBoxLayout(window._zoom_toolbar)
    zoom_layout.setContentsMargins(6, 2, 6, 2)
    zoom_layout.setSpacing(4)

    btn_style = """
        QPushButton { background: rgb(60,60,60); color: white; border: 1px solid rgb(80,80,80); border-radius: 3px; padding: 1px 8px; font-size: 12px; }
        QPushButton:hover { background: rgb(80,80,80); }
        QPushButton:checked { background: rgb(60, 100, 180); border: 1px solid rgb(100, 160, 240); }
    """

    window._snap_toggle_btn = QPushButton(tr("Snap"))
    window._snap_toggle_btn.setCheckable(True)
    window._snap_toggle_btn.setChecked(True)
    window._snap_toggle_btn.setFixedWidth(50)
    window._snap_toggle_btn.setStyleSheet(btn_style)
    window._snap_toggle_btn.setToolTip(tr("Toggle Magnetic Snap (S)"))
    window._snap_toggle_btn.clicked.connect(window._toggle_magnetic_snap)

    window._zoom_fit_btn = QPushButton(tr("Fit"))
    window._zoom_fit_btn.setFixedWidth(36)
    window._zoom_fit_btn.setStyleSheet(btn_style)
    window._zoom_fit_btn.setToolTip(tr("Fit entire timeline (Ctrl+0)"))
    window._zoom_fit_btn.clicked.connect(window._timeline.zoom_fit)

    window._ripple_toggle_btn = QPushButton("Ripple")
    window._ripple_toggle_btn.setCheckable(True)
    window._ripple_toggle_btn.setChecked(False)
    window._ripple_toggle_btn.setFixedWidth(50)
    window._ripple_toggle_btn.setStyleSheet(btn_style)
    window._ripple_toggle_btn.setToolTip(tr("Toggle Ripple Edit Mode (R)"))
    window._ripple_toggle_btn.clicked.connect(window._toggle_ripple_mode)

    window._zoom_out_btn = QPushButton("-")
    window._zoom_out_btn.setFixedWidth(28)
    window._zoom_out_btn.setStyleSheet(btn_style)
    window._zoom_out_btn.setToolTip(tr("Zoom out (Ctrl+-)"))
    window._zoom_out_btn.clicked.connect(window._timeline.zoom_out)

    window._zoom_slider = QSlider(Qt.Orientation.Horizontal)
    window._zoom_slider.setRange(10, 2000)  # 10% ~ 2000%
    window._zoom_slider.setValue(100)
    window._zoom_slider.setFixedWidth(120)
    window._zoom_slider.setToolTip(tr("Zoom Level"))

    window._zoom_label = QLabel("100%")
    window._zoom_label.setFixedWidth(50)
    window._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window._zoom_label.setStyleSheet(
        "color: rgb(180,180,180); font-size: 11px; border: none;"
    )

    window._zoom_in_btn = QPushButton("+")
    window._zoom_in_btn.setFixedWidth(28)
    window._zoom_in_btn.setStyleSheet(btn_style)
    window._zoom_in_btn.setToolTip(tr("Zoom in (Ctrl++)"))
    window._zoom_in_btn.clicked.connect(window._timeline.zoom_in)

    zoom_layout.addWidget(window._zoom_fit_btn)
    zoom_layout.addWidget(window._zoom_out_btn)
    zoom_layout.addWidget(window._zoom_slider)
    zoom_layout.addWidget(window._zoom_label)
    zoom_layout.addWidget(window._zoom_in_btn)
    zoom_layout.addStretch()

    # Connect slider to timeline
    window._zoom_slider.valueChanged.connect(window._timeline.set_zoom_percent)

    # Connect timeline zoom change to slider/label (prevent loop)
    def _update_zoom_ui(pct: int):
        window._zoom_label.setText(f"{pct}%")
        window._zoom_slider.blockSignals(True)
        window._zoom_slider.setValue(pct)
        window._zoom_slider.blockSignals(False)

    window._timeline.zoom_changed.connect(_update_zoom_ui)

    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)
    main_layout.addWidget(window._top_splitter, 1)
    main_layout.addWidget(window._controls)
    main_layout.addWidget(window._zoom_toolbar)
    main_layout.addWidget(window._timeline_container)

    window.setStatusBar(QStatusBar())
