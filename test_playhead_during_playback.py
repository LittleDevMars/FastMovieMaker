#!/usr/bin/env python3
"""
재생 중 playhead 드래그 테스트
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest

sys.path.insert(0, str(Path(__file__).parent))

from src.ui.main_window import MainWindow
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.ui.timeline_widget import _DragMode


def test_playhead_during_playback():
    """재생 중 playhead 드래그 테스트"""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()

    print("🧪 재생 중 playhead 드래그 테스트\n")

    QTest.qWait(1000)

    # TTS 트랙 생성
    print("📝 TTS 트랙 생성")
    track = SubtitleTrack()
    track.name = "Test Track"
    track.add_segment(SubtitleSegment(0, 2000, "Test 1"))
    track.add_segment(SubtitleSegment(2000, 4000, "Test 2"))
    track.audio_path = "/tmp/test.mp3"
    track.audio_duration_ms = 4000

    window._project.subtitle_track = track
    window._timeline.set_duration(4000)
    window._timeline.set_track(track)

    QTest.qWait(500)

    timeline = window._timeline

    print("\n🎬 시나리오 1: 정지 상태에서 playhead 드래그")
    # playhead를 500ms 위치로 설정
    timeline.set_playhead(500)
    print(f"  초기 위치: {timeline._playhead_ms}ms")

    # PLAYHEAD_DRAG 모드로 설정
    timeline._drag_mode = _DragMode.PLAYHEAD_DRAG

    # 재생 시뮬레이션 (positionChanged 이벤트)
    # 드래그 중이므로 무시되어야 함
    timeline.set_playhead(0)  # 0으로 설정 시도
    after_pos = timeline._playhead_ms

    if after_pos == 500:
        print(f"  ✓ 드래그 중 playhead 업데이트 무시됨: {after_pos}ms (500ms 유지)")
        result1 = True
    else:
        print(f"  ❌ 드래그 중 playhead가 변경됨: {after_pos}ms (500ms → {after_pos}ms)")
        result1 = False

    # 드래그 종료
    timeline._drag_mode = _DragMode.NONE

    print("\n🎬 시나리오 2: 드래그 종료 후 playhead 업데이트")
    timeline.set_playhead(1000)
    after_pos = timeline._playhead_ms

    if after_pos == 1000:
        print(f"  ✓ 정상 업데이트: {after_pos}ms")
        result2 = True
    else:
        print(f"  ❌ 업데이트 실패: {after_pos}ms")
        result2 = False

    # 결과
    print(f"\n{'='*60}")
    if result1 and result2:
        print("✅ 모든 테스트 통과!")
        print("재생 중 playhead 드래그가 정상 작동합니다.")
    else:
        print("❌ 테스트 실패")
    print(f"{'='*60}")

    QTimer.singleShot(1000, app.quit)
    sys.exit(0 if result1 and result2 else 1)


if __name__ == "__main__":
    test_playhead_during_playback()
