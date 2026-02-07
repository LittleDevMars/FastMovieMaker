# FastMovieMaker - 개발 진행 과정

---

## 2026-02-08 (Day 6) 작업 요약

**TTS (Text-to-Speech) 음성 생성 기능 구현 완료**

### 구현 내용

#### 1. 핵심 서비스 구현 (Day 1)
- **신규:** `src/services/text_splitter.py` - 대본 분할 서비스
  - 3가지 분할 전략: SENTENCE (문장 단위), NEWLINE (줄바꿈), FIXED_LENGTH (고정 길이)
  - 문장 경계 인식 (마침표, 물음표, 느낌표)
  - 단어 경계 존중 (고정 길이 분할 시)
  - 한국어/영어 다국어 지원

- **신규:** `src/services/tts_service.py` - edge-tts 통합 서비스
  - `generate_speech()` - 단일 텍스트 음성 생성
  - `generate_segments()` - 배치 음성 생성 (진행률 콜백)
  - `list_voices()` - 사용 가능한 음성 목록 조회
  - `format_rate()` - 속도 배율 → edge-tts rate 문자열 변환
  - 비동기 처리 (asyncio/await)
  - 타임아웃 설정 (기본 30초)

- **신규:** `src/services/audio_merger.py` - FFmpeg 오디오 병합/믹싱
  - `get_audio_duration()` - FFprobe로 오디오 길이 측정
  - `merge_audio_files()` - 여러 오디오 파일 concat
  - `mix_audio_tracks()` - 두 오디오 트랙 믹싱 (볼륨 조절)
  - `has_audio_stream()` - 오디오 스트림 존재 확인
  - 오디오 없는 비디오 처리 (TTS만 반환)

- **신규:** `src/utils/ffmpeg_utils.py` - FFmpeg/FFprobe 경로 찾기
  - `find_ffmpeg()` - ffmpeg 실행 파일 경로
  - `find_ffprobe()` - ffprobe 실행 파일 경로
  - 플랫폼별 경로 처리 (macOS/Windows)

- **개선:** `src/utils/config.py` - TTS 설정 추가
  - `TTS_DEFAULT_VOICE`, `TTS_DEFAULT_RATE`, `TTS_DEFAULT_SPEED`
  - `TTS_VOICES` - 언어/성별별 음성 목록 (한국어/영어)

- **개선:** `requirements.txt` - edge-tts>=7.2.0 추가

#### 2. Worker + Dialog 구현 (Day 2)
- **신규:** `src/workers/tts_worker.py` - TTS 백그라운드 워커
  - QThread 기반 비동기 실행
  - 대본 분할 → TTS 생성 → 병합 → 믹싱 → 자막 트랙 생성 파이프라인
  - 진행률 시그널 (current/total 세그먼트)
  - Cancel 기능
  - 임시 파일 자동 정리
  - 생성된 오디오를 `~/.fastmoviemaker/`에 영구 저장

- **신규:** `src/ui/dialogs/tts_dialog.py` - TTS 설정 다이얼로그
  - 대본 입력 (QPlainTextEdit, 여러 줄 지원)
  - 언어 선택 (한국어/영어)
  - 음성 선택 (성별별 음성 목록)
  - 속도 조절 (0.5x ~ 2.0x)
  - 분할 전략 선택 (문장/줄바꿈/고정 길이)
  - 볼륨 조절 (배경 오디오 + TTS 오디오)
  - 진행률 표시 (QProgressBar)
  - 에러 처리 (QMessageBox)

- **개선:** `src/ui/main_window.py` - TTS 메뉴 통합
  - Subtitles → "Generate &Speech (TTS)..." 메뉴 추가 (Ctrl+T)
  - `_on_generate_tts()` 핸들러 구현
  - 비디오 로드 확인
  - FFmpeg 확인
  - 생성된 트랙을 멀티트랙에 추가
  - 상태바 메시지 표시

#### 3. 테스트
- **신규:** `tests/test_text_splitter.py` - 11개 텍스트 분할 테스트
  - 빈 텍스트, 공백 처리
  - 문장 분할 (영어/한국어)
  - 줄바꿈 분할 (빈 줄 무시)
  - 고정 길이 분할 (단어 경계 존중)
  - 에러 처리

- **통합 테스트:** `test_tts_integration.py` (스크래치패드)
  - 대본 분할 → TTS 생성 → 병합 → 자막 트랙 생성 전체 워크플로우
  - 3개 한국어 문장 (10.42초 오디오 생성)
  - 오디오 믹싱 (배경 없는 비디오 처리 확인)

- **전체 테스트:** `pytest tests/ -v` → **96/96 passed**
  - 기존 85개 + 신규 11개
  - 0.13초 실행
  - 회귀 없음

### 기술 세부사항

#### TTS 워크플로우
```
사용자 대본 입력
    ↓
TextSplitter: 문장/줄바꿈/고정 길이로 분할
    ↓
TTSService: 각 세그먼트마다 edge-tts 음성 생성
    ↓
AudioMerger: 모든 세그먼트 오디오 병합 (concat)
    ↓
AudioMerger: 비디오 오디오와 믹싱 (볼륨 조절)
    ↓
SubtitleTrack 생성 (오디오 길이 기반 타이밍)
    ↓
프로젝트에 새 트랙으로 추가
```

#### 오디오 믹싱 전략
- **기본:** 배경 오디오 50%, TTS 오디오 100%
- **UI 조절:** 다이얼로그에서 각 트랙 볼륨 조절 가능 (0.0-1.0)
- **오디오 없는 비디오:** TTS 오디오만 반환 (shutil.copy2)

#### 타이밍 정확성
- FFprobe로 각 세그먼트 오디오 길이 정밀 측정 (초 단위)
- 밀리초 단위로 SubtitleSegment 생성
- 순차적 누적으로 정확한 타이밍 보장

### 수정/생성된 파일

**생성 (9개):**
1. `src/services/text_splitter.py` - 대본 분할 (183줄)
2. `src/services/tts_service.py` - edge-tts 통합 (164줄)
3. `src/services/audio_merger.py` - FFmpeg 병합/믹싱 (212줄)
4. `src/utils/ffmpeg_utils.py` - FFmpeg/FFprobe 경로 (32줄)
5. `src/workers/tts_worker.py` - TTS 워커 (184줄)
6. `src/ui/dialogs/tts_dialog.py` - TTS 다이얼로그 (283줄)
7. `tests/test_text_splitter.py` - 텍스트 분할 테스트 (108줄)
8. `scratchpad/test_tts.py` - 단위 테스트 스크립트
9. `scratchpad/test_tts_integration.py` - 통합 테스트 스크립트

**수정 (3개):**
1. `src/utils/config.py` - TTS 설정 추가
2. `src/ui/main_window.py` - TTS 메뉴 및 핸들러
3. `requirements.txt` - edge-tts 추가

**총 코드량:** 약 1,166줄 추가

### 검증
- [x] edge-tts 설치 및 음성 목록 조회
- [x] 한국어/영어 TTS 생성 테스트
- [x] 대본 분할 (3가지 전략)
- [x] 오디오 병합 (FFmpeg concat)
- [x] 오디오 믹싱 (볼륨 조절)
- [x] 오디오 없는 비디오 처리
- [x] 자막 트랙 생성 (정확한 타이밍)
- [x] 단위 테스트 96/96 passed
- [x] 통합 테스트 통과
- [x] 기존 기능 회귀 없음

### 수동 GUI 테스트 체크리스트 (TODO)
- [ ] 비디오 로드 (배경음악 포함 MP4)
- [ ] Subtitles → Generate Speech (TTS)... 메뉴 클릭
- [ ] TTSDialog 열림 확인
- [ ] 대본 입력 (한국어 3문장)
- [ ] 음성/속도/분할 전략 선택
- [ ] Generate 클릭 → 진행률 확인
- [ ] 자막 트랙 추가 확인 (SubtitlePanel)
- [ ] 세그먼트 타이밍 확인
- [ ] 비디오 재생 → TTS 음성 재생 확인
- [ ] 볼륨 균형 확인
- [ ] 프로젝트 저장/로드
- [ ] 에러 처리 (빈 대본, 비디오 없음)

### 향후 개선 (P1/P2)
- [ ] 실시간 볼륨 조절 (슬라이더)
- [ ] 프리뷰 재생 (생성 전 샘플)
- [ ] 세그먼트별 개별 설정 (음성/속도)
- [ ] 배경음악 자동 페이드 (ducking)
- [ ] Whisper 역방향 검증 (타이밍 자동 보정)
- [ ] TTS 설정 프리셋 저장/로드
- [ ] GPT 대본 자동 생성
- [ ] 배치 생성 (여러 대본 파일)

**다음 TODO:**
1. 수동 GUI 테스트 (TTS 다이얼로그 및 음성 재생)
2. Git commit and push
3. Phase 4 Week 3 나머지 (Waveform, Batch Export) 또는 Phase 5 계획

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
1. ~~Phase 4 Week 2 나머지: 자막 스타일 프리셋~~ → 완료
2. Phase 4 Week 3: Timecode 정밀 편집, Waveform, Batch Export, 키보드 커스터마이징

---

## 2026-02-08 (Day 4) 작업 요약

**Phase 4 Week 2 완료: 자막 스타일 프리셋 시스템**

### 구현 내용
- **신규:** `src/services/style_preset_manager.py` - StylePresetManager
  - QSettings 기반 스타일 프리셋 저장/로드/삭제/이름변경
  - 프리셋 리스트 관리 (알파벳 정렬)
  - 기본 프리셋 자동 생성 (YouTube, Cinema, Karaoke, Minimal)
  - 모든 프리셋 데이터 영구 저장

- **개선:** `src/ui/dialogs/style_dialog.py` - StyleDialog 프리셋 UI 추가
  - 왼쪽: 프리셋 목록 (QListWidget)
  - 오른쪽: 스타일 편집 패널 (기존)
  - 프리셋 관리 버튼: Save / Rename / Delete
  - 프리셋 선택 시 스타일 즉시 적용
  - 프리셋 덮어쓰기 확인 다이얼로그
  - UI 레이아웃: 수평 분할 (프리셋 목록 | 편집기)

### 기본 프리셋
1. **YouTube**: Arial Bold 24px, 흰색, 두꺼운 검은 외곽선
2. **Cinema**: Times New Roman Italic 20px, 크림색, 얇은 외곽선
3. **Karaoke**: Comic Sans Bold 28px, 노란색, 빨간 외곽선, 반투명 배경
4. **Minimal**: Helvetica 16px, 흰색, 기본 외곽선

### 테스트
- **신규:** `tests/test_style_preset_manager.py` - 13개 테스트
  - 저장/로드/삭제/이름변경
  - 프리셋 존재 여부 확인
  - 모든 프리셋 가져오기
  - 기본 프리셋 생성
  - 덮어쓰기
  - 지속성 (persistence across instances)
- **전체 테스트:** `pytest tests/ -v` → **49/49 passed** (기존 36 + 신규 13)

### 검증
- [x] 프리셋 매니저 QSettings 저장/로드
- [x] 스타일 다이얼로그 프리셋 UI
- [x] 기본 프리셋 자동 생성
- [x] 프리셋 선택하여 스타일 적용
- [x] 프리셋 저장/이름변경/삭제
- [x] 덮어쓰기 확인 다이얼로그
- [x] 단위 테스트 49/49 passed

### 문서화
- **신규:** `TESTING.md` - 포괄적 수동 테스트 체크리스트
  - 12개 카테고리 (기본 동작, 자막 생성, 편집, 멀티트랙, 스타일링, 검색, 번역, 설정, 내보내기, MKV, UI/UX, 에러 처리)
  - 100개 이상의 테스트 항목
  - 결과 기록 표
  - 알려진 이슈 섹션

### Git Commit
- `Phase 4 Week 2: 자막 스타일 프리셋 구현` (예정)

**다음 TODO:**
1. 수동 GUI 테스트 (TESTING.md 체크리스트 실행)
2. ~~Phase 4 Week 3 계획 및 구현~~ → Day 5 완료

---

## 2026-02-08 (Day 5) 작업 요약

**Phase 4 Week 3: 타임코드 정밀 편집 구현 완료**

### 구현 내용 (P0 - 핵심 기능)

#### 1. 프레임 변환 유틸리티
- **신규:** `src/utils/time_utils.py` - 6개 프레임 변환 함수 추가
  - `ms_to_frame(ms, fps)` - 밀리초를 프레임 번호로 변환
  - `frame_to_ms(frame, fps)` - 프레임 번호를 밀리초로 변환
  - `snap_to_frame(ms, fps)` - 가장 가까운 프레임 경계로 스냅
  - `ms_to_timecode_frames(ms, fps)` - HH:MM:SS:FF 형식으로 변환
  - `timecode_frames_to_ms(text, fps)` - HH:MM:SS:FF 형식 파싱
  - `parse_flexible_timecode(text, fps)` - 다양한 타임코드 형식 자동 파싱
- 정수 연산 사용으로 부동소수점 오차 방지
- 반올림으로 가장 가까운 프레임 선택

#### 2. 프레임 단위 키보드 시크
- **개선:** `src/ui/main_window.py` - 프레임 단위 키보드 단축키 추가
  - `Shift+Left` - 한 프레임 뒤로 이동
  - `Shift+Right` - 한 프레임 앞으로 이동
  - `_seek_frame_relative(frame_delta)` 메서드 구현
  - SettingsManager의 FPS 설정 사용 (기본 30fps)

#### 3. 향상된 타임코드 입력
- **개선:** `src/ui/subtitle_panel.py` - _TimeEditDialog 다이얼로그 개선
  - 4가지 타임코드 형식 지원:
    - `MM:SS.mmm` (기존, e.g., 01:23.456)
    - `HH:MM:SS.mmm` (시간 포함, e.g., 00:01:23.456)
    - `HH:MM:SS:FF` (프레임 포함, e.g., 00:01:23:15)
    - `F:123` 또는 `frame:123` (프레임 번호)
  - 도움말 텍스트 표시 (현재 FPS 포함)
  - 향상된 에러 처리 (명확한 에러 메시지)
  - FPS 파라미터 전달 (`SettingsManager`에서 가져옴)

### 테스트
- **신규:** `tests/test_time_utils.py` - 36개 프레임 변환 테스트 추가
  - `TestFrameConversion` - 프레임 변환 및 라운드트립 (10개 테스트)
  - `TestTimecodeFrames` - HH:MM:SS:FF 형식 변환 (14개 테스트)
  - `TestFlexibleParsing` - 유연한 타임코드 파싱 (12개 테스트)
  - 24/25/30/60/120 FPS 모두 테스트
  - 엣지 케이스 (0ms, 음수, 큰 값, 잘못된 형식)
- **전체 테스트:** `pytest tests/ -v` → **85/85 passed** (기존 49 + 신규 36)
  - 0.16초 실행 (빠른 성능)
  - 회귀 없음 (기존 테스트 모두 통과)

### 수정된 파일
1. `src/utils/time_utils.py` - 6개 함수 추가 (178줄 추가)
2. `src/ui/main_window.py` - 프레임 시크 단축키 및 메서드 추가
3. `src/ui/subtitle_panel.py` - _TimeEditDialog 개선 및 FPS 전달
4. `tests/test_time_utils.py` - 36개 테스트 추가

### 검증
- [x] 프레임 변환 함수 정확성 (24/30/60fps)
- [x] 프레임 → ms → 프레임 라운드트립 일치
- [x] 프레임 스냅 기능 (가장 가까운 프레임 선택)
- [x] 4가지 타임코드 형식 파싱
- [x] 타임코드 형식 에러 처리
- [x] 단위 테스트 85/85 passed
- [x] 기존 기능 회귀 없음

### 설계 원칙
- **정수 연산 우선**: 부동소수점 오차 방지 (`int(round(...))`)
- **FPS 독립성**: 밀리초만 저장, 프레임 번호는 실시간 계산
- **명확한 에러 메시지**: `ValueError` with 상세 설명
- **하위 호환성**: 기존 `MM:SS.mmm` 형식 유지

### 수동 테스트 체크리스트
- [ ] Shift+Right/Left로 프레임 단위 시크 동작
- [ ] 타임코드 다이얼로그에서 4가지 형식 입력 가능
- [ ] 잘못된 형식 입력 시 명확한 에러 메시지
- [ ] FPS 설정 변경 시 프레임 시크 간격 변경
- [ ] 프로젝트 저장/로드 시 시간 값 유지

### 다음 단계 (P1 - 향상 기능, 추후 작업)
- 타임라인 프레임 스냅 (드래그 시 프레임 경계로)
- 프레임 번호 실시간 표시 (상태바 또는 플레이어)
- Jump to Frame 다이얼로그

**다음 TODO:**
1. 수동 GUI 테스트 (프레임 시크 및 타임코드 입력)
2. Phase 4 Week 3 나머지 기능 (Waveform, Batch Export) 또는 Phase 5 계획

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
