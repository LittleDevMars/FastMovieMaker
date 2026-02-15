"""Time conversion utilities."""

from functools import lru_cache


@lru_cache(maxsize=4096)
def ms_to_display(ms: int) -> str:
    """Convert milliseconds to display string 'MM:SS.mmm'."""
    if ms < 0:
        ms = 0
    total_seconds = ms / 1000.0
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:06.3f}"


@lru_cache(maxsize=4096)
def ms_to_srt_time(ms: int) -> str:
    """Convert milliseconds to SRT time format 'HH:MM:SS,mmm'."""
    if ms < 0:
        ms = 0
    hours = ms // 3_600_000
    remainder = ms % 3_600_000
    minutes = remainder // 60_000
    remainder = remainder % 60_000
    seconds = remainder // 1000
    millis = remainder % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def seconds_to_ms(seconds: float) -> int:
    """Convert seconds (float) to integer milliseconds."""
    return int(round(seconds * 1000))


def srt_time_to_ms(text: str) -> int:
    """Parse SRT time 'HH:MM:SS,mmm' → milliseconds."""
    text = text.strip().replace(",", ".")
    parts = text.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    sec_ms = float(parts[2])
    return int(hours * 3_600_000 + minutes * 60_000 + sec_ms * 1000)


def display_to_ms(text: str) -> int:
    """Parse display time 'MM:SS.mmm' → milliseconds."""
    text = text.strip()
    parts = text.split(":")
    minutes = int(parts[0])
    sec_ms = float(parts[1])
    return int(minutes * 60_000 + sec_ms * 1000)


@lru_cache(maxsize=2048)
def ms_to_frame(ms: int, fps: int) -> int:
    """Convert milliseconds to frame number.

    Args:
        ms: Time in milliseconds
        fps: Frames per second

    Returns:
        Frame number (0-indexed)

    Example:
        >>> ms_to_frame(1000, 30)
        30  # 1 second = 30 frames at 30fps
    """
    return int(round(ms * fps / 1000))


@lru_cache(maxsize=2048)
def frame_to_ms(frame: int, fps: int) -> int:
    """Convert frame number to milliseconds.

    Args:
        frame: Frame number (0-indexed)
        fps: Frames per second

    Returns:
        Time in milliseconds

    Example:
        >>> frame_to_ms(30, 30)
        1000  # 30 frames = 1 second at 30fps
    """
    return int(round(frame * 1000 / fps))


def snap_to_frame(ms: int, fps: int) -> int:
    """Snap time to nearest frame boundary.

    Args:
        ms: Time in milliseconds
        fps: Frames per second

    Returns:
        Time in milliseconds at nearest frame boundary

    Example:
        >>> snap_to_frame(40, 30)
        33  # Nearest frame boundary at 30fps
    """
    frame = ms_to_frame(ms, fps)
    return frame_to_ms(frame, fps)


def ms_to_timecode_frames(ms: int, fps: int) -> str:
    """Convert milliseconds to HH:MM:SS:FF timecode format.

    Args:
        ms: Time in milliseconds
        fps: Frames per second

    Returns:
        Timecode string in HH:MM:SS:FF format

    Example:
        >>> ms_to_timecode_frames(83500, 30)
        '00:01:23:15'  # 1 min, 23 sec, 15 frames
    """
    if ms < 0:
        ms = 0

    total_frames = ms_to_frame(ms, fps)
    frames = total_frames % fps
    total_seconds = total_frames // fps
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def timecode_frames_to_ms(text: str, fps: int) -> int:
    """Parse HH:MM:SS:FF timecode format to milliseconds.

    Args:
        text: Timecode string in HH:MM:SS:FF format
        fps: Frames per second

    Returns:
        Time in milliseconds

    Raises:
        ValueError: If format is invalid

    Example:
        >>> timecode_frames_to_ms('00:01:23:15', 30)
        83500  # 1 min, 23 sec, 15 frames
    """
    text = text.strip()
    parts = text.split(":")

    if len(parts) != 4:
        raise ValueError(f"Expected HH:MM:SS:FF format, got '{text}'")

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
        frames = int(parts[3])
    except ValueError as e:
        raise ValueError(f"Invalid timecode '{text}': {e}")

    if frames >= fps:
        raise ValueError(f"Frame number {frames} exceeds FPS {fps}")

    total_frames = (hours * 3600 + minutes * 60 + seconds) * fps + frames
    return frame_to_ms(total_frames, fps)


def parse_flexible_timecode(text: str, fps: int) -> int:
    """Parse various timecode formats to milliseconds.

    Supported formats:
        - MM:SS.mmm (e.g., '01:23.456')
        - HH:MM:SS.mmm (e.g., '00:01:23.456')
        - HH:MM:SS:FF (e.g., '00:01:23:15')
        - F:123 or frame:123 (frame number)

    Args:
        text: Timecode string in any supported format
        fps: Frames per second (used for frame formats)

    Returns:
        Time in milliseconds

    Raises:
        ValueError: If format is invalid or cannot be parsed

    Examples:
        >>> parse_flexible_timecode('01:23.456', 30)
        83456
        >>> parse_flexible_timecode('00:01:23:15', 30)
        83500
        >>> parse_flexible_timecode('F:30', 30)
        1000
    """
    text = text.strip()

    # Check for frame number format: F:123 or frame:123
    if text.lower().startswith('f:') or text.lower().startswith('frame:'):
        frame_part = text.split(':', 1)[1].strip()
        try:
            frame_num = int(frame_part)
            if frame_num < 0:
                raise ValueError(f"Frame number cannot be negative: {frame_num}")
            return frame_to_ms(frame_num, fps)
        except ValueError as e:
            raise ValueError(f"Invalid frame number '{text}': {e}")

    # Check for HH:MM:SS:FF format (4 colons with no decimal point)
    if text.count(':') == 3 and '.' not in text:
        return timecode_frames_to_ms(text, fps)

    # Check for HH:MM:SS.mmm format (3 colons with decimal point)
    if text.count(':') == 2 and '.' in text:
        try:
            return srt_time_to_ms(text)
        except Exception:
            pass  # Fall through to try MM:SS.mmm

    # Check for MM:SS.mmm format (2 colons with decimal point)
    if text.count(':') == 1 and '.' in text:
        try:
            return display_to_ms(text)
        except Exception as e:
            raise ValueError(f"Invalid MM:SS.mmm format '{text}': {e}")

    # Check for MM:SS format (no decimal point, backward compatibility)
    if text.count(':') == 1 and '.' not in text:
        try:
            return display_to_ms(text + ".000")
        except Exception as e:
            raise ValueError(f"Invalid MM:SS format '{text}': {e}")

    raise ValueError(
        f"Unrecognized timecode format '{text}'. "
        f"Supported: MM:SS.mmm, HH:MM:SS.mmm, HH:MM:SS:FF, F:123"
    )
