Read docs TECHSPEC.md before conducting your work.

# Claude.md - 나의 Claude 사용법 & 프롬프트 모음
(2026년 기준, Claude 4 / Claude Code 중심)

## 1. 기본 원칙 & 태도 (가장 중요)
- 항상 한국어로 질문한다 (Claude는 한국어 매우 잘 이해함)
- 구체적일수록 좋은 결과를 준다
- 한 번에 너무 많은 일을 시키지 말 것
- "생각 과정을 단계별로 보여줘"를 자주 사용
- 코드 작성 시 "왜 이렇게 짰는지" 설명 요구하기
- 예외 처리 철저히
- 주석은 한국어로 핵심만
- 코드 끝에 사용 예시 주석 달아줘
- 가능하면 구조화된 프로젝트 형태로 제안 (파일 분리 등)
## 2. 가장 자주 쓰는 프롬프트 템플릿

### 2.1 코드 작성 기본 템플릿
```
이런 기능을 구현해줘: [기능 설명]
- [요구사항 1]
- [요구사항 2]
- [요구사항 3]

조건:
- 타입 힌트 필수 (전체 함수/클래스)
- docstring은 간단히 (한 줄)
- 예외 처리는 구체적으로 (ValueError, FileNotFoundError 등)
- 테스트 코드도 함께
- 관련 파일 경로와 실행할 테스트 명령도 적어줘 (예: src/... , tests/... , pytest tests/test_xxx.py -v)

왜 이렇게 짰는지 짧게 설명해줘.
```

### 2.2 리팩토링 / 개선 요청
```
이 파일/함수를 개선해줘:

개선 목표:
- 가독성 크게 높이기
- 순환 참조 제거
- 타입 힌트 추가 (PEP 484)
- 매직 넘버 상수화
- 성능 개선 (가능하면)
- 테스트 작성
- 관련 파일 경로와 실행할 테스트 명령도 적어줘 (예: src/... , tests/... , pytest tests/test_xxx.py -v)

변경 전후를 명확히 보여줘.
```

### 2.3 디버깅 / 에러 해결
```
이 에러가 발생했어:
---
[에러 메시지 전체]
---

상황:
- [어떤 액션을 했을 때]
- [파일/함수 이름]
- [가능하면 스택트레이스]

이미 시도한 것:
- [1]
- [2]

정확한 진단과 해결책을 단계별로 보여줘.
```

### 2.4 프로젝트 구조 잡기
```
[목표]를 위해 새로운 모듈/클래스를 추가해야 해.

요구사항:
- models/, services/, ui/, workers/ 중 어디에 배치할지
- 기존 코드와의 연동 방식
- 테스트 구조도 함께

파일 목록과 각 파일의 책임을 보여줘.
```

### 2.5 Claude Code / Aider 스타일 작업 지시
```
이 작업을 진행해줘:
[구체적 작업 설명]

파일들:
- src/models/xxx.py - [역할]
- src/services/xxx.py - [역할]
- tests/test_xxx.py - [역할]

우선순위:
1. [first]
2. [second]
3. [third]

각 파일마다 변경사항을 명확히 보여줄 것.
```

## 3. Claude가 잘하는 일 TOP 5 (내 경험 기준)
1. 복잡한 비즈니스 로직 설계 & 구현
2. 대규모 리팩토링
3. 타입 힌트 + 문서화 추가
4. 테스트 코드 작성
5. 아키텍처 제안 (MSA, 클린 아키텍처 등)

## 4. Claude가 약한 부분 & 대처법
- 학습 데이터 컷오프 이후 릴리스된 라이브러리 → 공식 문서 링크 주면서 물어보기
- 매우 긴 코드베이스 전체 이해 → 파일 단위로 쪼개서 주기
- 프론트엔드 UI 디자인 감성 → Qt Stylesheets (QSS) + QPainter 커스텀 위젯 예시 요청
- 숫자 계산 실수 → "정확한 계산 과정을 보여줘" 추가
- **Qt/PySide 디버깅** → 구체적인 스크린샷이나 로그 필수, QThread/Signal 관련은 동작 흐름도 함께
- **FFmpeg 통합** → 정확한 명령어 문법 검증 필요, 예제 검증 요청
- **Whisper 모델 로딩** → 장시간 작업은 진도 신호 + 타임아웃 처리 명시
- **실시간 UI 갱신** → 성능 병목 분석 시 프로파일링 결과 함께 제시

## 5. 자주 쓰는 짧은 명령어 모음
- "더 깔끔하게" → 가독성 개선
- "타입 힌트 추가해줘"
- "테스트 코드도 작성해줘"
- "이 로직을 async로 바꿔줘"
- "Worker 패턴으로 백그라운드 처리해줘"
- "QSS 스타일 개선해줘"

## 6. 기타 팁
- 긴 대화일수록 "지금까지의 맥락을 요약해줘" 자주 사용
- Claude가 이상한 답변을 하면 "이 부분 다시 설명해줘" 또는 "다시 생각해봐"라고 말하기
- 코드 리뷰 받을 때는 "이 패턴이 왜 좋은지" 설명 요구하기

## 7. FastMovieMaker 프로젝트 특화 팁

### 7.1 모델 & 서비스 작업
- models/ 에서 수정할 때: "models는 Qt 독립적이어야 함"을 항상 상기
- services/ 에서: "동기 코드 기본, Edge-TTS 등 네트워크 I/O만 async", "에러 메시지는 명확하게"
- 테스트: `pytest tests/test_models.py -v` 로 검증
  ```
  새 모델 추가할 때:
  1. src/models/xxx.py 에 순수 데이터클래스 작성
  2. src/services/xxx_service.py 에 비즈니스 로직
  3. tests/test_xxx.py 에 단위테스트 (Qt 의존 X)
  4. src/workers/xxx_worker.py 로 UI 연결 (필요시)
  ```

### 7.2 UI/PySide6 작업
- "QThread 패턴은 moveToThread() 사용"
- "Signal/Slot은 non-blocking 처리 명시"
- "Timeline 같은 커스텀 위젯은 QPainter 성능 고려"
- 디버그 시: `print()` 또는 `statusBar().showMessage()` 로 상태 확인

### 7.3 오디오/비디오 처리
- FFmpeg 명령어는 "실제로 실행 후 동작 확인" 단계 포함
- Whisper 모델 로딩: "first_run 시간 고려, progress bar 필수"
- 시간 단위: "항상 ms (int)로 통일, frame 변환은 fps 함께 전달"
  ```
  시간 관련 수정:
  - ms_to_display(), srt_time_to_ms() 등 time_utils.py 함수 검증
  - time_utils.py 테스트 먼저
  - UI에 반영 전 단위테스트 필수
  ```

### 7.4 테스트 작성
- "tests/ 폴더 구조와 이름 규칙 따를 것"
- "test_models.py 는 Qt 없이, test_*_gui.py 는 Qt 필요"
- Mock 패턴: `unittest.mock.patch()` 활용 (FFmpeg, Whisper 엔드포인트)
  ```
  테스트 실행:
  pytest tests/test_xxx.py -v          # 단일 파일
  pytest tests/test_xxx.py::TestClass::test_method -v  # 특정 테스트
  ```

마지막 업데이트: 2026년 2월 10일