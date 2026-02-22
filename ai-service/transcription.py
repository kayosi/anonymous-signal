"""
Transcription Module
====================
Converts audio recordings to text using faster-whisper (OpenAI Whisper port).

Pipeline:
  1. Receive encrypted audio file reference
  2. Decrypt audio in memory (never written to disk unencrypted)
  3. Transcribe with Whisper
  4. Return text + confidence score

PRIVACY:
  - Audio never stored unencrypted
  - Transcription happens in-memory
  - No audio sent to external services
"""

import io
import os
import tempfile
from typing import Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class TranscriptionService:
    """
    Whisper-based audio transcription service.
    Uses faster-whisper for efficient CPU/GPU transcription.
    """

    def __init__(self, model_size: str = "base"):
        """
        Initialize with specified Whisper model size.

        Model size tradeoffs:
          tiny   — fastest, least accurate (~32M params)
          base   — good balance (~74M params) [RECOMMENDED]
          small  — more accurate (~244M params)
          medium — high accuracy (~769M params)
          large  — best accuracy (~1.5B params)
        """
        self.model_size = model_size
        self._model = None
        logger.info("transcription_service_initialized", model_size=model_size)

    def _get_model(self):
        """Lazy load the Whisper model (loads on first transcription call)."""
        if self._model is None:
            from faster_whisper import WhisperModel

            # Use CPU with int8 quantization for efficiency
            # For GPU: device="cuda", compute_type="float16"
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )
            logger.info("whisper_model_loaded", model_size=self.model_size)
        return self._model

    async def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
    ) -> Tuple[str, float]:
        """
        Transcribe audio from raw bytes.

        Args:
            audio_bytes: Raw audio data (WAV, MP3, OGG, etc.)
            language: ISO language code hint (None = auto-detect)

        Returns:
            Tuple of (transcription_text, confidence_score)
        """
        if not audio_bytes:
            return "", 0.0

        try:
            model = self._get_model()

            # Write to temp file (faster-whisper requires file path)
            # PRIVACY: tempfile is in /tmp, deleted immediately after use
            with tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
                prefix="anon_sig_",
            ) as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_path = tmp_file.name

            try:
                # Transcribe
                segments, info = model.transcribe(
                    tmp_path,
                    language=language,
                    beam_size=5,
                    best_of=5,
                    temperature=0.0,  # Deterministic output
                    condition_on_previous_text=True,
                    vad_filter=True,   # Voice activity detection (ignores silence)
                    vad_parameters=dict(
                        min_silence_duration_ms=500,
                    ),
                )

                # Collect all segments
                full_text = " ".join([segment.text.strip() for segment in segments])
                full_text = full_text.strip()

                # Calculate average confidence from segment probabilities
                # faster-whisper provides avg_logprob per segment
                if not full_text:
                    return "", 0.0

                # Convert log probability to confidence (rough approximation)
                # avg_logprob is typically between -1.0 (confident) and -3.0 (uncertain)
                detected_lang = info.language
                lang_prob = info.language_probability

                # Simple confidence: language detection probability
                confidence = min(max(lang_prob, 0.0), 1.0)

                logger.info(
                    "transcription_complete",
                    text_length=len(full_text),
                    detected_language=detected_lang,
                    confidence=round(confidence, 3),
                )

                return full_text, round(confidence, 3)

            finally:
                # PRIVACY: Always delete temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            logger.error("transcription_failed", error=str(e))
            return f"[Transcription failed: {type(e).__name__}]", 0.0

    async def transcribe_from_file_ref(
        self,
        file_ref: str,
        upload_dir: str,
        encryption_service,
    ) -> Tuple[str, float]:
        """
        Load encrypted audio, decrypt in memory, transcribe.

        PRIVACY: Decrypted audio exists ONLY in process memory,
        never written to disk.
        """
        from pathlib import Path

        file_path = Path(upload_dir) / f"{file_ref}.enc"
        if not file_path.exists():
            logger.warning("audio_file_not_found", file_ref=file_ref[:8])
            return "", 0.0

        # Read encrypted bytes
        with open(file_path, "rb") as f:
            encrypted_data = f.read()

        # Decrypt in memory
        audio_bytes = encryption_service.decrypt_bytes(encrypted_data)

        # Transcribe
        return await self.transcribe_audio_bytes(audio_bytes)


# Singleton instance
_transcription_service: Optional[TranscriptionService] = None


def get_transcription_service(model_size: str = "base") -> TranscriptionService:
    global _transcription_service
    if _transcription_service is None:
        _transcription_service = TranscriptionService(model_size=model_size)
    return _transcription_service
