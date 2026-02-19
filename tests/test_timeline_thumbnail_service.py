"""TimelineThumbnailService 단위 테스트 — 캐시 히트/미스, LRU 퇴거, 중복 요청 방지."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import collections

import pytest


# ---------------------------------------------------------------------------
# Helpers — Qt 없이 서비스만 테스트하기 위한 최소 픽스처
# ---------------------------------------------------------------------------

def _make_service(cache_size: int = 5):
    """Qt 없이 TimelineThumbnailService 인스턴스를 생성한다.

    QObject.__init__ 및 QThreadPool은 mock으로 대체.
    """
    from src.services.timeline_thumbnail_service import TimelineThumbnailService

    with (
        patch("src.services.timeline_thumbnail_service.QObject.__init__", return_value=None),
        patch("src.services.timeline_thumbnail_service.QThreadPool"),
    ):
        svc = TimelineThumbnailService.__new__(TimelineThumbnailService)
        svc._cache = collections.OrderedDict()
        svc._cache_size = cache_size
        svc._pending_requests = set()
        svc._thread_pool = MagicMock()
        # thumbnail_ready는 실제 Signal이 아니므로 mock 처리
        svc.thumbnail_ready = MagicMock()

    return svc


def _fake_image(label: str = "img"):
    """테스트용 가짜 QImage."""
    img = MagicMock()
    img.isNull.return_value = False
    img.__repr__ = lambda self: label
    return img


# ---------------------------------------------------------------------------
# 캐시 히트
# ---------------------------------------------------------------------------

class TestCacheHit:
    def test_cached_thumbnail_returned_immediately(self):
        svc = _make_service()
        img = _fake_image("A")
        key = ("video.mp4", 1000)
        svc._cache[key] = img

        result = svc.request_thumbnail("video.mp4", 1000, 80)

        assert result is img

    def test_cache_hit_moves_to_end_for_lru(self):
        """캐시 히트 시 해당 항목이 LRU 맨 뒤로 이동해야 한다."""
        svc = _make_service()
        img_a = _fake_image("A")
        img_b = _fake_image("B")
        svc._cache[("v.mp4", 0)] = img_a
        svc._cache[("v.mp4", 1000)] = img_b

        # A를 다시 요청 → A가 맨 뒤로 이동
        svc.request_thumbnail("v.mp4", 0, 80)

        keys = list(svc._cache.keys())
        assert keys[-1] == ("v.mp4", 0), "최근 히트된 항목이 LRU 맨 뒤여야 함"

    def test_cache_hit_does_not_start_worker(self):
        svc = _make_service()
        img = _fake_image()
        svc._cache[("v.mp4", 500)] = img

        svc.request_thumbnail("v.mp4", 500, 80)

        svc._thread_pool.start.assert_not_called()


# ---------------------------------------------------------------------------
# 캐시 미스
# ---------------------------------------------------------------------------

class TestCacheMiss:
    def test_cache_miss_returns_none(self):
        svc = _make_service()
        result = svc.request_thumbnail("video.mp4", 2000, 80)
        assert result is None

    def test_cache_miss_starts_worker(self):
        svc = _make_service()

        with patch("src.services.timeline_thumbnail_service.ThumbnailRunnable") as MockRunnable:
            mock_worker = MagicMock()
            mock_worker.signals = MagicMock()
            MockRunnable.return_value = mock_worker

            svc.request_thumbnail("video.mp4", 3000, 80)

        svc._thread_pool.start.assert_called_once()

    def test_cache_miss_adds_to_pending(self):
        svc = _make_service()

        with patch("src.services.timeline_thumbnail_service.ThumbnailRunnable") as MockRunnable:
            mock_worker = MagicMock()
            mock_worker.signals = MagicMock()
            MockRunnable.return_value = mock_worker

            svc.request_thumbnail("video.mp4", 4000, 80)

        assert ("video.mp4", 4000) in svc._pending_requests


# ---------------------------------------------------------------------------
# 중복 요청 방지
# ---------------------------------------------------------------------------

class TestDuplicateRequestPrevention:
    def test_pending_request_not_duplicated(self):
        svc = _make_service()
        svc._pending_requests.add(("video.mp4", 5000))

        with patch("src.services.timeline_thumbnail_service.ThumbnailRunnable") as MockRunnable:
            result = svc.request_thumbnail("video.mp4", 5000, 80)

        assert result is None
        MockRunnable.assert_not_called()
        svc._thread_pool.start.assert_not_called()

    def test_multiple_same_requests_only_one_worker(self):
        svc = _make_service()

        with patch("src.services.timeline_thumbnail_service.ThumbnailRunnable") as MockRunnable:
            mock_worker = MagicMock()
            mock_worker.signals = MagicMock()
            MockRunnable.return_value = mock_worker

            svc.request_thumbnail("video.mp4", 6000, 80)
            svc.request_thumbnail("video.mp4", 6000, 80)  # 두 번째 — 무시되어야 함

        assert svc._thread_pool.start.call_count == 1


# ---------------------------------------------------------------------------
# LRU 퇴거
# ---------------------------------------------------------------------------

class TestLruEviction:
    def test_eviction_when_cache_full(self):
        svc = _make_service(cache_size=3)
        for i in range(3):
            svc._cache[("v.mp4", i * 1000)] = _fake_image(f"img{i}")

        oldest_key = ("v.mp4", 0)
        assert oldest_key in svc._cache

        # _on_thumbnail_ready 직접 호출 → 4번째 항목 추가
        new_img = _fake_image("new")
        svc._on_thumbnail_ready("v.mp4", 9999, new_img)

        assert ("v.mp4", 9999) in svc._cache
        assert oldest_key not in svc._cache, "가장 오래된 항목이 퇴거되어야 함"
        assert len(svc._cache) == 3

    def test_cache_size_never_exceeded(self):
        svc = _make_service(cache_size=5)
        for i in range(10):
            svc._on_thumbnail_ready("v.mp4", i * 1000, _fake_image(f"img{i}"))

        assert len(svc._cache) <= 5


# ---------------------------------------------------------------------------
# _on_thumbnail_ready — 정상 완료 흐름
# ---------------------------------------------------------------------------

class TestOnThumbnailReady:
    def test_image_stored_in_cache(self):
        svc = _make_service()
        img = _fake_image()
        svc._on_thumbnail_ready("v.mp4", 1234, img)

        assert ("v.mp4", 1234) in svc._cache
        assert svc._cache[("v.mp4", 1234)] is img

    def test_pending_cleared_on_ready(self):
        svc = _make_service()
        svc._pending_requests.add(("v.mp4", 777))

        svc._on_thumbnail_ready("v.mp4", 777, _fake_image())

        assert ("v.mp4", 777) not in svc._pending_requests

    def test_thumbnail_ready_signal_emitted(self):
        svc = _make_service()
        img = _fake_image()
        svc._on_thumbnail_ready("v.mp4", 555, img)

        svc.thumbnail_ready.emit.assert_called_once_with("v.mp4", 555, img)


# ---------------------------------------------------------------------------
# clear / cancel
# ---------------------------------------------------------------------------

class TestClearAndCancel:
    def test_clear_cache(self):
        svc = _make_service()
        svc._cache[("v.mp4", 0)] = _fake_image()
        svc._pending_requests.add(("v.mp4", 1000))

        svc.clear_cache()

        assert len(svc._cache) == 0
        assert len(svc._pending_requests) == 0

    def test_cancel_all_requests(self):
        svc = _make_service()
        svc._pending_requests.add(("v.mp4", 2000))

        svc.cancel_all_requests()

        assert len(svc._pending_requests) == 0
        svc._thread_pool.clear.assert_called_once()
