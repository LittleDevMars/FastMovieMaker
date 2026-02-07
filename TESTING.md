# FastMovieMaker Manual Testing Checklist

This document provides a comprehensive manual testing checklist for all features implemented in FastMovieMaker.

## Test Environment Setup

1. Launch the application:
   ```bash
   python main.py
   ```

2. Test video: Use any MP4 or MKV file with audio
   - For MKV testing, use a file with audio track
   - For drag-and-drop testing, have a video file ready

---

## 1. Basic Video Operations

### Video Loading
- [ ] **Load MP4 via File → Open Video** (Ctrl+O)
  - Video should load and display in player
  - Timeline should show video duration
  - Status bar should show file path

- [ ] **Load MKV via File → Open Video**
  - Should show conversion dialog
  - Should convert to MP4 with audio
  - Should load converted file

- [ ] **Drag and Drop Video**
  - Drag a video file onto the window
  - Should load automatically

- [ ] **Recent Projects Menu**
  - Load a project
  - Check File → Recent Projects shows it
  - Click to reopen

### Playback Controls
- [ ] **Play/Pause** (Space)
  - Toggle play/pause with spacebar
  - Button should update state

- [ ] **Seek with Arrow Keys**
  - Left Arrow: seek backward 5 seconds
  - Right Arrow: seek forward 5 seconds
  - Shift+Left: previous frame
  - Shift+Right: next frame

- [ ] **Timeline Seeking**
  - Click on timeline to seek
  - Drag playhead

### Project Management
- [ ] **Save Project** (Ctrl+S)
  - Save to .fmm file
  - Check file is created

- [ ] **Load Project** (Ctrl+O)
  - Load saved project
  - All tracks and subtitles should restore
  - Styles should be preserved

- [ ] **Auto-save**
  - Make changes
  - Wait for configured auto-save interval
  - Check that changes are auto-saved
  - Status bar should show "Auto-saved at [time]"

---

## 2. Subtitle Generation

### Whisper Transcription
- [ ] **Generate Subtitles** (Ctrl+G)
  - Select model (tiny, base, small, medium, large)
  - Select language
  - Click Generate
  - Progress dialog should show
  - Subtitles should appear in timeline

- [ ] **Cancel Generation**
  - Start generation
  - Click Cancel
  - Should stop cleanly

---

## 3. Subtitle Editing

### Text Editing
- [ ] **Edit Subtitle Text**
  - Double-click segment in list
  - Edit text
  - Press Enter to save
  - Verify text updates

- [ ] **Add Subtitle** (Ctrl+N)
  - Click Add Subtitle
  - New segment created at current time
  - Edit text

- [ ] **Delete Subtitle** (Delete)
  - Select segment
  - Press Delete or click Delete button
  - Segment removed

### Timing Adjustment
- [ ] **Drag Segment in Timeline**
  - Drag segment left/right to move
  - Drag edges to resize

- [ ] **Edit Start/End Times**
  - Double-click segment
  - Edit time values manually
  - Verify changes apply

- [ ] **Batch Shift**
  - Select multiple segments (Ctrl+Click)
  - Tools → Batch Shift
  - Enter offset (e.g., +500ms or -1000ms)
  - Verify all selected segments shift

### Advanced Editing
- [ ] **Split Segment**
  - Select segment
  - Position playhead in middle
  - Click Split
  - Segment splits at playhead

- [ ] **Merge Segments**
  - Select two adjacent segments (Ctrl+Click)
  - Click Merge
  - Should combine into one segment

- [ ] **Undo/Redo**
  - Make changes (add/edit/delete)
  - Undo (Ctrl+Z)
  - Redo (Ctrl+Shift+Z)
  - Verify changes revert/reapply

---

## 4. Multi-track System

### Track Management
- [ ] **Add New Track**
  - Click "Add Track"
  - New track appears in selector
  - Can be renamed

- [ ] **Switch Tracks**
  - Click different track in selector
  - Subtitle list updates
  - Timeline shows correct track

- [ ] **Rename Track**
  - Right-click track
  - Select Rename
  - Enter new name

- [ ] **Delete Track**
  - Right-click track
  - Select Delete
  - Confirm deletion
  - Track removed

### Track Independence
- [ ] **Independent Subtitles**
  - Create subtitles in Track 1
  - Switch to Track 2
  - Create different subtitles
  - Verify each track shows own subtitles

- [ ] **Track Visibility**
  - Toggle track visibility checkbox
  - Verify subtitles show/hide in video overlay

---

## 5. Styling System

### Default Style
- [ ] **Edit Default Style**
  - Styles → Edit Default Style
  - Change font, size, colors
  - Apply
  - New segments use this style

### Segment Style
- [ ] **Edit Individual Segment**
  - Right-click segment
  - Select "Edit Style"
  - Modify style
  - Apply
  - Verify only that segment changes

### Style Presets
- [ ] **View Default Presets**
  - Open Style dialog
  - Check preset list shows: YouTube, Cinema, Karaoke, Minimal

- [ ] **Load Preset**
  - Click preset in list
  - Style fields update
  - Preview shows style

- [ ] **Save Preset**
  - Configure custom style
  - Click "Save..."
  - Enter preset name
  - Verify appears in list

- [ ] **Rename Preset**
  - Select custom preset
  - Click "Rename..."
  - Enter new name
  - Verify name changes

- [ ] **Delete Preset**
  - Select custom preset
  - Click "Delete"
  - Confirm
  - Verify removed from list

- [ ] **Overwrite Preset**
  - Configure style
  - Save with existing name
  - Confirm overwrite
  - Verify preset updates

### Style Properties
- [ ] **Font Settings**
  - Change font family
  - Change size (8-72)
  - Toggle bold/italic
  - Verify preview updates

- [ ] **Colors**
  - Change text color
  - Change outline color
  - Change outline width
  - Change background color
  - Verify preview shows changes

- [ ] **Position**
  - Set to bottom-center
  - Set to top-center
  - Set to bottom-left
  - Set to bottom-right
  - Verify video overlay shows correct position

- [ ] **Margin**
  - Adjust margin value
  - Verify distance from edge changes

---

## 6. Search Functionality

### Basic Search
- [ ] **Open Search** (Ctrl+F)
  - Search panel appears
  - Focus in search box

- [ ] **Search Text**
  - Enter search term
  - Results highlight in list
  - Count shows "X of Y results"

- [ ] **Navigate Results**
  - F3: next result
  - Shift+F3: previous result
  - Arrow buttons also work

- [ ] **Clear Search** (Esc)
  - Press Escape
  - Search clears
  - Highlights removed

### Search Features
- [ ] **Case Sensitive Search**
  - Search "hello" vs "Hello"
  - Toggle case sensitivity
  - Verify results update

- [ ] **Partial Match**
  - Search partial word
  - Should find all matches

---

## 7. Translation

### Translation Dialog
- [ ] **Open Translation Dialog**
  - Tools → Translate Track
  - Dialog appears with options

### Translation Engines
- [ ] **Google Translate** (No API key required)
  - Select source language
  - Select target language
  - Select Google Translate
  - Click Translate
  - Verify new track created with translations

- [ ] **DeepL** (Requires API key)
  - Set API key in Preferences → API Keys
  - Select languages
  - Select DeepL
  - Translate
  - Verify translations

- [ ] **OpenAI GPT-4o-mini** (Requires API key)
  - Set API key in Preferences → API Keys
  - Select languages
  - Select OpenAI
  - Translate
  - Verify translations

### Translation Options
- [ ] **Create New Track**
  - Translation creates new track
  - Original track unchanged
  - New track has language suffix

- [ ] **Language Detection**
  - Auto-detect source language
  - Should work correctly

---

## 8. Preferences/Settings

### Open Preferences
- [ ] **Open via Menu**
  - File → Preferences
  - Dialog opens

- [ ] **Open via Keyboard** (Ctrl+,)
  - Press Ctrl+Comma
  - Dialog opens

### General Tab
- [ ] **Autosave Interval**
  - Change value (10-300 seconds)
  - Save and restart
  - Verify setting persists

- [ ] **Autosave Idle Timeout**
  - Change value (1-60 seconds)
  - Save
  - Verify idle detection works

- [ ] **Recent Files Max**
  - Change value (5-20)
  - Save
  - Verify recent files list respects limit

- [ ] **Default Language**
  - Change default language
  - Save
  - Create new project
  - Verify language is set

- [ ] **Theme**
  - Change theme (dark/light)
  - Save and restart
  - Verify theme changes

### Editing Tab
- [ ] **Default Subtitle Duration**
  - Change value (500-10000ms)
  - Save
  - Create new subtitle
  - Verify duration

- [ ] **Snap Tolerance**
  - Change value (5-50 pixels)
  - Save
  - Test snapping in timeline

- [ ] **Frame Seek FPS**
  - Change value (10-120)
  - Save
  - Test frame stepping

### Advanced Tab
- [ ] **FFmpeg Path**
  - Browse for FFmpeg
  - Save
  - Verify custom path used

- [ ] **Whisper Cache Directory**
  - Browse for directory
  - Save
  - Verify models download there

### API Keys Tab
- [ ] **DeepL API Key**
  - Enter key
  - Save
  - Verify stored securely
  - Test translation

- [ ] **OpenAI API Key**
  - Enter key
  - Save
  - Verify stored securely
  - Test translation

---

## 9. Export Functions

### SRT Export
- [ ] **Export SRT** (Ctrl+E)
  - File → Export → Export SRT
  - Save to file
  - Open in text editor
  - Verify format correct

- [ ] **Export with Styles**
  - Export SRT
  - Check if basic styles preserved

### Video Export (Hard Subtitles)
- [ ] **Export with Burned Subtitles**
  - File → Export → Export Video with Subtitles
  - Select output file
  - Progress dialog shows
  - Watch exported video
  - Verify subtitles burned in

---

## 10. MKV Audio Handling

### MKV Files
- [ ] **Load MKV with Audio**
  - Open MKV file
  - Should auto-detect audio
  - Should show conversion dialog

- [ ] **Audio Conversion**
  - Load MKV with 5.1 surround
  - Should downmix to stereo
  - Audio should play correctly

- [ ] **Multi-audio MKV**
  - Load MKV with multiple audio tracks
  - Should select first audio track
  - Should play audio

---

## 11. UI/UX Features

### Keyboard Shortcuts
Test all documented shortcuts:
- [ ] Ctrl+O: Open
- [ ] Ctrl+S: Save
- [ ] Ctrl+N: New subtitle
- [ ] Ctrl+G: Generate subtitles
- [ ] Ctrl+E: Export SRT
- [ ] Ctrl+F: Search
- [ ] Ctrl+Z: Undo
- [ ] Ctrl+Shift+Z: Redo
- [ ] Ctrl+,: Preferences
- [ ] Space: Play/Pause
- [ ] Delete: Delete segment
- [ ] F3: Next search result
- [ ] Shift+F3: Previous search result
- [ ] Esc: Close search

### Dark Theme
- [ ] **Verify Dark Theme**
  - All UI elements use dark colors
  - Good contrast
  - No white flashes

### Responsive UI
- [ ] **Resize Window**
  - Resize main window
  - All panels resize appropriately
  - No overlapping elements

### Status Bar
- [ ] **Status Messages**
  - Shows current file
  - Shows save status
  - Shows auto-save time
  - Shows errors when they occur

---

## 12. Error Handling

### File Errors
- [ ] **Invalid File**
  - Try to open non-video file
  - Should show error message

- [ ] **Missing File**
  - Open recent project with deleted video
  - Should handle gracefully

### API Errors
- [ ] **Invalid API Key**
  - Try translation with wrong key
  - Should show clear error

- [ ] **Network Error**
  - Disconnect network
  - Try translation
  - Should handle timeout

### Validation
- [ ] **Invalid Time Values**
  - Try to set end time before start time
  - Should validate and prevent

---

## Test Results

Date: ___________
Tester: ___________

| Category | Pass | Fail | Notes |
|----------|------|------|-------|
| Basic Video Operations | ☐ | ☐ | |
| Subtitle Generation | ☐ | ☐ | |
| Subtitle Editing | ☐ | ☐ | |
| Multi-track System | ☐ | ☐ | |
| Styling System | ☐ | ☐ | |
| Search Functionality | ☐ | ☐ | |
| Translation | ☐ | ☐ | |
| Preferences/Settings | ☐ | ☐ | |
| Export Functions | ☐ | ☐ | |
| MKV Audio Handling | ☐ | ☐ | |
| UI/UX Features | ☐ | ☐ | |
| Error Handling | ☐ | ☐ | |

---

## Known Issues

(Document any issues found during testing)

1.
2.
3.

---

## Notes

(Additional observations or feedback)
