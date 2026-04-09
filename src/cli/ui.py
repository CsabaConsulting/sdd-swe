"""Terminal UI using Textual framework — 4-region layout."""

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Static, DataTable, Input
from textual.reactive import reactive
from src.db.store import AegisStore
from src.cli.commands import execute_command
from src.cli.history import CommandHistory


class MainView(Static):
    """Main view — scrollable task list."""

    def __init__(self):
        super().__init__()
        self.tasks = []

    def update_tasks(self, tasks: list):
        """Update displayed tasks."""
        self.tasks = tasks
        self.refresh()

    def render(self) -> str:
        if not self.tasks:
            return "[cyan]Waiting for tasks... [dim](last refresh: now)"

        output = "[bold]Active Tasks:[/bold]\n\n"
        for task in self.tasks[:10]:
            status_icon = {
                "DISCOVERED": "[blue]?[/blue]",
                "BIDDING": "[yellow]?[/yellow]",
                "DELIVERY": "[cyan]?[/cyan]",
                "VALIDATION": "[magenta]?[/magenta]",
                "SUBMITTED": "[green]?[/green]",
            }.get(task.get("status", ""), "?")

            output += f"{status_icon} [{task.get('status', '')}] {task.get('title', 'Unknown')[:60]}\n"
            output += f"  Points: {task.get('points', 'N/A')} | Deadline: {task.get('deadline', 'N/A')}\n"

        return output


class SideColumn(Static):
    """Side column — errors and info messages."""

    def __init__(self):
        super().__init__()
        self.messages = []

    def add_message(self, msg: str):
        """Add a message to the side column."""
        self.messages.append(msg)
        self.refresh()

    def render(self) -> str:
        if not self.messages:
            return "[dim]No messages[/dim]"

        output = "[bold]Messages:[/bold]\n\n"
        for msg in self.messages[-10:]:  # Show last 10
            if "Guardrail" in msg or "error" in msg.lower():
                output += f"[red]{msg}[/red]\n"
            elif "Skill" in msg:
                output += f"[yellow]{msg}[/yellow]\n"
            else:
                output += f"{msg}\n"

        return output


class StatusBar(Static):
    """Bottom status line — summary counts."""

    def __init__(self):
        super().__init__()
        self.error_count = 0
        self.guardrail_fires = 0
        self.skills_loaded = 0

    def update_counts(self, errors: int, guardrails: int, skills: int):
        """Update status bar counts."""
        self.error_count = errors
        self.guardrail_fires = guardrails
        self.skills_loaded = skills
        self.refresh()

    def render(self) -> str:
        return f"Errors: {self.error_count} unviewed | Guardrail fires: {self.guardrail_fires} | Skills loaded: {self.skills_loaded}"


class PromptArea(Static):
    """Command prompt area — slash commands and output."""

    BINDINGS = [
        ("escape", "clear_output", "Clear output"),
    ]

    def __init__(self, store: AegisStore):
        super().__init__()
        self.store = store
        self.input = Input(placeholder="Type /help for commands...")
        self.output = Static("")
        self.history = CommandHistory()
        self.showing_help = False

    def compose(self) -> ComposeResult:
        yield self.input
        yield self.output

    def on_mount(self) -> None:
        self.input.focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input."""
        command = event.value.strip()
        if not command:
            return

        # Execute command
        result = await execute_command(command, self.store)
        self.history.add(command, result)

        # Display output
        self.output.update(f"[cyan]{command}[/cyan]\n{result}")
        self.input.value = ""

    def action_clear_output(self) -> None:
        """Clear command output."""
        self.output.update("")


class AegisApp(App):
    """Main Aegis terminal application."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main_view {
        height: 50%;
        border: solid green;
        overflow-y: auto;
    }

    #side_column {
        height: 30%;
        border: solid yellow;
        overflow-y: auto;
    }

    #status_bar {
        height: 1;
        border: solid blue;
        dock: bottom;
    }

    #prompt_area {
        height: 19%;
        border: solid cyan;
        dock: bottom;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, store: AegisStore):
        super().__init__()
        self.store = store

    def compose(self) -> ComposeResult:
        yield Header()
        yield MainView(id="main_view")
        yield SideColumn(id="side_column")
        yield StatusBar(id="status_bar")
        yield PromptArea(self.store, id="prompt_area")
        yield Footer()

    def on_mount(self) -> None:
        """Add placeholder data on mount."""
        main = self.query_one("#main_view", MainView)
        main.update_tasks([
            {"status": "DISCOVERED", "title": "Write a Python CLI tool", "points": 150, "deadline": "2026-04-10"},
            {"status": "DELIVERY", "title": "Create React dashboard", "points": 300, "deadline": "2026-04-12"},
        ])

        side = self.query_one("#side_column", SideColumn)
        side.add_message("System started")
        side.add_message("Guardrail service initialized")


async def main():
    """Run the Aegis terminal UI."""
    store = AegisStore()
    await store.init_db()

    app = AegisApp(store)
    await app.run_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
