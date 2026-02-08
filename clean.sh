#!/bin/bash
# FastMovieMaker 정리 스크립트 (캐시, 임시 파일 삭제)

cd "$(dirname "$0")"

echo "🧹 FastMovieMaker 정리 중..."
echo ""

# Python 캐시 삭제
echo "1️⃣ Python 캐시 삭제..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
find . -type f -name "*.pyo" -delete 2>/dev/null
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null
echo "   ✓ __pycache__, *.pyc, *.pyo 삭제 완료"
echo ""

# pytest 캐시 삭제
echo "2️⃣ Pytest 캐시 삭제..."
rm -rf .pytest_cache
echo "   ✓ .pytest_cache 삭제 완료"
echo ""

# 임시 파일 삭제
echo "3️⃣ 임시 파일 삭제..."
rm -f /tmp/fastmoviemaker_screenshot_*.png
rm -f /tmp/timeline_audio_debug.log
echo "   ✓ 임시 스크린샷 및 로그 파일 삭제 완료"
echo ""

# .DS_Store 삭제 (macOS)
echo "4️⃣ macOS .DS_Store 삭제..."
find . -name ".DS_Store" -delete 2>/dev/null
echo "   ✓ .DS_Store 삭제 완료"
echo ""

echo "✅ 정리 완료!"
echo ""
echo "참고: 사용자 데이터는 삭제되지 않았습니다."
echo "  - ~/.fastmoviemaker (TTS 오디오, 설정)"
