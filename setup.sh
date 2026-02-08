#!/bin/bash
# FastMovieMaker 환경 설정 스크립트

cd "$(dirname "$0")"

echo "⚙️  FastMovieMaker 환경 설정..."
echo ""

# Python 버전 확인
echo "1️⃣ Python 버전 확인..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3가 설치되어 있지 않습니다."
    echo "   macOS: brew install python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "   ✓ $PYTHON_VERSION"
echo ""

# pip 업그레이드
echo "2️⃣ pip 업그레이드..."
python3 -m pip install --upgrade pip
echo ""

# 패키지 설치
echo "3️⃣ 필수 패키지 설치..."
if [ -f "requirements.txt" ]; then
    python3 -m pip install -r requirements.txt
    echo "   ✓ requirements.txt 설치 완료"
else
    echo "   ❌ requirements.txt 파일이 없습니다."
    exit 1
fi
echo ""

# FFmpeg 확인
echo "4️⃣ FFmpeg 확인..."
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version | head -n1)
    echo "   ✓ $FFMPEG_VERSION"
else
    echo "   ⚠️  FFmpeg가 설치되어 있지 않습니다."
    echo "   macOS 설치: brew install ffmpeg"
    echo "   (비디오/오디오 처리에 필요)"
fi
echo ""

# 데이터 디렉토리 생성
echo "5️⃣ 데이터 디렉토리 생성..."
mkdir -p ~/.fastmoviemaker
echo "   ✓ ~/.fastmoviemaker 생성"
echo ""

echo "✅ 환경 설정 완료!"
echo ""
echo "실행 방법:"
echo "  ./run.sh"
