"""
Unit tests for Voice Support Architecture:
Provider-independent interface, mock provider, disabled fallback, and VoiceManager.
"""

import pytest

from voice_service import (
    DisabledVoiceProvider,
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
