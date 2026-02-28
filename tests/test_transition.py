"""트랜지션 기능 단위 테스트.

TransitionService 메서드, xfade/acrossfade 필터 형식, 제거 커맨드,
클램핑 버그 방지, i18n 키를 검증합니다.

실행:
    pytest tests/test_transition.py -v
"""
import pytest
from src.models.project import ProjectState
from src.models.video_clip import VideoClip, TransitionInfo
from src.services.transition_service import TransitionService
from src.services.video_exporter import _build_concat_filter
from src.ui.commands import EditTransitionCommand


# ── TransitionService 메서드 ──────────────────────────────────────────────────

def test_available_transitions_contains_fade():
    """get_available_transitions()에 'fade'가 포함되어야 합니다."""
    transitions = TransitionService.get_available_transitions()
    assert "fade" in transitions


def test_build_xfade_filter_format():
    """build_xfade_filter 반환 문자열이 xfade= 를 포함해야 합니다."""
    result = TransitionService.build_xfade_filter(
        clip_a_name="[v0]",
        clip_b_name="[v1]",
        clip_a_duration_sec=2.0,
        transition_type="fade",
        duration_sec=0.5,
    )
    assert "xfade=" in result
    assert "transition=fade" in result
    assert "duration=0.5" in result


def test_build_xfade_offset_calculation():
    """offset = clip_a_duration - transition_duration 을 검증합니다."""
    result = TransitionService.build_xfade_filter(
        clip_a_name="[v0]",
        clip_b_name="[v1]",
        clip_a_duration_sec=3.0,
        transition_type="dissolve",
        duration_sec=1.0,
    )
    # offset 값은 3.0 - 1.0 = 2.0 이어야 합니다
    assert "offset=2.0" in result


def test_build_acrossfade_filter_format():
    """build_acrossfade_filter 반환 문자열이 acrossfade= 를 포함해야 합니다."""
    result = TransitionService.build_acrossfade_filter(
        audio_a_name="[a0]",
        audio_b_name="[a1]",
        duration_sec=0.5,
    )
    assert "acrossfade=" in result
    assert "d=0.5" in result


# ── _build_concat_filter 검증 ─────────────────────────────────────────────────

def _make_clips(*durations_ms: int) -> list:
    """지정된 길이(ms)의 VideoClip 목록을 생성합니다."""
    clips = []
    for dur in durations_ms:
        c = VideoClip(source_in_ms=0, source_out_ms=dur)
        clips.append(c)
    return clips


def test_concat_with_transition_has_xfade():
    """트랜지션이 있으면 _build_concat_filter에 xfade 필터가 포함되어야 합니다."""
    clips = _make_clips(2000, 2000)
    clips[0].transition_out = TransitionInfo(type="fade", duration_ms=500)

    parts, v_label, a_label = _build_concat_filter(clips)

    combined = " ".join(parts)
    assert "xfade" in combined
    assert "transition=fade" in combined
    assert v_label == "[concatv]"
    assert a_label == "[concata]"


def test_concat_transition_clamp_prevents_negative_offset():
    """트랜지션 길이 > 클립 길이일 때 offset이 0 이상이어야 합니다 (클램핑 버그 방지)."""
    clips = _make_clips(300, 300)  # 클립 A: 300ms
    # 트랜지션을 클립보다 크게 설정 (500ms > 300ms)
    clips[0].transition_out = TransitionInfo(type="fade", duration_ms=500)

    parts, _, _ = _build_concat_filter(clips)

    # offset= 값을 파싱해서 음수가 없는지 확인
    for part in parts:
        if "xfade" in part and "offset=" in part:
            offset_str = part.split("offset=")[1].split(":")[0].split("[")[0]
            offset_val = float(offset_str)
            assert offset_val >= 0.0, f"offset이 음수입니다: {offset_val}"


def test_concat_transition_clamp_min_1ms():
    """극단적 케이스: 트랜지션 길이가 클립 길이보다 훨씬 커도 최소 1ms 유지."""
    clips = _make_clips(100, 100)  # 매우 짧은 클립
    clips[0].transition_out = TransitionInfo(type="fade", duration_ms=10000)

    parts, _, _ = _build_concat_filter(clips)

    # duration= 값이 0이 아닌지 확인
    for part in parts:
        if "xfade" in part and "duration=" in part:
            dur_str = part.split("duration=")[1].split(":")[0]
            dur_val = float(dur_str)
            assert dur_val > 0.0, f"duration이 0 이하입니다: {dur_val}"


def test_concat_no_transition_uses_fallback():
    """트랜지션이 없을 때 fallback xfade(duration=0.001)가 사용되어야 합니다."""
    clips = _make_clips(2000, 2000)
    # transition_out 없음

    parts, _, _ = _build_concat_filter(clips)

    combined = " ".join(parts)
    assert "xfade" in combined
    assert "duration=0.001" in combined  # fallback


# ── Remove Transition Command ─────────────────────────────────────────────────

def _make_project_with_two_clips(clip_a_dur=1000, clip_b_dur=1000, trans_dur=500):
    """트랜지션이 적용된 2개 클립 프로젝트를 반환합니다."""
    project = ProjectState()
    vt = project.video_tracks[0]
    clip_a = VideoClip(0, clip_a_dur)
    clip_a.transition_out = TransitionInfo(type="fade", duration_ms=trans_dur)
    clip_b = VideoClip(0, clip_b_dur)
    vt.clips.append(clip_a)
    vt.clips.append(clip_b)
    return project, vt, clip_a


def test_remove_transition_command():
    """EditTransitionCommand(None) 실행 시 transition_out이 None이 되어야 합니다."""
    project, vt, clip_a = _make_project_with_two_clips(1000, 1000, 500)

    # 제거 전: transition_out이 있음
    assert clip_a.transition_out is not None
    before_dur = vt.output_duration_ms  # 1000 + 1000 - 500 = 1500

    cmd = EditTransitionCommand(project, 0, 0, None, ripple=False)
    cmd.redo()

    assert clip_a.transition_out is None
    # ripple=False이므로 duration은 변하지 않음
    # (clip 길이는 그대로지만 transition_out이 None이므로 output_duration_ms가 변함)
    assert vt.output_duration_ms == 2000  # 1000 + 1000


def test_remove_transition_undo():
    """undo() 시 transition_out이 복원되어야 합니다."""
    project, vt, clip_a = _make_project_with_two_clips(1000, 1000, 500)

    original_info = clip_a.transition_out
    cmd = EditTransitionCommand(project, 0, 0, None, ripple=False)
    cmd.redo()

    assert clip_a.transition_out is None

    cmd.undo()

    assert clip_a.transition_out is not None
    assert clip_a.transition_out.duration_ms == original_info.duration_ms
    assert clip_a.transition_out.type == original_info.type
    assert vt.output_duration_ms == 1500  # 원래 상태로 복원


def test_remove_transition_ripple():
    """ripple=True 시 제거 후 자막이 앞으로 이동해야 합니다."""
    from src.models.subtitle import SubtitleSegment

    project, vt, clip_a = _make_project_with_two_clips(1000, 1000, 500)
    # duration = 1500, 자막을 1200ms에 배치
    sub = SubtitleSegment(1200, 1400, "Test")
    project.subtitle_track.segments.append(sub)

    # 트랜지션 제거 (ripple=True) → 500ms 복원 → 자막 +500ms 이동
    cmd = EditTransitionCommand(project, 0, 0, None, ripple=True)
    cmd.redo()

    assert clip_a.transition_out is None
    assert sub.start_ms == 1700  # 1200 + 500
    assert sub.end_ms == 1900    # 1400 + 500


# ── i18n ──────────────────────────────────────────────────────────────────────

def test_remove_transition_i18n_ko():
    """한국어 번역에 'Remove Transition' 키가 있어야 합니다."""
    from src.utils.lang.ko import STRINGS

    assert "Remove Transition" in STRINGS
    assert STRINGS["Remove Transition"] == "트랜지션 제거"


def test_remove_transition_i18n_tr_ko():
    """한국어 모드에서 tr('Remove Transition')이 번역을 반환해야 합니다."""
    from src.utils.i18n import init_language, tr

    init_language("ko")
    assert tr("Remove Transition") == "트랜지션 제거"

    # 테스트 격리: 영어로 복원
    init_language("en")


def test_remove_transition_i18n_tr_en():
    """영어 모드에서 tr('Remove Transition')이 키 자체를 반환해야 합니다."""
    from src.utils.i18n import init_language, tr

    init_language("en")
    assert tr("Remove Transition") == "Remove Transition"
