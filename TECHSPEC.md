# FastMovieMaker Technical Specification

**Version:** 0.1.0
**Platform:** Windows (primary), macOS/Linux (partial)
**Python:** 3.13
**Framework:** PySide6 (Qt 6)
**Last Updated:** 2026-02-09

---

## 1. Overview

FastMovieMaker is a desktop video subtitle editor combining AI-powered transcription (Whisper), text-to-speech synthesis (Edge-TTS / ElevenLabs), non-destructive video clip editing, and FFmpeg-based export into a single application.

### Core Capabilities

| Feature | Description |
|---------|-------------|
| Subtitle Editing | Multi-track segments with per-segment styling, volume, undo/redo |
| Whisper Transcription | GPU-accelerated speech-to-text (tiny ~ large models) |
| TTS Synthesis | Edge-TTS (free) + ElevenLabs (premium API) with audio merging |
| Video Clip Editing | Timeline-based cut/split/trim with multi-source video support |
| Export | Single/batch FFmpeg rendering with subtitle burn-in, audio mixing, PIP |
| Media Library | Persistent thumbnail browser with drag-to-timeline insertion |
| Image Overlays | Picture-in-Picture with drag/scale/opacity on video canvas |
| Waveform Display | Memory-efficient audio peak visualization on timeline |
| i18n | Korean / English UI localization |

---

## 2. Architecture

### 2.1 Three-Layer Design

```
src/
  models/      Pure Python dataclasses (no Qt dependency)
  services/    Business logic, FFmpeg/Whisper integration (no Qt)
  workers/     QObject-based background thread classes
  ui/          PySide6 widgets, dialogs, commands
  utils/       Configuration, i18n, time conversion, FFmpeg path detection
```

**Dependency rule:** `models` <- `services` <- `workers` / `ui`. Models never import Qt. Services never import Qt widgets.

### 2.2 Concurrency Model

Long-running operations use the **QObject + moveToThread** pattern:

```
MainWindow                        QThread
    |                                |
    | -- create Worker object -----> |
    | -- moveToThread(thread) -----> |
    | -- thread.start() -----------> |
    |                                | Worker.run() executes
    | <--- progress.emit(int,int) -- |
    | <--- finished.emit(result) --- |
    | -- thread.quit() / wait() ---> |
```

Worker classes: `WhisperWorker`, `ExportWorker`, `BatchExportWorker`, `TTSWorker`, `WaveformWorker`, `FrameCacheWorker`

### 2.3 Undo/Redo System

`QUndoStack` in MainWindow with `QUndoCommand` subclasses for every edit operation:

| Command | Target |
|---------|--------|
| `EditTextCommand` | Subtitle text change |
| `EditTimeCommand` | Subtitle start/end time change |
| `MoveSegmentCommand` | Subtitle timeline drag |
| `AddSegmentCommand` / `DeleteSegmentCommand` | Subtitle add/remove |
| `SplitCommand` / `MergeCommand` | Subtitle split/merge |
| `EditStyleCommand` | Per-segment style override |
| `EditVolumeCommand` | Per-segment volume |
| `AddVideoClipCommand` | Insert external video clip |
| `DeleteClipCommand` | Remove video clip |
| `SplitClipCommand` | Split video clip at playhead |
| `TrimClipCommand` | Trim clip left/right edge |

---

## 3. Data Models

### 3.1 Project State

```
ProjectState
  video_path: Path | None
  duration_ms: int
  subtitle_tracks: list[SubtitleTrack]   # multi-track
  active_track_index: int
  default_style: SubtitleStyle
  image_overlay_track: ImageOverlayTrack
  video_clip_track: VideoClipTrack | None
```

### 3.2 Subtitle Models

```
SubtitleSegment
  start_ms: int
  end_ms: int
  text: str
  style: SubtitleStyle | None   # per-segment override
  audio_file: str | None        # TTS audio path
  volume: float = 1.0           # 0.0 ~ 2.0

SubtitleTrack
  name: str
  language: str
  segments: list[SubtitleSegment]
  audio_path: str               # merged TTS audio
  audio_start_ms: int
  audio_duration_ms: int
```

### 3.3 Video Clip Models

```
VideoClip
  source_in_ms: int             # start in source video
  source_out_ms: int            # end in source video
  source_path: str | None       # None = primary video

VideoClipTrack
  clips: list[VideoClip]        # ordered playback sequence
```

**Time mapping:** Output timeline is the sequential concatenation of all clips. `timeline_to_source()` and `source_to_timeline()` convert between coordinate systems. `clip_timeline_start(idx)` returns clip start position on output timeline.

**Multi-source:** Clips can reference different video files. A `_NO_SOURCE_FILTER` sentinel distinguishes "no filter" from "primary video only" in `source_to_timeline()`.

**Playback tracking:** `_current_clip_index`로 재생 중인 클립을 추적. 시크 시 `clip_at_timeline()`으로 동기화, 경계 도달 시 자동 증가.

### 3.4 Style Model

```
SubtitleStyle
  font_family: str = "Arial"
  font_size: int = 18
  font_bold: bool = True
  font_italic: bool = False
  font_color: str = "#FFFFFF"
  outline_color: str = "#000000"
  outline_width: int = 1
  bg_color: str = ""
  position: str = "bottom-center"   # bottom-center | top-center | custom
  margin_bottom: int = 40
  custom_x: int | None
  custom_y: int | None
```

### 3.5 Image Overlay Model

```
ImageOverlay
  start_ms: int
  end_ms: int
  image_path: str
  x_percent: float              # 0.0 ~ 1.0 (relative position)
  y_percent: float
  scale_percent: float          # display scale
  opacity: float                # 0.0 ~ 1.0
```

### 3.6 Other Models

```
MediaItem              # Library entry: file_path, media_type, thumbnail_path, metadata
OverlayTemplate        # Predefined overlay: category (frame/watermark/lower_third)
ExportPreset           # Render preset: resolution, codec, container, audio_bitrate
BatchExportJob         # Job state: preset, output_path, status, progress_pct
```

---

## 4. Project File Format

**Extension:** `.fmm.json`
**Version:** 4
**Encoding:** UTF-8 (BOM-tolerant on read)

```json
{
  "version": 4,
  "video_path": "path/to/video.mp4",
  "duration_ms": 25300,
  "default_style": { ... },
  "active_track_index": 0,
  "tracks": [
    {
      "name": "Default",
      "language": "",
      "audio_path": "",
      "audio_start_ms": 0,
      "audio_duration_ms": 0,
      "segments": [
        {
          "start_ms": 0,
          "end_ms": 3000,
          "text": "Hello",
          "style": null,
          "audio_file": null,
          "volume": 1.0
        }
      ]
    }
  ],
  "image_overlays": [ ... ],
  "video_clips": [
    { "source_in_ms": 0, "source_out_ms": 4129 },
    { "source_in_ms": 0, "source_out_ms": 25301, "source_path": "extra.mp4" }
  ]
}
```

Backward compatible with v1-v3 (migration on load).

---

## 5. Services

### 5.1 Whisper Transcription

| Item | Detail |
|------|--------|
| Library | `openai-whisper` (faster-whisper) |
| Models | tiny, base, small, medium, large |
| GPU | CUDA float16 (auto-detect), CPU int8 fallback |
| Input | 16kHz mono WAV (extracted via FFmpeg) |
| Output | `SubtitleTrack` with timestamped segments |
| Default Language | Korean (`ko`) |

### 5.2 TTS Engines

**Edge-TTS** (free, no API key):
- Voices: Korean (SunHiNeural, InJoonNeural, HyunsuMultilingual), English (JennyNeural, AriaNeural, GuyNeural, ChristopherNeural)
- Rate control: `+0%` to `+100%`
- Async via `asyncio`

**ElevenLabs** (premium):
- REST API with API key authentication
- Voice ID selection, speed/stability controls
- Error handling: 401 (auth), 429 (rate limit)
- Returns audio duration metadata

**Pipeline:** Text splitting (sentence/word/char strategies) -> per-segment TTS -> audio merging with silence gaps -> optional mixing with video audio

### 5.3 Video Export

```
export_video(
  video_path, output_path,
  clips, subtitles, image_overlays,
  codec, resolution, audio_path, ...
)
```

**FFmpeg filter chain:**
- Multi-source: `_build_concat_filter()` generates per-clip trim + scale/pad + concat
- Subtitles: SRT temp file + `subtitles` filter
- PIP: `overlay` filter with time ranges
- Audio: `-filter_complex` for mixing tracks with volume control
- Codecs: H.264 (`libx264`), HEVC (`libx265`)
- Containers: MP4, MKV, WebM

### 5.4 Frame Cache

Pre-extracted JPEG thumbnails for instant preview during multi-source scrubbing:

```
<temp_dir>/
  <md5_hash_12char>/
    frame_000000000.jpg   (0ms)
    frame_000001000.jpg   (1000ms)
    ...
```

- Extraction: `ffmpeg -vf "fps=1,scale=640:-1" -q:v 5` (~30-50KB/frame)
- Lookup: Binary search on sorted filenames, O(log n)
- Lifecycle: Created per-session in temp dir, cleaned on exit

### 5.5 Waveform

Memory-efficient peak computation from WAV:
- 1-peak-per-millisecond resolution
- Chunk-based processing (~1 second chunks, ~128KB RAM)
- Output: `WaveformData(peaks_pos, peaks_neg)` normalized to [-1, 1]

### 5.6 Autosave & Recovery

- Timer-based: 30s interval (configurable)
- Idle timeout: 5s after last edit
- Recovery: Detects unclean shutdown, offers file selection dialog
- Recent files: QSettings-based MRU list
- Autosave dir: `~/.fastmoviemaker/autosave/`

---

## 6. UI Components

### 6.1 Main Window

`MainWindow(QMainWindow)` — Central orchestrator:
- Menu bar: File, Edit, Subtitle, Help
- Video player (left) + sidebar tabs (right: Subtitle, Media, Templates)
- Playback controls bar
- Timeline widget (bottom)
- Status bar with autosave indicator

### 6.2 Video Player

`VideoPlayerWidget(QGraphicsView)`:
- `QGraphicsVideoItem` at Z=0 (video)
- `QGraphicsPixmapItem` at Z=1 (cached frame preview)
- `QGraphicsTextItem` at Z=5 (subtitle overlay)
- Image overlays at Z=3 (PIP)
- Mouse interaction: subtitle position drag, PIP drag/scale

### 6.3 Timeline

`TimelineWidget(QWidget)` — Custom QPainter-based (with `resizeEvent` for zoom scaling):

```
Track layout (top to bottom):
  [Ruler]              Time ticks with labels
  [Video Clips]        Color-coded clip bars (cyan=primary, per-source colors)
  [Subtitles]          Segment bars with text labels
  [TTS Audio]          Audio track bar
  [Waveform]           Peak visualization
  [Image Overlays]     Overlay bars
```

**Interactions:**
- Click: seek to position
- Drag segment: move/resize (edge detection +-6px)
- Drag clip edge: trim left/right
- Scroll: pan view horizontally
- Ctrl+Scroll: zoom in/out
- Right-click: context menu (split clip, delete, add segment)

### 6.4 Subtitle Panel

`SubtitlePanel(QWidget)`:
- `QTableView` with virtual model (`_SubtitleTableModel(QAbstractTableModel)`)
- Columns: #, Start, End, Text, Volume
- Inline editing with undo/redo integration
- Context menu: Add, Delete, Split, Merge, Style
- Search bar integration (real-time filter/highlight)

### 6.5 Playback Controls

`PlaybackControls(QWidget)`:
- Play/Pause, Stop buttons
- Seek slider with time display + frame number
- Total duration label
- Volume slider + TTS volume slider
- **Output time mode:** When clip track exists, slider maps to output timeline (not source time)

### 6.6 Dialogs

| Dialog | Purpose |
|--------|---------|
| `WhisperDialog` | Model/language selection, progress bar |
| `TTSDialog` | Engine/voice selection, script input, preview |
| `ExportDialog` | Output path, resolution, codec, scale options |
| `BatchExportDialog` | Multi-preset table, output directory |
| `StyleDialog` | Font, color, position, margin pickers |
| `PreferencesDialog` | Autosave, FPS, language, API keys, theme |
| `TranslateDialog` | Target language, translation provider |
| `RecoveryDialog` | Crash recovery file selector |
| `JumpToFrameDialog` | Frame navigation |

### 6.7 Sidebar Panels

- `MediaLibraryPanel`: Thumbnail grid, filter buttons (All/Image/Video), drag-to-timeline, add/remove/favorite
- `TemplatesPanel`: Overlay template browser, category tabs, drag-to-apply

---

## 7. Signal Flow

### 7.1 Playback Position Update

```
QMediaPlayer.positionChanged(source_ms)
  -> MainWindow._on_player_position_changed()
    -> _current_clip_index로 현재 클립 결정
    -> if source_ms >= clip.source_out_ms - 30:
         다음 클립으로 전환 (_switch_player_source 또는 setPosition)
    -> clip_timeline_start(idx) + (source_ms - clip.source_in_ms)
      -> timeline_ms
    -> timeline.set_playhead(timeline_ms)
    -> controls.set_output_position(timeline_ms)
    -> video_widget._update_subtitle(timeline_ms)
```

**Clip index tracking:** `_current_clip_index`로 현재 재생 클립을 명시적 추적. `source_to_timeline()` 역매핑 대신 직접 계산하여, 같은 소스의 연속 클립 경계에서 건너뛰기 방지.

### 7.2 User Seek (Slider)

```
PlaybackControls.position_changed_by_user(timeline_ms)
  -> MainWindow._on_position_changed_by_user()
    -> clip_track.clip_at_timeline(timeline_ms)
      -> (idx, clip)
    -> source_ms = clip.source_in_ms + local_offset
    -> if different source: _switch_player_source(path, seek_ms, auto_play)
       else: player.setPosition(source_ms)
```

### 7.3 Source Switch (Multi-Video)

```
_switch_player_source(source_path, seek_ms, auto_play)
  -> [show cached frame if available]
  -> player.setSource(QUrl)          # async load starts
  -> _pending_seek_ms = seek_ms

QMediaPlayer.mediaStatusChanged(LoadedMedia)
  -> _on_media_status_changed()
    -> player.setPosition(seek_ms)
    -> if auto_play: player.play()
       else: player.play() + QTimer(50ms, pause)  # force frame render
    -> [hide cached frame]
```

### 7.4 Subtitle Edit

```
SubtitlePanel.text_committed(index, new_text)
  -> MainWindow: undo_stack.push(EditTextCommand(...))
    -> EditTextCommand.redo() -> segment.text = new_text
    -> undo_stack.indexChanged -> _on_document_edited() -> autosave
```

---

## 8. Theme & Styling

**Style engine:** Qt Fusion + custom QPalette + QSS

| Token | Color | Usage |
|-------|-------|-------|
| Base | `#1e1e1e` | Darkest background (inputs, lists) |
| Window | `#2d2d2d` | Default widget background |
| Controls | `#3a3a3a` | Buttons, combo boxes |
| Text | `#d4d4d4` | Primary text color |
| Accent | `#3c8cdc` | Selection, hover, highlights |
| Disabled | `#787878` | Grayed-out elements |

QSS file: `src/ui/styles/dark.qss`

---

## 9. Localization

Lightweight dict-based i18n system:

```python
# src/utils/i18n.py
init_language("ko")          # Load Korean strings
tr("menu_file")              # -> "파일(F)" (Korean) or "File" (English fallback)
current_language()           # -> "ko"
```

**Supported languages:**
- `en` — English (default, keys are English)
- `ko` — Korean (full translation in `src/utils/lang/ko.py`)

Extensible: add `src/utils/lang/{code}.py` with `STRINGS` dict.

---

## 10. File Structure

```
FastMovieMaker/
  main.py                         Entry point
  requirements.txt                Dependencies
  TECHSPEC.md                     This document
  PROGRESS.md                     Development progress tracker
  resources/
    icon.png                      App icon
    templates/                    Built-in overlay templates
  src/
    models/
      project.py                  ProjectState
      subtitle.py                 SubtitleSegment, SubtitleTrack
      style.py                    SubtitleStyle
      video_clip.py               VideoClip, VideoClipTrack
      image_overlay.py            ImageOverlay, ImageOverlayTrack
      media_item.py               MediaItem
      overlay_template.py         OverlayTemplate
      export_preset.py            ExportPreset, BatchExportJob
    services/
      whisper_service.py          Whisper AI transcription
      tts_service.py              Edge-TTS synthesis
      elevenlabs_tts_service.py   ElevenLabs API client
      video_exporter.py           FFmpeg export pipeline
      audio_extractor.py          WAV extraction for Whisper
      audio_merger.py             Audio concatenation/mixing
      audio_regenerator.py        TTS audio regeneration
      waveform_service.py         Peak computation
      frame_cache_service.py      JPEG frame thumbnail cache
      subtitle_exporter.py        SRT import/export
      text_splitter.py            Text segmentation strategies
      translator.py               Translation API client
      project_io.py               JSON project persistence (v4)
      media_library_service.py    Persistent media library
      settings_manager.py         QSettings wrapper
      style_preset_manager.py     Style preset CRUD
      template_service.py         Overlay template management
      autosave.py                 Auto-save & crash recovery
      video_probe.py              FFprobe metadata extraction
    workers/
      whisper_worker.py           Background transcription
      export_worker.py            Background single export
      batch_export_worker.py      Background batch export
      tts_worker.py               Background TTS generation
      waveform_worker.py          Background waveform computation
      frame_cache_worker.py       Background frame extraction
    ui/
      main_window.py              MainWindow (central orchestrator)
      video_player_widget.py      QGraphicsView video + overlays
      timeline_widget.py          Custom QPainter timeline
      subtitle_panel.py           Subtitle table + editing
      playback_controls.py        Play/seek/volume controls
      track_selector.py           Multi-track dropdown
      search_bar.py               Real-time subtitle search
      media_library_panel.py      Thumbnail grid browser
      templates_panel.py          Overlay template browser
      commands.py                 QUndoCommand subclasses
      styles/
        dark.qss                  Dark theme stylesheet
      dialogs/
        whisper_dialog.py         Whisper settings
        tts_dialog.py             TTS generation
        export_dialog.py          Export settings
        batch_export_dialog.py    Batch export
        style_dialog.py           Subtitle style editor
        preferences_dialog.py     App preferences
        translate_dialog.py       Translation
        recovery_dialog.py        Crash recovery
        jump_to_frame_dialog.py   Frame navigation
    utils/
      config.py                   App constants
      i18n.py                     Localization engine
      time_utils.py               Time conversion utilities
      ffmpeg_utils.py             FFmpeg/FFprobe path detection
      ffmpeg_bundled.py           Auto-download FFmpeg
      hw_accel.py                 Hardware acceleration detection
      lang/
        en.py                     English strings
        ko.py                     Korean strings
  tests/                          20 test modules, 336 test cases
```

---

## 11. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PySide6 | >= 6.7.0 | Qt 6 UI framework |
| openai-whisper | >= 20250625 | Speech-to-text transcription |
| torch | >= 2.3.0 | PyTorch (Whisper backend) |
| torchaudio | >= 2.3.0 | Audio processing for Whisper |
| edge-tts | >= 7.2.0 | Free TTS synthesis |
| pytest-qt | >= 4.5.0 | Qt widget testing |
| imageio-ffmpeg | >= 0.5.1 | Bundled FFmpeg fallback |

**Optional:** ElevenLabs API key for premium TTS.

**GPU:** PyTorch CUDA 12.4 (`pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124`)

---

## 12. Runtime Environment

| Item | Value |
|------|-------|
| Python | 3.13 (venv at `.venv/`) |
| FFmpeg | `E:\Python\Scripts\ffmpeg.exe` (configurable) |
| GPU | NVIDIA RTX 3080 (CUDA 12.4) |
| OS | Windows 10/11 |
| Data dir | `~/.fastmoviemaker/` |
| Temp cache | `%TEMP%/fmm_framecache_*` |

**Launch command:**
```
.venv/Scripts/python.exe main.py [optional_video_path]
```

---

## 13. Testing

- **Framework:** pytest + pytest-qt
- **Test count:** 326+ cases across 20 modules
- **Coverage:** Models, services, UI integration, export pipeline, i18n
- **Run:** `.venv/Scripts/python.exe -m pytest tests/ -v`
