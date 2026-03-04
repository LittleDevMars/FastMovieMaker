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
```

## Pre-push 루틴
권장 실행:
```bash
scripts/pre_push_checks.sh
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
