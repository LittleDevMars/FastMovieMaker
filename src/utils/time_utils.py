"""Time conversion utilities."""


def ms_to_display(ms: int) -> str:
    """Convert milliseconds to display string 'MM:SS.mmm'."""
    if ms < 0:
        ms = 0
    total_seconds = ms / 1000.0
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:06.3f}"


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
