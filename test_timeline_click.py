#!/usr/bin/env python3
"""
타임라인 클릭 자동 테스트 스크립트
- 타임라인 여러 위치 클릭
- 0ms로 이동하는지 확인
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from src.ui.main_window import MainWindow


class TimelineClickTester:
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.window = MainWindow()
        self.test_results = []
        self.test_video_path = Path("/Users/namhyunjun/MyProject/youtubeShort/temp/background.mp4")
        self.last_seek_position = None

        # seek_requested 시그널 모니터링
        self.window._timeline.seek_requested.connect(self._on_seek_requested)

    def _on_seek_requested(self, position_ms):
        """Seek 요청 모니터링"""
        self.last_seek_position = position_ms

    def run_tests(self):
        """모든 테스트 실행"""
        print("🧪 타임라인 클릭 자동 테스트 시작\n")

        # 0. 윈도우 표시 (paintEvent 트리거)
        self.window.show()
        QTest.qWait(500)  # paintEvent 대기

        # 1. 타임라인 초기화
        if not self._load_video():
            print("❌ 타임라인 초기화 실패")
            return False

        # 2. 타임라인이 준비될 때까지 대기
        QTest.qWait(300)

        # 3. 타임라인 클릭 테스트
        self._test_timeline_clicks()

        # 4. 결과 리포트
        self._print_results()

        return all(result["passed"] for result in self.test_results)

    def _load_video(self):
        """타임라인 초기화 (비디오 없이 테스트)"""
        print(f"⚙️  타임라인 초기화 중...")

        # 타임라인 duration 설정 (10초)
        test_duration_ms = 10000
        self.window._timeline.set_duration(test_duration_ms)

        # paintEvent가 호출되도록 강제 업데이트
        self.window._timeline.update()
        QTest.qWait(200)

        print(f"✓ 타임라인 준비 완료 (duration: {test_duration_ms}ms)")
        print(f"  _px_per_ms: {self.window._timeline._px_per_ms:.6f}")
        print(f"  _visible_start_ms: {self.window._timeline._visible_start_ms}\n")
        return True

    def _test_timeline_clicks(self):
        """타임라인 여러 위치 클릭 테스트"""
        timeline = self.window._timeline
        timeline_width = timeline.width()

        # 테스트 위치들 (픽셀)
        test_positions = [
            ("왼쪽 끝", 10),
            ("왼쪽 1/4", timeline_width // 4),
            ("중앙", timeline_width // 2),
            ("오른쪽 3/4", timeline_width * 3 // 4),
            ("오른쪽 끝", timeline_width - 10),
        ]

        for name, x_pos in test_positions:
            self._click_timeline_at(name, x_pos, timeline)
            QTest.qWait(100)  # 클릭 간 대기

    def _click_timeline_at(self, name, x_pos, timeline):
        """타임라인 특정 위치 클릭 (직접 메서드 호출)"""
        # 클릭 전 위치 저장
        before_pos = self.last_seek_position or 0

        # _seek_to_x 직접 호출 (클릭 시뮬레이션 대신)
        expected_ms = int(timeline._x_to_ms(x_pos))
        self.last_seek_position = None  # 리셋
        timeline._seek_to_x(x_pos)

        # 대기
        QTest.qWait(50)

        # 클릭 후 위치 (seek_requested로 전달된 값 확인)
        after_pos = self.last_seek_position if self.last_seek_position is not None else 0

        # 결과 기록
        passed = after_pos != 0 or x_pos < 20  # 맨 왼쪽 클릭은 0ms 허용
        result = {
            "name": name,
            "x_pos": x_pos,
            "before_pos": before_pos,
            "after_pos": after_pos,
            "passed": passed
        }
        self.test_results.append(result)

        # 즉시 출력
        status = "✓" if passed else "❌"
        print(f"{status} {name:12} | X={x_pos:4}px | {before_pos:5}ms → {after_pos:5}ms")

    def _print_results(self):
        """테스트 결과 요약"""
        print("\n" + "="*60)
        print("📊 테스트 결과 요약")
        print("="*60)

        passed = sum(1 for r in self.test_results if r["passed"])
        total = len(self.test_results)

        print(f"통과: {passed}/{total}")

        # 실패한 테스트만 표시
        failed = [r for r in self.test_results if not r["passed"]]
        if failed:
            print("\n❌ 실패한 테스트:")
            for r in failed:
                print(f"  - {r['name']}: {r['before_pos']}ms → {r['after_pos']}ms (0ms로 이동!)")
        else:
            print("\n✅ 모든 테스트 통과!")

        print("="*60)


def main():
    try:
        tester = TimelineClickTester()
        success = tester.run_tests()

        # 종료
        QTimer.singleShot(1000, tester.app.quit)

        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"\n❌ 테스트 중 에러 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
