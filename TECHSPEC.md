# FastMovieMaker Technical Specification

**Version:** 0.10.0
**Platform:** Windows (primary), macOS (Apple Silicon 지원)
**Python:** 3.13+ (3.14 테스트 완료)
**Framework:** PySide6 (Qt 6)
**Last Updated:** 2026-03-03

---

## 1. Overview

FastMovieMaker is a desktop video subtitle editor combining AI-powered transcription (Whisper), text-to-speech synthesis (Edge-TTS / ElevenLabs), non-destructive multi-track video clip editing, color correction, subtitle animation, and FFmpeg-based export into a single application.

### Core Capabilities

| Feature | Description |
|---------|-------------|
| Subtitle Editing | Multi-track segments with per-segment styling, volume, animation, undo/redo |
| Whisper Transcription | GPU-accelerated speech-to-text (tiny ~ large models) |
| TTS Synthesis | Edge-TTS (free) + ElevenLabs (premium API) with audio merging, batch TTS |
| Video Clip Editing | Timeline-based cut/split/trim with multi-source video support, ripple edit |
| Multi-Video Tracks | Layer compositing with blend modes (screen/multiply/lighten/darken) and chroma key |
| Color Correction | Per-clip brightness/contrast/saturation/hue with bulk apply |
| Subtitle Animation | Per-segment in/out effects (fade, slide, typewriter) with bulk apply |
| Export | Single/batch FFmpeg rendering with subtitle burn-in, audio mixing, PIP, export presets |
| Media Library | Persistent thumbnail browser with drag-to-timeline insertion |
| Image Overlays | Picture-in-Picture with drag/scale/opacity on video canvas |
| Waveform Display | Memory-efficient audio peak visualization on timeline |
| Timeline Markers | Named bookmarks with undo/redo |
| GPT Script Generation | OpenAI API-powered script draft for TTS |
| Scene Detection | FFmpeg-based automatic scene split detection |
| Project Templates | Built-in and user-defined project starting points |
| Crash Reporting | Unhandled exception capture with log file + clipboard copy |
| Deployment Packaging | PyInstaller .app (macOS) / .exe (Windows) build pipeline |
| i18n | Korean / English UI localization |

---

## 2. Architecture

### 2.1 Layered Design (Layered + Clean Architecture)

```
src/
  models/         Domain: Pure Python dataclasses (no Qt, no external deps)
  infrastructure/ External adapters: FFmpegRunner, ITranscriber (WhisperTranscriber)
  services/       Application: Business logic, uses infrastructure (no Qt widgets)
  workers/        QObject-based background thread classes
  ui/             Presentation: PySide6 widgets, dialogs, commands
    main_window_ui.py   UI 레이아웃 구성 (build_main_window_ui)
    main_window_menu.py 메뉴 구성 (build_main_window_menu)
    timeline_hit_test.py 타임라인 (x,y) 히트 테스트 (TimelineHitTester)
  utils/          Configuration, i18n, time conversion
```

**Dependency rule:** `models` <- `infrastructure` <- `services` <- `workers` / `ui`. Models never import Qt. Services use `FFmpegRunner`, `ITranscriber` instead of direct subprocess/faster-whisper calls.

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

Worker classes: `WhisperWorker`, `ExportWorker`, `BatchExportWorker`, `TTSWorker`, `WaveformWorker`, `FrameCacheWorker`, `VideoLoadWorker`, `ThumbnailRunnable`, `GptScriptWorker`, `SceneDetectWorker`, `TtsVerifyWorker`, `BatchTtsWorker`

**Thread safety notes:**
- `_cleanup_thread()`는 반드시 `quit()` → `wait()` 순서로 호출 (이벤트 루프 미종료 방지)
- Python 3.14에서 `import torch`는 QThread의 작은 C 스택(~512KB)에서 오버플로우 — 메인 스레드에서 사전 임포트 필수
- Whisper 취소: ctranslate2 C 연산은 중단 불가 → Cancel = 즉시 다이얼로그 닫기 + 스레드 백그라운드 자연 종료. `chunk_length=5`로 약 5초 단위 세그먼트 경계에서 취소 검사.
- 앱 종료 시 `QThreadPool.globalInstance().waitForDone()` 호출로 스레드 파괴 크래시 방지

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
| `AutoAlignSubtitlesCommand` | Auto-align overlapping subtitles |
| `WrapSubtitlesCommand` | Auto-wrap long subtitle lines |
| `EditColorLabelCommand` | Set clip color label |
| `EditColorCorrectionCommand` | Per-clip brightness/contrast/saturation/hue |
| `EditTrackBlendModeCommand` | Track blend mode / chroma key settings |
| `EditSubtitleAnimationCommand` | Per-segment animation in/out effects |
| `AddMarkerCommand` / `RemoveMarkerCommand` / `RenameMarkerCommand` | Timeline marker CRUD |
| `ApplyTTSVerificationCommand` | Apply Whisper-verified TTS timing corrections |
| `AddTransitionCommand` / `RemoveTransitionCommand` | Clip transition effects |
| `DeleteSelectedClipsCommand` | Bulk delete multiple selected clips (macro) |
| `BulkEditColorCommand` | Bulk color correction across track (macro) |
| `BulkEditAnimationCommand` | Bulk animation across selected subtitles (macro) |

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
  video_tracks: list[VideoClipTrack]     # multi-layer (index 0 = primary)
  text_overlay_track: TextOverlayTrack
  bgm_tracks: list[AudioTrack]
  markers: list[TimelineMarker]
```

**Backward compat:** `video_clip_track` property delegates to `video_tracks[0]`.

### 3.2 Subtitle Models

```
SubtitleSegment
  start_ms: int
  end_ms: int
  text: str
  style: SubtitleStyle | None   # per-segment override
  audio_file: str | None        # TTS audio path
  volume: float = 1.0           # 0.0 ~ 2.0
  animation: SubtitleAnimation | None

SubtitleAnimation
  in_effect: str   # "none" | "fade_in" | "slide_up" | "slide_down" | "typewriter"
  out_effect: str  # "none" | "fade_out" | "slide_up" | "slide_down"
  is_active: bool  # property: in_effect != "none" or out_effect != "none"

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
  speed: float = 1.0            # 0.25 ~ 4.0
  volume: float = 1.0
  volume_points: list[VolumePoint]
  brightness: float = 1.0       # 0.5 ~ 2.0
  contrast: float = 1.0         # 0.5 ~ 2.0
  saturation: float = 1.0       # 0.0 ~ 2.0
  hue: float = 0.0              # -180.0 ~ 180.0 (degrees)
  transition_out: TransitionInfo | None
  color_label: str = "none"     # none/red/orange/yellow/green/blue/purple/pink

VideoClipTrack
  clips: list[VideoClip]        # ordered playback sequence
  locked: bool = False
  muted: bool = False
  hidden: bool = False
  name: str = ""
  blend_mode: str = "normal"    # "normal"|"screen"|"multiply"|"lighten"|"darken"|"chroma_key"
  chroma_color: str = "#00FF00"
  chroma_similarity: float = 0.3
  chroma_blend: float = 0.1
```

**Time mapping:** Output timeline is the sequential concatenation of all clips. `timeline_to_source()` and `source_to_timeline()` convert between coordinate systems. `clip_timeline_start(idx)` returns clip start position on output timeline. `clip_boundaries_ms()` returns N+1 timestamps (start + final_end).

**Multi-source:** Clips can reference different video files. A `_NO_SOURCE_FILTER` sentinel distinguishes "no filter" from "primary video only" in `source_to_timeline()`.

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

### 3.6 Timeline Marker Model

```
TimelineMarker
  ms: int       # position on timeline
  label: str    # display name
```

### 3.7 Export Models

```
ExportPreset
  name: str
  width: int          # 0 = keep original
  height: int
  codec: str          # "h264" | "hevc"
  container: str      # "mp4" | "mkv" | "webm"
  audio_bitrate: str = "192k"
  crf: int = 23
  speed_preset: str = "medium"  # "fast" | "medium" | "slow"
  suffix: str = ""
  to_dict() / from_dict()

BatchExportJob
  preset: ExportPreset
  output_path: str
  status: str = "pending"   # pending | running | completed | failed | skipped
  error_message: str = ""
  progress_pct: int = 0
```

**DEFAULT_PRESETS:** 7개 내장 프리셋 (4K/1080p/720p/480p H.264, 1080p HEVC MP4/MKV, Original).

### 3.8 Other Models

```
MediaItem              # Library entry: file_path, media_type, thumbnail_path, metadata
OverlayTemplate        # Predefined overlay: category (frame/watermark/lower_third)
ProjectTemplate        # Project starting point: name, aspect_ratio, default_style preset
BatchTtsJob / Result   # Batch TTS job: file path, engine/voice settings, status
TextOverlay            # On-screen text with position, style, timing
AudioClip / AudioTrack # BGM track items with volume envelope, fade in/out
```

---

## 4. Project File Format

**Extension:** `.fmm.json` (또는 `.fmm`)
**Version:** 12
**Storage:** gzip-compressed binary (magic bytes `\x1f\x8b`); 기존 평문 JSON 자동 감지 하위호환
**Encoding:** UTF-8 (BOM-tolerant on read)

```json
{
  "version": 12,
  "video_path": "path/to/video.mp4",
  "duration_ms": 25300,
  "default_style": { "font_family": "Arial", "font_size": 18, "..." : "..." },
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
          "volume": 1.0,
          "animation": { "in_effect": "fade_in", "out_effect": "none" }
        }
      ]
    }
  ],
  "image_overlays": [],
  "video_tracks": [
    {
      "name": "Main",
      "blend_mode": "normal",
      "muted": false,
      "hidden": false,
      "clips": [
        {
          "source_in_ms": 0,
          "source_out_ms": 25301,
          "brightness": 1.1,
          "contrast": 1.0,
          "saturation": 1.2,
          "hue": 15.0,
          "color_label": "blue"
        }
      ]
    }
  ],
  "markers": [
    { "ms": 5000, "label": "Intro End" }
  ]
}
```

Backward compatible with v1–v11 (migration on load via `.get()` defaults).

**파일 크기:** gzip 압축으로 평문 JSON 대비 50-70% 감소.

---

## 5. Services

### 5.1 Whisper Transcription

| Item | Detail |
|------|--------|
| Library | `faster-whisper` (ctranslate2 backend) |
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

**Pipeline:** Text splitting (sentence/word/char strategies) → per-segment TTS → audio merging with silence gaps → optional mixing with video audio

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
- Color correction: `eq=brightness=:contrast=:saturation=` + `hue=h=` filter
- Blend modes: `blend` filter (`screen`/`multiply`/`lighten`/`darken`), chroma key: `chromakey`
- Transitions: `xfade` filter between consecutive clips
- Codecs: H.264 (`libx264`), HEVC (`libx265`)
- Containers: MP4, MKV, WebM

### 5.4 Export Preset Manager

`ExportPresetManager` (QSettings, Group: `"ExportPresets"`):
- 사용자 정의 프리셋 저장/로드/삭제/목록 조회
- 필드: name, width, height, codec, container, audio_bitrate, crf, speed_preset
- DEFAULT_PRESETS(7개)는 별도 관리 — `ExportPresetManager`에 저장되지 않음

### 5.5 Frame Cache

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

### 5.6 Waveform

Memory-efficient peak computation from WAV:
- 1-peak-per-millisecond resolution
- Chunk-based processing (~1 second chunks, ~128KB RAM)
- Output: `WaveformData(peaks_pos, peaks_neg)` normalized to [-1, 1]

### 5.7 Timeline Thumbnails

- **Service:** `TimelineThumbnailService`
- **Mechanism:** Async FFmpeg generation via `QThreadPool` + `ThumbnailRunnable`
- **Optimization:** "Double-SS" seeking (fast seek to keyframe + precise seek)
- **Caching:** LRU Cache (max 200 items) for instant reuse

### 5.8 Autosave & Recovery

- Timer-based: 30s interval (configurable)
- Idle timeout: 5s after last edit
- Recovery: Detects unclean shutdown, offers file selection dialog
- Recent files: QSettings-based MRU list
- Autosave dir: `~/.fastmoviemaker/autosave/`

### 5.9 GPT Script Generation

- `GptScriptService`: OpenAI ChatCompletion API를 사용하여 주제/톤에서 TTS 대본 생성
- `GptScriptWorker`: 백그라운드 QObject+moveToThread 패턴
- 지원 톤: Informative / Casual / Persuasive / Humorous

### 5.10 Scene Detection

- `SceneDetectionService`: FFmpeg `select` 필터로 씬 전환 감지
- `SceneDetectWorker`: 백그라운드 실행, 감지된 씬 타임스탬프 리스트 반환
- `SceneDetectDialog`: 민감도 슬라이더 + 결과 리스트 + "Apply Splits" 버튼

### 5.11 TTS Timing Verification

- `TtsVerifier.verify_and_align()`: Whisper로 TTS 오디오를 재전사 후 `difflib.SequenceMatcher`로 타이밍 보정
- 보정 결과를 `ApplyTTSVerificationCommand`(Undo/Redo)로 적용

### 5.12 Project Template Manager

- `TemplateManager`: 3종 내장 템플릿 (YT Shorts / Commentary / IG Reels) + 사용자 커스텀
- `apply_to_project()`: ProjectState에 기본 스타일/해상도/언어 적용

### 5.13 Crash Reporter

- `setup_excepthook()`: `sys.excepthook` 교체로 처리되지 않은 예외 캡처
- 크래시 로그 → `~/.fastmoviemaker/crash_reports/` (RotatingFileHandler 5MB×3)
- `CrashReportDialog`: 스택 트레이스 표시 + 클립보드 복사 + 로그 폴더 열기

---

## 6. UI Components

### 6.1 Main Window

`MainWindow(QMainWindow)` — Central orchestrator:
- Menu bar: File, Edit, Subtitle, Help
- Video player (left) + sidebar tabs (right: Subtitle, Media, Templates, History)
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
  [Video Clips]        Color-coded clip bars with filmstrip thumbnails
    [Track N...]       Additional video tracks (blend modes)
  [Subtitles]          Segment bars with text labels + animation badge (blue dot)
  [TTS Audio]          Audio track bar
  [Waveform]           Peak visualization
  [Image Overlays]     Overlay bars
  [BGM Tracks]         Background music clip bars
  [Text Overlays]      On-screen text overlay bars
  [Markers]            Named bookmarks on ruler
```

**Interactions:**
- Click: seek to position
- Drag segment: move/resize (edge detection ±6px)
- Drag clip edge: trim left/right
- Ctrl+Click: multi-select clips
- Shift+Click: range select clips
- Scroll: pan view horizontally
- Ctrl+Scroll: zoom in/out
- Right-click: context menu (split clip, delete, add segment, transitions, color correction, etc.)
- M key: add marker at playhead

### 6.4 Subtitle Panel

`SubtitlePanel(QWidget)`:
- `QTableView` with virtual model (`_SubtitleTableModel(QAbstractTableModel)`)
- Columns: #, Start, End, Text, Volume
- ExtendedSelection mode for bulk operations
- Inline editing with undo/redo integration
- Search bar integration (real-time filter/highlight)
- Animation badge: ForegroundRole + ToolTipRole per row

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
| `TTSDialog` | Engine/voice selection, script input, preview, presets |
| `ExportDialog` | Output path, resolution, codec, CRF, export presets, audio bitrate, container |
| `BatchExportDialog` | Multi-preset table, output directory |
| `StyleDialog` | Font, color, position, margin pickers, style presets |
| `PreferencesDialog` | Autosave, FPS, language, API keys, theme, shortcuts |
| `TranslateDialog` | Target language, translation provider |
| `RecoveryDialog` | Crash recovery file selector |
| `JumpToFrameDialog` | Frame navigation |
| `ColorCorrectionDialog` | Per-clip brightness/contrast/saturation/hue sliders |
| `SubtitleAnimationDialog` | Per-segment in/out effect picker |
| `TrackSettingsDialog` | Track blend mode + chroma key configuration |
| `SpeedDialog` | Clip playback speed (0.25x–4x) |
| `SceneDetectDialog` | FFmpeg scene detection + split preview |
| `GptScriptDialog` | GPT topic/tone input → generated script |
| `TtsVerifyDialog` | Whisper-based TTS timing verification |
| `BatchTtsDialog` | Batch TTS generation from multiple .txt files |
| `WelcomeDialog` | Recent projects + template cards on startup |
| `TemplatePickerDialog` | New project from template |
| `CrashReportDialog` | Unhandled exception display + log export |

### 6.7 Sidebar Panels

- `MediaLibraryPanel`: Thumbnail grid, filter buttons (All/Image/Video/Favorites), drag-to-timeline, add/remove/favorite
- `TemplatesPanel`: Overlay template browser, category tabs, drag-to-apply
- **History tab**: `QUndoView` showing full undo/redo stack

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
  pyproject.toml                  Project metadata (single-source version)
  FastMovieMaker.spec             PyInstaller spec
  build_macos.sh / build_windows.bat  Build scripts
  TECHSPEC.md                     This document
  PROGRESS.md                     Development progress tracker
  resources/
    icon.png                      App icon
    templates/                    Built-in overlay templates
  src/
    infrastructure/
      ffmpeg_runner.py    FFmpegRunner (run, run_async, run_ffprobe)
      transcriber.py      ITranscriber protocol, WhisperTranscriber
    models/
      project.py                  ProjectState
      subtitle.py                 SubtitleSegment, SubtitleTrack
      style.py                    SubtitleStyle
      video_clip.py               VideoClip, VideoClipTrack, TransitionInfo, VolumePoint
      image_overlay.py            ImageOverlay, ImageOverlayTrack
      text_overlay.py             TextOverlay, TextOverlayTrack
      audio.py                    AudioClip, AudioTrack (BGM)
      timeline_marker.py          TimelineMarker
      media_item.py               MediaItem
      overlay_template.py         OverlayTemplate
      project_template.py         ProjectTemplate
      export_preset.py            ExportPreset (crf/speed_preset/to_dict/from_dict), BatchExportJob
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
      timeline_thumbnail_service.py Async filmstrip generation
      subtitle_exporter.py        SRT/SMI import/export
      text_splitter.py            Text segmentation strategies
      translator.py               Translation API client
      project_io.py               JSON project persistence (v12)
      media_library_service.py    Persistent media library
      settings_manager.py         QSettings wrapper
      style_preset_manager.py     Style preset CRUD
      tts_preset_manager.py       TTS settings preset CRUD
      export_preset_manager.py    Export preset CRUD (NEW)
      template_service.py         Overlay template management
      template_manager.py         Project template management
      autosave.py                 Auto-save & crash recovery
      video_probe.py              FFprobe metadata extraction
      ducking_service.py          BGM auto-ducking during TTS playback
      ripple_edit_service.py      Ripple edit (cascade clip/subtitle shift)
      scene_detection_service.py  FFmpeg scene detection
      gpt_script_service.py       OpenAI GPT script generation
      tts_verifier.py             Whisper-based TTS timing verification
    workers/
      whisper_worker.py           Background transcription
      export_worker.py            Background single export
      batch_export_worker.py      Background batch export
      tts_worker.py               Background TTS generation
      waveform_worker.py          Background waveform computation
      frame_cache_worker.py       Background frame extraction
      video_load_worker.py        Async video loading
      gpt_script_worker.py        Background GPT script generation
      scene_detect_worker.py      Background scene detection
      tts_verify_worker.py        Background TTS verification
      batch_tts_worker.py         Background batch TTS generation
    ui/
      main_window.py              MainWindow (central orchestrator)
      video_player_widget.py      QGraphicsView video + overlays
      timeline_widget.py          Custom QPainter timeline
      timeline_painter.py         QPainter drawing helpers
      timeline_hit_test.py        Timeline (x,y) hit testing
      timeline_controller.py      Timeline interaction controller
      main_window_ui.py           UI layout builder
      main_window_menu.py         Menu builder
      subtitle_panel.py           Subtitle table + editing
      playback_controls.py        Play/seek/volume controls
      track_selector.py           Multi-track dropdown
      track_header_panel.py       Track name/mute/hide controls
      search_bar.py               Real-time subtitle search
      media_library_panel.py      Thumbnail grid browser
      templates_panel.py          Overlay template browser
      commands.py                 QUndoCommand subclasses
      controllers/
        clip_controller.py        Clip CRUD + bulk color/selection
        subtitle_controller.py    Subtitle CRUD + bulk animation
        media_controller.py       Media library operations
        playback_controller.py    Playback state management
      styles/
        dark.qss                  Dark theme stylesheet
      dialogs/
        whisper_dialog.py         Whisper settings
        tts_dialog.py             TTS generation
        export_dialog.py          Export settings + presets
        batch_export_dialog.py    Batch export
        style_dialog.py           Subtitle style editor
        preferences_dialog.py     App preferences + shortcuts
        translate_dialog.py       Translation
        recovery_dialog.py        Crash recovery
        jump_to_frame_dialog.py   Frame navigation
        color_correction_dialog.py Per-clip color correction
        subtitle_animation_dialog.py Subtitle in/out animation
        track_settings_dialog.py  Track blend mode / chroma key
        speed_dialog.py           Clip speed change
        scene_detect_dialog.py    Scene detection + splits
        gpt_script_dialog.py      GPT script generation
        tts_verify_dialog.py      Whisper TTS timing verification
        batch_tts_dialog.py       Batch TTS generation
        welcome_dialog.py         Startup welcome + recent projects
        crash_report_dialog.py    Crash report display
    utils/
      config.py                   App constants
      i18n.py                     Localization engine
      time_utils.py               Time conversion utilities
      ffmpeg_utils.py             FFmpeg/FFprobe path detection
      ffmpeg_bundled.py           Auto-download FFmpeg
      hw_accel.py                 Hardware acceleration detection
      resource_path.py            Resource path (frozen/dev env)
      logger.py                   RotatingFileHandler logger
      crash_reporter.py           sys.excepthook-based crash capture
      lang/
        en.py                     English strings
        ko.py                     Korean strings
  tests/                          35+ test modules, 744+ test cases
```

---

## 11. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PySide6 | >= 6.7.0 | Qt 6 UI framework |
| faster-whisper | >= 1.1.0 | Speech-to-text transcription |
| torch | >= 2.3.0 | PyTorch (Whisper backend) |
| torchaudio | >= 2.3.0 | Audio processing for Whisper |
| edge-tts | >= 7.2.0 | Free TTS synthesis |
| openai | >= 1.0.0 | GPT script generation |
| pytest-qt | >= 4.5.0 | Qt widget testing |
| imageio-ffmpeg | >= 0.5.1 | Bundled FFmpeg fallback |
| pyinstaller | >= 6.0 | Desktop app packaging |

**Optional:** ElevenLabs API key for premium TTS; OpenAI API key for GPT script generation.

**GPU:** PyTorch CUDA 12.4 (`pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124`)

---

## 12. Runtime Environment

| Item | Value |
|------|-------|
| Python | 3.13+ (3.14 테스트 완료, venv at `venv/`) |
| FFmpeg | macOS: `/opt/homebrew/bin/ffmpeg`, Windows: configurable |
| GPU | CUDA (Windows), MPS (Apple Silicon), CPU fallback |
| OS | macOS (Apple Silicon), Windows 10/11 |
| Data dir | `~/.fastmoviemaker/` |
| Temp cache | `%TEMP%/fmm_framecache_*` |

**Launch command:**
```
.venv/Scripts/python.exe main.py [optional_video_path]
```

---

## 13. Testing

- **Framework:** pytest + pytest-qt
- **Test count:** 744+ cases across 35+ modules
- **Coverage:** Models, services, UI integration, export pipeline, i18n, Whisper cancel/crash, controllers, export presets
- **Controller tests:** `tests/test_controllers.py` — AppContext 및 PlaybackController를 mock AppContext로 단위 테스트 (Qt 부담 최소)
- **Run:** `pytest tests/ -q --ignore=tests/test_tts_dialog_gui.py --ignore=tests/test_tts_ui_integration.py --ignore=tests/test_multi_source_playback.py`
- **GUI-only tests** (macOS Qt widget 초기화 이슈로 별도 실행): `test_tts_dialog_gui.py`, `test_tts_ui_integration.py`, `test_multi_source_playback.py`
