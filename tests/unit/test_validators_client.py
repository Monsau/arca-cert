"""Validators client unit tests — evidence content gate semantics.

Covers the fail-closed contract: denied/degraded outcomes must never report
valid content, the Null adapter must be a documented no-op, and the caller's
Authorization header must be forwarded verbatim (security by design). Mirrors
the packs reference adapter tests.
"""
import pytest

from src.infra.validators import (
    HttpContentValidator,
    NullContentValidator,
    ValidationOutcome,
    build_content_validator,
)


class _Response:
    def __init__(self, status_code, body=None, text=""):
        self.status_code = status_code
        self._body = body
        self.text = text
        self.content = b"{}" if body is not None else b""

    def json(self):
        return self._body


def _fake_client(response=None, error=None):
    class Client:
        def __init__(self):
            self.calls = []

        def post(self, url, json=None, headers=None):
            self.calls.append({"url": url, "json": json, "headers": headers})
            if error is not None:
                raise error
            return response

        def close(self):
            pass

    return Client()


def test_null_adapter_is_documented_noop():
    outcome = NullContentValidator().validate_ontology("@prefix x: <http://x/> .")
    assert outcome.status == "disabled"
    assert outcome.valid is True  # gate disabled, not failed


def test_factory_without_url_selects_null(monkeypatch):
    monkeypatch.setattr("src.infra.validators.settings.validators_url", "")
    assert isinstance(build_content_validator(), NullContentValidator)


def test_factory_with_url_selects_http(monkeypatch):
    # Cert reads the module-level Settings instance (import-time env), so patch
    # the settings attribute instead of the process env.
    monkeypatch.setattr("src.infra.validators.settings.validators_url", "http://validate:8080")
    validator = build_content_validator()
    assert isinstance(validator, HttpContentValidator)
    validator.close()


def test_valid_content_maps_to_valid():
    client = _fake_client(response=_Response(200, {"valid": True, "checks": []}))
    validator = HttpContentValidator("http://validate", client=client)
    outcome = validator.validate_ontology("<ttl>", authorization="Bearer tok")
    assert outcome.valid is True and outcome.status == "valid"
    assert client.calls[0]["headers"] == {"Authorization": "Bearer tok"}
    assert client.calls[0]["json"]["artifact_kind"] == "ontology_ttl"
    assert client.calls[0]["json"]["content"] == "<ttl>"


def test_invalid_content_maps_to_invalid():
    checks = [{"gate": "shacl-contracts", "passed": False, "message": "missing fr label"}]
    client = _fake_client(response=_Response(200, {"valid": False, "checks": checks}))
    validator = HttpContentValidator("http://validate", client=client)
    outcome = validator.validate_ontology("<ttl>")
    assert outcome.valid is False and outcome.status == "invalid"
    assert "shacl-contracts" in outcome.detail


def test_unauthorized_is_fail_closed_denied():
    client = _fake_client(response=_Response(401, text="unauthorized"))
    validator = HttpContentValidator("http://validate", client=client)
    outcome = validator.validate_ontology("<ttl>")
    assert outcome.valid is False and outcome.status == "denied"


def test_transport_error_is_fail_closed_degraded():
    validator = HttpContentValidator("http://validate", client=_fake_client())

    def raising_post(url, json=None, headers=None):
        raise validator._httpx.HTTPError("boom")

    validator._client.post = raising_post
    outcome = validator.validate_ontology("<ttl>")
    assert outcome.valid is False and outcome.status == "degraded"


def test_summary_truncates_long_failure_lists():
    checks = [{"gate": f"g{i}", "passed": False, "message": "m"} for i in range(8)]
    client = _fake_client(response=_Response(200, {"valid": False, "checks": checks}))
    validator = HttpContentValidator("http://validate", client=client)
    outcome = validator.validate_ontology("<ttl>")
    assert "+3 more" in outcome.detail


def test_manifest_payload_carries_content_format():
    client = _fake_client(response=_Response(200, {"valid": True, "checks": []}))
    validator = HttpContentValidator("http://validate", client=client)
    outcome = validator.validate_ontology(
        '{"pack": "x"}', artifact_kind="ooc_manifest", content_format="json"
    )
    assert outcome.valid is True
    assert client.calls[0]["json"]["content_format"] == "json"
