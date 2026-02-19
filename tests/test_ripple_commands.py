
from src.models.video_clip import VideoClip, VideoClipTrack
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.models.image_overlay import ImageOverlay, ImageOverlayTrack
from src.models.project import ProjectState
from src.ui.commands import DeleteClipCommand, TrimClipCommand, AddVideoClipCommand

class TestRippleCommands:
    def setup_method(self):
        # 3 Clips: 0-1000, 1000-2000, 2000-3000 (Duration 1000 each)
        self.clip_track = VideoClipTrack()
        self.c1 = VideoClip(0, 1000, "c1.mp4")
        self.c2 = VideoClip(0, 1000, "c2.mp4")
        self.c3 = VideoClip(0, 1000, "c3.mp4")
        self.clip_track.clips = [self.c1, self.c2, self.c3]
        
        self.sub_track = SubtitleTrack()
        # s1: inside c1
        self.s1 = SubtitleSegment(100, 900, "s1")
        # s2: inside c2
        self.s2 = SubtitleSegment(1100, 1900, "s2")
        # s3: inside c3
        self.s3 = SubtitleSegment(2100, 2900, "s3")
        # s4: overlaps c2 and c3 boundary (1900 - 2100)
        self.s4 = SubtitleSegment(1900, 2100, "s4")
        
        self.sub_track.segments = [self.s1, self.s2, self.s3, self.s4]
        
        self.overlay_track = ImageOverlayTrack()
        # o1: inside c2
        self.o1 = ImageOverlay(1200, 1800, "o1.png")
        self.overlay_track.overlays = [self.o1]

        # ProjectState wrapping the clip_track (needed by new Command API)
        self.project = ProjectState()
        self.project.video_tracks = [self.clip_track]
        self.project.subtitle_tracks = [self.sub_track]
        self.project.image_overlay_track = self.overlay_track

    def test_delete_clip_ripple(self):
        # Delete c2 (index 1, time 1000-2000). Duration 1000.
        # Expected:
        # c1 remains. c3 shifts to 1000-2000.
        # s1 (100-900) -> Unchanged
        # s2 (1100-1900) -> Removed (fully inside deleted region)
        # s3 (2100-2900) -> Shifted -1000 -> 1100-1900
        # s4 (1900-2100) -> Truncated?
        #   Original s4 spans 1900-2100. Deleted region is 1000-2000.
        #   Part inside (1900-2000) removed.
        #   Part outside (2000-2100) remains, shifted by -1000?
        #   Wait, timeline logic:
        #   Items after cut point (2000) shift left by 1000.
        #   s4 ends at 2100. 2100 is after 2000.
        #   s4 starts at 1900. 1900 is inside 1000-2000.
        #   So s4 is partially deleted.
        #   New s4 should start at 1000 (cut point) and end at 2100-1000=1100?
        #   Let's check logic in DeleteClipCommand:
        #   if overlap start but not end (start < end and end > start):
        #     truncated.
        #   s4: start 1900, end 2100. Clip: 1000-2000.
        #   Overlap: Yes. 
        #   Logic:
        #     start 1900 is < 2000. end 2100 > 1000.
        #     "elif seg.start_ms < self._clip_end and seg.end_ms > self._clip_start:"
        #     Trims.
        #     if 1900 < 1000: ...
        #     else: start = 1000, end = 2100 - 1000 = 1100.
        #     Correct. New s4: 1000-1100.
        
        cmd = DeleteClipCommand(
            self.project, 0, 1, self.c2,
            self.sub_track, self.overlay_track,
            1000, 2000, ripple=True
        )
        cmd.redo()
        
        assert len(self.clip_track.clips) == 2
        assert self.clip_track.clips[0] == self.c1
        assert self.clip_track.clips[1] == self.c3
        
        # Check subtitles
        # s1 unchanged
        assert self.s1 in self.sub_track.segments
        assert self.s1.start_ms == 100
        assert self.s1.end_ms == 900
        
        # s2 removed
        assert self.s2 not in self.sub_track.segments
        
        # s3 shifted
        assert self.s3 in self.sub_track.segments
        assert self.s3.start_ms == 1100
        assert self.s3.end_ms == 1900
        
        # s4 truncated/shifted
        assert self.s4 in self.sub_track.segments
        assert self.s4.start_ms == 1000
        assert self.s4.end_ms == 1100
        
        # Check overlay
        # o1 (1200-1800) inside deleted region -> Removed
        assert self.o1 not in self.overlay_track.overlays
        
        # UNDO
        cmd.undo()
        
        assert len(self.clip_track.clips) == 3
        assert self.c2 in self.clip_track.clips
        
        assert self.s2 in self.sub_track.segments
        assert self.s2.start_ms == 1100
        assert self.s2.end_ms == 1900
        
        assert self.s3.start_ms == 2100
        assert self.s3.end_ms == 2900
        
        assert self.s4.start_ms == 1900
        assert self.s4.end_ms == 2100
        
        assert self.o1 in self.overlay_track.overlays
        assert self.o1.start_ms == 1200
        
    def test_trim_clip_ripple(self):
        # Trim c1 end by -500 (duration 1000 -> 500).
        # Old out: 1000. New out: 500. Delta: -500.
        # Ripple point: 1000? Or 500?
        # Logic: self._ripple_point = self._clip_start_tl + old_duration = 0 + 1000 = 1000.
        # All items >= 1000 shift by -500.
        
        cmd = TrimClipCommand(
            self.project, 0, 0,
            0, 1000, 0, 500,
            self.sub_track, self.overlay_track,
            ripple=True
        )
        cmd.redo()
        
        assert self.c1.source_out_ms == 500
        
        # s1 (100-900). Start < 1000. 
        # Wait, if I trim the clip, the content AFTER the trim point is gone.
        # The clip itself becomes shorter.
        # Items *overlapping* the removed part of the clip?
        # TrimClipCommand logic:
        #   if start >= ripple_point: shift
        #   It does NOT remove items inside the trimmed-away portion of the clip automatically?
        #   Let's check code.
        #   _apply_shift just shifts items >= ripple_point.
        #   It does NOT check for overlaps.
        #   So s1 (100-900) stays 100-900?
        #   But c1 now ends at 500.
        #   So s1 is now hanging after c1 ends (in c2's new time?).
        #   c1: 0-500. c2 starts at 500.
        #   s1 is 100-900.
        #   s2 (was 1100-1900) >= 1000 -> shifts by -500 -> 600-1400.
        #   o1 (1200-1800) -> shifts to 700-1300.
        
        # Limitation: TrimClipCommand currently only shifts items *after* the clip.
        # It implies items *synced* to the clip (inside it) stay relative to *timeline*?
        # No, s1 is at 100-900 relative to timeline.
        # If I trim c1 to 500, c2 moves to 500.
        # s1 (100-900) now overlaps c1 (0-500) and c2 (500-1500).
        # This is standard NLE behavior (items don't get deleted just because underlying clip shortens, unless they are linked).
        # So s1 should be unchanged.
        # s2 (starts 1100 > 1000) should shift.
        
        assert self.s1.start_ms == 100
        assert self.s1.end_ms == 900
        
        assert self.s2.start_ms == 1100 - 500 # 600
        assert self.s2.end_ms == 1900 - 500 # 1400
        
        assert self.o1.start_ms == 1200 - 500 # 700
        
        cmd.undo()
        assert self.c1.source_out_ms == 1000
        assert self.s2.start_ms == 1100
        assert self.o1.start_ms == 1200

    def test_add_clip_ripple(self):
        # Insert new clip at index 1 (between c1 and c2). Duration 500.
        new_clip = VideoClip(0, 500, "new.mp4")
        
        cmd = AddVideoClipCommand(
            self.project, 0, new_clip,
            self.sub_track, self.overlay_track,
            1, ripple=True
        )
        cmd.redo()
        
        # c1 (0-1000), new (1000-1500), c2 (1500-2500), c3...
        assert len(self.clip_track.clips) == 4
        assert self.clip_track.clips[1] == new_clip
        
        # ripple point: 1000 (end of c1).
        # s1 (100-900) < 1000 -> Unchanged.
        assert self.s1.start_ms == 100
        
        # s2 (1100-1900) >= 1000 -> Shift +500 -> 1600-2400.
        assert self.s2.start_ms == 1600
        assert self.s2.end_ms == 2400
        
        # o1 (1200) -> Shift +500 -> 1700
        assert self.o1.start_ms == 1700
        
        cmd.undo()
        assert len(self.clip_track.clips) == 3
        assert self.s2.start_ms == 1100
        assert self.o1.start_ms == 1200
