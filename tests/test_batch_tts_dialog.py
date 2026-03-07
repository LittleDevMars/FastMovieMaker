"""UI tests for provider-first BatchTtsDialog behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.ui.dialogs import batch_tts_dialog as batch_module
from src.services.tts_provider import TTSRequestErrorCode, serialize_tts_error
from src.utils.config import TTSEngine


class _DummySignal:
    def connect(self, _slot) -> None:
        pass


class _DummyThread:
    def __init__(self, *_args, **_kwargs) -> None:
        self.started = _DummySignal()

    def start(self) -> None:
        pass

    def isRunning(self) -> bool:
        return False

    def quit(self) -> None:
        pass

    def wait(self, _timeout: int) -> None:
        pass


class _FakeSettingsManager:
    def __init__(self, provider_id: str, elevenlabs_key: str = "") -> None:
        self._provider_id = provider_id
        self._elevenlabs_key = elevenlabs_key

    def get_tts_default_provider(self) -> str:
        return self._provider_id

    def get_elevenlabs_api_key(self) -> str:
        return self._elevenlabs_key


def test_batch_dialog_uses_preferred_provider_as_default(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        batch_module,
        "SettingsManager",
        lambda: _FakeSettingsManager(TTSEngine.ELEVENLABS),
    )
    monkeypatch.setattr(
        batch_module,
        "get_provider",
        lambda _engine: SimpleNamespace(list_voices=lambda _lang: [("Voice A", "voice_a")]),
    )
    dialog = batch_module.BatchTtsDialog(parent=None)
    qtbot.addWidget(dialog)

    assert dialog._engine_combo.currentData() == TTSEngine.ELEVENLABS
    assert dialog._voice_combo.count() == 1
    assert dialog._voice_combo.currentData() == "voice_a"
    assert dialog._start_btn.isEnabled()
    assert dialog._voice_state_label.text() == ""


def test_batch_dialog_engine_change_updates_voice_list(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        batch_module,
        "SettingsManager",
        lambda: _FakeSettingsManager(TTSEngine.EDGE_TTS),
    )

    def _get_provider(engine: str):
        if engine == TTSEngine.ELEVENLABS:
            voices = [("EL One", "el_1"), ("EL Two", "el_2")]
        else:
            voices = [("Edge One", "edge_1")]
        return SimpleNamespace(list_voices=lambda _lang: voices)

    monkeypatch.setattr(batch_module, "get_provider", _get_provider)
    dialog = batch_module.BatchTtsDialog(parent=None)
    qtbot.addWidget(dialog)

    idx = dialog._engine_combo.findData(TTSEngine.ELEVENLABS)
    dialog._engine_combo.setCurrentIndex(idx)

    assert dialog._voice_combo.count() == 2
    assert dialog._voice_combo.itemData(0) == "el_1"
    assert dialog._voice_combo.itemData(1) == "el_2"
    assert dialog._start_btn.isEnabled()
    assert dialog._voice_state_label.text() == ""


def test_batch_dialog_disables_start_when_provider_unavailable(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        batch_module,
        "SettingsManager",
        lambda: _FakeSettingsManager(TTSEngine.EDGE_TTS),
    )
    monkeypatch.setattr(batch_module, "get_provider", lambda _engine: None)

    dialog = batch_module.BatchTtsDialog(parent=None)
    qtbot.addWidget(dialog)

    assert not dialog._start_btn.isEnabled()
    assert dialog._voice_state_label.text()


def test_batch_dialog_disables_start_when_no_voice_available(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        batch_module,
        "SettingsManager",
        lambda: _FakeSettingsManager(TTSEngine.EDGE_TTS),
    )
    monkeypatch.setattr(
        batch_module,
        "get_provider",
        lambda _engine: SimpleNamespace(list_voices=lambda _lang: []),
    )

    dialog = batch_module.BatchTtsDialog(parent=None)
    qtbot.addWidget(dialog)

    assert dialog._voice_combo.count() == 0
    assert not dialog._start_btn.isEnabled()
    assert dialog._voice_state_label.text()


def test_batch_dialog_blocks_elevenlabs_without_api_key(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        batch_module,
        "SettingsManager",
        lambda: _FakeSettingsManager(TTSEngine.ELEVENLABS, elevenlabs_key=""),
    )
    monkeypatch.setattr(
        batch_module,
        "get_provider",
        lambda _engine: SimpleNamespace(
            list_voices=lambda _lang: [("EL One", "el_1")],
            requires_api_key=lambda: True,
        ),
    )

    warning_calls: list[tuple] = []
    monkeypatch.setattr(
        batch_module.QMessageBox,
        "warning",
        lambda *args, **kwargs: warning_calls.append((args, kwargs)),
    )

    called_worker = {"value": False}

    class _SpyWorker:
        def __init__(self, **_kwargs):
            called_worker["value"] = True

        def moveToThread(self, _thread) -> None:
            pass

        def cancel(self) -> None:
            pass

    monkeypatch.setattr(batch_module, "BatchTtsWorker", _SpyWorker)

    dialog = batch_module.BatchTtsDialog(parent=None)
    qtbot.addWidget(dialog)

    txt = tmp_path / "a.txt"
    txt.write_text("hello", encoding="utf-8")
    dialog._file_list.addItem(str(txt))
    dialog._output_edit.setText(str(tmp_path))

    dialog._on_start()

    assert warning_calls
    assert called_worker["value"] is False


def test_batch_dialog_starts_worker_with_engine_speed_voice(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        batch_module,
        "SettingsManager",
        lambda: _FakeSettingsManager(TTSEngine.EDGE_TTS, elevenlabs_key="dummy"),
    )

    def _get_provider(engine: str):
        if engine == TTSEngine.ELEVENLABS:
            return SimpleNamespace(list_voices=lambda _lang: [("EL One", "el_1")])
        return SimpleNamespace(list_voices=lambda _lang: [("Edge One", "edge_1")])

    monkeypatch.setattr(batch_module, "get_provider", _get_provider)
    monkeypatch.setattr(batch_module, "QThread", _DummyThread)

    created_kwargs: dict = {}

    class _SpyWorker:
        def __init__(self, **kwargs):
            created_kwargs.update(kwargs)
            self.job_started = _DummySignal()
            self.job_finished = _DummySignal()
            self.progress = _DummySignal()
            self.all_finished = _DummySignal()
            self.error = _DummySignal()

        def moveToThread(self, _thread) -> None:
            pass

        def run(self) -> None:
            pass

        def cancel(self) -> None:
            pass

    monkeypatch.setattr(batch_module, "BatchTtsWorker", _SpyWorker)

    dialog = batch_module.BatchTtsDialog(parent=None)
    qtbot.addWidget(dialog)
    txt = tmp_path / "a.txt"
    txt.write_text("hello", encoding="utf-8")
    dialog._file_list.addItem(str(txt))
    dialog._output_edit.setText(str(tmp_path))
    dialog._speed_slider.setValue(15)  # 1.5x

    idx = dialog._engine_combo.findData(TTSEngine.ELEVENLABS)
    dialog._engine_combo.setCurrentIndex(idx)
    dialog._voice_combo.setCurrentIndex(0)

    dialog._on_start()

    assert created_kwargs["engine"] == TTSEngine.ELEVENLABS
    assert created_kwargs["voice"] == "el_1"
    assert created_kwargs["speed"] == 1.5
    assert len(created_kwargs["jobs"]) == 1
    assert created_kwargs["jobs"][0].txt_path == Path(str(txt))


def test_batch_dialog_worker_error_uses_presenter_message(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        batch_module,
        "SettingsManager",
        lambda: _FakeSettingsManager(TTSEngine.EDGE_TTS),
    )
    monkeypatch.setattr(
        batch_module,
        "get_provider",
        lambda _engine: SimpleNamespace(list_voices=lambda _lang: [("Edge One", "edge_1")]),
    )
    critical_calls: list[tuple] = []
    monkeypatch.setattr(
        batch_module.QMessageBox,
        "critical",
        lambda *args, **kwargs: critical_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        batch_module,
        "to_user_message",
        lambda _msg: "friendly from presenter",
    )

    dialog = batch_module.BatchTtsDialog(parent=None)
    qtbot.addWidget(dialog)
    dialog._on_worker_error(
        serialize_tts_error(TTSRequestErrorCode.INVALID_SPEED, "speed must be between 0.1 and 4.0")
    )

    assert critical_calls
    msg = critical_calls[0][0][2]
    assert msg == "friendly from presenter"


def test_batch_dialog_includes_plugin_provider_from_registry(qtbot, monkeypatch) -> None:
    providers = {
        TTSEngine.EDGE_TTS: SimpleNamespace(
            provider_id=TTSEngine.EDGE_TTS,
            display_name="Edge-TTS (Free)",
            list_voices=lambda _lang: [("Edge One", "edge_1")],
            requires_api_key=lambda: False,
        ),
        "plugin.demo": SimpleNamespace(
            provider_id="plugin.demo",
            display_name="Plugin Demo",
            list_voices=lambda _lang: [("Plugin Voice", "plugin_1")],
            requires_api_key=lambda: False,
        ),
    }
    monkeypatch.setattr(
        batch_module,
        "SettingsManager",
        lambda: _FakeSettingsManager("plugin.demo", elevenlabs_key="dummy"),
    )
    monkeypatch.setattr(batch_module, "get_all_providers", lambda: providers)
    monkeypatch.setattr(batch_module, "get_provider", lambda engine: providers.get(engine))

    dialog = batch_module.BatchTtsDialog(parent=None)
    qtbot.addWidget(dialog)

    assert dialog._engine_combo.findData("plugin.demo") >= 0
    assert dialog._engine_combo.currentData() == "plugin.demo"
    assert dialog._voice_combo.currentData() == "plugin_1"


def test_batch_dialog_blocks_provider_requiring_api_key(qtbot, monkeypatch, tmp_path) -> None:
    provider = SimpleNamespace(
        provider_id="plugin.requires_key",
        display_name="Plugin Requires Key",
        list_voices=lambda _lang: [("Voice", "voice_1")],
        requires_api_key=lambda: True,
    )
    providers = {provider.provider_id: provider}
    monkeypatch.setattr(
        batch_module,
        "SettingsManager",
        lambda: _FakeSettingsManager("plugin.requires_key", elevenlabs_key=""),
    )
    monkeypatch.setattr(batch_module, "get_all_providers", lambda: providers)
    monkeypatch.setattr(batch_module, "get_provider", lambda engine: providers.get(engine))

    warning_calls: list[tuple] = []
    monkeypatch.setattr(
        batch_module.QMessageBox,
        "warning",
        lambda *args, **kwargs: warning_calls.append((args, kwargs)),
    )

    dialog = batch_module.BatchTtsDialog(parent=None)
    qtbot.addWidget(dialog)
    txt = tmp_path / "a.txt"
    txt.write_text("hello", encoding="utf-8")
    dialog._file_list.addItem(str(txt))
    dialog._output_edit.setText(str(tmp_path))
    dialog._on_start()

    assert warning_calls
    assert "API Key Required" in warning_calls[0][0][1]
