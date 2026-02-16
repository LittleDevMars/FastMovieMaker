# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

FastMovieMaker is a video subtitle editor with Whisper-based automatic subtitle generation. Built with PySide6 (Qt) for the UI and OpenAI Whisper for speech-to-text transcription.

## Build & Run Commands

```bash
# macOS (Apple Silicon)
pip3 install -r requirements.txt
python3 main.py

# Windows (CUDA 12.4 - adjust for your GPU)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
python main.py

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_models.py -v

# Run a specific test
pytest tests/test_models.py::TestSubtitleTrack::test_segment_at -v

# Controller unit tests (mock AppContext, no GUI)
pytest tests/test_controllers.py -v
```

## External Dependencies

- **FFmpeg**: Required for audio extraction. The app auto-detects the path by platform:
  - macOS: `/opt/homebrew/bin/ffmpeg` (Homebrew default)
  - Windows: `E:\Python\Scripts\ffmpeg.exe`
  - Others: system PATH
  - Update `src/utils/config.py` if your FFmpeg is elsewhere.
- **GPU Support**: Whisper uses CUDA if available, MPS (Apple Silicon) if available, falls back to CPU.

## Architecture

### Layered + MVC Separation

```
src/
├── models/          # Pure Python dataclasses (no Qt dependency, __slots__)
├── infrastructure/  # External adapters (FFmpeg, Whisper abstraction)
├── services/        # Business logic (uses infrastructure, Qt-free)
├── workers/         # QThread workers bridging services to UI
├── utils/           # Config, time utils, hw_accel
└── ui/              # PySide6 UI components
    ├── controllers/     # MVC controllers (QObject-based for thread safety)
    │   ├── app_context.py       # Shared state container
    │   ├── media_controller.py  # Video load/proxy/waveform/frame cache/BGM
    │   ├── playback_controller.py
    │   ├── subtitle_controller.py
    │   ├── clip_controller.py
    │   ├── overlay_controller.py
    │   └── project_controller.py
    ├── main_window.py       # Thin shell (~460 lines: init + signal wiring)
    ├── main_window_ui.py    # UI layout (build_main_window_ui)
    ├── main_window_menu.py # Menu bar (build_main_window_menu)
    ├── timeline_widget.py   # Layout + event handlers (~940 lines)
    ├── timeline_painter.py  # NumPy-vectorized rendering
    ├── timeline_drag.py     # Drag handling with bisect snap
    ├── timeline_hit_test.py # (x,y) hit test (TimelineHitTester)
    └── dialogs/
```

Models and services are intentionally Qt-free for testability. Workers wrap services with Qt signals for background execution. Controllers inherit `QObject` so worker signal→slot connections auto-use `QueuedConnection` across threads.

### Key Patterns

**Video Playback**: Uses `QGraphicsView` + `QGraphicsVideoItem` instead of `QVideoWidget` to enable subtitle text overlay via `QGraphicsTextItem` on the same scene.

**Background Workers** use the `moveToThread` pattern:
1. Create `QThread` and worker object
2. Move worker to thread via `moveToThread()`
3. Connect `thread.started` to `worker.run`
4. Worker emits signals (`progress`, `finished`, `error`)
5. Controller (QObject on main thread) receives signals via `QueuedConnection` — GUI-safe

**IMPORTANT**: `MediaController` inherits `QObject` specifically because non-QObject receivers default to `DirectConnection` in PySide6, causing worker signals to run GUI code on the worker thread (crash on macOS).

**Video Import (special case)**: `VideoLoadWorker` uses a blocking `QProgressDialog.exec()` pattern. Results are stored in local variables via `DirectConnection` (GIL-safe), then processed on the main thread after `exec()` returns.

**Timeline Widget**: Custom-painted with `QPainter`. Supports zoom (Ctrl+wheel), scroll (wheel), click-to-seek, and auto-follows playhead. Waveform rendering uses NumPy vectorization.

**Algorithm Optimizations**: Core lookups use `bisect` binary search (O(log n)). `VideoClipTrack` uses prefix sums for O(1) timeline offset queries. All dataclasses use `__slots__`.

### Data Flow

1. User opens video → `MediaController.load_video()` → `VideoLoadWorker` (background, HW-accelerated MKV→MP4)
2. Generate subtitles → `WhisperDialog` → `WhisperWorker` runs in background:
   - Extract audio via FFmpeg (`audio_extractor.py`)
   - Load Whisper model
   - Transcribe → returns `SubtitleTrack`
3. `SubtitleTrack` is passed to `VideoPlayerWidget`, `TimelineWidget`, and `SubtitlePanel`
4. On `positionChanged`, `VideoPlayerWidget` queries `SubtitleTrack.segment_at(position_ms)` for current subtitle (O(log n) binary search)

**Whisper cancel:** Cancel closes the dialog immediately; transcription stops at the next segment boundary (~5s chunks via `chunk_length=5`).

### Time Units

All timestamps use **milliseconds (int)** internally. Conversion helpers in `src/utils/time_utils.py`.

**Frame-based editing** is supported via conversion functions:
- `ms_to_frame(ms, fps)` / `frame_to_ms(frame, fps)` - Convert between ms and frame numbers
- `snap_to_frame(ms, fps)` - Snap to nearest frame boundary
- Frame-based keyboard seek: `Shift+Left/Right` moves by 1 frame

**Timecode formats** supported in time edit dialogs:
- `MM:SS.mmm` - Minutes:Seconds.milliseconds (e.g., 01:23.456)
- `HH:MM:SS.mmm` - Hours:Minutes:Seconds.milliseconds (e.g., 00:01:23.456)
- `HH:MM:SS:FF` - Hours:Minutes:Seconds:Frames (e.g., 00:01:23:15)
- `F:123` or `frame:123` - Direct frame number

All timecode parsing is handled by `parse_flexible_timecode(text, fps)` which auto-detects the format.
