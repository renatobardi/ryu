"""CLI do Ryu (Typer + httpx contra a API local).

Auth: token PAT `ryu_...` via env RYU_TOKEN (Authorization: Bearer).
Base URL via env RYU_URL (default http://localhost:8000).

Comandos: serve · issues list · issues create · tasks list
"""
from __future__ import annotations

import os

import httpx
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Ryu — issue tracker com agentes de IA.")
issues_app = typer.Typer(help="Gerencia issues.")
tasks_app = typer.Typer(help="Fila de tasks dos agentes.")
app.add_typer(issues_app, name="issues")
app.add_typer(tasks_app, name="tasks")

console = Console()


def _client() -> httpx.Client:
    base = os.environ.get("RYU_URL", "http://localhost:8000")
    token = os.environ.get("RYU_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=base, headers=headers, timeout=30)


def _die(resp: httpx.Response) -> None:
    console.print(f"[red]HTTP {resp.status_code}[/red] {resp.text[:500]}")
    raise typer.Exit(1)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(None, help="Porta (default: settings.port)"),
    reload: bool = typer.Option(False, help="Auto-reload (dev)"),
):
    """Sobe o servidor Ryu (uvicorn)."""
    import uvicorn

    from ryu.config import settings

    uvicorn.run("ryu.main:app", host=host, port=port or settings.port, reload=reload)


@issues_app.command("list")
def issues_list(
    workspace_id: str = typer.Option(..., "--workspace-id", "-w"),
    status: str = typer.Option(None, "--status", "-s"),
    q: str = typer.Option(None, "--query", "-q"),
):
    """Lista issues do workspace."""
    params = {"workspace_id": workspace_id}
    if status:
        params["status"] = status
    if q:
        params["q"] = q
    with _client() as c:
        r = c.get("/api/issues", params=params)
    if r.status_code != 200:
        _die(r)
    table = Table(title="Issues")
    for col in ("key", "title", "status", "priority", "assignee"):
        table.add_column(col)
    for i in r.json():
        assignee = f"{i.get('assignee_type') or ''}:{i.get('assignee_id') or ''}".strip(":")
        table.add_row(i["key"], i["title"][:60], i["status"], i.get("priority", ""), assignee)
    console.print(table)


@issues_app.command("create")
def issues_create(
    workspace_id: str = typer.Option(..., "--workspace-id", "-w"),
    title: str = typer.Option(..., "--title", "-t"),
    description: str = typer.Option("", "--description", "-d"),
    status: str = typer.Option("backlog", "--status", "-s"),
    priority: str = typer.Option("none", "--priority", "-p"),
    agent_id: str = typer.Option(None, "--agent-id", help="Atribui a um agente (enfileira task se todo/in_progress)"),
):
    """Cria uma issue."""
    payload = {
        "workspace_id": workspace_id,
        "title": title,
        "description": description,
        "status": status,
        "priority": priority,
    }
    if agent_id:
        payload["assignee_type"] = "agent"
        payload["assignee_id"] = agent_id
    with _client() as c:
        r = c.post("/api/issues", json=payload)
    if r.status_code != 201:
        _die(r)
    i = r.json()
    console.print(f"[green]Criada[/green] {i['key']} — {i['title']} ({i['status']})")


@tasks_app.command("list")
def tasks_list(
    workspace_id: str = typer.Option(..., "--workspace-id", "-w"),
    status: str = typer.Option(None, "--status", "-s"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """Lista tasks da fila de agentes."""
    params = {"workspace_id": workspace_id, "limit": limit}
    if status:
        params["status"] = status
    with _client() as c:
        r = c.get("/api/tasks", params=params)
    if r.status_code != 200:
        _die(r)
    table = Table(title="Agent Tasks")
    for col in ("id", "kind", "status", "agent_id", "issue_id", "created_at"):
        table.add_column(col)
    for t in r.json():
        table.add_row(
            t["id"][:8], t["kind"], t["status"], (t.get("agent_id") or "")[:8],
            (t.get("issue_id") or "")[:8], (t.get("created_at") or "")[:19],
        )
    console.print(table)


if __name__ == "__main__":
    app()
