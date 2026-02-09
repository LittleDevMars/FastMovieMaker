# TTS (Text-to-Speech) Usage Guide

## Overview
FastMovieMaker provides TTS functionality to automatically generate voice and subtitles from a script.

## Supported Engines

### 1. Edge-TTS (Microsoft Azure)
- **Free to use**
- Multiple languages and voices:
  - Korean: `ko-KR-SunHiNeural` (female), `ko-KR-InJoonNeural` (male)
  - English: `en-US-JennyNeural`, `en-US-GuyNeural`, etc.
- Internet connection required

### 2. ElevenLabs API
- **API key required** (paid/free tier)
- High-quality natural voices
- Wide voice selection
- Setup: Edit → Preferences → TTS tab to enter API key

## How to Use

### Step 1: Open TTS Dialog
- Menu: `Subtitle` → `Generate &Speech (TTS)...`
- Shortcut: `Ctrl+T`

### Step 2: Write Script
Format your script like this:

```
# First sentence
Hello, today I'll show you how to use FastMovieMaker.

# Second sentence (separated by blank line)
The TTS feature automatically generates voice and subtitles.

# Third sentence
Pretty simple, right?
```

**Separation Rules:**
- Blank lines (`\n\n`) separate subtitle segments
- Lines starting with `#` are comments (ignored)
- Each segment becomes an individual subtitle + audio clip

### Step 3: Configure Settings

#### Engine Selection
- **Edge-TTS**: Free, fast, suitable for most purposes
- **ElevenLabs**: High quality, requires API key

#### Language & Voice
- Select desired voice from dropdown
- Korean projects: `ko-KR-SunHiNeural` recommended
- English projects: `en-US-JennyNeural` recommended

#### Options
- **Mix with video audio**: Mix with video audio (when video loaded)
- **Auto-timing**: Automatically adjust subtitle timing based on sentence length

### Step 4: Start Generation
- Click `Generate` button
- Monitor progress with progress bar
- New TTS track automatically added upon completion

## Generated Results

### Subtitle Track
- Added to project as `TTS Track N`
- Each sentence becomes a separate subtitle segment
- Editable on timeline (drag, text editing, etc.)

### Audio File
- Temp file: `C:\Users\USER\AppData\Local\Temp\fmm_tts_*.mp3`
- Separate audio file created when mixed with video
- Path preserved when saving project

### Playback
- TTS audio plays automatically during timeline playback
- Volume control: Use `🎤` slider in playback controls
- Independent volume control from video audio

## Advanced Features

### Video Audio Mixing
1. Load video file first
2. Check "Mix with video audio" when generating TTS
3. Result: Video audio + TTS voice mixed

### Multiple TTS Tracks
- Generate TTS multiple times to create multiple tracks
- Switch active track in track selector
- Each track has independent subtitles + audio

### Fine-tune Timing
1. After TTS generation, drag segments on timeline
2. Edit start/end times directly in subtitle table
3. Use Jump dialog (Ctrl+J) for frame-accurate positioning

## Export Options

### SRT File (Subtitles Only)
- `File` → `Export` → `SRT File`
- Export text + timing info only

### Video File (Burned Subtitles + Audio)
- `File` → `Export` → `Batch Export`
- Subtitles burned into video
- TTS audio mixed into video
- Resolution selection available (1080p, 720p, 480p)

## Troubleshooting

### "FFmpeg Missing" Error
- FFmpeg installation required: [ffmpeg.org](https://ffmpeg.org/download.html)
- After installation, set path in Edit → Preferences → General

### ElevenLabs API Key Error
1. Sign up at [elevenlabs.io](https://elevenlabs.io)
2. Generate API key
3. Enter in Edit → Preferences → TTS → ElevenLabs API Key

### Audio Not Playing
- Check `🎤` slider volume (muted if 0%)
- Verify TTS track is active
- Try reloading project

### Slow Generation Speed
- Edge-TTS: Depends on network speed
- ElevenLabs: API rate limits (free tier)
- Splitting script into shorter sentences enables parallel processing

## Tips

1. **When Writing Scripts**:
   - 10-20 words per sentence recommended (readability)
   - Very long sentences may overflow the screen in subtitles

2. **Voice Selection**:
   - Choose tone matching your project (male/female, age)
   - Test with multiple voices

3. **Timing Adjustment**:
   - More efficient to adjust on timeline after initial generation
   - Enable frame snap (F key) for precise adjustments

4. **Multi-language Support**:
   - Can create separate Korean + English tracks in one project
   - Distinguish track names as "Korean", "English"
