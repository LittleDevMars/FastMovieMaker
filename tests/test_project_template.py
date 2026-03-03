"""tests/test_project_template.py — ProjectTemplate + TemplateManager 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ─────────────────────── ProjectTemplate ───────────────────────

class TestProjectTemplateFields:
    def test_template_fields(self):
        from src.models.project_template import ProjectTemplate
        from src.models.style import SubtitleStyle
        tmpl = ProjectTemplate(
            name="test",
            display_name="Test Template",
            width=1280,
            height=720,
            fps=24.0,
            subtitle_style=SubtitleStyle(),
        )
        assert tmpl.name == "test"
        assert tmpl.display_name == "Test Template"
        assert tmpl.width == 1280
        assert tmpl.height == 720
        assert tmpl.fps == pytest.approx(24.0)
        assert tmpl.is_builtin is True

    def test_aspect_label_16x9(self):
        from src.models.project_template import ProjectTemplate
        from src.models.style import SubtitleStyle
        tmpl = ProjectTemplate("a", "A", 1920, 1080, 30.0, SubtitleStyle())
        assert "1920×1080" in tmpl.aspect_label
        assert "16:9" in tmpl.aspect_label

    def test_aspect_label_9x16(self):
        from src.models.project_template import ProjectTemplate
        from src.models.style import SubtitleStyle
        tmpl = ProjectTemplate("b", "B", 1080, 1920, 30.0, SubtitleStyle())
        assert "9:16" in tmpl.aspect_label

    def test_aspect_label_1x1(self):
        from src.models.project_template import ProjectTemplate
        from src.models.style import SubtitleStyle
        tmpl = ProjectTemplate("c", "C", 1080, 1080, 30.0, SubtitleStyle())
        assert "1:1" in tmpl.aspect_label


# ─────────────────────── TemplateManager — 내장 ───────────────────────

class TestBuiltinTemplates:
    def test_builtin_templates_count(self):
        from src.services.template_manager import TemplateManager
        mgr = TemplateManager()
        assert len(mgr.get_builtin_templates()) == 3

    def test_shorts_template_resolution(self):
        from src.services.template_manager import BUILTIN_TEMPLATES
        shorts = next(t for t in BUILTIN_TEMPLATES if t.name == "yt_shorts")
        assert shorts.width == 1080
        assert shorts.height == 1920

    def test_commentary_template_resolution(self):
        from src.services.template_manager import BUILTIN_TEMPLATES
        comm = next(t for t in BUILTIN_TEMPLATES if t.name == "yt_commentary")
        assert comm.width == 1920
        assert comm.height == 1080

    def test_reels_template_resolution(self):
        from src.services.template_manager import BUILTIN_TEMPLATES
        reels = next(t for t in BUILTIN_TEMPLATES if t.name == "ig_reels")
        assert reels.width == 1080
        assert reels.height == 1080


# ─────────────────────── TemplateManager — 사용자 정의 ───────────────────────

def _make_mgr(tmp_path: Path):
    """임시 QSettings 파일을 사용하는 TemplateManager 반환."""
    from PySide6.QtCore import QSettings
    from src.services.template_manager import TemplateManager
    settings = QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)
    return TemplateManager(settings=settings)


def _make_user_template(name="custom"):
    from src.models.project_template import ProjectTemplate
    from src.models.style import SubtitleStyle
    return ProjectTemplate(
        name=name,
        display_name="My Custom",
        width=1280,
        height=720,
        fps=25.0,
        subtitle_style=SubtitleStyle(font_size=16),
        is_builtin=False,
    )


class TestUserTemplates:
    def test_template_save_load_user(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        tmpl = _make_user_template("u1")
        mgr.save_user_template(tmpl)
        loaded = mgr.load_user_templates()
        assert any(t.name == "u1" for t in loaded)

    def test_template_delete_user(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        tmpl = _make_user_template("del_me")
        mgr.save_user_template(tmpl)
        assert mgr.delete_user_template("del_me") is True
        assert not any(t.name == "del_me" for t in mgr.load_user_templates())

    def test_template_cannot_delete_builtin(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        result = mgr.delete_user_template("yt_shorts")
        assert result is False

    def test_template_upsert_on_same_name(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        mgr.save_user_template(_make_user_template("same"))
        updated = _make_user_template("same")
        # SubtitleStyle은 slots=True이므로 직접 할당 불가
        from src.models.project_template import ProjectTemplate
        from src.models.style import SubtitleStyle
        updated2 = ProjectTemplate("same", "Updated", 640, 480, 25.0, SubtitleStyle(), is_builtin=False)
        mgr.save_user_template(updated2)
        loaded = [t for t in mgr.load_user_templates() if t.name == "same"]
        assert len(loaded) == 1
        assert loaded[0].display_name == "Updated"


# ─────────────────────── apply_to_project ───────────────────────

class TestApplyToProject:
    def test_template_apply_to_project(self):
        from src.models.project import ProjectState
        from src.models.project_template import ProjectTemplate
        from src.models.style import SubtitleStyle
        from src.services.template_manager import TemplateManager

        project = ProjectState()
        tmpl = ProjectTemplate(
            name="apply_test",
            display_name="Apply Test",
            width=1920,
            height=1080,
            fps=30.0,
            subtitle_style=SubtitleStyle(font_size=24, font_color="#FF0000"),
        )
        TemplateManager.apply_to_project(tmpl, project)
        assert project.default_style.font_size == 24
        assert project.default_style.font_color == "#FF0000"

    def test_apply_resets_project(self):
        """템플릿 적용 시 프로젝트가 초기화된다."""
        from pathlib import Path
        from src.models.project import ProjectState
        from src.models.project_template import ProjectTemplate
        from src.models.style import SubtitleStyle
        from src.services.template_manager import TemplateManager

        project = ProjectState()
        project.video_path = Path("/fake/video.mp4")

        tmpl = ProjectTemplate("t", "T", 1080, 1920, 30.0, SubtitleStyle())
        TemplateManager.apply_to_project(tmpl, project)

        # reset() 호출로 video_path 초기화됨
        assert project.video_path is None


# ─────────────────────── i18n ───────────────────────

class TestTemplateI18nKeys:
    def test_template_i18n_keys(self):
        from src.utils.lang.ko import STRINGS
        required = [
            "Welcome to FastMovieMaker",
            "Recent Projects",
            "No recent projects",
            "Open Selected",
            "New from Template",
            "New Empty Project",
            "Open Project\u2026",
            "Skip",
            "Create",
        ]
        for key in required:
            assert key in STRINGS, f"Missing i18n key: {key!r}"
