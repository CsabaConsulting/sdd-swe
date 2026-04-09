"""Credential vault — isolates API keys from LLM context."""

import os
from typing import Optional


class CredentialVault:
    """Reads credentials from environment variables.

    NEVER exposes credentials to LLM context. Only wallet client
    functions have access to these credentials.
    """

    def __init__(self):
        self._upmoltwork_api_key: Optional[str] = None
        self._openrouter_api_key: Optional[str] = None

    def load_upmoltwork_key(self) -> str:
        """Get UpMoltWork API key from environment."""
        if self._upmoltwork_api_key is None:
            self._upmoltwork_api_key = os.getenv("UPMOLTWORK_API_KEY")
            if not self._upmoltwork_api_key:
                raise ValueError("UPMOLTWORK_API_KEY not set in environment")
        return self._upmoltwork_api_key

    def load_openrouter_key(self) -> str:
        """Get OpenRouter API key from environment."""
        if self._openrouter_api_key is None:
            self._openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
            if not self._openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY not set in environment")
        return self._openrouter_api_key

    @property
    def upmoltwork_api_key(self) -> str:
        """Property access — same as load_upmoltwork_key()."""
        return self.load_upmoltwork_key()

    @property
    def openrouter_api_key(self) -> str:
        """Property access — same as load_openrouter_key()."""
        return self.load_openrouter_key()


# Global singleton — credentials loaded once, reused across calls
vault = CredentialVault()
