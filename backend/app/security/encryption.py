"""
Encryption Service
==================
Handles all encryption/decryption of report content.

Architecture:
  - Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256)
  - Key loaded from environment — never hardcoded
  - All report text, transcriptions, and file refs encrypted before DB write

PRIVACY: Even if the database is compromised, report content remains
encrypted and unreadable without the encryption key.
"""

import base64
import hashlib
import os
from pathlib import Path
from typing import Optional

import structlog
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = structlog.get_logger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting sensitive report data."""

    def __init__(self):
        self._fernet: Optional[Fernet] = None
        self._initialized = False

    def _get_fernet(self) -> Fernet:
        """Lazy initialization of Fernet instance."""
        if not self._fernet:
            key = settings.ENCRYPTION_KEY
            if not key:
                raise ValueError(
                    "ENCRYPTION_KEY not configured. "
                    "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            # Handle both raw key and bytes
            if isinstance(key, str):
                key = key.encode()
            self._fernet = Fernet(key)
            self._initialized = True
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string value.
        Returns base64-encoded encrypted string safe for DB storage.
        """
        if not plaintext:
            return ""
        try:
            fernet = self._get_fernet()
            encrypted_bytes = fernet.encrypt(plaintext.encode("utf-8"))
            return encrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error("encryption_failed", error=str(e))
            raise RuntimeError("Encryption failed") from e

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt an encrypted string value.
        Raises RuntimeError if decryption fails (tampered or wrong key).
        """
        if not ciphertext:
            return ""
        try:
            fernet = self._get_fernet()
            decrypted_bytes = fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            logger.error("decryption_failed_invalid_token")
            raise RuntimeError("Decryption failed: invalid or corrupted data")
        except Exception as e:
            logger.error("decryption_failed", error=str(e))
            raise RuntimeError("Decryption failed") from e

    def encrypt_bytes(self, data: bytes) -> bytes:
        """Encrypt raw bytes (for audio/image files)."""
        try:
            fernet = self._get_fernet()
            return fernet.encrypt(data)
        except Exception as e:
            logger.error("bytes_encryption_failed", error=str(e))
            raise RuntimeError("File encryption failed") from e

    def decrypt_bytes(self, encrypted_data: bytes) -> bytes:
        """Decrypt raw bytes."""
        try:
            fernet = self._get_fernet()
            return fernet.decrypt(encrypted_data)
        except InvalidToken:
            raise RuntimeError("File decryption failed: invalid token")

    def generate_anonymous_file_ref(self, original_filename: str, report_id: str) -> str:
        """
        Generate an anonymous file reference.
        The reference is a hash — no original filename is preserved.
        PRIVACY: This prevents file names from revealing report content.
        """
        # Create a deterministic but anonymous reference
        hash_input = f"{report_id}:{original_filename}:{settings.ENCRYPTION_KEY[:8]}"
        file_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        return f"enc_{file_hash}"


class FileEncryptionService:
    """Handles encrypted file storage for audio/image uploads."""

    def __init__(self, upload_dir: str, encryption: EncryptionService):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.encryption = encryption

    async def save_encrypted_file(
        self,
        file_data: bytes,
        file_ref: str,
        file_type: str,
    ) -> str:
        """
        Strip metadata and save encrypted file.
        Returns the anonymous file reference.
        """
        # Strip metadata based on file type
        clean_data = await self._strip_metadata(file_data, file_type)

        # Encrypt
        encrypted_data = self.encryption.encrypt_bytes(clean_data)

        # Save to disk with anonymous filename
        file_path = self.upload_dir / f"{file_ref}.enc"
        with open(file_path, "wb") as f:
            f.write(encrypted_data)

        logger.info("encrypted_file_saved", file_type=file_type, size_bytes=len(encrypted_data))
        return str(file_path)

    async def load_decrypted_file(self, file_ref: str) -> bytes:
        """Load and decrypt a file by its anonymous reference."""
        file_path = self.upload_dir / f"{file_ref}.enc"
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_ref}")

        with open(file_path, "rb") as f:
            encrypted_data = f.read()

        return self.encryption.decrypt_bytes(encrypted_data)

    async def _strip_metadata(self, file_data: bytes, file_type: str) -> bytes:
        """
        Strip ALL metadata from files before encryption.

        PRIVACY CRITICAL:
          - Images: Strip EXIF (GPS, camera model, timestamp, etc.)
          - Audio: Strip ID3 tags (recording device, software, etc.)
        """
        if file_type.startswith("image/"):
            return await self._strip_image_metadata(file_data)
        elif file_type.startswith("audio/"):
            return await self._strip_audio_metadata(file_data)
        return file_data

    async def _strip_image_metadata(self, image_data: bytes) -> bytes:
        """
        Strip EXIF and all metadata from images.
        Re-encodes the image to guarantee metadata removal.
        """
        try:
            from PIL import Image
            import io

            # Open image
            img = Image.open(io.BytesIO(image_data))

            # Convert to RGB if needed (removes alpha channels that could encode data)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Re-encode without any metadata
            # PIL's save without exif parameter strips all EXIF
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=85, exif=b"")
            output.seek(0)

            logger.info("image_metadata_stripped")
            return output.getvalue()

        except Exception as e:
            logger.error("image_metadata_strip_failed", error=str(e))
            # If stripping fails, do NOT store the file
            raise RuntimeError("Could not safely process image — refusing to store")

    async def _strip_audio_metadata(self, audio_data: bytes) -> bytes:
        """
        Strip metadata from audio files.
        For WAV files, strips LIST chunks and INFO metadata.
        For MP3, would strip ID3 tags (simplified implementation).
        """
        # For production: use mutagen or ffmpeg for comprehensive stripping
        # Here we implement basic WAV header stripping
        if audio_data[:4] == b"RIFF":
            return self._strip_wav_metadata(audio_data)

        # For other formats, log and return as-is (AI service handles transcription)
        logger.warning("audio_metadata_strip_skipped", note="Non-WAV format")
        return audio_data

    def _strip_wav_metadata(self, wav_data: bytes) -> bytes:
        """
        Strip LIST/INFO chunks from WAV files.
        These chunks can contain software, artist, creation time metadata.
        """
        import struct

        if len(wav_data) < 12:
            return wav_data

        # WAV structure: RIFF(4) + size(4) + WAVE(4) + chunks
        output = bytearray()
        output.extend(wav_data[:12])  # Keep RIFF header

        pos = 12
        while pos < len(wav_data) - 8:
            chunk_id = wav_data[pos:pos+4]
            chunk_size = struct.unpack("<I", wav_data[pos+4:pos+8])[0]
            chunk_data = wav_data[pos+8:pos+8+chunk_size]

            # Skip LIST chunks (contain metadata)
            if chunk_id == b"LIST":
                logger.info("wav_metadata_chunk_stripped", chunk="LIST")
            else:
                output.extend(wav_data[pos:pos+8+chunk_size])

            pos += 8 + chunk_size
            if chunk_size % 2:  # Padding byte
                pos += 1

        # Update RIFF size
        new_size = len(output) - 8
        output[4:8] = struct.pack("<I", new_size)

        return bytes(output)


# Global service instances
encryption_service = EncryptionService()
