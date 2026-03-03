"""tests/test_tts_verifier.py — TtsVerifier + ApplyTTSVerificationCommand 단위 테스트."""

from __future__ import annotations

import pytest

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.tts_verifier import CorrectionResult, TtsVerifier


# ─────────────────────── 헬퍼 ───────────────────────

def make_track(*segments: tuple[int, int, str]) -> SubtitleTrack:
    """(start_ms, end_ms, text) 튜플 목록으로 SubtitleTrack 생성."""
    track = SubtitleTrack()
    for start, end, text in segments:
        track.add_segment(SubtitleSegment(start, end, text))
    return track


# ─────────────────────── CorrectionResult ───────────────────────

class TestCorrectionResult:
    def test_correction_result_fields(self):
        cr = CorrectionResult(
            seg_index=2,
            old_start_ms=100,
            old_end_ms=500,
            new_start_ms=120,
            new_end_ms=510,
            confidence=0.9,
        )
        assert cr.seg_index == 2
        assert cr.old_start_ms == 100
        assert cr.old_end_ms == 500
        assert cr.new_start_ms == 120
        assert cr.new_end_ms == 510
        assert cr.confidence == pytest.approx(0.9)


# ─────────────────────── TtsVerifier.verify_and_align ───────────────────────

class TestVerifyAndAlign:
    def test_verify_exact_match_1to1(self):
        """텍스트가 동일하면 Whisper 타이밍으로 교체된다."""
        original = make_track((0, 1000, "안녕하세요"), (1000, 2000, "반갑습니다"))
        whisper = make_track((50, 980, "안녕하세요"), (1020, 1990, "반갑습니다"))

        corrections = TtsVerifier.verify_and_align(original, whisper)
        assert len(corrections) == 2
        assert corrections[0].new_start_ms == 50
        assert corrections[0].new_end_ms == 980
        assert corrections[0].confidence == pytest.approx(1.0)
        assert corrections[1].new_start_ms == 1020

    def test_verify_no_change_when_timing_matches(self):
        """타이밍이 이미 동일하면 보정 결과가 없다."""
        original = make_track((0, 1000, "hello"))
        whisper = make_track((0, 1000, "hello"))

        corrections = TtsVerifier.verify_and_align(original, whisper)
        assert corrections == []

    def test_verify_no_match_keeps_original(self):
        """텍스트가 완전히 다르면 보정하지 않는다."""
        original = make_track((0, 1000, "AAAA"))
        whisper = make_track((200, 800, "ZZZZ"))

        corrections = TtsVerifier.verify_and_align(original, whisper)
        # ratio("AAAA","ZZZZ") = 0.0 < 0.6 → 보정 없음
        assert corrections == []

    def test_verify_empty_whisper(self):
        """Whisper 트랙이 비어있으면 빈 목록."""
        original = make_track((0, 1000, "hello"))
        whisper = SubtitleTrack()
        corrections = TtsVerifier.verify_and_align(original, whisper)
        assert corrections == []

    def test_verify_empty_original(self):
        """원본 트랙이 비어있으면 빈 목록."""
        original = SubtitleTrack()
        whisper = make_track((0, 1000, "hello"))
        corrections = TtsVerifier.verify_and_align(original, whisper)
        assert corrections == []

    def test_verify_partial_match(self):
        """일부 세그먼트만 매핑된다."""
        original = make_track(
            (0, 1000, "안녕"),
            (1000, 2000, "완전히 다른 텍스트 ZZZZ"),
        )
        whisper = make_track(
            (50, 950, "안녕"),
            (1010, 1990, "완전히 다른 텍스트 ZZZZ"),
        )
        corrections = TtsVerifier.verify_and_align(original, whisper)
        # 두 세그먼트 모두 동일 텍스트 → equal 블록 → 타이밍 변경됨
        assert len(corrections) == 2

    def test_verify_similar_text_corrects(self):
        """유사도 > 0.6 인 텍스트는 replace 블록에서 보정된다."""
        # "안녕하세요" vs "안녕하셔요" — ratio > 0.6
        original = make_track((0, 1000, "안녕하세요"))
        whisper = make_track((80, 920, "안녕하셔요"))

        corrections = TtsVerifier.verify_and_align(original, whisper)
        assert len(corrections) == 1
        assert corrections[0].new_start_ms == 80
        assert corrections[0].confidence > 0.6

    def test_verify_dissimilar_text_skipped(self):
        """유사도 < 0.6 인 텍스트는 보정하지 않는다."""
        # "AAAA" vs "ZZZZ" — ratio = 0.0
        original = make_track((0, 1000, "AAAA"))
        whisper = make_track((200, 800, "ZZZZ"))

        corrections = TtsVerifier.verify_and_align(original, whisper)
        assert corrections == []

    def test_verify_multiple_segments_all_equal(self):
        """여러 세그먼트가 모두 동일 텍스트일 때 전부 보정된다."""
        texts = ["첫 번째", "두 번째", "세 번째"]
        orig_segs = [(i * 1000, i * 1000 + 900, t) for i, t in enumerate(texts)]
        whis_segs = [(i * 1000 + 50, i * 1000 + 880, t) for i, t in enumerate(texts)]

        original = make_track(*orig_segs)
        whisper = make_track(*whis_segs)

        corrections = TtsVerifier.verify_and_align(original, whisper)
        assert len(corrections) == 3


# ─────────────────────── ApplyTTSVerificationCommand ───────────────────────

class TestApplyTTSVerificationCommand:
    def test_apply_command_redo(self):
        """redo() 호출 시 new_start/end 가 적용된다."""
        from src.ui.commands import ApplyTTSVerificationCommand

        track = make_track((0, 1000, "테스트"))
        corrections = [
            CorrectionResult(
                seg_index=0,
                old_start_ms=0, old_end_ms=1000,
                new_start_ms=50, new_end_ms=950,
                confidence=1.0,
            )
        ]
        cmd = ApplyTTSVerificationCommand(track, corrections)
        cmd.redo()

        assert track.segments[0].start_ms == 50
        assert track.segments[0].end_ms == 950

    def test_apply_command_undo(self):
        """undo() 호출 시 old_start/end 가 복원된다."""
        from src.ui.commands import ApplyTTSVerificationCommand

        track = make_track((0, 1000, "테스트"))
        corrections = [
            CorrectionResult(
                seg_index=0,
                old_start_ms=0, old_end_ms=1000,
                new_start_ms=50, new_end_ms=950,
                confidence=1.0,
            )
        ]
        cmd = ApplyTTSVerificationCommand(track, corrections)
        cmd.redo()
        cmd.undo()

        assert track.segments[0].start_ms == 0
        assert track.segments[0].end_ms == 1000

    def test_apply_command_multiple(self):
        """여러 세그먼트를 일괄 적용한다."""
        from src.ui.commands import ApplyTTSVerificationCommand

        track = make_track(
            (0, 1000, "첫"),
            (1000, 2000, "둘"),
            (2000, 3000, "셋"),
        )
        corrections = [
            CorrectionResult(0, 0, 1000, 20, 980, 1.0),
            CorrectionResult(2, 2000, 3000, 2050, 2950, 1.0),
        ]
        cmd = ApplyTTSVerificationCommand(track, corrections)
        cmd.redo()

        assert track.segments[0].start_ms == 20
        assert track.segments[1].start_ms == 1000   # 변경 없음
        assert track.segments[2].start_ms == 2050

        cmd.undo()
        assert track.segments[0].start_ms == 0
        assert track.segments[2].start_ms == 2000


# ─────────────────────── i18n ───────────────────────

class TestVerifyI18nKeys:
    def test_verify_i18n_keys(self):
        """P2a i18n 키가 ko.py에 존재한다."""
        from src.utils.lang.ko import STRINGS

        required_keys = [
            "Verify TTS Timing\u2026",
            "TTS Timing Verification",
            "Whisper Model:",
            "Start Verification",
            "No corrections found",
            "Apply Corrections",
            "Apply TTS verification",
        ]
        for key in required_keys:
            assert key in STRINGS, f"Missing i18n key: {key!r}"
