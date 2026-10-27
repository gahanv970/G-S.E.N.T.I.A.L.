"""
Provider-Independent Voice Architecture for G-AI-ASSISTANT.
Provides an abstract base interface for text-to-speech (TTS),
ensuring zero blocking of the Qt UI loop, lightweight resource consumption,
and future pluggability for Edge TTS or Kokoro TTS.
"""

from abc import ABC, abstractmethod
import logging
import sys
import threading
from typing import Optional

from config import get_config_value, save_config

logger = logging.getLogger(__name__)


class VoiceProvider(ABC):
    """
    Abstract interface for Voice / Text-to-Speech engines.
    """

    @abstractmethod
    def speak(self, text: str) -> None:
        """Asynchronously plays spoken audio for text without blocking caller."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Immediately stops any ongoing speech playback."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the TTS backend is ready and operational."""
        pass

    @abstractmethod
    def get_status(self) -> str:
        """Returns a human-readable status description."""
        pass


class DisabledVoiceProvider(VoiceProvider):
    """Null provider when voice is disabled."""

    def speak(self, text: str) -> None:
        pass

    def stop(self) -> None:
        pass

    def is_available(self) -> bool:
        return False

    def get_status(self) -> str:
        return "Voice disabled in settings"


class MockVoiceProvider(VoiceProvider):
    """Mock provider for unit tests and verification."""

    def __init__(self):
        self.spoken_texts = []
        self.stopped = False

    def speak(self, text: str) -> None:
        self.spoken_texts.append(text)
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True

    def is_available(self) -> bool:
        return True

    def get_status(self) -> str:
        return "Mock TTS active"


class WindowsSapiVoiceProvider(VoiceProvider):
    """
    Native Windows SAPI provider using standard Windows COM / SAPI.
    Zero external dependencies, completely non-blocking via worker threads.
    """

    def __init__(self):
        self._sapi = None
        self._available = False
        self._status = "Initializing..."
        self._lock = threading.Lock()
        self._check_availability()

    def _check_availability(self) -> None:
        if sys.platform != "win32":
            self._available = False
            self._status = "SAPI only available on Windows"
            return

        try:
            # Test if SAPI is accessible via win32com or pythoncom
            import win32com.client
            # Attempt to create SAPI object
            test_voice = win32com.client.Dispatch("SAPI.SpVoice")
            self._sapi = test_voice
            self._available = True
            self._status = "Windows SAPI TTS ready"
            logger.info("Windows SAPI Voice Provider initialized.")
        except Exception as e:
            logger.debug(f"win32com SAPI not available: {e}. Voice fallback enabled.")
            self._available = False
            self._status = f"Windows SAPI not initialized: {e}"

    def speak(self, text: str) -> None:
        clean_text = (text or "").strip()
        if not clean_text or not self._available or not self._sapi:
            return

        def _worker():
            try:
                # Flag 1 = SVSFlagsAsync (Async speech in SAPI)
                with self._lock:
                    if self._sapi:
                        self._sapi.Speak(clean_text, 1)
            except Exception as e:
                logger.error(f"SAPI speak error: {e}")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def stop(self) -> None:
        if not self._available or not self._sapi:
            return
        try:
            with self._lock:
                if self._sapi:
                    # Flag 2 = SVSFPurgeBeforeSpeak with empty string cancels pending audio
                    self._sapi.Speak("", 2)
        except Exception as e:
            logger.debug(f"SAPI stop error: {e}")

    def is_available(self) -> bool:
        return self._available

    def get_status(self) -> str:
        return self._status


class VoiceManager:
    """
    Coordinates active voice provider based on configuration.
    """

    def __init__(self):
        self._provider: VoiceProvider = DisabledVoiceProvider()
        self.reload_provider()

    def reload_provider(self) -> None:
        """Reloads voice provider from configuration."""
        provider_name = get_config_value("voice_provider", "disabled").lower()
        if provider_name == "windows_sapi":
            self._provider = WindowsSapiVoiceProvider()
        elif provider_name == "mock":
            self._provider = MockVoiceProvider()
        else:
            self._provider = DisabledVoiceProvider()
        logger.info(f"VoiceManager active provider: {self._provider.__class__.__name__}")

    def set_provider_type(self, provider_type: str) -> None:
        save_config({"voice_provider": provider_type})
        self.reload_provider()

    def speak(self, text: str) -> None:
        if self._provider.is_available():
            self._provider.speak(text)

    def stop(self) -> None:
        if self._provider.is_available():
            self._provider.stop()

    def is_available(self) -> bool:
        return self._provider.is_available()

    def get_status(self) -> str:
        return self._provider.get_status()
