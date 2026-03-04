# FastMovieMaker TODO

## 🚧 진행 중 / In Progress

없음 — Phase ANIM2+CC2 완료 (Day 37)

---

## 🐛 현재 버그 수정

### 긴급 (Critical)
- [x] ~~멀티 소스 타임라인 재생 버그~~ (수정 완료)
- [x] ~~타임라인/슬라이더 동기화 문제~~ (수정 완료)
- [x] ~~클립 삭제 후 재생 문제~~ (수정 완료)
- [x] ~~영상 두 개 이상일 때 클립 분할 안 되는 문제~~ (수정 완료)

### 중요 (High)
- [x] ~~TTS 다이얼로그 진행률 표시 테스트 실패~~ (수정 완료, 762/762 통과)

### 보통 (Medium)
- [x] ~~프레임 스냅 활성화 시 UI 피드백~~ (완료 Day 38)
- [x] ~~대용량 프로젝트 로드 속도 개선~~ (완료 Day 39)

---

## 📋 백로그 / Backlog

### 기능 추가
- [ ] GPU 가속 비디오 렌더링
- [x] ~~AI 기반 자막 번역 (DeepL/GPT)~~ (완료, Phase 4 Week 2)
- [ ] 실시간 자막 프리뷰 (Whisper 진행 중)
- [ ] 플러그인 시스템 (커스텀 TTS 제공자)
- [ ] 클라우드 프로젝트 동기화

### 성능 개선
- [ ] 파이썬 코어 로직 Cython 변환
- [ ] 자막 렌더링 최적화
- [ ] 프로젝트 파일 압축

### 문서
- [x] ~~README.md 작성~~ (완료)
- [x] ~~TTS 사용 가이드 (한/영)~~ (완료)
- [x] ~~MIT License 추가~~ (완료)
- [ ] 개발자 가이드 (아키텍처, 기여 방법)
- [ ] 비디오 튜토리얼

---

## 📌 최근 완료 / Recently Completed

- ✅ 문서 동기화 + 테스트 안정화 — README/PROGRESS/TODO 최신화, TTS 진행률 GUI 테스트 픽스, pytest slow 마커 등록 (762 테스트) - 2026-03-04
- ✅ Phase PERF/UX3 — gzip 프로젝트 압축(50-70% 파일 크기 감소), 중복 비디오 로드 제거, import 최적화 (744 테스트) - 2026-03-03
- ✅ Phase ANIM2+CC2 — 자막 애니메이션 인디케이터·일괄 적용, Hue 슬라이더, 트랙 일괄 색보정 (731 테스트) - 2026-03-03
- ✅ Phase CLIP2 — 멀티 클립 선택 (Ctrl/Shift+클릭), Copy/Paste/Delete N Clips (706 테스트) - 2026-03-03
- ✅ Phase MV — 다중 비디오 트랙 레이어 합성, 블렌드 모드, 크로마키 (681 테스트) - 2026-03-03
- ✅ Phase E — PyInstaller 배포 패키징, macOS/Windows 자동 빌드 CI (663 테스트) - 2026-02-28
- ✅ Phase UX2 — 프로젝트 템플릿 + 웰컴 다이얼로그 (658 테스트) - 2026-02-28
- ✅ Phase Q — 로깅 & 크래시 리포트 (643 테스트) - 2026-02-28
- ✅ Phase P2 — Whisper 역방향 검증 + 배치 TTS (632 테스트) - 2026-02-25
- ✅ Phase D1~D3 — UX 개선 (내보내기 프리뷰, 단축키 커스터마이징, 마커, 컬러 레이블, Undo 패널) - 2026-02-24
- ✅ Phase SD — FFmpeg 장면 감지 (534 테스트) - 2026-02-22
- ✅ Phase T2/T3 트랜지션 완성 — Remove Transition, RippleEdit, SpeedDialog - 2026-02-21
- ✅ BGM Ducking — TTS 구간 자동 배경음 덕킹 (441 테스트) - 2026-02-21
- ✅ TTS 설정 프리셋 저장/로드 (454 테스트) - 2026-02-20
- ✅ 비디오 썸네일 버그 수정 (static cache 무효화) - 2026-02-20
- ✅ 프레임 버퍼링 및 성능 최적화 (VideoFramePlayer, FFmpegLogger) - 2026-02-19

---

**Last Updated**: 2026-03-04 (Day 40)
