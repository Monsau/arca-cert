"""OIDC/JWT authentication for arca-cert (ADR-009).

Security by design: only asymmetric RS256 tokens verified against the
configured Keycloak JWKS are accepted. The JWKS URL is provided via
CERT_OIDC_JWKS_URL because the public issuer URL does not resolve inside
the cluster. The Suite portal injects the user's SSO access token on every
call; there is no local token minting and no symmetric fallback.
"""
import logging
import os
from dataclasses import dataclass

from jose import JWTError, jwt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    sub: str
    email: str
    roles: list[str]
    claims: dict

    @classmethod
    def from_claims(cls, claims: dict) -> "AuthenticatedUser":
        return cls(
            sub=claims.get("sub", ""),
            email=claims.get("email", ""),
            roles=_extract_roles(claims),
            claims=claims,
        )


def _extract_roles(claims: dict) -> list[str]:
    roles = claims.get("roles", []) or claims.get("groups", [])
    if isinstance(roles, str):
        roles = [r.strip() for r in roles.split(",") if r.strip()]
    realm_access = claims.get("realm_access", {})
    if isinstance(realm_access, dict):
        roles = list(set(roles) | set(realm_access.get("roles", [])))
    return roles


class OIDCValidator:
    """Strict RS256 validator backed by a Keycloak realm JWKS."""

    def __init__(self, issuer: str | None = None,
                 audience: str | None = None, jwks: list | None = None):
        self._issuer = issuer
        self._audience = audience
        self._jwks = jwks or []
        self._kid_to_key = {k.get("kid"): k for k in self._jwks if k.get("kid")}

    def validate(self, token: str) -> AuthenticatedUser:
        if not token:
            raise JWTError("missing token")
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise JWTError(f"unsupported algorithm {header.get('alg')}")
        kid = header.get("kid")
        key = self._kid_to_key.get(kid) if kid else None
        if key is None:
            raise JWTError(f"RS256 key not found for kid={kid}")
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=self._issuer,
            audience=self._audience,
        )
        return AuthenticatedUser.from_claims(claims)


_JWKS_CACHE: dict = {}


def _load_jwks(url: str) -> list:
    """Fetch the Keycloak realm JWKS when CERT_OIDC_JWKS_URL is set.

    The public issuer URL does not resolve inside the cluster, so the suite
    ships the in-cluster Keycloak JWKS URL via configuration.
    """
    if not url:
        return []
    if url not in _JWKS_CACHE:
        import httpx

        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        _JWKS_CACHE[url] = resp.json().get("keys", [])
    return _JWKS_CACHE[url]


def validator_from_settings(settings) -> OIDCValidator:
    issuer = os.environ.get("CERT_OIDC_ISSUER") or settings.oidc_issuer or None
    audience = os.environ.get("CERT_OIDC_AUDIENCE") or settings.oidc_audience
    jwks = _load_jwks(os.environ.get("CERT_OIDC_JWKS_URL", ""))
    return OIDCValidator(issuer=issuer, audience=audience, jwks=jwks)
