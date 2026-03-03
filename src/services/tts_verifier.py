"""TTS 타이밍 검증 서비스.

TTS로 생성된 오디오를 Whisper로 재전사하여, 원본 자막 트랙의
타이밍(start_ms/end_ms)을 difflib 텍스트 매핑으로 자동 보정한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List

from src.models.subtitle import SubtitleTrack


@dataclass(slots=True)
class CorrectionResult:
    """단일 세그먼트의 타이밍 보정 결과."""

    seg_index: int       # 원본 트랙에서의 인덱스
    old_start_ms: int
    old_end_ms: int
    new_start_ms: int
    new_end_ms: int
    confidence: float    # 0.0~1.0 (0.0 = 변경 없음)


class TtsVerifier:
    """Whisper 재전사 결과와 원본 트랙을 비교해 타이밍을 보정한다."""

    # 'replace' 블록에서 타이밍 보정을 수행할 최소 유사도
    _SIMILARITY_THRESHOLD: float = 0.6

    @staticmethod
    def verify_and_align(
        original: SubtitleTrack,
        whisper: SubtitleTrack,
    ) -> List[CorrectionResult]:
        """원본 트랙과 Whisper 재전사 트랙을 비교해 타이밍 보정 목록을 반환한다.

        Args:
            original: 보정 대상 원본 자막 트랙.
            whisper:  TTS 오디오를 Whisper로 재전사한 트랙.

        Returns:
            confidence > 0.0 인 CorrectionResult 목록 (변경이 없으면 빈 리스트).
        """
        if not original.segments or not whisper.segments:
            return []

        orig_texts = [s.text.strip() for s in original.segments]
        whis_texts = [s.text.strip() for s in whisper.segments]

        matcher = SequenceMatcher(None, orig_texts, whis_texts, autojunk=False)
        corrections: List[CorrectionResult] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                # 텍스트 동일 → Whisper 타이밍 직접 사용 (confidence=1.0)
                for offset in range(i2 - i1):
                    orig_seg = original.segments[i1 + offset]
                    whis_seg = whisper.segments[j1 + offset]
                    if (orig_seg.start_ms != whis_seg.start_ms
                            or orig_seg.end_ms != whis_seg.end_ms):
                        corrections.append(CorrectionResult(
                            seg_index=i1 + offset,
                            old_start_ms=orig_seg.start_ms,
                            old_end_ms=orig_seg.end_ms,
                            new_start_ms=whis_seg.start_ms,
                            new_end_ms=whis_seg.end_ms,
                            confidence=1.0,
                        ))

            elif tag == "replace":
                # 텍스트 다름 → 1:1 매핑 가능한 범위에서 유사도 검사
                orig_block = original.segments[i1:i2]
                whis_block = whisper.segments[j1:j2]

                for idx, orig_seg in enumerate(orig_block):
                    if idx >= len(whis_block):
                        break
                    whis_seg = whis_block[idx]
                    ratio = SequenceMatcher(
                        None, orig_seg.text.strip(), whis_seg.text.strip()
                    ).ratio()
                    if ratio >= TtsVerifier._SIMILARITY_THRESHOLD:
                        if (orig_seg.start_ms != whis_seg.start_ms
                                or orig_seg.end_ms != whis_seg.end_ms):
                            corrections.append(CorrectionResult(
                                seg_index=i1 + idx,
                                old_start_ms=orig_seg.start_ms,
                                old_end_ms=orig_seg.end_ms,
                                new_start_ms=whis_seg.start_ms,
                                new_end_ms=whis_seg.end_ms,
                                confidence=ratio,
                            ))
            # 'insert' / 'delete' → 매핑 불가, 원본 타이밍 유지 (confidence=0.0)

        return corrections
