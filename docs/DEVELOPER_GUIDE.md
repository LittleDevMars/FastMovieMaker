# FastMovieMaker Developer Guide

## 목적
이 문서는 FastMovieMaker에 기여할 때 필요한 최소 개발 흐름, 아키텍처 규칙, 테스트 규칙을 정리합니다.

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

## 코드 변경 가이드
- 작은 단위로 커밋합니다: `feat:`, `fix:`, `docs:`, `chore:`.
- 런타임 산출물(`.fastmoviemaker/`, 로그, 캐시)은 커밋하지 않습니다.
- 새 기능에는 가능하면 단위 테스트를 함께 추가합니다.

## 테스트 가이드
```bash
# 빠른 전체 검증
QT_QPA_PLATFORM=offscreen pytest tests/ -q

# 테스트 수 수집 확인
QT_QPA_PLATFORM=offscreen pytest tests/ -q --collect-only
```

문서 테스트 수치 동기화:
```bash
python3 scripts/sync_test_counts.py
python3 scripts/sync_test_counts.py --check
```

## PR 체크리스트
- 기능 변경에 대한 테스트가 추가/수정되었는가?
- `README.md`, `TODO.md`, `PROGRESS.md`의 수치/상태가 최신인가?
- UI 변경 시 최소 1회 수동 동작 확인을 했는가?
