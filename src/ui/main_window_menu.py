"""MainWindow 메뉴 구성. Controller 생성 후 호출한다."""

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu

from src.utils.i18n import tr


def build_main_window_menu(window) -> None:
    """window에 메뉴바를 구성한다. window._media, _subtitle_ctrl, _project_ctrl, _overlay, _playback, _undo_stack 필요."""
    menubar = window.menuBar()

    file_menu = menubar.addMenu(tr("&File"))

    open_action = QAction(tr("&Open Video..."), window)
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    open_action.triggered.connect(window._media.on_open_video)
    file_menu.addAction(open_action)

    import_srt_action = QAction(tr("&Import SRT..."), window)
    import_srt_action.setShortcut(QKeySequence("Ctrl+I"))
    import_srt_action.triggered.connect(window._subtitle_ctrl.on_import_srt)
    file_menu.addAction(import_srt_action)

    import_srt_track_action = QAction(tr("Import SRT to &New Track..."), window)
    import_srt_track_action.triggered.connect(window._subtitle_ctrl.on_import_srt_new_track)
    file_menu.addAction(import_srt_track_action)

    file_menu.addSeparator()

    export_action = QAction(tr("&Export SRT..."), window)
    export_action.setShortcut(QKeySequence("Ctrl+E"))
    export_action.triggered.connect(window._subtitle_ctrl.on_export_srt)
    file_menu.addAction(export_action)

    export_video_action = QAction(tr("Export &Video..."), window)
    export_video_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
    export_video_action.triggered.connect(window._project_ctrl.on_export_video)
    file_menu.addAction(export_video_action)

    batch_export_action = QAction(tr("&Batch Export..."), window)
    batch_export_action.triggered.connect(window._project_ctrl.on_batch_export)
    file_menu.addAction(batch_export_action)

    file_menu.addSeparator()

    save_action = QAction(tr("&Save Project..."), window)
    save_action.setShortcut(QKeySequence("Ctrl+S"))
    save_action.triggered.connect(window._project_ctrl.on_save_project)
    file_menu.addAction(save_action)

    load_action = QAction(tr("&Load Project..."), window)
    load_action.setShortcut(QKeySequence("Ctrl+L"))
    load_action.triggered.connect(window._project_ctrl.on_load_project)
    file_menu.addAction(load_action)

    window._recent_menu = QMenu(tr("Recent &Projects"), window)
    file_menu.addMenu(window._recent_menu)
    window._project_ctrl.update_recent_menu()

    file_menu.addSeparator()

    quit_action = QAction(tr("&Quit"), window)
    quit_action.setShortcut(QKeySequence("Ctrl+Q"))
    quit_action.triggered.connect(window.close)
    file_menu.addAction(quit_action)

    edit_menu = menubar.addMenu(tr("&Edit"))
    undo_action = window._undo_stack.createUndoAction(window, tr("&Undo"))
    undo_action.setShortcut(QKeySequence("Ctrl+Z"))
    edit_menu.addAction(undo_action)
    redo_action = window._undo_stack.createRedoAction(window, tr("&Redo"))
    redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
    edit_menu.addAction(redo_action)
    edit_menu.addSeparator()

    split_action = QAction(tr("S&plit Subtitle"), window)
    split_action.triggered.connect(window._subtitle_ctrl.on_split_subtitle)
    edit_menu.addAction(split_action)
    merge_action = QAction(tr("&Merge Subtitles"), window)
    merge_action.triggered.connect(window._subtitle_ctrl.on_merge_subtitles)
    edit_menu.addAction(merge_action)
    edit_menu.addSeparator()

    add_text_overlay_action = QAction(tr("Add &Text Overlay"), window)
    add_text_overlay_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
    add_text_overlay_action.triggered.connect(window._overlay.on_add_text_overlay)
    edit_menu.addAction(add_text_overlay_action)
    edit_menu.addSeparator()

    batch_shift_action = QAction(tr("&Batch Shift Timing..."), window)
    batch_shift_action.triggered.connect(window._subtitle_ctrl.on_batch_shift)
    edit_menu.addAction(batch_shift_action)
    edit_menu.addSeparator()

    jump_frame_action = QAction(tr("&Jump to Frame..."), window)
    jump_frame_action.setShortcut(QKeySequence("Ctrl+J"))
    jump_frame_action.triggered.connect(window._playback.on_jump_to_frame)
    edit_menu.addAction(jump_frame_action)
    edit_menu.addSeparator()

    scene_detect_action = QAction(tr("Detect &Scenes..."), window)
    scene_detect_action.triggered.connect(window._on_scene_detect)
    edit_menu.addAction(scene_detect_action)
    edit_menu.addSeparator()

    preferences_action = QAction(tr("&Preferences..."), window)
    preferences_action.setShortcut(QKeySequence("Ctrl+,"))
    preferences_action.triggered.connect(window._on_preferences)
    edit_menu.addAction(preferences_action)

    sub_menu = menubar.addMenu(tr("&Subtitles"))

    gen_action = QAction(tr("&Generate (Whisper)..."), window)
    gen_action.setShortcut(QKeySequence("Ctrl+G"))
    gen_action.triggered.connect(window._subtitle_ctrl.on_generate_subtitles)
    sub_menu.addAction(gen_action)

    gen_timeline_action = QAction(tr("Generate from &Edited Timeline..."), window)
    gen_timeline_action.setShortcut(QKeySequence("Ctrl+Shift+G"))
    gen_timeline_action.triggered.connect(window._subtitle_ctrl.on_generate_subtitles_from_timeline)
    sub_menu.addAction(gen_timeline_action)

    tts_action = QAction(tr("Generate &Speech (TTS)..."), window)
    tts_action.setShortcut(QKeySequence("Ctrl+T"))
    tts_action.triggered.connect(window._subtitle_ctrl.on_generate_tts)
    sub_menu.addAction(tts_action)

    play_tts_action = QAction(tr("&Play TTS Audio"), window)
    play_tts_action.setShortcut(QKeySequence("Ctrl+P"))
    play_tts_action.triggered.connect(window._subtitle_ctrl.on_play_tts_audio)
    sub_menu.addAction(play_tts_action)

    regen_audio_action = QAction(tr("&Regenerate Audio from Timeline"), window)
    regen_audio_action.setShortcut(QKeySequence("Ctrl+R"))
    regen_audio_action.triggered.connect(window._subtitle_ctrl.on_regenerate_audio)
    sub_menu.addAction(regen_audio_action)

    clear_action = QAction(tr("&Clear Subtitles"), window)
    clear_action.triggered.connect(window._subtitle_ctrl.on_clear_subtitles)
    sub_menu.addAction(clear_action)
    sub_menu.addSeparator()

    translate_action = QAction(tr("&Translate Track..."), window)
    translate_action.triggered.connect(window._subtitle_ctrl.on_translate_track)
    sub_menu.addAction(translate_action)
    sub_menu.addSeparator()

    style_action = QAction(tr("Default &Style..."), window)
    style_action.triggered.connect(window._subtitle_ctrl.on_edit_default_style)
    sub_menu.addAction(style_action)
    sub_menu.addSeparator()

    edit_position_action = QAction(tr("Edit Subtitle &Position"), window)
    edit_position_action.setCheckable(True)
    edit_position_action.setShortcut(QKeySequence("Ctrl+E"))
    edit_position_action.triggered.connect(window._subtitle_ctrl.on_toggle_position_edit)
    sub_menu.addAction(edit_position_action)
    window._edit_position_action = edit_position_action

    sub_menu.addSeparator()
    auto_align_action = QAction(tr("Auto-align &Subtitles"), window)
    auto_align_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
    auto_align_action.triggered.connect(window._subtitle_ctrl.on_auto_align_subtitles)
    sub_menu.addAction(auto_align_action)

    wrap_action = QAction(tr("Auto-wrap &Subtitles\u2026"), window)
    wrap_action.setShortcut(QKeySequence("Ctrl+Shift+W"))
    wrap_action.triggered.connect(window._subtitle_ctrl.on_wrap_subtitles)
    sub_menu.addAction(wrap_action)

    view_menu = menubar.addMenu(tr("&View"))
    window._proxy_action = QAction(tr("Use &Proxy Media"), window)
    window._proxy_action.setCheckable(True)
    window._proxy_action.setChecked(False)
    window._proxy_action.triggered.connect(window._media.toggle_proxies)
    view_menu.addAction(window._proxy_action)

    help_menu = menubar.addMenu(tr("&Help"))
    screenshot_action = QAction(tr("Take &Screenshot"), window)
    screenshot_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    screenshot_action.triggered.connect(window._on_take_screenshot)
    help_menu.addAction(screenshot_action)
    help_menu.addSeparator()
    about_action = QAction(tr("&About"), window)
    about_action.triggered.connect(window._on_about)
    help_menu.addAction(about_action)
