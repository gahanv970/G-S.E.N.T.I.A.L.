"""
Provider-Independent Voice Architecture for G-AI-ASSISTANT.
Provides an abstract base interface for text-to-speech (TTS),
ensuring zero blocking of the Qt UI loop, lightweight resource consumption,
and future pluggability for Edge TTS or Kokoro TTS.
"""

from abc import ABC, abstractmethod
import logging
import os
import sys
import tempfile
import threading
from typing import Optional

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from config import get_config_value, get_secret, save_config, set_secret

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


class AudioPlayerSignals(QObject):
    play_audio_signal = Signal(bytes)


class ElevenLabsVoiceProvider(VoiceProvider):
    """
    ElevenLabs Text-to-Speech provider for custom authorized voice clones.
    Generates audio asynchronously via official ElevenLabs REST API and streams output safely on Qt main thread.
    """

    def __init__(self):
        self._api_key: Optional[str] = None
        self._voice_id: Optional[str] = None
        self._status: str = "Initializing ElevenLabs..."
        self._available: bool = False
        self._current_player = None
        self._audio_output = None
        self._temp_file_path: Optional[str] = None
        self._lock = threading.Lock()

        # Qt thread-safe signal for audio playback
        self._signals = AudioPlayerSignals()
        self._signals.play_audio_signal.connect(self._on_play_audio_bytes)

        self.reload_credentials()

    def reload_credentials(self) -> None:
        """Loads ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID from env or secure store."""
        self._api_key = get_secret("elevenlabs_api_key")
        self._voice_id = get_secret("elevenlabs_voice_id") or get_config_value("elevenlabs_voice_id", "")

        if self._api_key and self._voice_id:
            self._available = True
            masked_id = self._voice_id[:6] + "..." if len(self._voice_id) > 6 else self._voice_id
            self._status = f"ElevenLabs TTS ready (Voice ID: {masked_id})"
        elif not self._api_key:
            self._available = False
            self._status = "ElevenLabs API Key missing (Set ELEVENLABS_API_KEY env or configure in Settings)"
        else:
            self._available = False
            self._status = "ElevenLabs Voice ID missing (Set ELEVENLABS_VOICE_ID env or configure in Settings)"

    def speak(self, text: str) -> None:
        """Generates speech via ElevenLabs API in background thread and triggers main thread playback."""
        clean_text = (text or "").strip()
        if not clean_text or not self.is_available():
            logger.warning(f"ElevenLabs TTS unavailable: {self.get_status()}")
            return

        def _worker():
            try:
                import requests
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._voice_id}"
                headers = {
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                    "xi-api-key": self._api_key,
                }
                payload = {
                    "text": clean_text,
                    "model_id": "eleven_monolingual_v1",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                }
                response = requests.post(url, json=payload, headers=headers, timeout=12)
                if response.status_code == 200:
                    audio_data = response.content
                    self._play_audio_bytes(audio_data)
                elif response.status_code == 401:
                    logger.error("ElevenLabs API 401: Unauthorized API key.")
                    self._status = "ElevenLabs Error: Unauthorized API Key"
                elif response.status_code == 404:
                    logger.error(f"ElevenLabs API 404: Voice ID '{self._voice_id}' not found.")
                    self._status = "ElevenLabs Error: Invalid Voice ID"
                else:
                    logger.error(f"ElevenLabs API error HTTP {response.status_code}: {response.text}")
                    self._status = f"ElevenLabs HTTP Error {response.status_code}"
            except Exception as e:
                logger.error(f"ElevenLabs TTS generation failed: {e}")
                self._status = f"ElevenLabs Network Error: {e}"

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _play_audio_bytes(self, audio_bytes: bytes) -> None:
        """Emits signal to trigger main thread audio playback safely."""
        self._signals.play_audio_signal.emit(audio_bytes)

    @Slot(bytes)
    def _on_play_audio_bytes(self, audio_bytes: bytes) -> None:
        """Executes audio playback safely on Qt main GUI thread with temp file cleanup."""
        try:
            self._cleanup_temp_file()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                f.write(audio_bytes)
                self._temp_file_path = f.name

            with self._lock:
                if self._current_player:
                    self._current_player.stop()

                self._current_player = QMediaPlayer()
                self._audio_output = QAudioOutput()
                self._current_player.setAudioOutput(self._audio_output)
                self._audio_output.setVolume(1.0)
                self._current_player.setSource(QUrl.fromLocalFile(self._temp_file_path))
                self._current_player.mediaStatusChanged.connect(self._on_media_status_changed)
                self._current_player.play()
        except Exception as e:
            logger.error(f"Audio playback error: {e}")

    def _on_media_status_changed(self, status):
        """Cleans up temp audio file when media finishes or stops."""
        if status in (QMediaPlayer.EndOfMedia, QMediaPlayer.StoppedState):
            self._cleanup_temp_file()

    def _cleanup_temp_file(self):
        """Safely removes temporary MP3 audio file."""
        if self._temp_file_path and os.path.exists(self._temp_file_path):
            try:
                os.unlink(self._temp_file_path)
            except Exception as e:
                logger.debug(f"Could not delete temp audio file: {e}")
            finally:
                self._temp_file_path = None

    def stop(self) -> None:
        """Stops ongoing ElevenLabs audio playback and cleans temp files."""
        with self._lock:
            if self._current_player:
                try:
                    self._current_player.stop()
                except Exception as e:
                    logger.debug(f"Error stopping player: {e}")
        self._cleanup_temp_file()

    def is_available(self) -> bool:
        return self._available

    def get_status(self) -> str:
        return self._status


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
        if provider_name == "elevenlabs":
            self._provider = ElevenLabsVoiceProvider()
        elif provider_name == "windows_sapi":
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
