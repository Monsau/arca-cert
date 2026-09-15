"""Vault integration — secrets, PKI, transit signing. References only, no plaintext secrets."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)


class VaultError(RuntimeError):
    """Raised when a Vault operation fails."""


class VaultClient:
    """Minimal Vault client for transit sign/verify operations.

    Authentication relies on the runtime environment (Vault agent, Kubernetes
    service-account token, or `VAULT_TOKEN`). No token is stored in settings.
    """

    def __init__(self, addr: str, role: str, timeout: float = 10.0):
        self.addr = addr.rstrip("/")
        self.role = role
        self.timeout = timeout

    def _token(self) -> str:
        token = os.environ.get("VAULT_TOKEN")
        if not token:
            raise VaultError("VAULT_TOKEN environment variable is not set")
        return token

    def _request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        import httpx

        url = f"{self.addr}{path}"
        headers = {"X-Vault-Token": self._token()}
        try:
            response = httpx.request(method, url, headers=headers, json=json_body, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Vault HTTP error: %s %s", exc.response.status_code, exc.response.text)
            raise VaultError(f"Vault request failed: {exc.response.status_code}") from exc
        except Exception as exc:
            logger.error("Vault request failed: %s", exc)
            raise VaultError(f"Vault request failed: {exc}") from exc

    def read_secret(self, path: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/{path}")

    def transit_encrypt(self, key_name: str, plaintext: bytes) -> str:
        b64 = base64.b64encode(plaintext).decode()
        result = self._request("POST", f"/v1/transit/encrypt/{key_name}", {"plaintext": b64})
        return result["data"]["ciphertext"]

    def transit_decrypt(self, key_name: str, ciphertext: str) -> bytes:
        result = self._request("POST", f"/v1/transit/decrypt/{key_name}", {"ciphertext": ciphertext})
        return base64.b64decode(result["data"]["plaintext"])

    def sign(self, key_name: str, payload: bytes) -> str:
        """Sign payload with the named transit key."""
        b64 = base64.b64encode(payload).decode()
        result = self._request("POST", f"/v1/transit/sign/{key_name}", {"input": b64})
        return result["data"]["signature"]

    def verify(self, key_name: str, payload: bytes, signature: str) -> bool:
        """Verify a transit signature against the named key."""
        b64 = base64.b64encode(payload).decode()
        result = self._request(
            "POST",
            f"/v1/transit/verify/{key_name}",
            {"input": b64, "signature": signature},
        )
        return result["data"]["valid"] is True

    def rotate(self, key_name: str) -> str:
        result = self._request("POST", f"/v1/transit/keys/{key_name}/rotate")
        return result["data"]["latest_version"]


class Signer:
    """Signature interface (dossier sealing)."""

    def sign(self, key_name: str, payload: bytes) -> str:
        raise NotImplementedError

    def verify(self, key_name: str, payload: bytes, signature: str) -> bool:
        raise NotImplementedError


class VaultTransitSigner(Signer):
    """Signature via Vault Transit (production)."""

    def __init__(self, client: VaultClient):
        self.client = client

    def sign(self, key_name: str, payload: bytes) -> str:
        return self.client.sign(key_name, payload)

    def verify(self, key_name: str, payload: bytes, signature: str) -> bool:
        return self.client.verify(key_name, payload, signature)


class DevSigner(Signer):
    """Development/test signer: local HMAC-SHA256.

    Must NOT be used in production. The constructor intentionally accepts a
    secret so tests can keep deterministic signatures.
    """

    def __init__(self, secret: bytes = b"arca-dev-signing-key"):
        self._secret = secret

    def sign(self, key_name: str, payload: bytes) -> str:
        digest = hmac.new(self._secret, key_name.encode() + b":" + payload, hashlib.sha256).hexdigest()
        return f"hmac-sha256:{digest}"

    def verify(self, key_name: str, payload: bytes, signature: str) -> bool:
        if not signature.startswith("hmac-sha256:"):
            return False
        expected = self.sign(key_name, payload)
        return hmac.compare_digest(expected, signature)


def get_signer() -> Signer:
    """Return the configured signer for this environment.

    Production must use Vault Transit; dev/test may use the HMAC dev signer.
    """
    backend = settings.signer_backend.lower()
    if backend == "vault":
        if not settings.vault_addr:
            raise RuntimeError("VAULT_ADDR is required for vault signer")
        return VaultTransitSigner(VaultClient(settings.vault_addr, settings.vault_role))
    if backend == "dev":
        if settings.environment.lower() not in ("dev", "test"):
            raise RuntimeError(
                "dev signer is not allowed outside dev/test environments; set CERT_SIGNER_BACKEND=vault"
            )
        return DevSigner()
    raise ValueError(f"unknown signer backend: {backend}")
