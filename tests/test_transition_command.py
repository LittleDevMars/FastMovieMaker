import pytest
from src.models.project import ProjectState
from src.models.video_clip import VideoClip, TransitionInfo
from src.ui.commands import EditTransitionCommand
from src.models.subtitle import SubtitleSegment

def test_edit_transition_ripple():
    project = ProjectState()
    # Assume video_tracks[0] is the default track
    vt = project.video_tracks[0]
    
    # Clip A: 0-1000
    clip_a = VideoClip(0, 1000) # duration 1000
    vt.clips.append(clip_a)
    # Clip B: 1000-2000
    clip_b = VideoClip(0, 1000) # duration 1000
    vt.clips.append(clip_b)
    
    # Subtitle at 1500 (inside Clip B)
    sub = SubtitleSegment(1500, 1800, "Test")
    project.subtitle_track.segments.append(sub)
    
    # Current state: Total duration 2000, Sub at 1500
    assert vt.output_duration_ms == 2000
    
    # Apply transition of 500ms to Clip A (A overlaps B by 500ms)
    new_info = TransitionInfo(type="fade", duration_ms=500)
    # track_idx=0, clip_idx=0
    cmd = EditTransitionCommand(project, 0, 0, new_info, ripple=True)
    cmd.redo()
    
    # Total duration should shrink by 500ms (1000 + 1000 - 500 = 1500)
    assert vt.output_duration_ms == 1500
    
    # Subtitle should shift left by 500ms (1500 - 500 = 1000)
    assert sub.start_ms == 1000
    assert sub.end_ms == 1300
    
    # Undo
    cmd.undo()
    assert vt.output_duration_ms == 2000
    assert sub.start_ms == 1500
    assert clip_a.transition_out is None

def test_edit_transition_modify_ripple():
    project = ProjectState()
    vt = project.video_tracks[0]
    
    clip_a = VideoClip(0, 1000)
    clip_a.transition_out = TransitionInfo(duration_ms=200)
    vt.clips.append(clip_a)
    
    clip_b = VideoClip(0, 1000)
    vt.clips.append(clip_b)
    
    # duration = 1000 + 1000 - 200 = 1800
    assert vt.output_duration_ms == 1800
    
    sub = SubtitleSegment(1500, 1800, "Test")
    project.subtitle_track.segments.append(sub)
    
    # Change transition to 500ms (extra 300ms overlap -> extra 300ms shrink)
    new_info = TransitionInfo(duration_ms=500)
    cmd = EditTransitionCommand(project, 0, 0, new_info, ripple=True)
    cmd.redo()
    
    assert vt.output_duration_ms == 1500
    # 1500 - 300 = 1200
    assert sub.start_ms == 1200
    
    cmd.undo()
    assert vt.output_duration_ms == 1800
    assert sub.start_ms == 1500
