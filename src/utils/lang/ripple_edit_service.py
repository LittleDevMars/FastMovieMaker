"""
Service for handling ripple edits across multiple tracks.
"""
from src.models.project import ProjectState

class RippleEditService:
    """
    Provides logic to propagate time shifts (ripples) to other tracks
    when a clip is inserted, deleted, or trimmed in the main video track.
    """

    @staticmethod
    def apply_ripple(project: ProjectState, ripple_start_ms: int, delta_ms: int, exclude_track_indices: list[int] = None) -> int:
        """
        Apply a time shift to all applicable elements in the project starting from ripple_start_ms.
        
        Args:
            project: The project state to modify.
            ripple_start_ms: The timeline position where the ripple begins.
            delta_ms: The amount of time to shift (positive = push, negative = pull).
            exclude_track_indices: Optional list of video track indices to exclude (e.g. the track being edited).
            
        Returns:
            The number of items moved.
        """
        if delta_ms == 0:
            return 0
            
        moved_count = 0
        exclude_tracks = exclude_track_indices or []

        # 1. Subtitle Tracks
        for track in project.subtitle_tracks:
            if track.locked:
                continue
            
            # Shift segments
            for seg in track.segments:
                if seg.start_ms >= ripple_start_ms:
                    seg.start_ms += delta_ms
                    seg.end_ms += delta_ms
                    moved_count += 1
                elif seg.end_ms > ripple_start_ms:
                    # Segment overlaps the ripple point - extend/shrink or split?
                    # For simplicity in this version, we only move fully subsequent items.
                    # Alternatively, we could extend the end time if it's a push.
                    pass
            
            # Shift audio track associated with subtitles (if any)
            if track.audio_path and track.audio_start_ms >= ripple_start_ms:
                track.audio_start_ms += delta_ms

        # 2. Image Overlays
        if project.image_overlay_track and not project.image_overlay_track.locked:
            for overlay in project.image_overlay_track.overlays:
                if overlay.start_ms >= ripple_start_ms:
                    overlay.start_ms += delta_ms
                    overlay.end_ms += delta_ms
                    moved_count += 1

        # 3. Text Overlays
        if project.text_overlay_track and not project.text_overlay_track.locked:
            for overlay in project.text_overlay_track.overlays:
                if overlay.start_ms >= ripple_start_ms:
                    overlay.start_ms += delta_ms
                    overlay.end_ms += delta_ms
                    moved_count += 1

        # 4. BGM Tracks
        if hasattr(project, "bgm_tracks"):
            for track in project.bgm_tracks:
                if track.locked:
                    continue
                for clip in track.clips:
                    if clip.start_ms >= ripple_start_ms:
                        clip.start_ms += delta_ms
                        moved_count += 1

        return moved_count