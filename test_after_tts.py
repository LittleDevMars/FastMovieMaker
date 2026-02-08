#!/usr/bin/env python3
"""
TTS 생성 후 타임라인 클릭 테스트
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest

sys.path.insert(0, str(Path(__file__).parent))

from src.ui.main_window import MainWindow
from src.models.subtitle import SubtitleSegment, SubtitleTrack


def test_after_tts():
    """TTS 생성 후 시나리오 테스트"""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()

    print("🧪 TTS 생성 후 타임라인 테스트\n")

    # 1. 초기화 대기
    QTest.qWait(1000)

    # 2. TTS 트랙 시뮬레이션 (오디오 없는 비디오 시나리오)
    print("📝 TTS 트랙 생성 (비디오 없음)")
    track = SubtitleTrack()
    track.name = "TTS Track 1"

    # 샘플 세그먼트 추가
    segments = [
        (0, 2000, "첫 번째 자막"),
        (2000, 4000, "두 번째 자막"),
        (4000, 6000, "세 번째 자막"),
    ]

    for start, end, text in segments:
        seg = SubtitleSegment(start_ms=start, end_ms=end, text=text)
        track.add_segment(seg)

    # 오디오 경로 설정 (TTS 생성 후 상황)
    track.audio_path = "/tmp/test_audio.mp3"
    track.audio_duration_ms = 6000

    # 프로젝트에 설정
    window._project.subtitle_track = track

    # 타임라인 duration 설정 (TTS 생성 후 - 비디오 없음)
    print(f"  Duration: {track.audio_duration_ms}ms (오디오 기준)\n")
    window._timeline.set_duration(track.audio_duration_ms)
    window._timeline.set_track(track)

    QTest.qWait(500)

    # 3. 타임라인 상태 확인
    timeline = window._timeline
    print(f"📊 타임라인 상태 (TTS 생성 후):")
    print(f"  _duration_ms: {timeline._duration_ms}")
    print(f"  _px_per_ms: {timeline._px_per_ms:.6f}")
    print(f"  _visible_start_ms: {timeline._visible_start_ms}")
    print(f"  has_video: {window._project.has_video}")

    # 4. 타임라인 클릭 테스트
    print(f"\n🖱️  타임라인 클릭 테스트:")

    results = []
    test_positions = [
        ("시작", 50),
        ("1/4", timeline.width() // 4),
        ("중앙", timeline.width() // 2),
        ("3/4", timeline.width() * 3 // 4),
        ("끝", timeline.width() - 50),
    ]

    for name, x_pos in test_positions:
        seek_positions = []

        def on_seek(pos):
            seek_positions.append(pos)

        timeline.seek_requested.connect(on_seek)

        # 직접 _seek_to_x 호출
        timeline._seek_to_x(x_pos)
        QTest.qWait(50)

        # 결과
        if seek_positions:
            seek_pos = seek_positions[-1]
            passed = seek_pos != 0 or x_pos < 100
            status = "✓" if passed else "❌"
            print(f"  {status} {name:8} (X={x_pos:4}px) → {seek_pos:5}ms")
            results.append(passed)
        else:
            print(f"  ❌ {name:8} (X={x_pos:4}px) → seek 안됨!")
            results.append(False)

        timeline.seek_requested.disconnect(on_seek)

    # 5. 결과
    print(f"\n{'='*60}")
    passed = sum(results)
    total = len(results)
    print(f"결과: {passed}/{total} 통과")

    if passed == total:
        print("✅ TTS 생성 후 테스트 통과!")
    else:
        print("❌ TTS 생성 후 테스트 실패 - 이것이 문제!")
    print(f"{'='*60}")

    QTimer.singleShot(1000, app.quit)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    test_after_tts()
