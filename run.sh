#!/bin/bash
# FastMovieMaker 실행 스크립트

# 스크립트가 있는 디렉토리로 이동
cd "$(dirname "$0")"

echo "🎬 FastMovieMaker 시작 중..."
echo ""

# Python 버전 확인
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3가 설치되어 있지 않습니다."
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✓ $PYTHON_VERSION"

# 필수 패키지 확인
echo "✓ 패키지 확인 중..."
python3 -c "import PySide6" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ PySide6가 설치되어 있지 않습니다."
    echo "   설치: pip install -r requirements.txt"
    exit 1
fi

# FastMovieMaker 실행
echo "✓ FastMovieMaker 실행"
echo ""
python3 main.py

# 종료 메시지
echo ""
echo "👋 FastMovieMaker 종료"
