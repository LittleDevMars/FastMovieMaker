#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

source .venv/bin/activate
pip install pyinstaller --quiet
python -m PyInstaller FastMovieMaker.spec --noconfirm --clean
echo "✅ dist/FastMovieMaker.app"
