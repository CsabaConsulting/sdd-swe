"""Unit tests for the configuration loader.

Covers:
- AegisConfig model construction with defaults
- load_config() with environment variables
- Missing required var raises ConfigurationError
- Optional vars fall back to defaults
- validate_config() flow with mocked external services
- IMAP test (mocked)
- Podman check (mocked)
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.loader import (
    AegisConfig,
    ConfigurationError,
    load_config,
    validate_config,
    _test_imap,
)


# ---------------------------------------------------------------------------
# AegisConfig model
# ---------------------------------------------------------------------------


class TestAegisConfigModel:
    """AegisConfig pydantic model validation."""

    def test_valid_config(self):
        """All required fields accepted."""
        config = AegisConfig(
            upmoltwork_api_key="test-key",
            openrouter_api_key="test-key",
            imap_host="imap.test.com",
            imap_user="user@test.com",
            imap_pass="password",
        )

        assert config.upmoltwork_api_key == "test-key"

    def test_optional_defaults(self):
        """Optional fields have sensible defaults."""
        config = AegisConfig(
            upmoltwork_api_key="k",
            openrouter_api_key="k",
            imap_host="h",
            imap_user="u",
            imap_pass="p",
        )

        assert config.validation_confidence_threshold == 0.8
        assert config.max_validation_iterations == 3
        assert config.guardrail_model_path is None
        assert config.specializations == []
        assert config.email_poll_interval_seconds == 60

    def test_custom_optional_values(self):
        """Optional fields can be customized."""
        config = AegisConfig(
            upmoltwork_api_key="k",
            openrouter_api_key="k",
            imap_host="h",
            imap_user="u",
            imap_pass="p",
            validation_confidence_threshold=0.5,
            max_validation_iterations=5,
            specializations=["python", "web"],
            email_poll_interval_seconds=30,
        )

        assert config.validation_confidence_threshold == 0.5
        assert config.max_validation_iterations == 5
        assert config.specializations == ["python", "web"]
        assert config.email_poll_interval_seconds == 30

    def test_missing_required_field_raises(self):
        """Pydantic raises when a required field is missing."""
        with pytest.raises(Exception):  # pydantic.ValidationError
            AegisConfig(
                upmoltwork_api_key="k",
                # missing openrouter_api_key
                imap_host="h",
                imap_user="u",
                imap_pass="p",
            )


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """load_config reads env vars and constructs AegisConfig."""

    def _set_required_env(self, monkeypatch, extra=None):
        """Set required environment variables."""
        env = {
            "UPMOLTWORK_API_KEY": "test-upmoltwork-key",
            "OPENROUTER_API_KEY": "test-openrouter-key",
            "IMAP_HOST": "imap.example.com",
            "IMAP_USER": "user@example.com",
            "IMAP_PASS": "secret",
        }
        if extra:
            env.update(extra)
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    def test_load_config_with_all_vars(self, monkeypatch):
        """All required vars set -> config loads successfully."""
        self._set_required_env(monkeypatch)

        import asyncio
        config = asyncio.run(load_config())

        assert config.upmoltwork_api_key == "test-upmoltwork-key"
        assert config.imap_host == "imap.example.com"

    def test_load_config_missing_var_raises(self, monkeypatch):
        """Missing any required var raises ConfigurationError."""
        # Set only some, omit OPENROUTER_API_KEY
        monkeypatch.setenv("UPMOLTWORK_API_KEY", "key")
        monkeypatch.setenv("IMAP_HOST", "h")
        monkeypatch.setenv("IMAP_USER", "u")
        monkeypatch.setenv("IMAP_PASS", "p")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        import asyncio
        with pytest.raises(ConfigurationError, match="Missing required"):
            asyncio.run(load_config())

    def test_load_config_multiple_missing_vars(self, monkeypatch):
        """Error message lists all missing variables."""
        # Set none of the required vars
        for var in ["UPMOLTWORK_API_KEY", "OPENROUTER_API_KEY",
                     "IMAP_HOST", "IMAP_USER", "IMAP_PASS"]:
            monkeypatch.delenv(var, raising=False)

        import asyncio
        with pytest.raises(ConfigurationError) as exc_info:
            asyncio.run(load_config())

        error_msg = str(exc_info.value)
        assert "UPMOLTWORK_API_KEY" in error_msg
        assert "OPENROUTER_API_KEY" in error_msg

    def test_load_config_optional_defaults(self, monkeypatch):
        """Optional vars not set -> defaults are used."""
        self._set_required_env(monkeypatch)

        import asyncio
        config = asyncio.run(load_config())

        assert config.max_validation_iterations == 3
        assert config.validation_confidence_threshold == 0.8

    def test_load_config_custom_optional(self, monkeypatch):
        """Optional vars can be overridden via environment."""
        self._set_required_env(monkeypatch, extra={
            "VALIDATION_CONFIDENCE_THRESHOLD": "0.6",
            "MAX_VALIDATION_ITERATIONS": "5",
            "EMAIL_POLL_INTERVAL_SECONDS": "30",
            "SPECIALIZATIONS": "python, backend",
        })

        import asyncio
        config = asyncio.run(load_config())

        assert config.validation_confidence_threshold == 0.6
        assert config.max_validation_iterations == 5
        assert config.email_poll_interval_seconds == 30
        assert config.specializations == ["python", "backend"]

    def test_load_config_invalid_int_raises(self, monkeypatch):
        """Non-integer optional var raises ConfigurationError."""
        self._set_required_env(monkeypatch, extra={
            "MAX_VALIDATION_ITERATIONS": "not-a-number",
        })

        import asyncio
        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            asyncio.run(load_config())


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    """validate_config tests external connectivity with mocks."""

    @pytest.mark.asyncio
    async def test_all_checks_pass(self, mock_config):
        """When all external services respond, validate_config succeeds."""
        with patch("src.wallet.client.get_balance", AsyncMock()), \
             patch("openai.AsyncOpenAI"), \
             patch("imaplib.IMAP4_SSL"), \
             patch("src.execution.sandbox.check_podman_available", return_value=True):
            await validate_config(mock_config)
        # Should not raise

    @pytest.mark.asyncio
    async def test_upmoltwork_failure_raises(self, mock_config):
        """UpMoltWork API failure raises ConfigurationError."""
        with patch(
            "src.wallet.client.get_balance",
            AsyncMock(side_effect=RuntimeError("API unreachable")),
        ), \
             patch("openai.AsyncOpenAI"), \
             patch("imaplib.IMAP4_SSL"), \
             patch("src.execution.sandbox.check_podman_available", return_value=True):
            with pytest.raises(ConfigurationError, match="UPMOLTWORK_API_KEY"):
                await validate_config(mock_config)

    @pytest.mark.asyncio
    async def test_imap_failure_raises(self, mock_config):
        """IMAP failure raises ConfigurationError."""
        with patch("src.wallet.client.get_balance", AsyncMock()), \
             patch("openai.AsyncOpenAI"), \
             patch(
                 "imaplib.IMAP4_SSL",
                 side_effect=RuntimeError("auth failed"),
             ), \
             patch("src.execution.sandbox.check_podman_available", return_value=True):
            with pytest.raises(ConfigurationError, match="IMAP credentials"):
                await validate_config(mock_config)

    @pytest.mark.asyncio
    async def test_podman_warning_printed_when_unavailable(self, mock_config, capsys):
        """Podman unavailable prints a warning but does not fail."""
        with patch("src.wallet.client.get_balance", AsyncMock()), \
             patch("openai.AsyncOpenAI"), \
             patch("imaplib.IMAP4_SSL"), \
             patch(
                 "src.execution.sandbox.check_podman_available",
                 return_value=False,
             ):
            await validate_config(mock_config)

        captured = capsys.readouterr()
        assert "Podman not available" in captured.out

    @pytest.mark.asyncio
    async def test_podman_check_exception_warned(self, mock_config, capsys):
        """Podman check exception prints a warning but does not fail."""
        with patch("src.wallet.client.get_balance", AsyncMock()), \
             patch("openai.AsyncOpenAI"), \
             patch("imaplib.IMAP4_SSL"), \
             patch(
                 "src.execution.sandbox.check_podman_available",
                 side_effect=RuntimeError("some error"),
             ):
            await validate_config(mock_config)

        captured = capsys.readouterr()
        assert "Podman check failed" in captured.out


# ---------------------------------------------------------------------------
# _test_imap
# ---------------------------------------------------------------------------


class TestTestImap:
    """_test_imap sync IMAP connectivity test."""

    def test_successful_imap_login(self):
        """IMAP login and logout succeed on mocked client."""
        mock_imap = MagicMock()

        with patch("imaplib.IMAP4_SSL") as mock_ssl:
            mock_ssl.return_value = mock_imap
            from src.config.loader import AegisConfig
            config = AegisConfig(
                upmoltwork_api_key="test",
                openrouter_api_key="test",
                imap_host="imap.test.com",
                imap_user="user",
                imap_pass="pass",
            )
            _test_imap(config)

        mock_imap.login.assert_called_once_with("user", "pass")
        mock_imap.logout.assert_called_once()

    def test_imap_login_failure_raises(self):
        """IMAP login failure propagates as an exception."""
        mock_imap = MagicMock()
        mock_imap.login.side_effect=Exception("authentication failed")

        with patch("imaplib.IMAP4_SSL") as mock_ssl:
            mock_ssl.return_value = mock_imap
            from src.config.loader import AegisConfig
            config = AegisConfig(
                upmoltwork_api_key="test",
                openrouter_api_key="test",
                imap_host="bad",
                imap_user="wrong",
                imap_pass="wrong",
            )
            with pytest.raises(Exception, match="authentication failed"):
                _test_imap(config)
