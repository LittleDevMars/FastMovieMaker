#!/usr/bin/env python3
"""
실제 사용 시나리오 테스트
- 비디오 로드
- 타임라인 클릭
- 실제 위치 확인
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest

sys.path.insert(0, str(Path(__file__).parent))

from src.ui.main_window import MainWindow


def test_real_scenario():
    """실제 사용 시나리오 테스트"""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()

    print("🧪 실제 시나리오 테스트\n")

    # 1. 윈도우 초기화 대기
    QTest.qWait(1000)

    # 2. 비디오 로드
    test_video = Path("/Users/namhyunjun/MyProject/youtubeShort/temp/background.mp4")
    if test_video.exists():
        print(f"📹 비디오 로드: {test_video.name}")
        # MainWindow의 _on_open_video 로직 시뮬레이션
        window._project.video_path = test_video

        # QMediaPlayer로 비디오 로드
        from PySide6.QtCore import QUrl
        window._player.setSource(QUrl.fromLocalFile(str(test_video)))
        QTest.qWait(500)

        duration = window._player.duration()
        print(f"  Duration: {duration}ms")

        if duration > 0:
            window._timeline.set_duration(duration)
            QTest.qWait(500)
    else:
        print("⚠️  테스트 비디오 없음, duration 10초로 설정")
        window._timeline.set_duration(10000)
        QTest.qWait(500)

    # 3. 타임라인 상태 확인
    timeline = window._timeline
    print(f"\n📊 타임라인 상태:")
    print(f"  _duration_ms: {timeline._duration_ms}")
    print(f"  _px_per_ms: {timeline._px_per_ms:.6f}")
    print(f"  _visible_start_ms: {timeline._visible_start_ms}")
    print(f"  width: {timeline.width()}px")

    # 4. 타임라인 여러 위치 클릭 테스트
    print(f"\n🖱️  타임라인 클릭 테스트:")

    results = []
    test_positions = [
        ("시작 부근", 50),
        ("1/4 지점", timeline.width() // 4),
        ("중앙", timeline.width() // 2),
        ("3/4 지점", timeline.width() * 3 // 4),
        ("끝 부근", timeline.width() - 50),
    ]

    for name, x_pos in test_positions:
        # seek_requested 시그널 연결
        seek_positions = []
        def on_seek(pos):
            seek_positions.append(pos)

        timeline.seek_requested.connect(on_seek)

        # 타임라인에 직접 마우스 이벤트 전송
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import Qt, QEvent

        pos = QPointF(x_pos, timeline.height() // 2)
        press_event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            pos, pos, pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )

        app.sendEvent(timeline, press_event)
        QTest.qWait(100)

        # 결과 확인
        if seek_positions:
            seek_pos = seek_positions[-1]
            passed = seek_pos != 0 or x_pos < 100
            status = "✓" if passed else "❌"
            print(f"  {status} {name:12} (X={x_pos:4}px) → {seek_pos:5}ms")
            results.append(passed)
        else:
            print(f"  ❌ {name:12} (X={x_pos:4}px) → seek 안됨!")
            results.append(False)

        timeline.seek_requested.disconnect(on_seek)

    # 5. 결과 요약
    print(f"\n{'='*60}")
    passed = sum(results)
    total = len(results)
    print(f"결과: {passed}/{total} 통과")

    if passed == total:
        print("✅ 모든 테스트 통과!")
    else:
        print("❌ 일부 테스트 실패")
    print(f"{'='*60}")

    # 종료
    QTimer.singleShot(1000, app.quit)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    test_real_scenario()
