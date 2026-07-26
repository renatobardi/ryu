"""Criptografia simétrica simples para secrets de integrações (tokens de VCS,
Slack/Lark bot tokens, webhook secrets etc.) usando apenas hashlib+hmac —
sem dependências novas (sem Fernet/cryptography).

Esquema: keystream determinístico via HMAC-SHA256 em modo contador,
XOR com o plaintext, resultado em base64 urlsafe. Chave derivada de
RYU_INTEGRATIONS_SECRET_KEY (fallback: RYU_JWT_SECRET) — nunca comitada.
Isso NÃO é AEAD (sem autenticação de integridade); é suficiente para
"não guardar token em texto puro no banco", não para uso adversarial.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from ryu.config import settings


def _key() -> bytes:
    raw = getattr(settings, "integrations_secret_key", None) or settings.jwt_secret or "ryu-default"
    return raw.encode()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def encrypt_secret(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    if plaintext == "":
        return ""
    key = _key()
    nonce = hashlib.sha256((plaintext[:1] + str(len(plaintext))).encode()).digest()[:16]
    data = plaintext.encode()
    ks = _keystream(key, nonce, len(data))
    cipher = bytes(a ^ b for a, b in zip(data, ks))
    return "enc:" + base64.urlsafe_b64encode(nonce + cipher).decode()


def decrypt_secret(stored: str | None) -> str | None:
    if not stored:
        return stored
    if not stored.startswith("enc:"):
        return stored  # compat: valor legado não criptografado
    raw = base64.urlsafe_b64decode(stored[4:].encode())
    nonce, cipher = raw[:16], raw[16:]
    key = _key()
    ks = _keystream(key, nonce, len(cipher))
    data = bytes(a ^ b for a, b in zip(cipher, ks))
    return data.decode()


def mask_secret(plaintext_or_none: str | None) -> str:
    if not plaintext_or_none:
        return ""
    if len(plaintext_or_none) <= 6:
        return "***"
    return plaintext_or_none[:3] + "…" + plaintext_or_none[-3:]


def verify_hmac_sha256(secret: str, payload: bytes, signature: str, prefix: str = "sha256=") -> bool:
    """Verifica assinatura HMAC-SHA256 hex, no formato `sha256=<hex>` (GitHub)
    ou hex puro (Forgejo/Gitea)."""
    if not secret or not signature:
        return False
    sig = signature[len(prefix):] if signature.startswith(prefix) else signature
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False
