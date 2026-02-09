@echo off
chcp 65001 > nul
echo ⚙️  FastMovieMaker 환경 설정 (Windows)...
echo.

:: 1. Python 버전 확인
echo 1️⃣ Python 버전 확인...
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python이 설치되어 있지 않거나 PATH에 없습니다.
    echo    Python 3.10 이상을 설치해주세요.
    pause
    exit /b 1
)
python --version
echo.

:: 2. pip 업그레이드
echo 2️⃣ pip 업그레이드...
python -m pip install --upgrade pip
echo.

:: 3. 패키지 설치
echo 3️⃣ 필수 패키지 설치...
if exist requirements.txt (
    python -m pip install -r requirements.txt
    echo    ✓ requirements.txt 설치 완료
) else (
    echo    ❌ requirements.txt 파일이 없습니다.
    pause
    exit /b 1
)
echo.

:: 4. FFmpeg 확인
echo 4️⃣ FFmpeg 확인...
ffmpeg -version > nul 2>&1
if %errorlevel% neq 0 (
    echo    ⚠️  FFmpeg가 설치되어 있지 않거나 PATH에 없습니다.
    echo    (비디오/오디오 처리에 필요합니다. https://ffmpeg.org/download.html)
) else (
    echo    ✓ FFmpeg 확인됨
)
echo.

echo ✅ 환경 설정 완료!
echo 실행 방법: run.bat
pause