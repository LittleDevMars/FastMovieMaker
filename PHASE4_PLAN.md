# Phase 4 구현 계획: 프로 워크플로우 + 사용성 강화

## 목표
Phase 1~3에서 구축한 핵심 편집 기능 위에 **프로페셔널 워크플로우**와 **실용적 편의 기능**을 추가하여 실전 사용 가능한 완성도 높은 애플리케이션으로 발전.

---

## Step 1: 자동 저장 + 크래시 복구 (최우선)

**목적:** 작업 손실 방지, 안정성 확보

### 구현 내용
1. **자동 저장**
   - 30초마다 또는 편집 후 5초 idle 시 자동 저장
   - `~/.fastmoviemaker/autosave/` 디렉토리에 타임스탬프 파일
   - 설정에서 간격 조정 가능

2. **크래시 복구**
   - 앱 시작 시 autosave 디렉토리 확인
   - 복구 가능한 파일이 있으면 다이얼로그 표시
   - "Restore" / "Discard" 선택

3. **프로젝트 히스토리**
   - 최근 프로젝트 목록 (최대 10개)
   - File → Recent Projects 메뉴

**신규 파일:**
- `src/services/autosave.py` - AutoSaveManager (QTimer 기반)
- `src/ui/dialogs/recovery_dialog.py` - 복구 다이얼로그

**수정 파일:**
- `main_window.py` - AutoSaveManager 통합, recent projects

---

## Step 2: 드래그 앤 드롭

**목적:** 파일 열기 편의성 향상

### 구현 내용
1. **비디오 파일 드롭**
   - MainWindow에 dragEnterEvent/dropEvent
   - 지원 포맷: `.mp4`, `.mkv`, `.avi`, `.mov` 등

2. **SRT 파일 드롭**
   - 현재 트랙에 덮어쓰기 또는 새 트랙 추가 선택

3. **프로젝트 파일 드롭**
   - `.fmm.json` 드롭 시 프로젝트 로드

**수정 파일:**
- `main_window.py` - setAcceptDrops(True), dragEnterEvent, dropEvent

---

## Step 3: 자막 검색 + 필터

**목적:** 긴 영상에서 특정 자막 빠르게 찾기

### 구현 내용
1. **검색 바**
   - subtitle_panel 상단에 QLineEdit 검색창
   - 실시간 하이라이팅 (입력하면 즉시 필터)
   - Ctrl+F 단축키

2. **필터 기능**
   - 텍스트 검색 (대소문자 구분/무시)
   - 시간 범위 필터 (예: "00:10 ~ 00:30")
   - 트랙별 필터 (현재 트랙만 또는 전체)

3. **검색 결과 네비게이션**
   - F3/Shift+F3로 다음/이전 결과 이동
   - 검색 결과 개수 표시

**신규 파일:**
- `src/ui/search_bar.py` - SearchBar 위젯

**수정 파일:**
- `subtitle_panel.py` - SearchBar 통합, 필터링 로직

---

## Step 4: 자동 번역 (DeepL + GPT)

**목적:** 다국어 자막 제작 자동화

### 구현 내용
1. **번역 엔진 통합**
   - DeepL API (무료 tier: 500k chars/month)
   - OpenAI GPT-4o-mini (저렴, 컨텍스트 활용)
   - Google Translate (무료 fallback)

2. **번역 다이얼로그**
   - Subtitles → Translate Track...
   - 소스 언어 → 타겟 언어 선택
   - 엔진 선택 (DeepL / GPT / Google)
   - 새 트랙으로 추가 또는 현재 트랙 교체

3. **배치 번역**
   - 프로그레스바 + 취소 가능
   - API 키 설정 (Preferences)

4. **번역 후처리**
   - 타이밍 유지 (원본과 동일한 start/end)
   - 스타일 복사 (폰트는 언어별 기본값으로 변경 가능)

**신규 파일:**
- `src/services/translator.py` - TranslatorService (DeepL/GPT/Google)
- `src/ui/dialogs/translate_dialog.py` - 번역 설정 다이얼로그
- `src/ui/dialogs/preferences_dialog.py` - API 키 설정

**수정 파일:**
- `main_window.py` - Subtitles 메뉴에 "Translate Track..." 추가

---

## Step 5: 타임코드 정밀 편집

**목적:** 프레임 단위 정확도, 타임코드 입력 지원

### 구현 내용
1. **프레임 단위 시크**
   - , / . 키로 -1 / +1 프레임 이동
   - FPS 자동 감지 (ffprobe)

2. **타임코드 입력**
   - 시간 편집 시 다양한 포맷 지원:
     - `MM:SS.mmm` (기존)
     - `HH:MM:SS.mmm`
     - `00:01:23.456` (SRT 스타일)
     - 프레임 번호 (예: `1234f`)

3. **스냅 기능**
   - 타임라인에서 드래그 시 다른 자막 경계에 스냅
   - Shift 누르면 스냅 해제

**수정 파일:**
- `timeline_widget.py` - 프레임 단위 시크, 스냅
- `subtitle_panel.py` - 타임코드 파싱 개선
- `src/utils/time_utils.py` - 다양한 타임코드 포맷 파싱

---

## Step 6: 자막 프리셋 + 템플릿

**목적:** 자주 쓰는 스타일 재사용

### 구현 내용
1. **스타일 프리셋**
   - 현재 스타일을 프리셋으로 저장
   - Subtitles → Style Presets → Save Current...
   - 프리셋 라이브러리 (JSON)

2. **빠른 적용**
   - 선택된 자막에 프리셋 적용
   - 우클릭 → Apply Preset → [프리셋 이름]

3. **기본 프리셋**
   - "YouTube", "Netflix", "Viki" 등 인기 플랫폼 스타일 내장

**신규 파일:**
- `src/services/preset_manager.py` - 프리셋 저장/로드
- `~/.fastmoviemaker/presets/` - 프리셋 저장 디렉토리

**수정 파일:**
- `style_dialog.py` - "Save as Preset..." 버튼
- `subtitle_panel.py` - Apply Preset 컨텍스트 메뉴

---

## Step 7: 배치 내보내기

**목적:** 여러 트랙을 한 번에 내보내기

### 구현 내용
1. **다중 트랙 SRT 내보내기**
   - File → Export All Tracks...
   - 각 트랙을 별도 SRT 파일로 (예: `video_ko.srt`, `video_en.srt`)

2. **다중 언어 비디오**
   - 각 트랙 하드번 영상을 배치 생성
   - 병렬 처리 (멀티프로세싱)

3. **프로그레스 추적**
   - 전체 진행률 + 개별 작업 상태

**신규 파일:**
- `src/ui/dialogs/batch_export_dialog.py`

---

## Step 8: 환경 설정 (Preferences)

**목적:** 사용자 커스터마이징

### 구현 내용
1. **일반 설정**
   - 자동 저장 간격
   - 최근 파일 개수
   - 기본 언어

2. **편집 설정**
   - 기본 자막 길이 (신규 추가 시)
   - 스냅 허용 오차 (픽셀)
   - 프레임 시크 FPS

3. **고급 설정**
   - FFmpeg 경로 (자동 감지 또는 수동 지정)
   - Whisper 모델 캐시 경로
   - API 키 (DeepL, OpenAI)

**신규 파일:**
- `src/ui/dialogs/preferences_dialog.py` - QTabWidget 기반 설정 창
- `src/services/settings_manager.py` - QSettings 래퍼

**수정 파일:**
- `main_window.py` - Edit → Preferences... 메뉴

---

## Step 9: 파형 표시 (Waveform)

**목적:** 오디오 시각화로 타이밍 조정 편의성 향상

### 구현 내용
1. **타임라인에 파형 렌더링**
   - FFmpeg로 오디오 샘플링
   - numpy + QPainter로 파형 그리기
   - 줌 레벨에 따라 해상도 조정

2. **On-demand 로딩**
   - 영상 로드 시 백그라운드에서 파형 생성
   - 캐시 (`~/.fastmoviemaker/waveforms/`)

**신규 파일:**
- `src/services/waveform_generator.py`
- `src/workers/waveform_worker.py`

**수정 파일:**
- `timeline_widget.py` - paintEvent에 파형 오버레이

---

## Step 10: 단축키 커스터마이징

**목적:** 사용자 워크플로우 최적화

### 구현 내용
1. **키 바인딩 에디터**
   - Preferences → Keyboard Shortcuts
   - 테이블로 모든 액션 표시
   - 더블클릭으로 키 재할당

2. **프리셋**
   - "Default", "Premiere Pro-like", "Final Cut-like"

**수정 파일:**
- `preferences_dialog.py` - Shortcuts 탭
- `main_window.py` - 동적 단축키 로딩

---

## 구현 순서 (우선순위)

```
┌─────────────────────────────────────────────┐
│ Week 1 (필수 기능)                           │
├─────────────────────────────────────────────┤
│ Step 1: 자동 저장 + 크래시 복구              │
│ Step 2: 드래그 앤 드롭                       │
│ Step 3: 자막 검색 + 필터                     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Week 2 (AI + 워크플로우)                     │
├─────────────────────────────────────────────┤
│ Step 4: 자동 번역 (DeepL/GPT)               │
│ Step 8: 환경 설정 (Preferences)             │
│ Step 6: 자막 프리셋 + 템플릿                │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Week 3 (고급 기능)                           │
├─────────────────────────────────────────────┤
│ Step 5: 타임코드 정밀 편집                   │
│ Step 9: 파형 표시                            │
│ Step 7: 배치 내보내기                        │
│ Step 10: 단축키 커스터마이징                 │
└─────────────────────────────────────────────┘
```

---

## 검증 방법

### Week 1
- [ ] 자동 저장 후 강제 종료 → 복구 다이얼로그 표시
- [ ] 비디오/SRT 파일 드래그앤드롭 동작
- [ ] Ctrl+F로 자막 검색, F3로 다음 결과 이동

### Week 2
- [ ] DeepL API로 한→영 번역 트랙 생성
- [ ] Preferences에서 자동 저장 간격 변경 반영
- [ ] 스타일 프리셋 저장 후 다른 자막에 적용

### Week 3
- [ ] , / . 키로 프레임 단위 시크
- [ ] 타임라인에 파형 표시
- [ ] 모든 트랙 SRT 배치 내보내기
- [ ] 단축키 재할당 후 동작 확인

---

## 추가 고려사항 (Phase 5)

- **클라우드 동기화** (Google Drive / Dropbox 연동)
- **협업 기능** (댓글, 리뷰 모드)
- **플러그인 시스템** (Python 스크립트로 확장)
- **macOS/Windows 인스톨러** (.dmg / .exe)
- **화자 분리** (Pyannote.audio)
- **자막 애니메이션** (페이드인/아웃, 슬라이드)

---

**Phase 4 완료 시 달성 목표:**
- ✅ 작업 손실 없는 안정적인 워크플로우
- ✅ AI 기반 다국어 자막 자동화
- ✅ 프로페셔널 타임코드 편집
- ✅ 사용자 커스터마이징 (프리셋, 단축키)
- ✅ 배치 처리로 대량 작업 효율화
