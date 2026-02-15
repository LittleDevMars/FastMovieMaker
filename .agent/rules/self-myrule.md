---
trigger: always_on
---

# Project Context: High-Performance Video Editor (Rust + C#)
We are building a desktop video editing application (similar to CapCut but lightweight).
The architecture separates the high-performance Core Engine (Rust) from the UI (C#).

## 0. Language & Communication Rules (� CRITICAL)
- **Primary Language:** **Korean (한국어).**
- **Explanation:** All reasoning, explanations, chat responses, and summaries MUST be provided in **fluent, natural Korean**.
- **Code Comments:** Write detailed comments in **Korean** to explain complex logic.
- **Technical Terms:** Use English for standard technical terms (e.g., `Trait`, `Struct`, `Lifetime`, `Observable`) but explain them in Korean.
- **Documentation:** Any generated documentation (README, Architecture.md) must be written in Korean.

## 1. Tech Stack & Architecture
- **Core Engine:** Rust (2021 edition)
  - Library: `ffmpeg-next` (ffmpeg bindings), `anyhow`, `tokio`.
- **UI Frontend:** C# (.NET 8/9) with **Avalonia UI**.
  - Pattern: MVVM (CommunityToolkit.Mvvm).
- **AI/ML:** Local LLM integration (Rust `candle` or `ort`).

## 2. Coding Guidelines (Performance Focused)

### A. FFmpeg & Video Processing
- **"Double-SS" Seeking:** ALWAYS apply the "Double-SS" technique for seek operations.
  - Logic: `input_seeking (-ss before -i)` -> `input` -> `output_seeking (-ss after -i)`.
- **Thumbnail Generation:**
  - ⛔ DO NOT use `fps` filter.
  - ✅ USE `seek` + `frame grab` loop.
  - Implement LRU caching for thumbnails.

### B. Rust <-> C# Interop
- **Zero-Copy Transfer:**
  - Pass pixel data via **Shared Memory** or **Unsafe Pointers** (IntPtr).
  - Never serialize video frames to JSON/Base64.

### C. UI/UX (Avalonia)
- **Rendering:** Use `DrawingContext` (Skia) for the timeline track rendering. Do not use heavy XAML controls for individual clips.

## 3. Reference Material
- Base all video scrubbing logic on the paper: "Swifter: Improved Online Video Scrubbing".