"""OIDC/JWT authentication for arca-cert (ADR-009).

Supports two modes:
- Development/tests: HS256 tokens validated with CERT_JWT_SECRET.
- Production: RS256 tokens validated via OIDC discovery (CERT_OIDC_ISSUER,
  CERT_OIDC_AUDIENCE) and JWKS.
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
    def __init__(self, secret: str | None = None, issuer: str | None = None,
                 audience: str | None = None, jwks: list | None = None):
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._jwks = jwks or []
        self._kid_to_key = {k.get("kid"): k for k in self._jwks if k.get("kid")}

    def validate(self, token: str) -> AuthenticatedUser:
        if not token:
            raise JWTError("missing token")
        header = jwt.get_unverified_header(token)
        algo = header.get("alg", "HS256")
        if algo == "HS256":
            if not self._secret:
                raise JWTError("HS256 configured without secret")
            claims = jwt.decode(token, self._secret, algorithms=["HS256"])
        elif algo == "RS256":
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
        else:
            raise JWTError(f"unsupported algorithm {algo}")
        return AuthenticatedUser.from_claims(claims)


def validator_from_settings(settings) -> OIDCValidator:
    secret = os.environ.get("CERT_JWT_SECRET") or settings.vault_addr
    issuer = os.environ.get("CERT_OIDC_ISSUER")
    audience = os.environ.get("CERT_OIDC_AUDIENCE", "arca-cert")
    return OIDCValidator(secret=secret, issuer=issuer, audience=audience)


def mint_dev_token(sub: str, roles: list[str], secret: str) -> str:
    """Issue an HS256 dev token. Only for local development and tests."""
    return jwt.encode(
        {"sub": sub, "email": f"{sub}@arca.local", "roles": roles},
        secret,
        algorithm="HS256",
    )
