# Orchestration Examples (FastMovieMaker)

`commands/orchestrate.md`, `commands/plan.md`, `commands/verify.md`를 실제로 사용하는 예시 모음이다.

## 1) Feature Example — TTS Plugin Loader (Phase 2)

### Step A: Plan
```text
/plan TTS provider 플러그인 로더(동적 등록) 2단계 구현
```

### Step B: Orchestrate
```text
/orchestrate feature TTS provider 동적 로딩(importlib) + 오류 격리 + fallback 구현
```

### Step C: Verify
```text
/verify full
```

### Expected Deliverables
- `src/services/tts_provider_registry.py` 확장
- 동적 로더 테스트 추가
- 실패 시 Edge-TTS fallback 보장

## 2) Bugfix Example — APV Load Regression

### Step A: Plan
```text
/plan APV 코덱 영상 로드 시 변환 후 오디오 누락되는 회귀 버그 수정
```

### Step B: Orchestrate
```text
/orchestrate bugfix APV ffprobe 감지 경로에서 remux/hw/sw fallback 이후 오디오 매핑 안정화
```

### Step C: Verify
```text
/verify pre-pr
```

### Expected Deliverables
- APV 분기 로직 수정
- 회귀 테스트 추가 (`video_load_worker` 관련)
- 수동 검증 체크리스트 업데이트

## 3) Refactor Example — Timeline Painter Cleanup

### Step A: Plan
```text
/plan timeline_painter 중복 계산/스타일 생성 코드 정리 (동작 동일 유지)
```

### Step B: Orchestrate
```text
/orchestrate refactor visible-range 계산 공통화 + painter 객체 재사용 + 관련 테스트 정리
```

### Step C: Verify
```text
/verify full
```

### Expected Deliverables
- `src/ui/timeline_painter.py` 리팩
- `src/models/subtitle.py` 헬퍼 유지/확장
- 타임라인 관련 테스트 green 유지

## Usage Tip

각 예시에서 작업 설명만 바꿔 재사용하면 된다.  
작업이 커지면 `/plan` 결과를 먼저 고정한 뒤 `/orchestrate`를 실행하는 것을 권장한다.
