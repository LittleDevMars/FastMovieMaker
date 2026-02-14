# FastMovieMaker

> 🎬 AI 기반 자막 생성 및 편집을 지원하는 전문 비디오 에디터

**FastMovieMaker**는 멀티 소스 비디오 편집, Whisper 기반 자동 자막 생성, AI 텍스트 음성 변환(TTS) 등 고급 기능을 갖춘 데스크톱 자막 편집 프로그램입니다.

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.10-green.svg)](https://pypi.org/project/PySide6/)
[![Tests](https://img.shields.io/badge/tests-43%20passing-brightgreen.svg)](tests/)
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
- **43개의 유닛 테스트**로 검증된 견고한 재생 시스템
- **스마트 화면 비율 조정** — 9:16 (Shorts/Reels) 템플릿 적용 시 자막 레이아웃 자동 최적화
- **자석 스냅 (Magnetic Snap)** — 클립 이동 시 인접 클립 및 플레이헤드에 자동 정렬 (Toggle: `S`)
- **타임라인 썸네일** — 비디오 트랙에 연속된 썸네일(필름스트립) 표시로 시각적 편집 강화

### ⚡️ 성능 및 안정성
- **최적화된 탐색** — 썸네일 생성 및 미리보기 시 프레임 캐싱 고도화로 지연 시간 최소화
- **프록시 미디어 (Proxy Media)** — 고해상도(4K 등) 영상의 부드러운 편집을 위한 저해상도 프록시 자동 생성 및 전환 기능
- **MKV 지원 (macOS)** — macOS 환경에서 MKV 파일의 자동 프록시 변환 및 재생 지원
- **재생 동기화 개선** — 스크럽, 분할(Split) 후 재생 재개 시 끊김 없는 경험 제공

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

### 🔧 최근 안정성 개선 (v0.9.2)
- **멀티 트랙 리팩토링 리그레션 수정:**
  - `TimelineWidget` 초기화 오류 해결 (`_project`, `_clip_track` 속성 누락)
  - `AddVideoClipCommand` 시그니처 불일치 수정
  - 썸네일 서비스 API 호출 오류 수정 (`request_thumbnail` 사용)
  - 동적 Y 좌표 계산 메서드 추가 (웨이브폼, 이미지 오버레이)
  - `VideoClip` 라벨 렌더링 로직 개선 (파일명 기반 표시)

---

## 🏗️ 아키텍처

### 깔끔한 3계층 설계
```
src/
├── models/          # 순수 Python 데이터 모델 (Qt 종속성 없음)
│   ├── project.py
│   ├── subtitle.py
│   ├── video_clip.py
│   └── style.py
├── services/        # 비즈니스 로직 (FFmpeg, Whisper, TTS)
│   ├── ffmpeg_service.py
│   ├── whisper_service.py
│   ├── tts_service.py
│   └── frame_cache_service.py
├── workers/         # QThread 백그라운드 워커
│   ├── whisper_worker.py
│   ├── tts_worker.py
│   ├── waveform_worker.py
│   └── frame_cache_worker.py
└── ui/              # PySide6 UI 컴포넌트
    ├── main_window.py
    ├── timeline_widget.py
    ├── video_player_widget.py
    └── playback_controls.py
```

### 기술적 특징
- **Worker-moveToThread 패턴** — Whisper/TTS 작업을 위한 논블로킹 백그라운드 처리
- **커스텀 QPainter 타임라인** — 줌/스크롤을 지원하는 프레임 단위 비디오 편집
- **멀티 소스 재생 시스템:**
  - 명시적인 `_current_clip_index` 추적 (모호한 소스→타임라인 매핑 방지)
  - 자동 전환을 위한 클립 경계 감지 (30ms 임계값)
  - 즉각적인 스크럽 미리보기를 위한 프레임 캐시 통합
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
# 전체 테스트 실행 (20개 모듈에 걸친 326개 이상의 테스트 케이스)
pytest tests/ -v

# 멀티 소스 재생 테스트 실행 (43개 테스트 케이스)
pytest tests/test_multi_source_playback.py -v

# 테스트 범주:
# - 스크럽 시 소스 전환
# - 재생/일시정지 레이스 컨디션
# - 미디어 상태 처리
# - 위치 변경 이벤트
# - 스크럽→재생 시나리오
# - 재생 버튼 동기화
# - 클립 경계 교차
# - 타임라인/슬라이더 동기화
# - 엣지 케이스 (짧은 클립, 빠른 전환 등)
```

---

## 🛠️ 기술 스택

| 분류 | 기술 |
|----------|-----------|
| **언어** | Python 3.13 |
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

- [ ] Whisper 변환 중 실시간 자막 미리보기
- [ ] GPU 가속 비디오 렌더링
- [ ] 커스텀 TTS 제공자를 위한 플러그인 시스템
- [ ] 클라우드 프로젝트 동기화 (협업 편집)
- [ ] AI 기반 자막 번역 (DeepL/GPT 연동)

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
