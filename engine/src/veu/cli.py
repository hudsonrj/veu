from __future__ import annotations

import uvicorn
import typer
from rich.console import Console

from veu.runtime import Runtime

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


@app.command()
def pulse() -> None:
    """Mostra se o kernel está vivo."""
    console.print(Runtime().pulse())


@app.command()
def weave(
    intent: str = typer.Argument(..., help="Intenção em linguagem natural"),
    breath: str = typer.Option("guided", "--breath", "-b", help="guided|semi|free"),
) -> None:
    """Tece uma formação a partir da intenção."""
    console.print(Runtime().weave(intent, breath=breath))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8821, "--port"),
) -> None:
    """Sobe a API do kernel (chat SSE + weave)."""
    uvicorn.run("veu.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
