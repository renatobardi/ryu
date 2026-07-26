"""CLI do Ryu (Typer + httpx contra a API) — daemon-cli ciclo 1.

Auth: `ryu login` (browser + callback local, ou --token) persiste em
~/.ryu/config.json; env RYU_TOKEN / RYU_URL continuam tendo precedência.
Workspace default: flag --workspace-id > env RYU_WORKSPACE_ID > config
(`ryu workspace switch`).

Comandos (paridade multica CLI_AND_DAEMON.md):
  serve · login · auth status/logout · config show/set · setup
  workspace list/switch/get/member list
  issues list/create/get/update/status/assign/reorder/runs/run-messages/usage
  issues subscriber add/remove/list · issues metadata list/get/set/delete
  issues comment list/add/delete
  tasks list · daemon start/stop/status/logs · update
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from ryu import cliconf

app = typer.Typer(help="Ryu — issue tracker com agentes de IA.")
issues_app = typer.Typer(help="Gerencia issues.")
tasks_app = typer.Typer(help="Fila de tasks dos agentes.")
auth_app = typer.Typer(help="Autenticação do CLI.")
config_app = typer.Typer(help="Config local (~/.ryu).")
workspace_app = typer.Typer(help="Workspaces.")
member_app = typer.Typer(help="Membros do workspace.")
daemon_app = typer.Typer(help="Daemon local de execução de agentes.")
subscriber_app = typer.Typer(help="Subscribers de uma issue.")
metadata_app = typer.Typer(help="Metadata KV de uma issue.")
comment_app = typer.Typer(help="Comentários de uma issue.")

app.add_typer(issues_app, name="issues")
app.add_typer(issues_app, name="issue", hidden=True)  # alias multica
app.add_typer(tasks_app, name="tasks")
app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")
app.add_typer(workspace_app, name="workspace")
app.add_typer(daemon_app, name="daemon")
workspace_app.add_typer(member_app, name="member")
issues_app.add_typer(subscriber_app, name="subscriber")
issues_app.add_typer(metadata_app, name="metadata")
issues_app.add_typer(comment_app, name="comment")

console = Console()
err_console = Console(stderr=True)

ISSUE_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-\d+$")


def _client(token: str | None = None) -> httpx.Client:
    base = cliconf.resolve_server_url()
    tok = token if token is not None else cliconf.resolve_token()
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}
    return httpx.Client(base_url=base, headers=headers, timeout=30)


def _die(resp: httpx.Response) -> None:
    console.print(f"[red]HTTP {resp.status_code}[/red] {resp.text[:500]}")
    raise typer.Exit(1)


def _require_ws(workspace_id: str | None) -> str:
    ws = cliconf.resolve_workspace_id(workspace_id)
    if not ws:
        console.print(
            "[red]workspace não definido[/red] — use --workspace-id, RYU_WORKSPACE_ID "
            "ou `ryu workspace switch <id|slug>`"
        )
        raise typer.Exit(1)
    return ws


def _resolve_issue(c: httpx.Client, ws_id: str, ref: str) -> dict:
    """Aceita UUID ou key RYU-123 (resolução via /api/issues/by-key)."""
    if ISSUE_KEY_RE.match(ref):
        r = c.get(f"/api/issues/by-key/{ref.upper()}", params={"workspace_id": ws_id})
    else:
        r = c.get(f"/api/issues/{ref}")
    if r.status_code != 200:
        _die(r)
    return r.json()


def _autotype(value: str, forced: str | None = None) -> Any:
    """Auto-tipagem multica: true/false → bool, número → number, senão string."""
    if forced == "string":
        return value
    if forced == "bool":
        return value.lower() in ("true", "1", "yes")
    if forced == "number":
        try:
            return int(value)
        except ValueError:
            return float(value)
    try:
        parsed = json.loads(value)
        if isinstance(parsed, (bool, int, float)):
            return parsed
    except ValueError:
        pass
    return value


def _resolve_assignee(c: httpx.Client, ws_id: str, name: str) -> tuple[str, str]:
    """Nome → (assignee_type, id): procura agentes (name/handle) e membros."""
    r = c.get("/api/agents", params={"workspace_id": ws_id})
    if r.status_code == 200:
        for a in r.json():
            if name.lower() in (a.get("name", "").lower(), a.get("handle", "").lower().lstrip("@")):
                return "agent", a["id"]
    r = c.get(f"/api/workspaces/{ws_id}/members")
    if r.status_code == 200:
        for m in r.json():
            if name.lower() in (m.get("name", "").lower(), m.get("email", "").lower()):
                return "member", m["user_id"]
    console.print(f"[red]assignee não encontrado:[/red] {name}")
    raise typer.Exit(1)


# ── serve ─────────────────────────────────────────────────────────────
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


# ── login / auth ──────────────────────────────────────────────────────
def _verify_and_save(token: str) -> dict:
    with _client(token) as c:
        r = c.get("/api/auth/me")
    if r.status_code != 200:
        console.print(f"[red]token inválido[/red] (HTTP {r.status_code})")
        raise typer.Exit(1)
    me = r.json()
    cfg = cliconf.load_config()
    cfg["token"] = token
    if not cfg.get("workspace_id") and me.get("workspaces"):
        cfg["workspace_id"] = me["workspaces"][0]["id"]
    cliconf.save_config(cfg)
    return me


@app.command()
def login(
    token: str = typer.Option(None, "--token", help="Autentica com um token existente (ryu_...)"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Só imprime a URL de login"),
):
    """Autentica o CLI: abre o browser e recebe o token via callback local."""
    if token:
        me = _verify_and_save(token)
        console.print(f"[green]Autenticado[/green] como {me['email']}")
        return

    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    received: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            qs = parse_qs(urlparse(self.path).query)
            tok = (qs.get("token") or [""])[0]
            if tok:
                received["token"] = tok
                body = b"<html><body><h3>Ryu CLI autenticado. Pode fechar esta aba.</h3></body></html>"
            else:
                body = b"<html><body><h3>Token ausente.</h3></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silencia
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    app_url = cliconf.resolve_app_url()
    url = f"{app_url}/cli-login?redirect_uri=http://127.0.0.1:{port}/callback"
    console.print(f"Abrindo o browser para autenticar: [cyan]{url}[/cyan]")
    if not no_browser:
        webbrowser.open(url)
    console.print("Aguardando o callback (3 min)… faça login no browser se necessário.")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline and "token" not in received:
        time.sleep(0.3)
    server.shutdown()
    if "token" not in received:
        console.print("[red]timeout[/red] — use `ryu login --token <ryu_...>`")
        raise typer.Exit(1)
    me = _verify_and_save(received["token"])
    console.print(f"[green]Autenticado[/green] como {me['email']}")


@auth_app.command("status")
def auth_status():
    """Mostra o estado de autenticação atual."""
    token = cliconf.resolve_token()
    server = cliconf.resolve_server_url()
    if not token:
        console.print(f"server: {server}\n[yellow]não autenticado[/yellow] — rode `ryu login`")
        raise typer.Exit(1)
    with _client() as c:
        r = c.get("/api/auth/me")
    if r.status_code != 200:
        console.print(f"server: {server}\n[red]token inválido/expirado[/red]")
        raise typer.Exit(1)
    me = r.json()
    ws_default = cliconf.resolve_workspace_id(None)
    console.print(f"server: {server}")
    console.print(f"user:   {me['email']} ({me['id']})")
    console.print(f"workspace default: {ws_default or '—'}")


@auth_app.command("logout")
def auth_logout():
    """Remove o token salvo no config local."""
    cfg = cliconf.load_config()
    cfg.pop("token", None)
    cliconf.save_config(cfg)
    console.print("[green]Logout feito[/green] (token removido de ~/.ryu)")


# ── config ────────────────────────────────────────────────────────────
@config_app.command("show")
def config_show():
    """Mostra o config local (token mascarado)."""
    cfg = cliconf.load_config()
    out = dict(cfg)
    if out.get("token"):
        out["token"] = out["token"][:8] + "…"
    out.setdefault("server_url", cliconf.resolve_server_url())
    console.print_json(json.dumps(out))
    console.print(f"[dim]{cliconf.config_path()}[/dim]")


@config_app.command("set")
def config_set(key: str, value: str):
    """Define uma chave do config: server_url | app_url | workspace_id | token."""
    try:
        cliconf.set_value(key, value)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]{key}[/green] = {value if key != 'token' else value[:8] + '…'}")


# ── setup ─────────────────────────────────────────────────────────────
@app.command()
def setup(
    server_url: str = typer.Option(None, "--server-url", help="URL do servidor Ryu"),
    app_url: str = typer.Option(None, "--app-url", help="URL do app (default: server_url)"),
    skip_daemon: bool = typer.Option(False, "--skip-daemon", help="Não inicia o daemon"),
):
    """Setup em um comando: config → login → daemon start (multica setup)."""
    if server_url:
        cliconf.set_value("server_url", server_url.rstrip("/"))
    if app_url:
        cliconf.set_value("app_url", app_url.rstrip("/"))
    console.print(f"server_url = {cliconf.resolve_server_url()}")
    if not cliconf.resolve_token():
        login(token=None, no_browser=False)
    else:
        console.print("[green]token já configurado[/green]")
    if not skip_daemon:
        daemon_start(foreground=False)


# ── workspace ─────────────────────────────────────────────────────────
def _me_workspaces(c: httpx.Client) -> list[dict]:
    r = c.get("/api/auth/me")
    if r.status_code != 200:
        _die(r)
    return r.json().get("workspaces", [])


@workspace_app.command("list")
def workspace_list(full_id: bool = typer.Option(False, "--full-id")):
    """Lista os workspaces acessíveis (marca o default)."""
    default = cliconf.resolve_workspace_id(None)
    with _client() as c:
        wss = _me_workspaces(c)
    table = Table(title="Workspaces")
    for col in ("", "id", "slug", "name", "role"):
        table.add_column(col)
    for w in wss:
        mark = "*" if w["id"] == default or w["slug"] == default else ""
        table.add_row(mark, w["id"] if full_id else w["id"][:8], w["slug"], w["name"], w.get("role", ""))
    console.print(table)


@workspace_app.command("switch")
def workspace_switch(ref: str = typer.Argument(..., help="id ou slug do workspace")):
    """Troca o workspace default do config (com checagem de acesso)."""
    with _client() as c:
        wss = _me_workspaces(c)
    match = next((w for w in wss if w["id"] == ref or w["slug"] == ref), None)
    if match is None:
        console.print(f"[red]sem acesso ao workspace[/red] {ref}")
        raise typer.Exit(1)
    cliconf.set_value("workspace_id", match["id"])
    console.print(f"[green]workspace default:[/green] {match['slug']} ({match['id'][:8]}…)")


@workspace_app.command("get")
def workspace_get(
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    output: str = typer.Option("table", "--output"),
):
    """Detalhes do workspace atual (ou do informado)."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        r = c.get(f"/api/workspaces/{ws}")
    if r.status_code != 200:
        _die(r)
    data = r.json()
    if output == "json":
        console.print_json(json.dumps(data))
    else:
        for k, v in data.items():
            console.print(f"{k}: {v}")


@member_app.command("list")
def member_list(
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    output: str = typer.Option("table", "--output"),
):
    """Lista membros do workspace."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        r = c.get(f"/api/workspaces/{ws}/members")
    if r.status_code != 200:
        _die(r)
    members = r.json()
    if output == "json":
        console.print_json(json.dumps(members))
        return
    table = Table(title="Members")
    for col in ("user_id", "name", "email", "role"):
        table.add_column(col)
    for m in members:
        table.add_row(m["user_id"][:8], m.get("name", ""), m["email"], m.get("role", ""))
    console.print(table)


# ── issues ────────────────────────────────────────────────────────────
@issues_app.command("list")
def issues_list(
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    status: str = typer.Option(None, "--status", "-s"),
    priority: str = typer.Option(None, "--priority"),
    q: str = typer.Option(None, "--query", "-q"),
    assignee_id: str = typer.Option(None, "--assignee-id"),
    metadata: list[str] = typer.Option([], "--metadata", help="k=v (repetível, AND; valor JSON-parseado)"),
    limit: int = typer.Option(None, "--limit", "-n"),
    sort: str = typer.Option(None, "--sort", help="position|title|created_at|due_date|priority"),
    direction: str = typer.Option(None, "--direction", help="asc|desc"),
    full_id: bool = typer.Option(False, "--full-id"),
    output: str = typer.Option("table", "--output"),
):
    """Lista issues do workspace (filtros multica: --metadata, --sort, --limit)."""
    ws = _require_ws(workspace_id)
    params: dict = {"workspace_id": ws}
    if status:
        params["status"] = status
    if priority:
        params["priorities"] = [priority]
    if q:
        params["q"] = q
    if assignee_id:
        params["assignee_id"] = assignee_id
    if metadata:
        meta_obj: dict = {}
        for kv in metadata:
            if "=" not in kv:
                console.print(f"[red]--metadata inválido:[/red] {kv} (use k=v)")
                raise typer.Exit(1)
            k, v = kv.split("=", 1)
            meta_obj[k] = _autotype(v)
        params["metadata"] = json.dumps(meta_obj)
    if limit:
        params["limit"] = limit
    if sort:
        params["sort"] = sort
    if direction:
        params["direction"] = direction
    with _client() as c:
        r = c.get("/api/issues", params=params)
    if r.status_code != 200:
        _die(r)
    data = r.json()
    items = data["items"] if isinstance(data, dict) else data
    if output == "json":
        console.print_json(json.dumps(items))
        return
    table = Table(title="Issues")
    for col in ("key", "id" if full_id else "", "title", "status", "priority", "assignee"):
        if col:
            table.add_column(col)
    for i in items:
        assignee = f"{i.get('assignee_type') or ''}:{i.get('assignee_id') or ''}".strip(":")
        row = [i["key"]]
        if full_id:
            row.append(i["id"])
        row += [i["title"][:60], i["status"], i.get("priority", ""), assignee[:24]]
        table.add_row(*row)
    console.print(table)


@issues_app.command("create")
def issues_create(
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    title: str = typer.Option(..., "--title", "-t"),
    description: str = typer.Option("", "--description", "-d"),
    status: str = typer.Option("backlog", "--status", "-s"),
    priority: str = typer.Option("none", "--priority", "-p"),
    agent_id: str = typer.Option(None, "--agent-id", help="Atribui a um agente"),
    assignee: str = typer.Option(None, "--assignee", help="Nome do agente/membro"),
    parent: str = typer.Option(None, "--parent", help="Issue pai (id ou key)"),
    project: str = typer.Option(None, "--project", help="Project id"),
    due_date: str = typer.Option(None, "--due-date", help="ISO 8601"),
):
    """Cria uma issue."""
    ws = _require_ws(workspace_id)
    payload: dict = {
        "workspace_id": ws,
        "title": title,
        "description": description,
        "status": status,
        "priority": priority,
    }
    with _client() as c:
        if agent_id:
            payload["assignee_type"], payload["assignee_id"] = "agent", agent_id
        elif assignee:
            at, aid = _resolve_assignee(c, ws, assignee)
            payload["assignee_type"], payload["assignee_id"] = at, aid
        if parent:
            payload["parent_issue_id"] = _resolve_issue(c, ws, parent)["id"]
        if project:
            payload["project_id"] = project
        r = c.post("/api/issues", json=payload)
        if r.status_code != 201:
            _die(r)
        i = r.json()
        if due_date:
            c.patch(f"/api/issues/{i['id']}", json={"due_date": due_date})
    console.print(f"[green]Criada[/green] {i['key']} — {i['title']} ({i['status']})")


@issues_app.command("get")
def issue_get(
    ref: str = typer.Argument(..., help="id ou key (RYU-123)"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    output: str = typer.Option("table", "--output"),
):
    """Mostra uma issue (aceita key RYU-123)."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
    if output == "json":
        console.print_json(json.dumps(issue))
        return
    for k in ("key", "id", "title", "status", "priority", "assignee_type", "assignee_id",
              "parent_issue_id", "project_id", "due_date", "created_at"):
        console.print(f"{k}: {issue.get(k)}")
    if issue.get("description"):
        console.print(f"\n{issue['description']}")
    if issue.get("meta"):
        console.print(f"\nmetadata: {json.dumps(issue['meta'])}")


@issues_app.command("update")
def issue_update(
    ref: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    title: str = typer.Option(None, "--title"),
    description: str = typer.Option(None, "--description"),
    priority: str = typer.Option(None, "--priority"),
    parent: str = typer.Option(None, "--parent", help="id/key da issue pai ('' remove)"),
    project: str = typer.Option(None, "--project", help="project id ('' remove)"),
    due_date: str = typer.Option(None, "--due-date"),
    position: float = typer.Option(None, "--position"),
):
    """Atualiza title/priority/parent/project/due-date/position."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        changes: dict = {}
        if title is not None:
            changes["title"] = title
        if description is not None:
            changes["description"] = description
        if priority is not None:
            changes["priority"] = priority
        if parent is not None:
            changes["parent_issue_id"] = _resolve_issue(c, ws, parent)["id"] if parent else None
        if project is not None:
            changes["project_id"] = project or None
        if due_date is not None:
            changes["due_date"] = due_date or None
        if position is not None:
            changes["position"] = position
        if not changes:
            console.print("[yellow]nada para atualizar[/yellow]")
            raise typer.Exit(0)
        r = c.patch(f"/api/issues/{issue['id']}", json=changes)
    if r.status_code != 200:
        _die(r)
    console.print(f"[green]Atualizada[/green] {r.json()['key']}")


@issues_app.command("status")
def issue_status(
    ref: str = typer.Argument(...),
    status: str = typer.Argument(..., help="backlog|todo|in_progress|in_review|done|blocked|cancelled"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Muda o status de uma issue."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        r = c.patch(f"/api/issues/{issue['id']}", json={"status": status})
    if r.status_code != 200:
        _die(r)
    console.print(f"[green]{r.json()['key']}[/green] → {status}")


@issues_app.command("assign")
def issue_assign(
    ref: str = typer.Argument(...),
    to: str = typer.Option(None, "--to", help="Nome do agente/membro"),
    to_id: str = typer.Option(None, "--to-id", help="UUID do agente/membro"),
    unassign: bool = typer.Option(False, "--unassign"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Atribui (ou remove atribuição de) uma issue."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        if unassign:
            changes = {"assignee_type": None, "assignee_id": None}
        elif to_id:
            r = c.get(f"/api/agents/{to_id}")
            at = "agent" if r.status_code == 200 else "member"
            changes = {"assignee_type": at, "assignee_id": to_id}
        elif to:
            at, aid = _resolve_assignee(c, ws, to)
            changes = {"assignee_type": at, "assignee_id": aid}
        else:
            console.print("[red]use --to, --to-id ou --unassign[/red]")
            raise typer.Exit(1)
        r = c.patch(f"/api/issues/{issue['id']}", json=changes)
    if r.status_code != 200:
        _die(r)
    console.print(f"[green]{r.json()['key']}[/green] atribuída")


@issues_app.command("reorder")
def issue_reorder(
    ref: str = typer.Argument(...),
    top: bool = typer.Option(False, "--top"),
    bottom: bool = typer.Option(False, "--bottom"),
    before: str = typer.Option(None, "--before", help="acima desta issue (id/key)"),
    after: str = typer.Option(None, "--after", help="abaixo desta issue (id/key)"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Move a issue dentro da coluna atual (--top/--bottom/--before/--after)."""
    picked = sum([top, bottom, before is not None, after is not None])
    if picked != 1:
        console.print("[red]escolha exatamente um:[/red] --top | --bottom | --before | --after")
        raise typer.Exit(1)
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        payload: dict = {"status": issue["status"]}
        if before:
            payload["before_id"] = _resolve_issue(c, ws, before)["id"]
        elif after:
            payload["after_id"] = _resolve_issue(c, ws, after)["id"]
        else:
            r = c.get("/api/issues", params={"workspace_id": ws, "status": issue["status"], "sort": "position"})
            if r.status_code != 200:
                _die(r)
            data = r.json()
            column = data["items"] if isinstance(data, dict) else data
            column = [i for i in column if i["id"] != issue["id"]]
            if column:
                if top:
                    payload["before_id"] = column[0]["id"]
                else:
                    payload["after_id"] = column[-1]["id"]
        r = c.post(f"/api/issues/{issue['id']}/move", json=payload)
    if r.status_code != 200:
        _die(r)
    console.print(f"[green]{issue['key']}[/green] reordenada")


@issues_app.command("runs")
def issue_runs(
    ref: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    full_id: bool = typer.Option(False, "--full-id"),
    output: str = typer.Option("table", "--output"),
):
    """Histórico de execuções (AgentTasks) de uma issue."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        r = c.get(f"/api/tasks/issues/{issue['id']}/runs")
    if r.status_code != 200:
        _die(r)
    runs = r.json()
    if output == "json":
        console.print_json(json.dumps(runs))
        return
    table = Table(title=f"Runs — {issue['key']}")
    for col in ("task_id", "status", "attempt", "started_at", "finished_at", "failure"):
        table.add_column(col)
    for t in runs:
        table.add_row(
            t["id"] if full_id else t["id"][:8], t["status"], str(t.get("attempt") or 1),
            (t.get("started_at") or "")[:19], (t.get("finished_at") or "")[:19],
            t.get("failure_reason") or "",
        )
    console.print(table)


@issues_app.command("run-messages")
def issue_run_messages(
    task_ref: str = typer.Argument(..., help="task id (ou prefixo com --issue)"),
    issue: str = typer.Option(None, "--issue", help="escopo p/ prefixo curto de task"),
    since: int = typer.Option(None, "--since", help="só mensagens com seq > N"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    output: str = typer.Option("table", "--output"),
):
    """Mensagens (transcript) de uma execução."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        task_id = task_ref
        if issue:
            iss = _resolve_issue(c, ws, issue)
            r = c.get(f"/api/tasks/issues/{iss['id']}/runs")
            if r.status_code != 200:
                _die(r)
            matches = [t for t in r.json() if t["id"].startswith(task_ref)]
            if len(matches) != 1:
                console.print(f"[red]{len(matches)} tasks casam com o prefixo[/red] {task_ref}")
                raise typer.Exit(1)
            task_id = matches[0]["id"]
        params = {}
        if since is not None:
            params["after_seq"] = since
        r = c.get(f"/api/tasks/{task_id}/messages", params=params)
    if r.status_code != 200:
        _die(r)
    msgs = r.json()
    if output == "json":
        console.print_json(json.dumps(msgs))
        return
    for m in msgs:
        tool = f" [{m.get('tool')}]" if m.get("tool") else ""
        console.print(f"[dim]{m.get('seq'):>4}[/dim] [cyan]{m.get('type') or m.get('role')}[/cyan]{tool} {m.get('content', '')[:200]}")


@issues_app.command("usage")
def issue_usage(
    ref: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    output: str = typer.Option("table", "--output"),
):
    """Usage agregado de tokens da issue (soma dos task runs)."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        r = c.get(f"/api/issues/{issue['id']}/usage")
    if r.status_code != 200:
        _die(r)
    data = r.json()
    if output == "json":
        console.print_json(json.dumps(data))
        return
    for k, v in data.items():
        console.print(f"{k}: {v}")


# ── issue subscriber ──────────────────────────────────────────────────
@subscriber_app.command("list")
def subscriber_list(
    ref: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Lista subscribers de uma issue."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        r = c.get(f"/api/issues/{issue['id']}/subscribers")
    if r.status_code != 200:
        _die(r)
    for s in r.json():
        console.print(f"{s['user_type']}:{s['user_id']} ({s.get('reason')})")


@subscriber_app.command("add")
def subscriber_add(
    ref: str = typer.Argument(...),
    user: str = typer.Option(None, "--user", help="Nome do membro/agente (default: você)"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Inscreve você (ou --user) numa issue."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        payload = {}
        if user:
            at, aid = _resolve_assignee(c, ws, user)
            payload = {"user_type": at, "user_id": aid}
        r = c.post(f"/api/issues/{issue['id']}/subscribe", json=payload)
    if r.status_code not in (200, 201):
        _die(r)
    console.print("[green]inscrito[/green]")


@subscriber_app.command("remove")
def subscriber_remove(
    ref: str = typer.Argument(...),
    user: str = typer.Option(None, "--user"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Remove a inscrição (sua ou de --user)."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        payload = {}
        if user:
            at, aid = _resolve_assignee(c, ws, user)
            payload = {"user_type": at, "user_id": aid}
        r = c.post(f"/api/issues/{issue['id']}/unsubscribe", json=payload)
    if r.status_code not in (200, 204):
        _die(r)
    console.print("[green]removido[/green]")


# ── issue metadata ────────────────────────────────────────────────────
@metadata_app.command("list")
def metadata_list(
    ref: str = typer.Argument(...),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    output: str = typer.Option("table", "--output"),
):
    """Lista todas as chaves de metadata da issue."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        r = c.get(f"/api/issues/{issue['id']}/metadata")
    if r.status_code != 200:
        _die(r)
    meta = r.json().get("metadata", {})
    if output == "json":
        console.print_json(json.dumps(meta))
        return
    if not meta:
        console.print("[dim](vazio)[/dim]")
    for k, v in meta.items():
        console.print(f"{k} = {json.dumps(v)}")


@metadata_app.command("get")
def metadata_get(
    ref: str = typer.Argument(...),
    key: str = typer.Option(..., "--key"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Lê uma chave de metadata."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        r = c.get(f"/api/issues/{issue['id']}/metadata")
    if r.status_code != 200:
        _die(r)
    meta = r.json().get("metadata", {})
    if key not in meta:
        console.print(f"[red]chave não encontrada:[/red] {key}")
        raise typer.Exit(1)
    console.print(json.dumps(meta[key]))


@metadata_app.command("set")
def metadata_set(
    ref: str = typer.Argument(...),
    key: str = typer.Option(..., "--key"),
    value: str = typer.Option(..., "--value"),
    type_: str = typer.Option(None, "--type", help="string|number|bool (força o tipo)"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Grava uma chave (single-key atômico; valor auto-tipado)."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        r = c.put(f"/api/issues/{issue['id']}/metadata/{key}", json={"value": _autotype(value, type_)})
    if r.status_code != 200:
        _die(r)
    console.print(f"[green]{key}[/green] gravada")


@metadata_app.command("delete")
def metadata_delete(
    ref: str = typer.Argument(...),
    key: str = typer.Option(..., "--key"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Remove uma chave de metadata."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        r = c.delete(f"/api/issues/{issue['id']}/metadata/{key}")
    if r.status_code != 200:
        _die(r)
    console.print(f"[green]{key}[/green] removida")


# ── issue comment ─────────────────────────────────────────────────────
@comment_app.command("list")
def comment_list(
    ref: str = typer.Argument(...),
    thread: str = typer.Option(None, "--thread", help="raiz + réplicas de um thread"),
    tail: int = typer.Option(None, "--tail", help="só as N réplicas mais recentes"),
    recent: int = typer.Option(None, "--recent", help="N threads mais ativas"),
    before: str = typer.Option(None, "--before", help="cursor: timestamp"),
    before_id: str = typer.Option(None, "--before-id", help="cursor: id"),
    since: str = typer.Option(None, "--since", help="polling incremental (RFC3339)"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    output: str = typer.Option("table", "--output"),
):
    """Lista comentários (modos thread-aware com cursor — paridade multica)."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        params: dict = {}
        if thread:
            params["thread"] = thread
        if tail is not None:
            params["tail"] = tail
        if recent is not None:
            params["recent"] = recent
        if before:
            params["before"] = before
        if before_id:
            params["before_id"] = before_id
        if since:
            params["since"] = since
        r = c.get(f"/api/issues/{issue['id']}/comments", params=params)
    if r.status_code != 200:
        _die(r)
    comments = r.json()
    if output == "json":
        console.print_json(json.dumps(comments))
    else:
        for cm in comments:
            indent = "  " if cm.get("parent_comment_id") else ""
            console.print(
                f"{indent}[dim]{(cm.get('created_at') or '')[:19]}[/dim] "
                f"[cyan]{cm['author_type']}:{cm['author_id'][:8]}[/cyan] "
                f"[dim]({cm['id'][:8]})[/dim] {cm['body'][:200]}"
            )
    nb = r.headers.get("X-Ryu-Next-Before")
    nbi = r.headers.get("X-Ryu-Next-Before-Id")
    if nb:
        label = "Next thread cursor" if recent else "Next reply cursor"
        err_console.print(f"{label}: --before {nb} --before-id {nbi}")


@comment_app.command("add")
def comment_add(
    ref: str = typer.Argument(...),
    content: str = typer.Option(..., "--content", "-m"),
    parent: str = typer.Option(None, "--parent", help="responde a um comentário"),
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
):
    """Adiciona um comentário (ou resposta com --parent)."""
    ws = _require_ws(workspace_id)
    with _client() as c:
        issue = _resolve_issue(c, ws, ref)
        r = c.post(
            f"/api/issues/{issue['id']}/comments",
            json={"body": content, "parent_comment_id": parent},
        )
    if r.status_code != 201:
        _die(r)
    console.print(f"[green]comentário criado[/green] ({r.json()['id'][:8]})")


@comment_app.command("delete")
def comment_delete(comment_id: str = typer.Argument(...)):
    """Apaga um comentário."""
    with _client() as c:
        r = c.delete(f"/api/issues/comments/{comment_id}")
    if r.status_code != 204:
        _die(r)
    console.print("[green]comentário removido[/green]")


# ── tasks ─────────────────────────────────────────────────────────────
@tasks_app.command("list")
def tasks_list(
    workspace_id: str = typer.Option(None, "--workspace-id", "-w"),
    status: str = typer.Option(None, "--status", "-s"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """Lista tasks da fila de agentes."""
    ws = _require_ws(workspace_id)
    params = {"workspace_id": ws, "limit": limit}
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


# ── daemon ────────────────────────────────────────────────────────────
def _daemon_pid() -> int | None:
    path = cliconf.daemon_pid_path()
    if not path.exists():
        return None
    try:
        pid = int(path.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        return None


@daemon_app.command("start")
def daemon_start(foreground: bool = typer.Option(False, "--foreground", help="Roda em primeiro plano")):
    """Inicia o daemon local (executor de tasks na sua máquina)."""
    if not cliconf.resolve_token():
        console.print("[red]sem token[/red] — rode `ryu login` primeiro")
        raise typer.Exit(1)
    if foreground:
        from ryu.daemon_client import run_daemon

        run_daemon()
        return
    if _daemon_pid():
        console.print(f"[yellow]daemon já rodando[/yellow] (pid {_daemon_pid()})")
        raise typer.Exit(0)
    import subprocess

    log_path = cliconf.daemon_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as logf:
        proc = subprocess.Popen(
            [sys.executable, "-m", "ryu.daemon_client"],
            stdout=logf, stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ},
        )
    cliconf.daemon_pid_path().write_text(str(proc.pid))
    console.print(f"[green]daemon iniciado[/green] (pid {proc.pid}) — logs em {log_path}")


@daemon_app.command("stop")
def daemon_stop():
    """Para o daemon local."""
    pid = _daemon_pid()
    if pid is None:
        console.print("[yellow]daemon não está rodando[/yellow]")
        raise typer.Exit(0)
    import signal as _signal

    os.kill(pid, _signal.SIGTERM)
    for _ in range(50):
        if _daemon_pid() is None:
            break
        time.sleep(0.2)
    cliconf.daemon_pid_path().unlink(missing_ok=True)
    console.print("[green]daemon parado[/green]")


@daemon_app.command("status")
def daemon_status(output: str = typer.Option("table", "--output")):
    """Estado do daemon: pid, CLIs detectados, workspaces observados."""
    from ryu.runner.adapters import detect_runtimes

    pid = _daemon_pid()
    detected = [d for d in detect_runtimes() if d["available"]]
    info = {
        "running": pid is not None,
        "pid": pid,
        "server_url": cliconf.resolve_server_url(),
        "log": str(cliconf.daemon_log_path()),
        "detected_agents": [d["provider"] for d in detected],
        "workspace_default": cliconf.resolve_workspace_id(None),
    }
    if output == "json":
        console.print_json(json.dumps(info))
        return
    console.print(f"daemon: {'[green]rodando[/green] (pid ' + str(pid) + ')' if pid else '[red]parado[/red]'}")
    console.print(f"server: {info['server_url']}")
    console.print(f"agents detectados: {', '.join(info['detected_agents']) or 'nenhum'}")
    console.print(f"workspace default: {info['workspace_default'] or '—'}")
    console.print(f"log: {info['log']}")


@daemon_app.command("logs")
def daemon_logs(
    n: int = typer.Option(50, "-n", "--lines"),
    follow: bool = typer.Option(False, "-f", "--follow"),
):
    """Mostra o log do daemon (~/.ryu/daemon.log)."""
    path = cliconf.daemon_log_path()
    if not path.exists():
        console.print("[yellow]sem log ainda[/yellow]")
        raise typer.Exit(0)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[-n:]:
        console.print(line, markup=False)
    if follow:
        with open(path, encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            try:
                while True:
                    line = f.readline()
                    if line:
                        console.print(line.rstrip(), markup=False)
                    else:
                        time.sleep(0.5)
            except KeyboardInterrupt:
                pass


# ── update (self-update do CLI) ───────────────────────────────────────
@app.command()
def update():
    """Atualiza o Ryu CLI (auto-detecta método de instalação: git/pipx/uv/pip)."""
    from ryu.daemon_client import self_update

    method, rc, output = self_update()
    console.print(f"método: {method}")
    console.print(output, markup=False)
    if rc == 0:
        console.print("[green]atualizado[/green]")
    else:
        console.print("[red]falha na atualização[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
