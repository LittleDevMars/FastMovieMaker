## Summary
- [ ] `feat(export): multi-stage gpu fallback with structured status`
- [ ] `feat(playback): detect apv codec and auto-convert for playback`
- [ ] `test/docs: add APV regression tests and manual checklist`

## Problem
- GPU export fallback was limited to a single retry path and status visibility was coarse.
- APV codec inputs were not explicitly detected for playback conversion.

## Solution
- Added multi-stage encoder fallback (HW candidate chain to software fallback).
- Added structured status events (`probe`, `retry`, `final_encoder`) with worker/UI string formatting compatibility.
- Added APV codec detection via `ffprobe codec_name` and auto-convert-to-MP4 playback path.
- Synced docs/checklists for APV and export behavior.

## Risks
- Hardware encoder probing behavior can vary by FFmpeg build/platform.
- GUI automation remains environment-sensitive (`pytest-qt` abort risk on some macOS setups).

## Validation Scope
- [ ] `pytest -q tests/test_video_export.py`
- [ ] `pytest -q tests/test_export_integration.py`
- [ ] `pytest -q tests/test_video_load_worker.py`
- [ ] `pytest -q tests/test_controllers.py`
- [ ] Manual GUI smoke checklist in `TESTING.md` (non-blocking for this PR gate)

## Open Items
- APV real-file manual verification pending (requires sample file).
