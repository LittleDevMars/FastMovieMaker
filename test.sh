#!/bin/bash
# FastMovieMaker 테스트 실행 스크립트

cd "$(dirname "$0")"

echo "🧪 FastMovieMaker 테스트 시작..."
echo ""

# pytest 확인
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest가 설치되어 있지 않습니다."
    echo "   설치: pip install pytest"
    exit 1
fi

# 테스트 실행
echo "📝 단위 테스트 실행 중..."
echo ""
pytest tests/ -v

# 결과 표시
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 모든 테스트 통과!"
else
    echo ""
    echo "❌ 일부 테스트 실패"
    exit 1
fi
