# FastMovieMaker

> 🎬 AI 기반 자막 생성 및 편집을 지원하는 전문 비디오 에디터

**FastMovieMaker**는 멀티 소스 비디오 편집, Whisper 기반 자동 자막 생성, AI 텍스트 음성 변환(TTS) 등 고급 기능을 갖춘 데스크톱 자막 편집 프로그램입니다.

[![Python](https://img.shields.io/badge/Python-3.13%2B-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.10-green.svg)](https://pypi.org/project/PySide6/)
[![Tests](https://img.shields.io/badge/tests-414%20passing-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## ✨ 주요 기능

### 🎯 AI 기반 자막 생성
- **Faster-Whisper 통합** — CTranslate2 최적화로 최대 4배 빠른 음성 인식
- 여러 Whisper 모델 지원 (tiny, base, small, medium, large)
- 실시간 변환 진행률 표시 및 취소 지원

### 🎞️ 멀티 소스 비디오 편집
- **고급 타임라인** — 서로 다른 비디오 파일의 클립을 자유롭게 배치 (A→B→A 패턴 등)
- **필름스트립 썸네일** — 비디오 클립 내 연속된 썸네일 표시로 직관적인 편집
- 커스텀 QPainter 타임라인 위젯으로 프레임 단위 정밀 편집
- 끊김 없는 클립 간 자동 소스 전환
- **414개의 유닛 테스트**로 검증된 견고한 재생 시스템
- **GPU 가속 인코딩** — NVENC, QSV, AMF 내보내기 가속 지원
- **스마트 화면 비율 조정** — 9:16 (Shorts/Reels) 템플릿 적용 시 자막 레이아웃 자동 최적화
- **자석 스냅 (Magnetic Snap)** — 클립 이동 시 인접 클립 및 플레이헤드에 자동 정렬 (Toggle: `S`)
- **타임라인 썸네일** — 비디오 트랙에 연속된 썸네일(필름스트립) 표시로 시각적 편집 강화
- **BGM 트랙 및 오디오 믹싱** — 독립적인 BGM 트랙 관리, 트리밍, 자석 스냅 및 볼륨 제어 지원 (Day 18)

### ⚡️ 성능 및 안정성
- **알고리즘 최적화** — 핵심 모델 조회(`segment_at`, `clip_at_timeline`, `overlays_at`)를 O(log n) 이진 탐색으로 교체
- **NumPy 벡터화 렌더링** — 타임라인 웨이브폼 픽셀별 Python 루프를 NumPy 배열 연산으로 치환
- **메모리 최적화** — 전 데이터클래스 `__slots__` 적용, `@lru_cache` 메모이제이션, LRU 캐시 관리
- **HW 가속 미디어 임포트** — MKV→MP4 변환 시 VideoToolbox(macOS)/NVENC(Windows) 자동 활용
- **프록시 미디어 (Proxy Media)** — 고해상도(4K 등) 영상의 부드러운 편집을 위한 저해상도 프록시 자동 생성 및 전환 기능
- **MKV 지원 (macOS)** — macOS 환경에서 MKV 파일의 자동 프록시 변환 및 재생 지원
- **재생 동기화 개선** — 스크럽, 분할(Split) 후 재생 재개 시 끊김 없는 경험 제공
- **스레드 안전성** — `MediaController(QObject)` 기반으로 worker→UI signal이 메인 스레드에서만 실행됨

### 🎨 전문적인 비디오 미리보기
- **비동기 비디오 로드** — 대용량 파일도 즉시 로딩 (UI 멈춤 없음)
- **비디오 필터 (Video Filters)** — 클립별 밝기(Brightness), 대비(Contrast), 채도(Saturation) 실시간 조절 및 수출 적용
- **프레임 캐시 시스템** — FFmpeg 프레임 추출을 통한 즉각적인 스크럽 미리보기
- **광범위한 자막 지원** — SRT 뿐만 아니라 SMI 자막 파일 가져오기 지원
- 커스터마이징 가능한 실시간 자막 오버레이
- 이미지 오버레이(PIP) 지원 및 위치/크기 조절
- QSS 스타일링이 적용된 다크 테마 UI

### 🔊 AI 텍스트 음성 변환 (TTS)
- **다양한 TTS 엔진:**
  - Edge-TTS (Microsoft Azure 음성)
  - ElevenLabs API 통합
- 세그먼트별 TTS 생성 및 오디오 믹싱
- 비디오 및 TTS 오디오 개별 볼륨 제어
- **AI 자막 번역** — Google/GPT 엔진 연동을 통한 자동 자막 번역 및 트랙 관리

### 🎬 영상 전환 효과 (Transitions) - 신규! (v0.9.5)
- **시각적 효과:** `xfade` 기반의 다양한 전환 (Fade, Wipe, Slide, Dissolve, Pixelize 등)
- **오디오 크로스페이드:** `acrossfade`를 통한 자연스러운 소리 연결
- **직관적 편집:** 타임라인 우클릭 메뉴 및 전용 설정 다이얼로그 제공
- **자동 리플:** 전환 길이 수정 시 뒤따르는 클립과 요소들을 자동으로 이동 (Ripple Edit)

### ✍️ 독립 텍스트 오버레이 - 신규! (v0.3.0)
- **자막과 독립적인 텍스트 레이어** — 자막과 별개로 타이틀, 캡션, 워터마크 등 추가
- **완전한 스타일 제어** — 폰트, 크기, 색상, 투명도, 위치 자유롭게 설정
- **텍스트 정렬 지원** — 가로(좌/우/중앙) 및 세로(상/하/중앙) 정렬 기준(Anchor) 설정 가능
- **인터랙티브 드래그** — 플레이어 화면에서 마우스 드래그로 텍스트 위치 직관적 조정
- **실시간 미리보기** — 비디오 플레이어에서 텍스트 오버레이 실시간 렌더링
- **FFmpeg 통합** — `drawtext` 필터를 통한 고품질 텍스트 렌더링 및 내보내기
- **Undo/Redo 지원** — 텍스트 추가/편집/삭제/이동 작업 완벽 지원


### 🌍 국제화 (I18n)
- **완전한 다국어 지원** — 한국어 및 영어 지원
- 런타임 언어 전환이 가능한 로케일 인식 UI
- 포괄적인 번역 커버리지

### 📦 내보내기 및 가져오기
- **유연한 내보내기:**
  - SRT 자막 파일
  - 자막이 입혀진(Burned-in) 비디오 배치 렌더링
  - 커스텀 해상도 프리셋 (1080p, 720p, 480p)
- **프로젝트 관리:**
  - `.fmm.json` 프로젝트 파일 저장/불러오기
  - 백업 시스템을 포함한 자동 저장
  - QUndoStack을 이용한 실행 취소/다시 실행

### 🔧 안정성 개선 (v0.9.7)
- **아키텍처 개선 (Layered + Clean Architecture):**
  - `infrastructure/` 계층 도입 — `FFmpegRunner`, `ITranscriber` 프로토콜로 외부 의존성 추상화
  - 모든 서비스에서 직접 `subprocess` 호출 제거 → `FFmpegRunner` 통합
- **Whisper 자막 생성 안정화:**
  - Python 3.14 호환 — QThread C 스택 오버플로우 해결 (메인 스레드 사전 임포트)
  - 취소 즉시 반영 — Cancel 버튼 클릭 시 다이얼로그 즉시 닫힘 (스레드 백그라운드 종료)
  - 모델 로딩 중 취소 지원 — `load_model()` 후 취소 상태 체크 추가
- **QThread 크래시 방지:**
  - `_cleanup_thread()`에 `quit()` 호출 추가 (이벤트 루프 미종료 버그 수정)
  - 앱 종료 시 `QThreadPool.waitForDone()` 안전망 추가
  - 강제 닫기 시 고아 스레드 참조 보관 (GC 파괴 방지)
- **타임라인 드래그 수정:**
  - 자막 세그먼트 이동/리사이즈 드래그 복원 (`_start_drag` 메서드 누락 수정)

### ⚡ 성능 최적화 및 리팩토링 (v0.9.8)

#### 📐 알고리즘 최적화 (CLRS 기반)
- **O(log n) 이진 탐색** — `segment_at()`, `clip_at_timeline()`, `overlays_at()` 등 핵심 조회를 `bisect` 기반 이진 탐색으로 교체 (기존 O(n) 선형 스캔)
- **접두사 합(Prefix Sum)** — `VideoClipTrack`의 타임라인 위치 계산을 접두사 합 배열로 최적화, `clip_timeline_start()` O(1) 조회
- **정렬 삽입** — `add_segment()`, `add_overlay()`, `add_clip()` 등에 `bisect.insort` 적용 (기존 append+sort O(n log n) → O(n))
- **자석 스냅** — `apply_snap()`의 후보 탐색을 O(log k) 이진 탐색으로 개선

#### 🚀 High-Performance Python 최적화
- **`__slots__` 적용** — 모든 모델 데이터클래스(`SubtitleSegment`, `VideoClip`, `ImageOverlay` 등 12개)에 메모리 효율 및 속성 접근 가속
- **`@lru_cache` 메모이제이션** — `ms_to_display()`, `ms_to_srt_time()`, `ms_to_frame()`, `frame_to_ms()` 등 빈번 호출 함수 캐싱
- **NumPy 벡터화** — 타임라인 웨이브폼 렌더링의 Python 루프를 NumPy 배열 연산으로 교체 (60fps 타임라인 스크롤 성능 대폭 개선)
- **LRU 캐시 관리** — `TimelineWaveformService`(메모리) 및 `FrameCacheService`(디스크) 무한 증가 방지를 위한 LRU 정리 정책 도입
- **로컬 변수 캐싱** — 타임라인 페인팅 핫루프 내 `self.tw._xxx` 속성 조회를 로컬 변수로 캐싱
- **문자열 연결 최적화** — FFmpeg 필터 그래프 빌드의 `str +=` 패턴을 `list.append()` + `"".join()`으로 교체

#### 🔧 아키텍처 리팩토링
- **MVC 컨트롤러 분리** — `MainWindow`(3200행)에서 7개 컨트롤러 모듈로 분리:
  - `MediaController` — 비디오 로드/프록시/웨이브폼/프레임캐시/BGM
  - `PlaybackController` — 재생/시크/클립 전환
  - `SubtitleController` — 자막 편집/생성/번역
  - `ClipController` — 비디오 클립 편집/분할/전환
  - `OverlayController` — 이미지/텍스트 오버레이
  - `ProjectController` — 프로젝트 저장/불러오기/내보내기
  - `AppContext` — 공유 상태 컨테이너
- **타임라인 위젯 분리** — `TimelineWidget`(2100행)에서 드래그/페인팅 로직 분리:
  - `TimelineDragManager` — 모든 드래그 핸들링 로직
  - `TimelinePainter` — 모든 페인팅/렌더링 로직

#### 🛡️ 스레드 안전성 수정
- **`MediaController(QObject)` 변환** — non-QObject signal→slot 연결 시 DirectConnection으로 GUI 코드가 워커 스레드에서 실행되던 크래시 해결
- **비디오 임포트 store-and-process 패턴** — `progress.exec()` 반환 후 메인 스레드에서 안전하게 GUI 업데이트
- **MKV→MP4 변환 HW 가속** — Remux → VideoToolbox/NVENC → libx264 3단계 폴백 전략 ([상세 문서](docs/HARDWARE_ACCELERATION.md))

---

## 🏗️ 아키텍처

### Layered + Clean Architecture (MVC)
```
src/
├── models/              # 순수 Python 데이터 모델 (Qt 종속성 없음, __slots__ 적용)
│   ├── project.py
│   ├── subtitle.py       # bisect 기반 O(log n) 탐색
│   ├── video_clip.py     # 접두사 합 기반 타임라인 계산
│   ├── image_overlay.py
│   ├── text_overlay.py
│   └── style.py
├── infrastructure/      # 외부 어댑터 (FFmpeg, Whisper 추상화)
│   ├── ffmpeg_runner.py     # FFmpeg/FFprobe 실행 통합
│   └── transcriber.py       # ITranscriber 프로토콜 + WhisperTranscriber
├── services/            # 비즈니스 로직 (infrastructure 사용, Qt 무관)
│   ├── whisper_service.py
│   ├── tts_service.py
│   ├── video_exporter.py
│   ├── frame_cache_service.py  # LRU 디스크 캐시
│   └── timeline_waveform_service.py  # LRU 메모리 캐시
├── workers/             # QThread 백그라운드 워커
│   ├── whisper_worker.py
│   ├── tts_worker.py
│   ├── video_load_worker.py  # HW 가속 변환 (3단계 폴백)
│   └── frame_cache_worker.py
├── utils/               # 유틸리티 (@lru_cache 메모이제이션)
│   ├── config.py
│   ├── time_utils.py
│   └── hw_accel.py       # HW 인코더 자동 탐지
└── ui/                  # PySide6 UI 컴포넌트
    ├── main_window.py       # 얇은 셸 (이벤트 바인딩만)
    ├── controllers/         # MVC 컨트롤러 (v0.9.8)
    │   ├── app_context.py       # 공유 상태 컨테이너
    │   ├── media_controller.py  # QObject 기반 — 스레드 안전
    │   ├── playback_controller.py
    │   ├── subtitle_controller.py
    │   ├── clip_controller.py
    │   ├── overlay_controller.py
    │   └── project_controller.py
    ├── timeline_widget.py   # 레이아웃/이벤트 핸들러
    ├── timeline_painter.py  # NumPy 벡터화 렌더링
    ├── timeline_drag.py     # bisect 기반 자석 스냅
    ├── video_player_widget.py
    └── dialogs/
```

**의존성 규칙:** `models` ← `infrastructure` ← `services` ← `workers` / `ui`

### 기술적 특징
- **Worker-moveToThread 패턴** — Whisper/TTS 작업을 위한 논블로킹 백그라운드 처리
- **QObject 기반 컨트롤러** — `MediaController(QObject)` 상속으로 worker signal→slot 자동 `QueuedConnection` 보장
- **커스텀 QPainter 타임라인** — 줌/스크롤을 지원하는 프레임 단위 비디오 편집 (NumPy 벡터화 웨이브폼)
- **멀티 소스 재생 시스템:**
  - 명시적인 `_current_clip_index` 추적 (모호한 소스→타임라인 매핑 방지)
  - 자동 전환을 위한 클립 경계 감지 (30ms 임계값)
  - 즉각적인 스크럽 미리보기를 위한 프레임 캐시 통합
- **알고리즘 최적화:** 이진 탐색(CLRS Ch.2.3), 접두사 합(CLRS Ch.15), `bisect.insort`로 핵심 조회 O(log n)
- **출력 시간 모드(Output Time Mode)** — A→B→A 등 복합 클립 전반에 걸친 통합 타임라인 동기화

---

## 🚀 설치 방법

### 요구 사항
- **Python 3.13+** (3.9+ 지원)
- **FFmpeg** (비디오 처리에 필수)
- **NVIDIA GPU** (선택 사항, CUDA 가속 Whisper 사용 시)

### 설정
```bash
# 저장소 복제
git clone https://github.com/yourusername/FastMovieMaker.git
cd FastMovieMaker

# 가상환경 생성
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 의존성 설치
pip install -r requirements.txt

# PyTorch 및 CUDA 지원 설치 (선택 사항, GPU 가속용)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

# 애플리케이션 실행
python main.py
```

### FFmpeg 설치
- **Windows:** [ffmpeg.org](https://ffmpeg.org/download.html)에서 다운로드 후 PATH에 추가
- **Linux:** `sudo apt install ffmpeg`
- **Mac:** `brew install ffmpeg`

---

## 🧪 테스트

### 포괄적인 테스트 스위트
```bash
# 전체 테스트 실행 (29개 모듈에 걸친 414개 테스트 케이스)
pytest tests/ -v

# 주요 테스트 모듈:
pytest tests/test_multi_source_playback.py -v   # 멀티 소스 재생 (43개)
pytest tests/test_time_utils.py -v               # 시간 변환 (46개)
pytest tests/test_video_clip.py -v               # 비디오 클립 (44개)
pytest tests/test_cancel_crash.py -v             # 취소 크래시 방지 (8개)
pytest tests/test_whisper_cancel.py -v           # Whisper 취소 (3개)
pytest tests/test_whisper_integration.py -v      # Whisper 통합 (5개)
```

---

## 🛠️ 기술 스택

| 분류 | 기술 |
|----------|-----------|
| **언어** | Python 3.13+ (3.14 테스트 완료) |
| **GUI 프레임워크** | PySide6 6.10 (Qt 6.10) |
| **비디오 처리** | FFmpeg, opencv-python |
| **AI/ML** | OpenAI Whisper, PyTorch 2.6 (CUDA 12.4) |
| **TTS** | Edge-TTS, ElevenLabs API |
| **테스트** | pytest, pytest-qt |
| **국제화** | 커스텀 번역 시스템 |

---

## 📖 사용 방법

### 기본 워크플로우
1. **비디오 로드** — 드래그 앤 드롭 또는 파일 → 비디오 열기
2. **자막 생성:**
   - 옵션 A: 자막 → Whisper로 생성
   - 옵션 B: 자막 → 스크립트로 생성 (TTS)
3. **타임라인 편집:**
   - 다른 소스의 비디오 클립 추가
   - 세그먼트를 드래그하여 자막 타이밍 조절
   - 자막 테이블에서 텍스트 편집
4. **내보내기:**
   - 파일 → 내보내기 → SRT 파일
   - 파일 → 내보내기 → 배치 내보내기 (자막 하드코딩 영상)

### 📚 상세 가이드
- **[TTS 사용 가이드 (한국어)](docs/TTS_USAGE.md)**
- **[TTS Usage Guide (English)](docs/TTS_USAGE_EN.md)**

### 멀티 소스 비디오 편집 예시
```python
# 예: A(0-10초) → B(0-5초) → A(10-20초) 타임라인 구성
from src.models.video_clip import VideoClip, VideoClipTrack

track = VideoClipTrack(clips=[
    VideoClip(0, 10000),               # A: 0-10s
    VideoClip(0, 5000),                # B: 0-5s (외부 소스)
    VideoClip(10000, 20000),           # A: 10-20s
])
track.clips[1].source_path = "path/to/video_b.mp4"

# 총 출력 길이: 25초 (10 + 5 + 10)
```

---

## 🎯 로드맵

- [x] Whisper 변환 중 실시간 자막 미리보기 (v0.9.6)
- [ ] 커스텀 TTS 제공자를 위한 플러그인 시스템
- [ ] 클라우드 프로젝트 동기화 (협업 편집)
- [ ] 오디오 더킹 (Audio Ducking) 고도화

---

## 📝 라이선스

MIT 라이선스 - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

---

## 🙏 감사의 글

- [OpenAI Whisper](https://github.com/openai/whisper) — 음성 인식 모델
- [PySide6](https://pypi.org/project/PySide6/) — Qt for Python
- [FFmpeg](https://ffmpeg.org/) — 비디오 처리
- [Edge-TTS](https://github.com/rany2/edge-tts) — Microsoft Azure TTS

---

## 🤝 기여하기

기여는 언제나 환영합니다!
1. 저장소 포크 (Fork)
2. 기능 브랜치 생성 (`git checkout -b feature/amazing-feature`)
3. 변경 사항 커밋 (`git commit -m 'Add amazing feature'`)
4. 브랜치에 푸시 (`git push origin feature/amazing-feature`)
5. Pull Request 생성

### 개발 환경 설정
```bash
# 개발 의존성 설치
pip install pytest pytest-qt black ruff

# 커밋 전 테스트 실행
pytest tests/ -v

# 코드 포맷팅
black src/ tests/
ruff check src/ tests/
```

---

## 💬 연락처

- **이슈:** [GitHub Issues](https://github.com/yourusername/FastMovieMaker/issues)
- **토론:** [GitHub Discussions](https://github.com/yourusername/FastMovieMaker/discussions)

---

<div align="center">
Made with ❤️ by [Your Name]
</div>
