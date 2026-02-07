# FastMovieMaker - 개발 진행 과정

---

## 2026-02-07 (Day 1) 작업 요약

**Phase 1 전체 코드 구현 완료 + GitHub push**

- Step 1~6 전체 구현 (30개 파일, 1604줄)
- Git 초기화, `.gitignore` 작성
- GitHub CLI 설치 및 공개 레포 생성
- push 완료: https://github.com/LittleDevMars/FastMovieMaker

---

## 2026-02-08 (Day 2) 작업 요약

**macOS 환경 세팅 및 크로스 플랫폼 지원**

- 의존성 전체 설치 완료 (PySide6, torch, torchaudio, openai-whisper, ffmpeg-python)
- `python3 main.py` 실행 테스트 → 영상 로드 및 재생 확인 완료
- macOS/Windows 크로스 플랫폼 대응:
  - `main.py`: `QT_MEDIA_BACKEND`를 플랫폼별 자동 설정 (darwin/windows)
  - `src/utils/config.py`: FFmpeg 경로를 플랫폼별 자동 감지 (macOS: `/opt/homebrew/bin/ffmpeg`)
  - `AGENTS.md`: macOS/Windows 양쪽 빌드 가이드 업데이트
- Git push 완료

**Whisper 자막 생성 파이프라인 테스트**

- `audio_extractor.py`: `subprocess.CREATE_NO_WINDOW` macOS 호환성 수정 (Windows 전용 → 플랫폼 분기)
- Python SSL 인증서 설치 (Whisper 모델 다운로드용)
- Whisper tiny 모델 다운로드 및 전사 테스트 성공
  - 오디오 추출 (FFmpeg) → Whisper 전사 → SubtitleTrack 변환 파이프라인 정상 동작 확인

**전체 기능 테스트**

- UI에서 Whisper Generate 다이얼로그 자동 호출 테스트 → 정상 표시 확인 (모델/언어 선택, 프로그레스바)
- Whisper medium 모델 다운로드 완료 (1.42GB)
- SRT 내보내기/가져오기: round-trip 일치 확인
- 영상 내보내기 (자막 하드번):
  - Homebrew FFmpeg에 `libass` 미포함 → `homebrew-ffmpeg/ffmpeg` tap으로 재설치하여 해결
  - `video_exporter.py`: subtitles 필터 경로 이스케이프 macOS 분기 처리 수정
  - 자막 하드번 영상 내보내기 성공

**End-to-end 테스트 (실제 음성 영상)**

- edge-tts로 한국어 음성 TTS 영상 생성 → Whisper tiny 모델 전사
- 4개 자막 세그먼트 정확 인식 (안녕하세요 / 자막 테스트 영상 / FastMovieMaker / 정상 생성 확인)
- 자막 패널, 타임라인 블록, 비디오 오버레이 모두 정상 표시

**자막 편집 기능 테스트**

- 텍스트 수정 (더블클릭 인라인 편집): 성공
- 시간 조정 (start/end 변경): 성공
- 세그먼트 추가/삭제: 성공
- 편집 후 SRT 내보내기: 성공
- 타임라인/패널 동기화: 성공

**검증 결과:**
- [x] 앱 창이 정상적으로 뜨는지
- [x] 커맨드라인 인자로 MP4 로드 및 재생 동작
- [x] 타임라인에 재생 헤드 표시 및 이동
- [x] Whisper 자막 생성 파이프라인 (오디오 추출 → 모델 로드 → 전사 → SubtitleTrack)
- [x] UI에서 Subtitles → Generate 다이얼로그 표시
- [x] 실제 음성 영상 end-to-end (TTS → Whisper → 오버레이)
- [x] 자막 편집 (텍스트 수정, 시간 조정, 추가/삭제)
- [x] SRT 내보내기/가져오기 (round-trip 정상)
- [x] 영상 내보내기 (자막 하드번)
- [x] `pytest tests/ -v` 단위 테스트: 20/20 passed (0.03s)

**다음 세션 TODO:**
1. ~~Phase 3 기능 구현 시작~~ → Day 3에서 완료

---

## 2026-02-08 (Day 3) 작업 요약

**Phase 3 전체 구현 완료**

### Step 1: 다크 테마 + 키보드 단축키
- `main.py`: QPalette 기반 다크 테마 (`_apply_dark_theme()`) - Fusion 스타일
- `main_window.py`: 키보드 단축키 바인딩
  - `Space` - 재생/일시정지 토글
  - `Ctrl+O/S/Z/Shift+Z/G/E` - 파일/편집 단축키
  - `Left/Right` - 5초 시크
  - `Delete` - 선택된 자막 삭제

### Step 2: 자막 스타일 데이터 모델
- 신규: `src/models/style.py` - `SubtitleStyle` dataclass (폰트, 색상, 위치 등)
- `SubtitleSegment`에 `style: SubtitleStyle | None` 필드 추가
- `SubtitleTrack`에 `name: str` 필드 추가

### Step 3: 프로젝트 I/O v2
- `project_io.py`: PROJECT_VERSION = 2
  - 스타일 직렬화/역직렬화 (`_style_to_dict`, `_dict_to_style`)
  - 멀티트랙 저장/로드
  - v1 → v2 자동 마이그레이션

### Step 4: 비디오 플레이어 스타일 렌더링
- `video_player_widget.py`: `_get_effective_style()`, `_apply_style()`
  - QGraphicsDropShadowEffect으로 아웃라인 효과
  - position 옵션에 따른 자막 배치 (top/bottom, left/center/right)

### Step 5: 자막 스타일 다이얼로그
- 신규: `src/ui/dialogs/style_dialog.py` - `StyleDialog`
  - QFontComboBox, QColorDialog, 미리보기 패널
  - 기본 스타일: Subtitles → Default Style...
  - 개별 세그먼트: 우클릭 → Edit Style...

### Step 6: Undo/Redo (QUndoStack)
- 신규: `src/ui/commands.py` - 8개 QUndoCommand 서브클래스
  - EditTextCommand, EditTimeCommand, AddSegmentCommand, DeleteSegmentCommand
  - MoveSegmentCommand, EditStyleCommand, SplitCommand, MergeCommand, BatchShiftCommand
- Edit 메뉴: Undo (`Ctrl+Z`), Redo (`Ctrl+Shift+Z`)

### Step 7: 고급 편집 - Split/Merge/Batch Shift
- **Split**: 재생 위치에서 선택된 자막을 둘로 분할
- **Merge**: 연속 2개 자막을 하나로 합침
- **Batch Shift**: 모든 자막 타이밍을 ±N ms 일괄 이동
- 모든 편집이 QUndoStack Command로 래핑

### Step 8-9: 멀티트랙
- `ProjectState`: `subtitle_tracks: list[SubtitleTrack]`, `active_track_index: int`
- `active_subtitle_track` 프로퍼티로 하위 호환성 유지
- 신규: `src/ui/track_selector.py` - QComboBox + 추가/삭제/이름 변경 버튼
- File 메뉴: "Import SRT to New Track..." 추가

### 테스트
- `pytest tests/ -v`: **36/36 passed** (기존 20 + 신규 16)
- 신규 테스트:
  - `test_models.py`: SubtitleStyle, 멀티트랙, style 할당 테스트
  - `test_project_io.py`: v2 roundtrip, 멀티트랙 roundtrip, 세그먼트 스타일, v1 마이그레이션

### 검증 체크리스트
- [x] 다크 테마 적용
- [x] 키보드 단축키 바인딩
- [x] SubtitleStyle 모델 + 복사
- [x] 프로젝트 v2 저장/로드 + v1 호환
- [x] 비디오 플레이어 스타일 렌더링
- [x] 스타일 다이얼로그 (기본 + 개별)
- [x] Undo/Redo 시스템
- [x] Split/Merge/Batch Shift
- [x] 멀티트랙 데이터 모델
- [x] 멀티트랙 UI (TrackSelector)
- [x] 단위 테스트 36/36 passed

**다음 세션 TODO:**
1. ~~GUI 통합 테스트 (실행하여 전체 기능 수동 검증)~~ → Day 3에서 완료
2. ~~Phase 4 계획 논의~~ → Phase 4 구현 시작

---

## 2026-02-08 (Day 3 - 계속) 작업 요약

**Phase 4 Week 1-2 구현 완료**

### MKV 파일 지원
- MKV 파일 로딩 시 자동 MP4 변환 (macOS AVFoundation 미지원 대응)
- `main_window.py`: FFmpeg 기반 변환 (`_convert_to_mp4()`) + QProgressDialog

### 윈도우 크기 조정
- 기본 윈도우 크기: 1100x700 → 1440x900
- 비디오 위젯 최소 크기: 640x360
- 스플리터 사이즈 명시 설정

### Phase 4 Week 1: Professional Workflow
- **신규:** `src/services/autosave.py` - AutoSaveManager
  - 30초 간격 자동 저장
  - 5초 idle timeout (편집 후 5초 뒤 저장)
  - Recovery 파일 관리 (`~/.fastmoviemaker/autosave/`)
  - Recent files 리스트 관리 (최대 10개)
- **신규:** `src/ui/dialogs/recovery_dialog.py` - RecoveryDialog
  - 앱 시작 시 복구 파일 감지 → 복원/삭제 선택
- **File 메뉴:** Recent Projects 서브메뉴 추가
- **Drag & Drop:** 비디오/SRT/프로젝트 파일 드래그 앤 드롭 지원
- **신규:** `src/ui/search_bar.py` - SearchBar 위젯
  - 자막 텍스트 검색 (대소문자 구분 옵션)
  - 검색 결과 카운터 및 네비게이션 (Next/Previous)
- **subtitle_panel.py:** SearchBar 통합
  - `Ctrl+F` - 검색창 표시
  - `F3` / `Shift+F3` - 다음/이전 결과
  - `Escape` - 검색 닫기
  - 검색 결과 하이라이트 (라이트 블루 배경)
  - 검색 결과 클릭 시 자동 시크

### Phase 4 Week 2: Translation & Settings
- **신규:** `src/services/translator.py` - TranslatorService
  - 3가지 번역 엔진 지원: DeepL API, GPT-4o-mini, Google Translate
  - 배치 번역 + 속도 제한 (rate limiting)
  - 언어 코드 매핑 (ISO_639_1_CODES, DEEPL_LANGUAGE_CODES)
- **신규:** `src/ui/dialogs/translate_dialog.py` - TranslateDialog
  - Source/Target 언어 선택
  - 번역 엔진 선택 + API 키 입력/저장
  - 프로그레스바 + 미리보기
  - 옵션: 새 트랙 생성 vs 현재 트랙 교체
- **main_window.py:** Subtitles 메뉴에 "Translate Track..." 추가
- **신규:** `src/services/settings_manager.py` - SettingsManager
  - QSettings 래퍼 (type-safe 환경 설정 관리)
  - 일반 설정 (autosave interval/idle, recent files max, default language)
  - 편집 설정 (default subtitle duration, snap tolerance, frame FPS)
  - 고급 설정 (FFmpeg path, Whisper cache directory)
  - API 키 설정 (DeepL, OpenAI)
  - UI 설정 (theme)
- **신규:** `src/ui/dialogs/preferences_dialog.py` - PreferencesDialog
  - 4개 탭: General / Editing / Advanced / API Keys
  - QTabWidget 기반 환경 설정 UI
  - 실시간 설정 로드/저장 (QSettings 동기화)
- **main_window.py:** Edit 메뉴에 "Preferences..." 추가 (`Ctrl+,`)
- **translate_dialog.py:** SettingsManager 사용으로 마이그레이션 (QSettings 직접 호출 제거)

### Git Commits
1. Phase 3 전체 구현 (78cfece)
2. Phase 4 Week 1 기능 (4bce445)
3. Phase 4 Week 2 Translation (8115f02)

### 검증
- [x] MKV 파일 자동 변환 및 로드
- [x] 윈도우 크기 적절히 조정
- [x] Autosave + Recovery 동작
- [x] Recent Projects 메뉴 표시
- [x] Drag & Drop 파일 로드
- [x] 자막 검색 (Ctrl+F, F3/Shift+F3)
- [x] 번역 다이얼로그 표시 및 API 키 저장
- [x] Preferences 다이얼로그 표시 및 설정 저장
- [x] `python3 main.py` 실행 정상 (import 에러 없음)

### 버그 수정
- **MKV 오디오 재생 문제 해결**
  - 문제: 5.1/7.1 서라운드 오디오가 MacBook 스피커에서 재생 안 됨
  - 원인: FFmpeg 변환 시 멀티채널 오디오가 스테레오로 다운믹스되지 않음
  - 해결: `-ac 2` 옵션 추가로 모든 오디오를 스테레오로 강제 변환
  - 영향: MKV, AVI, FLV 등 모든 변환 포맷에 적용

**다음 TODO:**
1. Phase 4 Week 2 나머지: 자막 스타일 프리셋
2. Phase 4 Week 3: Timecode 정밀 편집, Waveform, Batch Export, 키보드 커스터마이징

---

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
