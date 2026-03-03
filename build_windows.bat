@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
pip install pyinstaller --quiet
python -m PyInstaller FastMovieMaker.spec --noconfirm --clean
echo Build complete: dist\FastMovieMaker\
