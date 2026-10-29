"""
Unit tests for Voice Support Architecture:
Provider-independent interface, mock provider, disabled fallback, and VoiceManager.
"""

import pytest

from unittest.mock import MagicMock, patch
from voice_service import (
    DisabledVoiceProvider,
    ElevenLabsVoiceProvider,
    MockVoiceProvider,
    VoiceManager,
    VoiceProvider,
)


def test_mock_voice_provider():
    provider = MockVoiceProvider()
    assert provider.is_available() is True
    provider.speak("Test voice speech")
    assert "Test voice speech" in provider.spoken_texts

    provider.stop()
    assert provider.stopped is True


def test_disabled_voice_provider():
    provider = DisabledVoiceProvider()
    assert provider.is_available() is False
    # Should not raise exception
    provider.speak("Silent audio")
    provider.stop()


def test_voice_manager():
    mgr = VoiceManager()
    mgr._provider = MockVoiceProvider()

    assert mgr.is_available() is True
    mgr.speak("Voice output from manager")
    assert "Voice output from manager" in mgr._provider.spoken_texts

    mgr.stop()
    assert mgr._provider.stopped is True


def test_elevenlabs_voice_provider_missing_credentials():
    with patch("voice_service.get_secret", return_value=None), patch("voice_service.get_config_value", return_value=""):
        provider = ElevenLabsVoiceProvider()
        assert provider.is_available() is False
        assert "API Key missing" in provider.get_status()


def test_elevenlabs_voice_provider_missing_voice_id():
    def mock_secret(key):
        return "fake_key_123" if key == "elevenlabs_api_key" else None

    with patch("voice_service.get_secret", side_effect=mock_secret), patch("voice_service.get_config_value", return_value=""):
        provider = ElevenLabsVoiceProvider()
        assert provider.is_available() is False
        assert "Voice ID missing" in provider.get_status()


@patch("requests.post")
def test_elevenlabs_voice_provider_speak_success(mock_post):
    def mock_secret(key):
        if key == "elevenlabs_api_key":
            return "fake_key_123"
        if key == "elevenlabs_voice_id":
            return "21m00Tcm4TlvDq8ikWAM"
        return None

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"fake_mp3_bytes"
    mock_post.return_value = mock_resp

    with patch("voice_service.get_secret", side_effect=mock_secret), patch.object(ElevenLabsVoiceProvider, "_play_audio_bytes") as mock_play:
        provider = ElevenLabsVoiceProvider()
        assert provider.is_available() is True
        provider.speak("Hello from ElevenLabs!")

        # Wait briefly for background thread to run
        import time
        time.sleep(0.2)

        assert mock_post.called
        assert "21m00Tcm4TlvDq8ikWAM" in mock_post.call_args[0][0]


@patch("requests.post")
def test_elevenlabs_voice_provider_http_401_error(mock_post):
    def mock_secret(key):
        return "invalid_key" if key == "elevenlabs_api_key" else "21m00Tcm4TlvDq8ikWAM"

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_post.return_value = mock_resp

    with patch("voice_service.get_secret", side_effect=mock_secret):
        provider = ElevenLabsVoiceProvider()
        provider.speak("Test 401")

        import time
        time.sleep(0.2)

        assert "Unauthorized" in provider.get_status()
