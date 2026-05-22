"""Matchbox CLI entry point.

The CLI is intentionally thin: most user interaction happens in the web UI,
and the brain (Claude Code) invokes the deterministic CLIs `jobreqs` and
`assemble` directly. This module exists so `matchbox --help` works.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="matchbox",
    help="Local desktop app for tailored CV/cover-letter assembly.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def version() -> None:
    """Print the installed Matchbox version."""
    from matchbox import __version__

    typer.echo(__version__)


@app.command()
def web(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the local web UI."""
    from matchbox.web.app import run

    run(host=host, port=port)


if __name__ == "__main__":
    app()
