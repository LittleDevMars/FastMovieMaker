# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

FastMovieMaker is a video subtitle editor with Whisper-based automatic subtitle generation. Built with PySide6 (Qt) for the UI and OpenAI Whisper for speech-to-text transcription.

## Build & Run Commands

```powershell
# Install dependencies (CUDA 12.4 - adjust for your GPU)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt

# Run application
python main.py

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_models.py -v

# Run a specific test
pytest tests/test_models.py::TestSubtitleTrack::test_segment_at -v
```

## External Dependencies

- **FFmpeg**: Required for audio extraction. The app looks for it at `E:\Python\Scripts\ffmpeg.exe` or via system PATH. Update `src/utils/config.py` if your FFmpeg is elsewhere.
- **GPU Support**: Whisper uses CUDA if available, falls back to CPU.

## Architecture

### Three-Layer Separation

```
src/
├── models/     # Pure Python dataclasses (no Qt dependency)
├── services/   # Business logic (no Qt dependency)
├── workers/    # QThread workers bridging services to UI
├── ui/         # PySide6 widgets
└── utils/      # Config and utilities
```

Models and services are intentionally Qt-free for testability. Workers wrap services with Qt signals for background execution.

### Key Patterns

**Video Playback**: Uses `QGraphicsView` + `QGraphicsVideoItem` instead of `QVideoWidget` to enable subtitle text overlay via `QGraphicsTextItem` on the same scene.

**Background Transcription**: `WhisperWorker` uses the `moveToThread` pattern:
1. Create `QThread` and worker object
2. Move worker to thread via `moveToThread()`
3. Connect `thread.started` to `worker.run`
4. Worker emits signals (`progress`, `finished`, `error`) that are safely received on the main thread

**Timeline Widget**: Custom-painted with `QPainter`. Supports zoom (Ctrl+wheel), scroll (wheel), click-to-seek, and auto-follows playhead.

### Data Flow

1. User opens video → `MainWindow._load_video()` → `QMediaPlayer.setSource()`
2. Generate subtitles → `WhisperDialog` → `WhisperWorker` runs in background:
   - Extract audio via FFmpeg (`audio_extractor.py`)
   - Load Whisper model
   - Transcribe → returns `SubtitleTrack`
3. `SubtitleTrack` is passed to `VideoPlayerWidget`, `TimelineWidget`, and `SubtitlePanel`
4. On `positionChanged`, `VideoPlayerWidget` queries `SubtitleTrack.segment_at(position_ms)` for current subtitle

### Time Units

All timestamps use **milliseconds (int)** internally. Conversion helpers in `src/utils/time_utils.py`.
