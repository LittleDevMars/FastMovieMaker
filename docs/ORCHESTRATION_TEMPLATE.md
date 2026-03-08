# Orchestration Template

이 템플릿은 Codex/에이전트에게 작업을 단계적으로 위임할 때 사용한다.
복붙 후 `[]`만 채우면 된다.

## 1) Standard Template

```text
다음 작업 오케스트레이션 해줘.

목표:
- [최종 결과 1문장]

배경/의도:
- [왜 이 작업을 하는지]

범위 (In Scope):
- [포함 1]
- [포함 2]

범위 (Out of Scope):
- [제외 1]
- [제외 2]

제약사항:
- [호환성 제약]
- [성능/UX 제약]
- [코딩 스타일/아키텍처 제약]

구현 순서:
1. [탐색]
2. [구현]
3. [테스트]
4. [문서화]

검증 기준 (Acceptance Criteria):
- [기준 1]
- [기준 2]
- [기준 3]

실행할 테스트:
- [pytest ...]
- [pytest ...]

산출물:
- 변경 파일 목록
- 핵심 변경 요약
- 테스트 결과
- 후속 작업 제안 (선택)
```

## 2) Quick Template (Fast Path)

```text
이 작업 바로 진행해줘.
목표: [무엇을]
범위: [포함/제외]
제약: [필수 조건]
검증: [실행할 테스트]
산출물: [요약 형식]
```

## 3) Review-Oriented Template

```text
아래 변경을 리뷰 오케스트레이션 해줘.
기준: 버그/회귀/리스크 우선
범위: staged + unstaged + untracked
출력: 우선순위별 이슈, 파일/라인, 재현 조건, 수정 방향
검증: 필요 시 관련 테스트 제안
```

## 4) Example (This Project)

```text
다음 작업 오케스트레이션 해줘.

목표:
- Timeline subtitle 렌더링 성능 최적화(가시 구간만 순회)

범위 (In Scope):
- src/models/subtitle.py
- src/ui/timeline_painter.py
- tests/test_models.py
- tests/test_timeline_visible_range_rendering.py

범위 (Out of Scope):
- UI 스타일 변경
- 텍스트 레이아웃 캐시 대규모 개편

제약사항:
- 기존 렌더링 결과 동일 유지
- 기존 공개 인터페이스 호환

검증 기준:
- 가시 구간 밖 세그먼트 순회 제거
- 관련 테스트 통과

실행할 테스트:
- QT_QPA_PLATFORM=offscreen pytest tests/test_models.py tests/test_timeline_visible_range_rendering.py -q
- QT_QPA_PLATFORM=offscreen pytest tests/test_frame_snap.py -q
```

## 5) Usage Notes

- 처음부터 너무 큰 목표를 넣지 말고 1~2시간 단위로 쪼개는 것이 좋다.
- 반드시 `Out of Scope`를 적어야 스코프 확장을 막을 수 있다.
- 테스트 명령을 명시하면 결과가 일관된다.
- 산출물 형식을 지정하면 리뷰/핸드오프가 쉬워진다.
