"""Command output history for scroll-back persistence."""

from typing import NamedTuple
from datetime import datetime


class CommandEntry(NamedTuple):
    """A single command output entry."""
    command: str
    output: str
    timestamp: str


class CommandHistory:
    """Stores command outputs for scroll-back viewing."""

    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self._entries: list[CommandEntry] = []

    def add(self, command: str, output: str) -> None:
        """Add a command output to history."""
        entry = CommandEntry(
            command=command,
            output=output,
            timestamp=datetime.now().strftime("%H:%M:%S")
        )
        self._entries.append(entry)
        # Trim old entries
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

    def get_entries(self) -> list[CommandEntry]:
        """Get all command entries."""
        return self._entries

    def clear(self) -> None:
        """Clear all history."""
        self._entries.clear()
