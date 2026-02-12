# FastMovieMaker

> 🎬 Professional Video Subtitle Editor with AI-Powered Transcription

**FastMovieMaker** is a desktop application for creating, editing, and exporting video subtitles with advanced features like multi-source video editing, automatic transcription via Whisper, and AI-powered text-to-speech.

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.10-green.svg)](https://pypi.org/project/PySide6/)
[![Tests](https://img.shields.io/badge/tests-43%20passing-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## ✨ Key Features

### 🎯 AI-Powered Subtitle Generation
- **Faster-Whisper Integration** — Optimized speech recognition with CTranslate2 (up to 4x faster)
- Support for multiple Whisper models (tiny, base, small, medium, large)
- Real-time transcription progress with cancel support

### 🎞️ Multi-Source Video Editing
- **Advanced Timeline** — Combine clips from different video files (A→B→A patterns)
- Frame-accurate editing with custom QPainter timeline widget
- Seamless clip boundary transitions with automatic source switching
- **43 comprehensive unit tests** ensuring rock-solid multi-source playback
- **Smart Aspect Ratio Adaptation** — Subtitles automatically adjust layout for 9:16 (Shorts/Reels) templates

### 🎨 Professional Video Preview
- **Frame Cache System** — Instant scrub preview with FFmpeg-extracted frames
- Real-time subtitle overlay with customizable styles
- Image overlay support (PIP) with position/scale controls
- Dark theme UI with QSS styling

### 🔊 AI Text-to-Speech
- **Multiple TTS Engines:**
  - Edge-TTS (Microsoft Azure voices)
  - ElevenLabs API integration
- Per-segment TTS generation and audio mixing
- Independent volume controls for video and TTS audio

### 🌍 Internationalization
- **Full i18n Support** — Korean (한국어) and English
- Locale-aware UI with runtime language switching
- Comprehensive translation coverage

### 📦 Export & Import
- **Flexible Export:**
  - SRT subtitle files
  - Batch video rendering with subtitles burned-in
  - Custom resolution presets (1080p, 720p, 480p)
- **Project Management:**
  - Save/load `.fmm.json` project files
  - Auto-save with backup system
  - Undo/redo support with QUndoStack

---

## 🏗️ Architecture

### Clean 3-Layer Design
```
src/
├── models/          # Pure Python data models (Qt-independent)
│   ├── project.py
│   ├── subtitle.py
│   ├── video_clip.py
│   └── style.py
├── services/        # Business logic (FFmpeg, Whisper, TTS)
│   ├── ffmpeg_service.py
│   ├── whisper_service.py
│   ├── tts_service.py
│   └── frame_cache_service.py
├── workers/         # QThread background workers
│   ├── whisper_worker.py
│   ├── tts_worker.py
│   ├── waveform_worker.py
│   └── frame_cache_worker.py
└── ui/              # PySide6 UI components
    ├── main_window.py
    ├── timeline_widget.py
    ├── video_player_widget.py
    └── playback_controls.py
```

### Technical Highlights
- **Worker-moveToThread Pattern** — Non-blocking background processing for Whisper/TTS
- **Custom QPainter Timeline** — Frame-accurate video editing with zoom/scroll
- **Multi-Source Playback System:**
  - Explicit `_current_clip_index` tracking (no ambiguous source→timeline mapping)
  - Clip boundary detection (30ms threshold) for auto-transition
  - Frame cache integration for instant scrub preview
- **Output Time Mode** — Unified timeline→slider synchronization across A→B→A clips

---

## 🚀 Installation

### Requirements
- **Python 3.13+** (3.9+ supported with `from __future__ import annotations`)
- **FFmpeg** (required for video processing)
- **NVIDIA GPU** (optional, for CUDA-accelerated Whisper)

### Setup
```bash
# Clone repository
git clone https://github.com/yourusername/FastMovieMaker.git
cd FastMovieMaker

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Install PyTorch with CUDA support (optional, for GPU acceleration)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

# Run application
python main.py
```

### FFmpeg Installation
- **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
- **Linux:** `sudo apt install ffmpeg`
- **Mac:** `brew install ffmpeg`

---

## 🧪 Testing

### Comprehensive Test Suite
```bash
# Run all tests (326+ test cases across 20 modules)
pytest tests/ -v

# Run multi-source playback tests (43 test cases)
pytest tests/test_multi_source_playback.py -v

# Test categories:
# - Scrub source switching
# - Play/pause race conditions
# - Media status handling
# - Position changed events
# - Scrub→play scenarios
# - Play button sync
# - Clip boundary crossing
# - Timeline/slider sync
# - Edge cases (short clips, rapid transitions, etc.)
```

---

## 🛠️ Tech Stack

| Category | Technology |
|----------|-----------|
| **Language** | Python 3.13 |
| **GUI Framework** | PySide6 6.10 (Qt 6.10) |
| **Video Processing** | FFmpeg, opencv-python |
| **AI/ML** | OpenAI Whisper, PyTorch 2.6 (CUDA 12.4) |
| **TTS** | Edge-TTS, ElevenLabs API |
| **Testing** | pytest, pytest-qt |
| **I18n** | Custom translation system |

---

## 📖 Usage

### Basic Workflow
1. **Load Video** — Drag & drop or File → Open Video
2. **Generate Subtitles:**
   - Option A: Subtitle → Generate from Whisper
   - Option B: Subtitle → Generate from Script (TTS)
3. **Edit Timeline:**
   - Add video clips from different sources
   - Adjust subtitle timing by dragging segments
   - Edit text in the subtitle table
4. **Export:**
   - File → Export → SRT File
   - File → Export → Batch Export (burned-in subtitles)

### 📚 Detailed Guides
- **[TTS Usage Guide (한국어)](docs/TTS_USAGE.md)** — 텍스트 음성 변환 상세 가이드
- **[TTS Usage Guide (English)](docs/TTS_USAGE_EN.md)** — Comprehensive TTS tutorial

### Multi-Source Video Editing
```python
# Example: A(0-10s) → B(0-5s) → A(10-20s) timeline
from src.models.video_clip import VideoClip, VideoClipTrack

track = VideoClipTrack(clips=[
    VideoClip(0, 10000),               # A: 0-10s
    VideoClip(0, 5000),                # B: 0-5s (external source)
    VideoClip(10000, 20000),           # A: 10-20s
])
track.clips[1].source_path = "path/to/video_b.mp4"

# Total output duration: 25 seconds (10 + 5 + 10)
```

---

## 🎯 Roadmap

- [ ] Real-time subtitle preview during Whisper transcription
- [ ] GPU-accelerated video rendering
- [ ] Plugin system for custom TTS providers
- [ ] Collaborative editing (cloud project sync)
- [ ] Subtitle translation with AI (DeepL/GPT integration)

---

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) — Speech recognition model
- [PySide6](https://pypi.org/project/PySide6/) — Qt for Python
- [FFmpeg](https://ffmpeg.org/) — Video processing
- [Edge-TTS](https://github.com/rany2/edge-tts) — Microsoft Azure TTS

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup
```bash
# Install dev dependencies
pip install pytest pytest-qt black ruff

# Run tests before committing
pytest tests/ -v

# Format code
black src/ tests/
ruff check src/ tests/
```

---

## 💬 Contact

- **Issues:** [GitHub Issues](https://github.com/yourusername/FastMovieMaker/issues)
- **Discussions:** [GitHub Discussions](https://github.com/yourusername/FastMovieMaker/discussions)

---

<div align="center">
Made with ❤️ by [Your Name]
</div>
