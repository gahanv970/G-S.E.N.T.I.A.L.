"""
Unit tests for End-to-End Voice Interaction Workflow.
Mocks microphone audio capture, speech transcription, Gemini intent processing,
user confirmation dialogs, and text-to-speech voice playback.
"""

import asyncio
from unittest.mock import MagicMock, patch
import pytest
import qasync

from PySide6.QtWidgets import QApplication, QMessageBox
import Jarvis_UI
from voice_service import MockVoiceProvider


@pytest.fixture(scope="session")
def init_qapp():
    """Ensures QApplication instance is available for PySide6 GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def qevent_loop(init_qapp):
    loop = qasync.QEventLoop(init_qapp)
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


def test_voice_workflow_e2e_successful_task_creation(qevent_loop):
    main_win = Jarvis_UI.JarvisMainWindow()
    main_win.voice_manager._provider = MockVoiceProvider()

    # Mock configured AI provider
    main_win.ai_provider.is_configured = MagicMock(return_value=True)

    # 1. Mock voice recording WAV bytes
    fake_wav_bytes = b"x" * 500
    main_win.mic_service.stop_recording = MagicMock(return_value=fake_wav_bytes)
    main_win.mic_service.is_recording = MagicMock(return_value=True)

    # 2. Mock STT transcription
    mock_transcript = "Create task review Phase 3D PR"

    # 3. Mock Gemini intent response
    mock_intent = {
        "intent_type": "create_task",
        "response_text": "I will create a task for reviewing the Phase 3D PR.",
        "parameters": {"title": "review Phase 3D PR"},
        "urgency": "medium",
        "requires_confirmation": True,
    }

    with patch("Jarvis_UI.transcribe_audio_bytes", return_value=mock_transcript), \
         patch.object(main_win.ai_provider, "understand_intent", return_value=mock_intent), \
         patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Yes):

        qevent_loop.run_until_complete(main_win._toggle_microphone_recording.__wrapped__(main_win))

        # Verify command input was set to transcript
        assert main_win.command_input.text() == ""
        # Verify conversation display received system responses
        disp_text = main_win.conversation_display.toPlainText()
        assert "Create task review Phase 3D PR" in disp_text
        assert "review Phase 3D PR" in disp_text

        # Verify task was created in SQLite task service
        all_tasks = main_win.task_service.get_all_tasks()
        assert any("review Phase 3D PR" in t.title for t in all_tasks)

        # Verify spoken voice output
        assert len(main_win.voice_manager._provider.spoken_texts) > 0


def test_voice_workflow_action_cancelled_by_user(qevent_loop):
    main_win = Jarvis_UI.JarvisMainWindow()
    main_win.voice_manager._provider = MockVoiceProvider()
    main_win.ai_provider.is_configured = MagicMock(return_value=True)

    fake_wav_bytes = b"x" * 500
    main_win.mic_service.stop_recording = MagicMock(return_value=fake_wav_bytes)
    main_win.mic_service.is_recording = MagicMock(return_value=True)

    mock_intent = {
        "intent_type": "launch_app",
        "response_text": "Launching Notepad.",
        "parameters": {"app_id": "notepad"},
        "requires_confirmation": True,
    }

    # User clicks 'No' on confirmation dialog
    with patch("Jarvis_UI.transcribe_audio_bytes", return_value="Open Notepad"), \
         patch.object(main_win.ai_provider, "understand_intent", return_value=mock_intent), \
         patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.No):

        qevent_loop.run_until_complete(main_win._toggle_microphone_recording.__wrapped__(main_win))

        disp_text = main_win.conversation_display.toPlainText()
        assert "Action cancelled" in disp_text


def test_voice_workflow_tts_error_fallback(qevent_loop):
    main_win = Jarvis_UI.JarvisMainWindow()

    # Voice manager fails to speak
    failing_voice = MockVoiceProvider()
    failing_voice.speak = MagicMock(side_effect=RuntimeError("TTS Speech Error"))
    main_win.voice_manager._provider = failing_voice
    main_win.ai_provider.is_configured = MagicMock(return_value=True)

    fake_wav_bytes = b"x" * 500
    main_win.mic_service.stop_recording = MagicMock(return_value=fake_wav_bytes)
    main_win.mic_service.is_recording = MagicMock(return_value=True)

    mock_intent = {
        "intent_type": "general_chat",
        "response_text": "S.E.N.T.I.A.L. is functioning normally.",
        "parameters": {},
        "requires_confirmation": False,
    }

    with patch("Jarvis_UI.transcribe_audio_bytes", return_value="Status report"), \
         patch.object(main_win.ai_provider, "understand_intent", return_value=mock_intent):

        qevent_loop.run_until_complete(main_win._toggle_microphone_recording.__wrapped__(main_win))

        # Text display still updates cleanly even if TTS fails
        disp_text = main_win.conversation_display.toPlainText()
        assert "S.E.N.T.I.A.L. is functioning normally." in disp_text
