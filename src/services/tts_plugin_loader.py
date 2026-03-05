"""Dynamic loader for external TTS provider plugins."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from types import ModuleType

from src.services.tts_provider import TTSProvider

_logger = logging.getLogger(__name__)


def _load_module_from_path(path: Path) -> ModuleType:
    module_name = f"fmm_tts_plugin_{path.stem}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to create module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_valid_provider_instance(provider: object) -> bool:
    required_methods = (
        "requires_api_key",
        "list_voices",
        "synthesize",
        "generate_segments",
    )
    if not isinstance(getattr(provider, "provider_id", None), str):
        return False
    if not str(getattr(provider, "provider_id", "")).strip():
        return False
    if not isinstance(getattr(provider, "display_name", None), str):
        return False
    for method_name in required_methods:
        if not callable(getattr(provider, method_name, None)):
            return False
    return True


def load_tts_plugin_providers(
    paths: list[str],
    *,
    reserved_provider_ids: set[str] | None = None,
) -> tuple[dict[str, TTSProvider], list[str]]:
    """Load plugin providers from file paths with failure isolation."""
    providers: dict[str, TTSProvider] = {}
    errors: list[str] = []
    reserved_ids = reserved_provider_ids or set()

    for raw_path in paths:
        plugin_path = Path(str(raw_path)).expanduser()
        if not plugin_path.is_file():
            continue

        try:
            module = _load_module_from_path(plugin_path)
            register_fn = getattr(module, "register_tts_providers", None)
            if not callable(register_fn):
                raise RuntimeError("register_tts_providers() is missing")

            registered = register_fn()
            if not isinstance(registered, list):
                raise RuntimeError("register_tts_providers() must return list[TTSProvider]")
            if len(registered) == 0:
                raise RuntimeError("register_tts_providers() returned an empty provider list")

            for provider in registered:
                if not _is_valid_provider_instance(provider):
                    msg = f"{plugin_path}: invalid provider object ignored"
                    errors.append(msg)
                    _logger.warning(msg)
                    continue
                provider_id = str(provider.provider_id)
                if provider_id in reserved_ids:
                    msg = f"{plugin_path}: provider_id '{provider_id}' conflicts with builtin provider"
                    errors.append(msg)
                    _logger.warning(msg)
                    continue
                if provider_id in providers:
                    msg = f"{plugin_path}: duplicate provider_id '{provider_id}' ignored"
                    errors.append(msg)
                    _logger.warning(msg)
                    continue
                providers[provider_id] = provider

        except Exception as exc:  # pragma: no cover - defensive path
            msg = f"{plugin_path}: {exc}"
            errors.append(msg)
            _logger.warning(msg)

    return providers, errors
