"""Authenticated encryption for user-provided Apify API tokens."""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_AAD = b"scoutwise:apify-credential:v1"
_ENV_NAME = "SCOUTWISE_CREDENTIAL_ENCRYPTION_KEY"


def _key(environ: dict[str, str] | None = None) -> bytes:
    raw = (environ or os.environ).get(_ENV_NAME, "").strip()
    if not raw:
        raise RuntimeError(f"{_ENV_NAME} is not configured")
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError(f"{_ENV_NAME} must be URL-safe base64") from exc
    if len(decoded) != 32:
        raise RuntimeError(f"{_ENV_NAME} must decode to exactly 32 bytes")
    return decoded


def encrypt_secret(value: str, *, environ: dict[str, str] | None = None) -> str:
    if not value or value != value.strip() or any(char.isspace() for char in value):
        raise ValueError("Credential format is invalid.")
    nonce = os.urandom(12)
    encrypted = AESGCM(_key(environ)).encrypt(nonce, value.encode("utf-8"), _AAD)
    return "v1." + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_secret(value: str, *, environ: dict[str, str] | None = None) -> str:
    if not value.startswith("v1."):
        raise ValueError("Credential format is unsupported.")
    try:
        packed = base64.urlsafe_b64decode(value[3:].encode("ascii"))
        return AESGCM(_key(environ)).decrypt(packed[:12], packed[12:], _AAD).decode("utf-8")
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("Credential could not be decrypted.") from exc
