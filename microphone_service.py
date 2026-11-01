"""
Microphone Recording and Speech-to-Text (STT) Service for S.E.N.T.I.A.L.
Handles PySide6 QtMultimedia audio capture, push-to-talk recording, cancellation,
temporary audio cleanup, and Gemini multimodal speech-to-text transcription.
"""

import io
import logging
import os
import tempfile
import wave
from typing import Optional

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, Signal, Slot
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices

logger = logging.getLogger(__name__)


def check_microphone_availability() -> bool:
    """Returns True if a valid audio input device (microphone) is connected."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication.instance() or QApplication([])

        inputs = QMediaDevices.audioInputs()
        return bool(inputs and len(inputs) > 0)
    except Exception as e:
        logger.debug(f"Error checking microphone devices: {e}")
        return False


def create_standard_audio_format() -> QAudioFormat:
    """Returns standard 16kHz Mono 16-bit PCM audio format for speech recognition."""
    fmt = QAudioFormat()
    fmt.setSampleRate(16000)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.Int16)
    return fmt


class MicrophoneService(QObject):
    """
    Dedicated service for managing microphone capture, push-to-talk recording,
    cancellation, and audio stream processing.
    """

    recording_started = Signal()
    recording_stopped = Signal(bytes)  # Emits WAV audio bytes
    recording_cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio_source: Optional[QAudioSource] = None
        self._buffer: Optional[QBuffer] = None
        self._is_recording: bool = False
        self._format = create_standard_audio_format()

    def is_recording(self) -> bool:
        return self._is_recording

    def has_microphone(self) -> bool:
        return check_microphone_availability()

    @Slot()
    def start_recording(self) -> bool:
        """Starts capturing microphone audio."""
        if self._is_recording:
            return True

        if not self.has_microphone():
            logger.warning("No microphone input device detected.")
            return False

        try:
            default_device = QMediaDevices.defaultAudioInput()
            if not default_device or getattr(default_device, "isNull", lambda: True)():
                logger.warning("No valid default audio input device.")
                self._is_recording = False
                return False

            if hasattr(default_device, "isFormatSupported") and not default_device.isFormatSupported(self._format):
                self._format = default_device.preferredFormat()

            self._buffer = QBuffer()
            self._buffer.open(QIODevice.ReadWrite)

            self._audio_source = QAudioSource(default_device, self._format, self)
            self._audio_source.start(self._buffer)
            self._is_recording = True
            self.recording_started.emit()
            logger.info("Microphone recording started.")
            return True
        except Exception as e:
            logger.error(f"Failed to start microphone recording: {e}")
            self._is_recording = False
            return False

    @Slot()
    def stop_recording(self) -> bytes:
        """Stops recording and returns raw WAV audio bytes."""
        if not self._is_recording or not self._audio_source or not self._buffer:
            return b""

        try:
            self._audio_source.stop()
            self._is_recording = False

            raw_data = self._buffer.data().data()
            self._buffer.close()

            # Wrap PCM data into a standard WAV header
            wav_bytes = self._pcm_to_wav(
                raw_data,
                channels=self._format.channelCount(),
                sample_rate=self._format.sampleRate(),
                sample_size=2  # 16-bit = 2 bytes
            )

            logger.info(f"Microphone recording stopped ({len(wav_bytes)} bytes captured).")
            self.recording_stopped.emit(wav_bytes)
            return wav_bytes
        except Exception as e:
            logger.error(f"Error stopping microphone recording: {e}")
            self._is_recording = False
            return b""

    @Slot()
    def cancel_recording(self) -> None:
        """Cancels recording and discards audio buffer."""
        if self._audio_source:
            try:
                self._audio_source.stop()
            except Exception:
                pass
        if self._buffer:
            try:
                self._buffer.close()
            except Exception:
                pass

        self._is_recording = False
        logger.info("Microphone recording cancelled.")
        self.recording_cancelled.emit()

    def _pcm_to_wav(self, pcm_data: bytes, channels: int, sample_rate: int, sample_size: int) -> bytes:
        """Converts raw PCM audio bytes to WAV byte format."""
        if not pcm_data:
            return b""

        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(channels if channels > 0 else 1)
            wf.setsampwidth(sample_size)
            wf.setframerate(sample_rate if sample_rate > 0 else 16000)
            wf.writeframes(pcm_data)
        return out.getvalue()


def transcribe_audio_bytes(wav_bytes: bytes, ai_provider) -> str:
    """
    Transcribes audio WAV bytes into text using Google GenAI SDK multimodal vision/audio input.
    """
    if not wav_bytes or len(wav_bytes) < 200:
        logger.debug("Audio bytes empty or too small for transcription.")
        return ""

    if not ai_provider or not ai_provider.is_configured():
        raise RuntimeError("Gemini API key is not configured for Speech-to-Text.")

    if getattr(ai_provider, "_use_modern_sdk", False) and getattr(ai_provider, "_client", None):
        try:
            from google.genai import types

            audio_part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")
            prompt = (
                "Transcribe the spoken audio accurately into plain text. "
                "Do NOT add commentary, explanations, or notes outside the transcript."
            )

            response = ai_provider._client.models.generate_content(
                model=ai_provider.get_current_model(),
                contents=[audio_part, prompt]
            )

            if response and response.text:
                return response.text.strip()
            return ""
        except Exception as e:
            logger.error(f"Gemini audio transcription failed: {e}")
            raise RuntimeError(f"Speech-to-Text error: {e}") from e
    else:
        raise RuntimeError("Modern google-genai SDK client required for speech recognition.")
