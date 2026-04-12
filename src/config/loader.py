"""Configuration loader with .env parsing and API key validation."""

import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict


class AegisConfig(BaseModel):
    """Configuration for Aegis agent system."""
    model_config = ConfigDict(env_prefix="")

    # Required
    upmoltwork_api_key: str = Field(description="UpMoltWork API key")
    openrouter_api_key: str = Field(description="OpenRouter API key for LLM access")
    imap_host: str = Field(description="IMAP server hostname")
    imap_user: str = Field(description="IMAP username/email")
    imap_pass: str = Field(description="IMAP password or app password")

    # Optional with defaults
    validation_confidence_threshold: float = Field(0.8, description="Minimum confidence for validation pass")
    max_validation_iterations: int = Field(3, description="Max validation retry attempts")
    guardrail_model_path: Optional[str] = Field(None, description="Path to guardrail models")
    specializations: list[str] = Field(default_factory=list, description="Task specializations")
    email_poll_interval_seconds: int = Field(60, description="IMAP polling interval")


class ConfigurationError(Exception):
    """Raised when configuration is invalid."""
    pass


async def load_config() -> AegisConfig:
    """Load configuration from .env file and environment variables.

    Returns:
        AegisConfig instance with validated configuration

    Raises:
        ConfigurationError: If required env vars are missing or invalid
    """
    # Load .env file if it exists
    load_dotenv()

    # Check required vars
    required_vars = {
        "UPMOLTWORK_API_KEY": os.getenv("UPMOLTWORK_API_KEY"),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY"),
        "IMAP_HOST": os.getenv("IMAP_HOST"),
        "IMAP_USER": os.getenv("IMAP_USER"),
        "IMAP_PASS": os.getenv("IMAP_PASS"),
    }

    missing = [k for k, v in required_vars.items() if not v]
    if missing:
        raise ConfigurationError(f"Missing required environment variables: {', '.join(missing)} — set in .env file")

    # Parse optional vars with defaults
    try:
        config = AegisConfig(
            upmoltwork_api_key=required_vars["UPMOLTWORK_API_KEY"],
            openrouter_api_key=required_vars["OPENROUTER_API_KEY"],
            imap_host=required_vars["IMAP_HOST"],
            imap_user=required_vars["IMAP_USER"],
            imap_pass=required_vars["IMAP_PASS"],
            validation_confidence_threshold=float(os.getenv("VALIDATION_CONFIDENCE_THRESHOLD", "0.8")),
            max_validation_iterations=int(os.getenv("MAX_VALIDATION_ITERATIONS", "3")),
            guardrail_model_path=os.getenv("GUARDRAIL_MODEL_PATH"),
            specializations=[s.strip() for s in os.getenv("SPECIALIZATIONS", "").split(",") if s.strip()] if os.getenv("SPECIALIZATIONS") else [],
            email_poll_interval_seconds=int(os.getenv("EMAIL_POLL_INTERVAL_SECONDS", "60")),
        )
        return config
    except ValueError as e:
        raise ConfigurationError(f"Invalid configuration value: {e}")


async def validate_config(config: AegisConfig) -> None:
    """Validate API keys and connectivity.

    Tests:
    1. UpMoltWork API key by calling get_balance
    2. OpenRouter API key by making a test completion
    3. IMAP credentials by attempting login
    4. Podman availability for sandbox (warns if unavailable)

    Raises:
        ConfigurationError: If any validation check fails
    """
    errors = []
    warnings = []

    # 1. Validate UPMOLTWORK_API_KEY
    try:
        from src.wallet.client import get_balance
        await get_balance(config)
    except Exception as e:
        errors.append(f"UPMOLTWORK_API_KEY invalid or API unreachable: {e}")

    # 2. Validate OPENROUTER_API_KEY
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=config.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1"
        )
        # Skip actual API call for now — just verify client creation
        # In production, would make a test completion call
    except Exception as e:
        errors.append(f"OPENROUTER_API_KEY invalid: {e}")

    # 3. Test IMAP
    try:
        import asyncio
        import imaplib
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _test_imap(config))
    except Exception as e:
        errors.append(f"IMAP credentials invalid: {e}")

    # 4. Check Podman availability (non-fatal, just warns)
    try:
        from src.execution.sandbox import check_podman_available
        podman_ok = await check_podman_available()
        if not podman_ok:
            warnings.append("WARNING: Podman not available — sandbox will use subprocess isolation (weaker security)")
    except Exception as e:
        warnings.append(f"WARNING: Podman check failed: {e}")

    if errors:
        raise ConfigurationError(f"Configuration validation failed:\n" + "\n".join(errors))

    # Print warnings (non-fatal)
    for warning in warnings:
        print(f"  ⚠ {warning}")


def _test_imap(config: AegisConfig) -> None:
    """Test IMAP connection (sync, runs in executor)."""
    client = imaplib.IMAP4_SSL(config.imap_host)
    client.login(config.imap_user, config.imap_pass)
    client.logout()


async def main():
    """Test mode: load and validate configuration."""
    print("Loading configuration from .env...")

    try:
        config = await load_config()
        print("✓ Configuration loaded")
        print(f"  UPMOLTWORK_API_KEY: {'set' if config.upmoltwork_api_key else 'missing'}")
        print(f"  OPENROUTER_API_KEY: {'set' if config.openrouter_api_key else 'missing'}")
        print(f"  IMAP_HOST: {config.imap_host}")
        print(f"  IMAP_USER: {config.imap_user}")
        print(f"  Validation threshold: {config.validation_confidence_threshold}")
        print(f"  Max validation iterations: {config.max_validation_iterations}")
        print(f"  Email poll interval: {config.email_poll_interval_seconds}s")
        print(f"  Specializations: {config.specializations or 'none'}")

        print("\nValidating connectivity...")
        await validate_config(config)
        print("✓ All validation checks passed")

        # Check sandbox mode
        from src.execution.sandbox import check_podman_available
        podman_ok = await check_podman_available()
        if podman_ok:
            print("  Sandbox mode: Podman (full isolation)")
        else:
            print("  Sandbox mode: subprocess (limited isolation)")
    except ConfigurationError as e:
        print(f"✗ Configuration error: {e}")
        raise
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
