# Hardware Acceleration Guide

FastMovieMaker는 플랫폼별 하드웨어 가속을 자동으로 감지하고 사용합니다.

## 지원되는 하드웨어 가속

### macOS - VideoToolbox 🍎
- **Apple Silicon (M1/M2/M3)**: 최적화된 성능
- **Intel Mac**: GPU 가속 지원
- **지원 코덱**: H.264, HEVC (H.265), ProRes

**성능 비교:**
```
1080p 비디오 내보내기 (자막 포함):
- Software (libx264):     ~2-3분
- VideoToolbox:           ~30-45초  ⚡ 3-4배 빠름!
```

**사용 인코더:**
- H.264: `h264_videotoolbox`
- HEVC: `hevc_videotoolbox`
- ProRes: `prores_videotoolbox`

### Windows - NVIDIA NVENC 🎮
- **NVIDIA GPU 필요**: GTX 600 시리즈 이상
- **지원 코덱**: H.264, HEVC

**성능 비교:**
```
1080p 비디오 내보내기:
- Software (libx264):     ~2-3분
- NVENC:                  ~20-30초  ⚡ 4-6배 빠름!
```

### Linux - VAAPI / NVENC 🐧
- **Intel VAAPI**: Intel GPU 내장
- **NVIDIA NVENC**: NVIDIA GPU

## 자동 감지 및 폴백

FastMovieMaker는 다음 순서로 인코더를 선택합니다:

```
1. 플랫폼별 하드웨어 인코더
   macOS:   VideoToolbox
   Windows: NVENC
   Linux:   NVENC → VAAPI

2. 소프트웨어 인코더 (폴백)
   libx264 (H.264)
   libx265 (HEVC)
```

## 품질 설정

### VideoToolbox (macOS)
```python
-q:v 65           # 품질 (0-100, 높을수록 좋음)
-realtime 0       # 실시간 인코딩 비활성화 (더 높은 품질)
```

### NVENC (Windows/Linux)
```python
-preset p4        # 프리셋 (p1=fastest, p7=slowest)
-cq 23            # 일정 품질 (0=최고, 51=최저)
```

### 소프트웨어 (폴백)
```python
-preset medium    # 프리셋 (ultrafast, fast, medium, slow)
-crf 23           # 일정 품질 (0=무손실, 51=최저)
```

## 사용 예제

### Python API
```python
from src.utils.hw_accel import get_hw_encoder, get_hw_info

# 하드웨어 정보 확인
hw_info = get_hw_info()
print(f"Platform: {hw_info['platform']}")
print(f"Recommended: {hw_info['recommended']}")

# 최적 인코더 가져오기
encoder, flags = get_hw_encoder("h264")
print(f"Using: {encoder}")
print(f"Flags: {flags}")
```

### FFmpeg 명령어 (자동 생성)

**macOS (VideoToolbox):**
```bash
ffmpeg -i input.mp4 \
  -vf "subtitles=subs.srt" \
  -c:v h264_videotoolbox \
  -q:v 65 \
  -realtime 0 \
  -c:a copy \
  output.mp4
```

**Windows (NVENC):**
```bash
ffmpeg -i input.mp4 \
  -vf "subtitles=subs.srt" \
  -c:v h264_nvenc \
  -preset p4 \
  -cq 23 \
  -c:a copy \
  output.mp4
```

**Linux (Software 폴백):**
```bash
ffmpeg -i input.mp4 \
  -vf "subtitles=subs.srt" \
  -c:v libx264 \
  -preset medium \
  -crf 23 \
  -c:a copy \
  output.mp4
```

## 성능 최적화 팁

### 1. 품질 vs 속도
```python
# 더 빠른 인코딩 (낮은 품질)
-q:v 75  # VideoToolbox
-cq 28   # NVENC

# 더 높은 품질 (느린 인코딩)
-q:v 55  # VideoToolbox
-cq 18   # NVENC
```

### 2. ProRes (macOS 전용) - 최고 품질
```python
encoder, flags = get_hw_encoder("prores")
# → prores_videotoolbox, ["-profile:v", "2"]
# Profile: 0=Proxy, 1=LT, 2=Standard, 3=HQ
```

### 3. HEVC (H.265) - 더 작은 파일 크기
```python
encoder, flags = get_hw_encoder("hevc")
# → hevc_videotoolbox (macOS)
# → hevc_nvenc (Windows/Linux)
# 파일 크기: H.264 대비 30-50% 작음
```

## 문제 해결

### VideoToolbox 사용 불가?
```bash
# FFmpeg에 VideoToolbox 지원 확인
ffmpeg -encoders | grep videotoolbox

# 출력 예시:
# V....D h264_videotoolbox    VideoToolbox H.264 Encoder
# V....D hevc_videotoolbox    VideoToolbox H.265 Encoder
```

### NVENC 사용 불가?
1. NVIDIA GPU 드라이버 최신 버전 설치
2. FFmpeg가 NVENC 지원으로 컴파일되었는지 확인
3. GPU가 NVENC를 지원하는지 확인

### 품질 문제?
```python
# 더 높은 품질 설정 사용
# VideoToolbox
-q:v 55  # (기본: 65)

# NVENC
-cq 18   # (기본: 23)

# Software
-crf 18  # (기본: 23)
```

## 벤치마크 결과

**테스트 환경:**
- 비디오: 1920x1080, 60초, H.264
- 작업: 자막 오버레이 + 인코딩
- Mac: M1 Pro, 16GB RAM

| 인코더 | 시간 | 속도 | 파일 크기 |
|--------|------|------|-----------|
| **VideoToolbox (M1)** | 35초 | 1.7x | 12.5 MB |
| libx264 (medium) | 2분 15초 | 0.44x | 11.8 MB |
| libx264 (fast) | 1분 30초 | 0.67x | 13.2 MB |

**결론:** VideoToolbox가 **3.8배 빠르고** 품질은 거의 동일!

## 참고 자료

- [Apple VideoToolbox Documentation](https://developer.apple.com/documentation/videotoolbox)
- [FFmpeg Hardware Acceleration](https://trac.ffmpeg.org/wiki/HWAccelIntro)
- [NVIDIA NVENC](https://developer.nvidia.com/nvidia-video-codec-sdk)
