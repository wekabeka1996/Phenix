"""Tests for deep redaction — Phase 17.3."""
from vfoundation.security.redaction import redact_deep


class TestRedactDeep:
    """Phase 17.3: Recursive redaction tests."""

    def test_nested_dict_redaction(self):
        """Sensitive keys in nested dicts are redacted."""
        data = {
            "name": "aurora",
            "credentials": {
                "api_key": "secret123",
                "endpoint": "https://api.example.com",
            },
        }
        result = redact_deep(data)
        assert result["name"] == "aurora"
        assert result["credentials"]["api_key"] == "***"
        assert result["credentials"]["endpoint"] == "https://api.example.com"

    def test_list_of_dicts_redaction(self):
        """Sensitive keys in lists of dicts are redacted."""
        data = [
            {"name": "adapter1", "token": "abc"},
            {"name": "adapter2", "password": "xyz"},
        ]
        result = redact_deep(data)
        assert result[0]["name"] == "adapter1"
        assert result[0]["token"] == "***"
        assert result[1]["password"] == "***"
