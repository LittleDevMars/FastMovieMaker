"""프로젝트 템플릿 관리 서비스.

내장 3종 템플릿과 사용자 정의 템플릿을 제공한다.
"""

from __future__ import annotations

import dataclasses
import json
from typing import List, Optional

from PySide6.QtCore import QSettings

from src.models.project_template import ProjectTemplate
from src.models.style import SubtitleStyle


# ── 내장 템플릿 ──────────────────────────────────────────────────────────────

BUILTIN_TEMPLATES: List[ProjectTemplate] = [
    ProjectTemplate(
        name="yt_shorts",
        display_name="YouTube Shorts",
        width=1080,
        height=1920,
        fps=30.0,
        subtitle_style=SubtitleStyle(
            font_size=22,
            position="bottom-center",
            margin_bottom=120,
            outline_width=2,
        ),
        description="세로형 숏폼 (9:16)",
        is_builtin=True,
    ),
    ProjectTemplate(
        name="yt_commentary",
        display_name="YouTube Commentary",
        width=1920,
        height=1080,
        fps=30.0,
        subtitle_style=SubtitleStyle(
            font_size=18,
            position="bottom-center",
            margin_bottom=40,
            outline_width=1,
        ),
        description="가로형 해설 영상 (16:9)",
        is_builtin=True,
    ),
    ProjectTemplate(
        name="ig_reels",
        display_name="Instagram Reels",
        width=1080,
        height=1080,
        fps=30.0,
        subtitle_style=SubtitleStyle(
            font_size=20,
            position="bottom-center",
            margin_bottom=80,
            outline_width=2,
        ),
        description="정사각형 릴스 (1:1)",
        is_builtin=True,
    ),
]

_SETTINGS_KEY = "templates/user_templates"


class TemplateManager:
    """내장/사용자 템플릿 관리."""

    def __init__(self, settings: Optional[QSettings] = None) -> None:
        """
        Args:
            settings: QSettings 인스턴스. None 이면 기본 QSettings 사용.
        """
        self._settings = settings or QSettings()

    # ------------------------------------------------------------------ 조회

    def get_builtin_templates(self) -> List[ProjectTemplate]:
        """내장 템플릿 목록을 반환한다."""
        return list(BUILTIN_TEMPLATES)

    def load_user_templates(self) -> List[ProjectTemplate]:
        """QSettings에서 사용자 정의 템플릿을 로드한다."""
        raw = self._settings.value(_SETTINGS_KEY, "[]")
        try:
            items: list = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return []

        templates: List[ProjectTemplate] = []
        for item in items:
            try:
                style_data: dict = item.get("subtitle_style", {})
                valid_fields = {f.name for f in dataclasses.fields(SubtitleStyle)}
                style = SubtitleStyle(**{
                    k: v for k, v in style_data.items()
                    if k in valid_fields
                })
                templates.append(ProjectTemplate(
                    name=item["name"],
                    display_name=item["display_name"],
                    width=int(item["width"]),
                    height=int(item["height"]),
                    fps=float(item["fps"]),
                    subtitle_style=style,
                    is_builtin=False,
                    description=item.get("description", ""),
                ))
            except (KeyError, TypeError):
                continue
        return templates

    def get_all_templates(self) -> List[ProjectTemplate]:
        """내장 + 사용자 정의 템플릿 전체를 반환한다."""
        return self.get_builtin_templates() + self.load_user_templates()

    # ------------------------------------------------------------------ 저장/삭제

    def save_user_template(self, template: ProjectTemplate) -> None:
        """사용자 정의 템플릿을 QSettings에 저장한다.

        동일 name 이 이미 존재하면 덮어쓴다.
        """
        if template.is_builtin:
            raise ValueError("내장 템플릿은 수정할 수 없습니다.")

        existing = self.load_user_templates()
        # 동일 name 제거 후 추가 (upsert)
        updated = [t for t in existing if t.name != template.name]
        updated.append(template)
        self._save_user_templates(updated)

    def delete_user_template(self, name: str) -> bool:
        """사용자 정의 템플릿을 이름으로 삭제한다.

        Returns:
            삭제 성공 여부 (없으면 False).
        """
        # 내장 템플릿 삭제 시도 방지
        if any(t.name == name for t in BUILTIN_TEMPLATES):
            return False

        existing = self.load_user_templates()
        filtered = [t for t in existing if t.name != name]
        if len(filtered) == len(existing):
            return False
        self._save_user_templates(filtered)
        return True

    # ------------------------------------------------------------------ 적용

    @staticmethod
    def apply_to_project(template: ProjectTemplate, project) -> None:
        """템플릿 설정을 ProjectState에 적용한다.

        프로젝트를 초기화하고 템플릿의 자막 스타일을 기본값으로 설정한다.

        Args:
            template: 적용할 템플릿.
            project:  대상 ProjectState 인스턴스.
        """
        project.reset()
        project.default_style = template.subtitle_style.copy()

    # ------------------------------------------------------------------ 내부

    def _save_user_templates(self, templates: List[ProjectTemplate]) -> None:
        data = []
        for t in templates:
            style_data = {
                f.name: getattr(t.subtitle_style, f.name)
                for f in dataclasses.fields(t.subtitle_style)
            }
            data.append({
                "name": t.name,
                "display_name": t.display_name,
                "width": t.width,
                "height": t.height,
                "fps": t.fps,
                "subtitle_style": style_data,
                "description": t.description,
            })
        self._settings.setValue(_SETTINGS_KEY, json.dumps(data))
