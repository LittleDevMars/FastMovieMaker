# FastMovieMaker - 개발 진행 과정

## Phase 1 구현 상태

### 완료된 작업 (Step 1~6 모두 완료)

#### Step 1: 기반 구축
- [x] `requirements.txt` - 의존성 정의 (PySide6, openai-whisper, torch, torchaudio, ffmpeg-python)
- [x] `src/utils/config.py` - FFmpeg 경로, Whisper 모델 설정, UI 상수
- [x] `src/utils/time_utils.py` - ms_to_display, ms_to_srt_time, seconds_to_ms
- [x] `src/models/subtitle.py` - SubtitleSegment, SubtitleTrack 데이터클래스
- [x] `src/models/project.py` - ProjectState 상태 관리

#### Step 2: 비디오 재생
- [x] `main.py` - QApplication 런처, Fusion 스타일
- [x] `src/ui/main_window.py` - 메뉴바(File/Subtitles/Help), 레이아웃, QSettings 저장/복원
- [x] `src/ui/video_player_widget.py` - QGraphicsView + QGraphicsVideoItem 기반 플레이어
- [x] `src/ui/playback_controls.py` - 재생/정지, 시크바, 시간 표시, 볼륨 컨트롤

#### Step 3: 자막 오버레이
- [x] `video_player_widget.py`에 QGraphicsTextItem 자막 오버레이 구현
- [x] set_subtitle_track() 및 position 기반 자막 조회
- [x] 비디오 하단 중앙에 자막 자동 배치

#### Step 4: Whisper 백엔드
- [x] `src/services/audio_extractor.py` - FFmpeg로 16kHz mono WAV 추출
- [x] `src/services/whisper_service.py` - 모델 로딩(GPU/CPU 자동), 전사, VRAM 해제

#### Step 5: Whisper UI 통합
- [x] `src/workers/whisper_worker.py` - QThread moveToThread 패턴, progress 시그널
- [x] `src/ui/dialogs/whisper_dialog.py` - 모델/언어 선택, 진행률 바, 시작/취소

#### Step 6: 타임라인 & 패널
- [x] `src/ui/timeline_widget.py` - 커스텀 페인팅, 자막 블록 표시, 줌(Ctrl+휠)/스크롤, 클릭 시크, 플레이헤드 자동 스크롤
- [x] `src/ui/subtitle_panel.py` - QTableWidget 기반 자막 목록, 클릭 시 해당 위치로 시크
- [x] `src/services/subtitle_exporter.py` - SRT 파일 내보내기
- [x] 테스트 파일: `tests/test_models.py`, `tests/test_time_utils.py`, `tests/test_audio_extractor.py`

### 생성된 파일 목록

```
H:\MyProject\FastMovieMaker\
├── main.py
├── requirements.txt
├── PROGRESS.md
├── src/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── subtitle.py
│   │   └── project.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── audio_extractor.py
│   │   ├── whisper_service.py
│   │   └── subtitle_exporter.py
│   ├── workers/
│   │   ├── __init__.py
│   │   └── whisper_worker.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py
│   │   ├── video_player_widget.py
│   │   ├── playback_controls.py
│   │   ├── timeline_widget.py
│   │   ├── subtitle_panel.py
│   │   └── dialogs/
│   │       ├── __init__.py
│   │       └── whisper_dialog.py
│   └── utils/
│       ├── __init__.py
│       ├── time_utils.py
│       └── config.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_audio_extractor.py
    └── test_time_utils.py
```

### 다음에 해야 할 작업

1. **의존성 설치**:
   ```bash
   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
   pip install -r requirements.txt
   ```

2. **실행 테스트**:
   ```bash
   python main.py
   ```

3. **단위 테스트**:
   ```bash
   pytest tests/ -v
   ```

4. **검증 체크리스트**:
   - [ ] 앱 창이 정상적으로 뜨는지
   - [ ] File → Open Video로 MP4 로드 및 재생/시크 동작
   - [ ] Subtitles → Generate → Whisper 모델 선택 → 진행률 → 완료
   - [ ] 자막이 비디오 위에 오버레이 표시
   - [ ] 타임라인에 자막 블록 표시, 클릭 시 시크
   - [ ] 자막 패널 항목 클릭 시 해당 위치로 이동
   - [ ] File → Export SRT로 SRT 파일 저장

### 아키텍처 메모
- **3계층 분리**: models(순수 Python) / services(비즈니스 로직) / ui(PySide6)
- **QGraphicsView + QGraphicsVideoItem**: QVideoWidget 대신 사용하여 자막 오버레이 가능
- **Worker-moveToThread 패턴**: Whisper가 백그라운드에서 실행되어 UI 멈춤 없음
- **커스텀 TimelineWidget**: QPainter로 직접 그리기, 줌/스크롤/클릭시크 지원
