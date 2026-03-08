"""Shared pytest test-time configuration."""

from __future__ import annotations

import os


# Keep Qt tests headless/stable on macOS CI and local CLI runs.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
