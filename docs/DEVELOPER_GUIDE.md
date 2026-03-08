# FastMovieMaker Developer Guide

## 목적
이 문서는 FastMovieMaker 기여 시 필요한 개발 흐름과 품질 기준을 정의합니다.

## 로컬 개발 환경
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

## 아키텍처 원칙
- `src/models`: Qt 의존성 없는 순수 데이터 모델
- `src/services`: 비즈니스 로직 (Qt-free)
- `src/workers`: 백그라운드 처리(QThread bridge)
- `src/ui/controllers`: UI 이벤트-비즈니스 로직 연결(QObject 기반)
- `src/ui`: 화면 구성/렌더링

핵심 규칙:
- 모델/서비스 레이어에 Qt 객체를 넣지 않습니다.
- 워커 시그널은 컨트롤러(QObject)에서 받아 메인 스레드에서 UI를 갱신합니다.
- 시간 단위는 내부적으로 `milliseconds(int)`를 사용합니다.
- TTS Worker 입력 계약은 `speed(float)` 단일값을 사용하고, 엔진별 변환은 provider에서만 처리합니다.
- TTS 오류 문자열 계약은 `TTS_ERROR::<CODE>::<detail>`이며, 코드→사용자 메시지 매핑은 `src/services/tts_error_presenter.py` 단일 모듈에서 관리합니다.
- UI는 presenter가 반환한 친화 메시지만 노출하고, raw detail은 tooltip/로그 디버깅 용도로만 사용합니다.
- TTS provider 레지스트리는 내장 provider를 항상 유지하고, 외부 플러그인(`register_tts_providers`)은 실패 격리 후 선택적으로 병합합니다.
- 플러그인 경로는 `tts/plugin_paths` 설정 + `FMM_TTS_PLUGIN_PATHS` 환경변수를 병합해 로드합니다.
- provider가 `provider_id`/`display_name`/`list_voices`/`requires_api_key` 계약을 만족하면 Preferences/TTS/Batch 엔진 UI에 자동 노출됩니다.

## 브랜치 및 커밋 규칙
- 기능/수정 브랜치는 `codex/<short-topic>` 형식을 사용합니다.
- 커밋 타입은 `feat:`, `fix:`, `test:`, `docs:`, `chore:`를 사용합니다.
- 커밋은 가능한 작은 단위로 분리합니다(기능/리팩터/문서 혼합 금지).
- 런타임 산출물(`.fastmoviemaker/`, 로그, 캐시)은 커밋하지 않습니다.

## 테스트 전략
### Unit
- 모델/서비스 로직은 Qt 의존성 없이 단위 테스트를 우선 작성합니다.

### Integration
- 컨트롤러, export, 프로젝트 I/O 등 계층 연동 동작을 테스트합니다.

### GUI
- `pytest-qt`로 위젯 상태 변경/시그널 흐름을 검증합니다.
- GUI 테스트는 `QT_QPA_PLATFORM=offscreen` 환경에서 실행합니다.

기본 명령:
```bash
# 전체 테스트
QT_QPA_PLATFORM=offscreen pytest tests/ -q

# 테스트 수 수집 확인
QT_QPA_PLATFORM=offscreen pytest tests/ -q --collect-only

# 문서 테스트 수치 동기화(운영 모드: Day 자동 갱신 없음)
python3 scripts/sync_test_counts.py
python3 scripts/sync_test_counts.py --check

# APV 파이프라인 스모크 검증 (샘플 없으면 SKIPPED)
python3 scripts/verify_apv_pipeline.py
FMM_APV_SAMPLE=/path/to/sample_apv.mov python3 scripts/verify_apv_pipeline.py

# APV 운영 준비 상태 검증 (gh 인증/권한 없으면 SKIPPED)
python3 scripts/verify_apv_secret_ready.py

# 운영 강제 검증 (PASS가 아니면 실패)
python3 scripts/verify_apv_secret_ready.py --require-pass

# 프로젝트 I/O 압축 계측
python3 scripts/benchmark_project_io.py --segments 2000 --iterations 3 --text-length 80
```

APV 스모크 결과 해석:
- `PASS`: APV 감지 + MP4 변환 + 비디오/오디오 스트림 검증 완료
- `SKIPPED`: `FMM_APV_SAMPLE` 미설정(실패 아님)
- `FAIL`: APV 감지/변환/스트림 검증 중 하나라도 실패

CI APV 잡(`tests.yml`의 `apv-smoke`):
- 기본 동작은 `SKIPPED` 허용
- 시크릿 `APV_SAMPLE_B64`(base64 인코딩 APV 샘플)를 설정하면 자동으로 `FMM_APV_SAMPLE` 주입 후 검증 수행
- 시크릿 decode 실패/빈 샘플은 즉시 `FAIL` 처리

APV CI 시크릿 준비:
```bash
# macOS/Linux: base64 한 줄 문자열 생성
base64 -i /path/to/sample_apv.mov | tr -d '\n'
```
- GitHub 저장소 `Settings > Secrets and variables > Actions`에 `APV_SAMPLE_B64` 등록
- `apv-smoke` 로그에서 단계별 고정 프리픽스 확인:
  - `[APV][prepare]`
  - `[APV][verify-script]`
  - `[APV][pytest]`
- 운영 마감 검증:
  - `python3 scripts/verify_apv_secret_ready.py` 결과가 `PASS`
  - `apv-smoke` 최근 3회 `PASS`
  - 증빙 템플릿 `docs/operations/APV_READINESS.md` 갱신

트러블슈팅:
- `result: FAIL` + `reason: APV_SAMPLE_B64 decode failed.`: 시크릿 문자열이 base64 형식인지 확인
- `result: FAIL` + `reason: decoded APV sample is empty.`: 빈 문자열/잘못된 복사 여부 확인
- `result: FAIL` + `reason: expected APV codec...`: 샘플이 실제 APV 코덱인지 `ffprobe`로 확인
- `result: FAIL` + `reason: required secret is missing: APV_SAMPLE_B64`: 저장소 시크릿 등록 누락
- `result: FAIL` + `reason: recent apv-smoke job ended with ...`: GitHub Actions `apv-smoke` 최근 실행 로그 확인

프로젝트 I/O 압축 계측 해석:
- `compression_ratio_avg`: 작을수록 좋음(권장 기준: `<= 0.50`)
- `save_ms_avg`/`load_ms_avg`: 로컬 반복 비교용 지표(절대값보다 이전 대비 회귀 여부를 우선 확인)
- 운영/CI에서는 동일 옵션(`--segments 2000 --iterations 3 --text-length 80`)으로 비교

## Pre-push 루틴
권장 실행:
```bash
scripts/pre_push_checks.sh

# 운영 준비 상태를 로컬에서 강제 검증하려면:
FMM_ENFORCE_APV_READY=1 scripts/pre_push_checks.sh
```

Git hook 자동 설정:
```bash
scripts/install_git_hooks.sh
```

## 릴리즈 체크리스트
- 전체 테스트 통과 (`pytest tests/ -q`)
- 문서 테스트 수치 동기화 확인 (`sync_test_counts.py --check`)
- 배포 워크플로 대상 변경점 확인(`build_macos.sh`, `build_windows.bat`, workflow)
- 사용자 영향 기능은 수동 시나리오 1회 이상 검증

## GPU Export 정책 (MVP)
- ExportDialog의 GPU 체크 시 하드웨어 인코더를 우선 시도합니다.
- 하드웨어 인코더 실패 시 소프트웨어 인코더로 자동 fallback 1회 재시도합니다.
- CRF는 인코더별 근사 매핑값을 사용하며(예: NVENC `-cq`, VideoToolbox `-q:v`), 품질 완전 동등성은 보장하지 않습니다.

## PR 체크리스트
- 기능 변경에 대한 테스트가 추가/수정되었는가?
- `README.md`, `TODO.md`, `PROGRESS.md`의 수치/상태가 최신인가?
- UI 변경 시 최소 1회 수동 동작 확인을 했는가?
