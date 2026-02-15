# FastMovieMaker Documentation

Welcome to the FastMovieMaker documentation! This directory contains guides and tutorials for using the application.

## 📚 Available Guides

### User Guides
- **[TTS Usage Guide (한국어)](TTS_USAGE.md)** — 텍스트 음성 변환 기능 사용 가이드
  - Edge-TTS 및 ElevenLabs 설정 방법
  - 대본 작성 및 음성 생성
  - 비디오 오디오 믹싱
  - 문제 해결 및 팁

- **[TTS Usage Guide (English)](TTS_USAGE_EN.md)** — Comprehensive text-to-speech tutorial
  - Edge-TTS and ElevenLabs setup
  - Script writing and voice generation
  - Video audio mixing
  - Troubleshooting and tips

### Technical Guides
- **[Hardware Acceleration Guide](HARDWARE_ACCELERATION.md)** — 하드웨어 가속 인코딩 가이드
  - VideoToolbox (macOS), NVENC (Windows/Linux), QSV (Intel) 지원
  - MKV→MP4 변환 시 자동 HW 가속 활용
  - 3단계 폴백 전략 (Remux → HW 인코딩 → SW 폴백)

## 🚀 Quick Start

### For Beginners
1. Read the main [README](../README.md) for installation instructions
2. Follow the Basic Workflow section to get started
3. Refer to specific guides above for advanced features

### For Advanced Users
- Check out the [Architecture section](../README.md#-architecture) in main README
- Review [test cases](../tests/) for usage examples
- Explore the source code in [src/](../src/)

## 🔗 External Resources

- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
- [PySide6 Documentation](https://doc.qt.io/qtforpython-6/)
- [OpenAI Whisper GitHub](https://github.com/openai/whisper)
- [Edge-TTS GitHub](https://github.com/rany2/edge-tts)
- [ElevenLabs API Docs](https://elevenlabs.io/docs)

## 📝 Contributing to Docs

If you'd like to improve these docs:
1. Fork the repository
2. Add or update documentation in this directory
3. Submit a Pull Request with your changes

---

<div align="center">
Questions? <a href="https://github.com/yourusername/FastMovieMaker/issues">Open an issue</a> on GitHub!
</div>
