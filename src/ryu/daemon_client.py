"""Daemon do Ryu — executor de tasks na máquina do usuário (multica cmd_daemon).

Fluxo (paridade multica 'How It Works'):
1. Detecta os CLIs de agente instalados (adapters.detect_runtimes).
2. Registra um runtime por CLI em cada workspace observado
   (POST /api/daemon/register) e guarda o token rdt_ workspace-scoped.
3. Faz poll de claim (POST /api/daemon/tasks/claim) + heartbeat periódico
   (POST /api/daemon/heartbeat); heartbeat-ack entrega pending_update /
   pending_model_list, que o daemon executa e reporta.
4. Task reivindicada roda num workspace local isolado
   (~/.ryu/workspaces/<task_id>), com transcript em lote
   (POST /tasks/{id}/messages), lease renovado (POST /tasks/{id}/progress),
   cancelamento observado (GET /tasks/{id}/status → cancel-ack) e
   complete/fail no final.
5. No shutdown, deregistra os runtimes.
6. Wakeup via WS (/api/daemon/ws → daemon:task_available) quando a lib
   `websockets` está instalada; sem ela, só poll (mesma capacidade, + latência).

Config: ~/.ryu/config.json (server_url, token, workspace default) + env:
  RYU_DAEMON_POLL_INTERVAL (s, default 3)
  RYU_DAEMON_HEARTBEAT_INTERVAL (s, default 15)
  RYU_DAEMON_MAX_CONCURRENT_TASKS (default 4)
  RYU_DAEMON_ID / RYU_DAEMON_DEVICE_NAME (default: hostname)
  RYU_DAEMON_WORKSPACES_ROOT (default ~/.ryu/workspaces)
  RYU_<AGENT>_PATH/_MODEL/_ARGS (overrides por CLI — ver adapters.py)
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ryu import cliconf, providers
from ryu.runner.adapters import (
    build_command,
    detect_runtimes,
    resolution_failure,
    resolve_binary,
    runtime_env,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[{_now_iso()}] {msg}", flush=True)


async def _run_capture(cmd: list[str], *, timeout: float) -> tuple[int, str, str]:
    """Roda um binário sem bloquear o event loop; devolve (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return (
        proc.returncode or 0,
        (stdout or b"").decode(errors="replace"),
        (stderr or b"").decode(errors="replace"),
    )


class Daemon:
    def __init__(self, profile: str | None = None) -> None:
        self.profile = profile
        self.server_url = cliconf.resolve_server_url(profile)
        self.user_token = cliconf.resolve_token(profile)
        self.daemon_id = os.environ.get("RYU_DAEMON_ID", "").strip() or socket.gethostname()
        self.device_name = os.environ.get("RYU_DAEMON_DEVICE_NAME", "").strip() or socket.gethostname()
        self.poll_interval = float(os.environ.get("RYU_DAEMON_POLL_INTERVAL", "3") or 3)
        self.heartbeat_interval = float(os.environ.get("RYU_DAEMON_HEARTBEAT_INTERVAL", "15") or 15)
        self.max_concurrent = int(os.environ.get("RYU_DAEMON_MAX_CONCURRENT_TASKS", "4") or 4)
        self.task_timeout_minutes = float(os.environ.get("RYU_DAEMON_TASK_TIMEOUT_MINUTES", "30") or 30)
        self.workspaces_root = cliconf.workspaces_root(profile)
        self.detected = [r for r in detect_runtimes(with_version=True) if r["available"]]
        # workspace_id -> {"token": rdt_, "runtimes": [{id, provider}]}
        self.registered: dict[str, dict] = {}
        self.running_tasks: dict[str, asyncio.Task] = {}
        self._stop = asyncio.Event()
        self._wakeup = asyncio.Event()

    # ── HTTP helpers ──────────────────────────────────────────────────
    def _client(self, token: str | None = None) -> httpx.AsyncClient:
        tok = token or self.user_token
        return httpx.AsyncClient(
            base_url=self.server_url,
            headers={"Authorization": f"Bearer {tok}"} if tok else {},
            timeout=30,
        )

    def _ws_token(self, workspace_id: str) -> str:
        return self.registered.get(workspace_id, {}).get("token") or self.user_token

    # ── Registro ──────────────────────────────────────────────────────
    async def register_all(self) -> None:
        if not self.detected:
            _log(f"nenhum CLI de agente detectado — instale {'/'.join(providers.NAMES)} e reinicie")
        async with self._client() as c:
            r = await c.get("/api/daemon/workspaces")
            r.raise_for_status()
            workspaces = r.json()
        default_ws = cliconf.resolve_workspace_id(None, self.profile)
        if default_ws:
            workspaces = [w for w in workspaces if w["id"] == default_ws or w["slug"] == default_ws] or workspaces
        for ws in workspaces:
            payload = {
                "workspace_id": ws["id"],
                "daemon_id": self.daemon_id,
                "device_name": self.device_name,
                "device_info": f"{sys.platform} python{sys.version_info.major}.{sys.version_info.minor}",
                "runtimes": [
                    {"provider": d["provider"], "version": d.get("version", ""), "name": f"{d['provider']} @ {self.device_name}"}
                    for d in self.detected
                ],
            }
            async with self._client() as c:
                r = await c.post("/api/daemon/register", json=payload)
            if r.status_code != 200:
                _log(f"register falhou p/ workspace {ws['slug']}: HTTP {r.status_code} {r.text[:200]}")
                continue
            data = r.json()
            self.registered[ws["id"]] = {
                "slug": ws["slug"],
                "token": data.get("daemon_token") or self.user_token,
                "runtimes": data.get("runtimes", []),
            }
            _log(f"registrado no workspace {ws['slug']}: {[rt['provider'] for rt in data.get('runtimes', [])]}")
            # recupera órfãs de execução anterior deste daemon
            token = self.registered[ws["id"]]["token"]
            async with self._client(token) as c:
                for rt in data.get("runtimes", []):
                    with contextlib.suppress(Exception):
                        rr = await c.post(f"/api/daemon/runtimes/{rt['id']}/recover-orphans")
                        rec = rr.json().get("recovered", []) if rr.status_code == 200 else []
                        if rec:
                            _log(f"recover-orphans {rt['provider']}: {rec}")

    async def deregister_all(self) -> None:
        for ws_id, info in self.registered.items():
            with contextlib.suppress(Exception):
                async with self._client(info["token"]) as c:
                    await c.post(
                        "/api/daemon/deregister",
                        json={"workspace_id": ws_id, "daemon_id": self.daemon_id},
                    )
        _log("runtimes deregistrados")

    # ── Heartbeat + pendências ────────────────────────────────────────
    async def heartbeat_once(self) -> None:
        for ws_id, info in list(self.registered.items()):
            async with self._client(info["token"]) as c:
                for rt in list(info["runtimes"]):
                    try:
                        r = await c.post("/api/daemon/heartbeat", json={"runtime_id": rt["id"]})
                    except httpx.HTTPError as e:
                        _log(f"heartbeat erro: {e}")
                        continue
                    if r.status_code != 200:
                        continue
                    ack = r.json()
                    if ack.get("runtime_gone"):
                        _log(f"runtime {rt['provider']} removido no servidor — re-registrando")
                        await self.register_all()
                        return
                    if ack.get("pending_update"):
                        await self.run_update(ws_id, rt, ack["pending_update"])
                    if ack.get("pending_model_list"):
                        await self.report_models(ws_id, rt, ack["pending_model_list"])
                    if (ack.get("queued_tasks") or 0) > 0:
                        self._wakeup.set()

    async def run_update(self, ws_id: str, rt: dict, pending: dict) -> None:
        provider = rt["provider"]
        spec = providers.get(provider)
        args = spec.update if spec else None
        binary = resolve_binary(provider)
        status, message, version = "failed", "", ""
        if binary and args is not None:
            try:
                rc, out, err = await _run_capture([binary, *args], timeout=300)
                status = "completed" if rc == 0 else "failed"
                message = (out or err or "")[-1000:]
                _, ver_out, _ = await _run_capture([binary, "--version"], timeout=10)
                version = ver_out.strip().splitlines()[0][:80] if ver_out.strip() else ""
            except Exception as e:  # noqa: BLE001
                message = str(e)
        else:
            install = spec.install.get(sys.platform) if spec else None
            message = f"update automático não suportado para {provider}" + (
                f" — reinstale: {install}" if install else " (atualize manualmente)"
            )
        info = self.registered[ws_id]
        async with self._client(info["token"]) as c:
            with contextlib.suppress(Exception):
                await c.post(
                    f"/api/daemon/runtimes/{rt['id']}/update/{pending['id']}/result",
                    json={"status": status, "message": message, "version": version},
                )
        _log(f"update {provider}: {status} {message[:120]}")

    async def report_models(self, ws_id: str, rt: dict, pending: dict) -> None:
        provider = rt["provider"]
        # sem catálogo embutido: o modelo vem do próprio agente via ACP (ADR-0002)
        spec = providers.get(provider)
        override = os.environ.get(f"RYU_{spec.env_key}_MODELS", "") if spec else ""
        models = [m.strip() for m in override.split(",") if m.strip()] if override else []
        info = self.registered[ws_id]
        async with self._client(info["token"]) as c:
            with contextlib.suppress(Exception):
                await c.post(
                    f"/api/daemon/runtimes/{rt['id']}/models/{pending['id']}/result",
                    json={"models": models,
                          "error": "" if models else f"catálogo de modelos do {provider} ainda não vem do CLI"},
                )

    # ── Claim + execução ──────────────────────────────────────────────
    async def claim_once(self) -> int:
        slots = self.max_concurrent - len(self.running_tasks)
        if slots <= 0:
            return 0
        total = 0
        for ws_id, info in list(self.registered.items()):
            if slots <= 0:
                break
            runtime_ids = [rt["id"] for rt in info["runtimes"]]
            if not runtime_ids:
                continue
            async with self._client(info["token"]) as c:
                try:
                    r = await c.post(
                        "/api/daemon/tasks/claim",
                        json={"runtime_ids": runtime_ids, "max_tasks": slots},
                    )
                except httpx.HTTPError:
                    continue
            if r.status_code != 200:
                continue
            for task in r.json().get("tasks", []):
                slots -= 1
                total += 1
                at = asyncio.get_event_loop().create_task(self.execute_task(ws_id, task))
                self.running_tasks[task["id"]] = at
                at.add_done_callback(lambda _t, tid=task["id"]: self.running_tasks.pop(tid, None))
        return total

    async def execute_task(self, ws_id: str, task: dict) -> None:
        token = self._ws_token(ws_id)
        task_id = task["id"]
        agent = task.get("agent") or {}
        provider = agent.get("runtime") or "claude"
        _log(f"task {task_id[:8]} claimed (agent={agent.get('handle')}, provider={provider})")
        async with self._client(token) as c:
            r = await c.post(f"/api/daemon/tasks/{task_id}/start")
            if r.status_code != 200 or not r.json().get("ok"):
                _log(f"task {task_id[:8]}: start rejeitado ({r.text[:120]})")
                return
            workdir = self.workspaces_root / task_id
            workdir.mkdir(parents=True, exist_ok=True)
            prompt = task.get("prompt") or ""
            (workdir / "PROMPT.md").write_text(prompt, encoding="utf-8")
            instructions = (agent.get("instructions") or "").strip() or None
            if instructions:
                (workdir / "AGENT.md").write_text(instructions, encoding="utf-8")
            argv = build_command(
                provider,
                prompt,
                agent.get("runtime_config") or {},
                model=agent.get("model"),
                instructions=instructions,
                resume_session_id=task.get("session_id"),
                structured=False,
            )
            if argv is None:
                reason, message = resolution_failure(provider)
                await c.post(
                    f"/api/daemon/tasks/{task_id}/fail",
                    json={"error": message, "failure_reason": reason},
                )
                return
            env = {
                **os.environ,
                **runtime_env(provider, thinking_level=agent.get("thinking_level"),
                              service_tier=agent.get("service_tier")),
                **((agent.get("runtime_config") or {}).get("env") or {}),
                "RYU_TASK_ID": task_id,
            }
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv, cwd=str(workdir), env=env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                )
            except OSError as e:
                await c.post(f"/api/daemon/tasks/{task_id}/fail",
                             json={"error": str(e), "failure_reason": "crash"})
                return

            lines: list[str] = []
            batch: list[dict] = []
            cancelled = False

            async def _flush() -> None:
                nonlocal batch
                if not batch:
                    return
                payload, batch = batch, []
                with contextlib.suppress(Exception):
                    await c.post(f"/api/daemon/tasks/{task_id}/messages", json={"messages": payload})

            async def _watchdog() -> None:
                nonlocal cancelled
                while proc.returncode is None:
                    await asyncio.sleep(10)
                    with contextlib.suppress(Exception):
                        pr = await c.post(f"/api/daemon/tasks/{task_id}/progress", json={})
                        if pr.status_code == 200:
                            data = pr.json()
                            if data.get("cancel_requested") or data.get("status") in ("cancelled",):
                                cancelled = True
                                with contextlib.suppress(ProcessLookupError):
                                    proc.terminate()
                                await asyncio.sleep(5)
                                if proc.returncode is None:
                                    with contextlib.suppress(ProcessLookupError):
                                        proc.kill()
                                return

            wd = asyncio.get_event_loop().create_task(_watchdog())
            timed_out = False
            try:
                assert proc.stdout is not None
                async for raw in proc.stdout:
                    line = raw.decode(errors="replace").rstrip()
                    if not line:
                        continue
                    lines.append(line)
                    batch.append({"role": "stdout", "type": "stdout", "content": line[:4000]})
                    if len(batch) >= 20:
                        await _flush()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=self.task_timeout_minutes * 60)
                except asyncio.TimeoutError:
                    timed_out = True
                    with contextlib.suppress(ProcessLookupError):
                        proc.terminate()
                    await asyncio.sleep(5)
                    if proc.returncode is None:
                        with contextlib.suppress(ProcessLookupError):
                            proc.kill()
            finally:
                wd.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await wd
                await _flush()

            if cancelled:
                with contextlib.suppress(Exception):
                    await c.post(f"/api/daemon/tasks/{task_id}/cancel-ack")
                _log(f"task {task_id[:8]}: cancelada (ack)")
                return
            summary = "\n".join(lines[-50:]) or "(sem saída)"
            if proc.returncode == 0 and not timed_out:
                await c.post(f"/api/daemon/tasks/{task_id}/complete",
                             json={"result_summary": summary[:16000]})
                _log(f"task {task_id[:8]}: completed")
            else:
                reason = "timeout" if timed_out else "crash"
                error_msg = (
                    f"timeout de {int(self.task_timeout_minutes)}min excedido"
                    if timed_out
                    else f"runtime saiu com código {proc.returncode}: {summary[-500:]}"
                )
                await c.post(
                    f"/api/daemon/tasks/{task_id}/fail",
                    json={"error": error_msg, "failure_reason": reason},
                )
                _log(f"task {task_id[:8]}: failed ({reason})")

    # ── WS wakeup (opcional — precisa da lib `websockets`) ────────────
    async def ws_listener(self) -> None:
        try:
            import websockets  # type: ignore
        except ImportError:
            _log("lib `websockets` ausente — usando só poll HTTP")
            return
        # mesma origem do server, só trocando o esquema HTTP pelo WebSocket
        parts = urllib.parse.urlsplit(self.server_url)
        ws_scheme = "wss" if parts.scheme == "https" else "ws"
        url = urllib.parse.urlunsplit(parts._replace(scheme=ws_scheme))
        token = self.user_token
        while not self._stop.is_set():
            try:
                async with websockets.connect(f"{url}/api/daemon/ws?token={token}") as ws:
                    _log("WS conectado (wakeup em tempo real)")
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        if msg.get("type") == "daemon:task_available":
                            payload = msg.get("payload") or {}
                            provider = payload.get("provider")
                            # só acorda se o daemon tem um runtime com aquele provider
                            if provider is None or any(
                                rt["provider"] == provider
                                for info in self.registered.values()
                                for rt in info["runtimes"]
                            ):
                                self._wakeup.set()
            except Exception:
                await asyncio.sleep(5)

    # ── Loop principal ────────────────────────────────────────────────
    async def run(self) -> None:
        _log(f"ryu daemon start — server={self.server_url} daemon_id={self.daemon_id}")
        _log(f"CLIs detectados: {[d['provider'] for d in self.detected] or 'nenhum'}")
        if not self.user_token:
            _log("ERRO: sem token — rode `ryu login` (ou defina RYU_TOKEN)")
            return
        await self.register_all()
        if not self.registered:
            _log("ERRO: nenhum workspace registrado")
            return
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._stop.set)
        ws_task = loop.create_task(self.ws_listener())
        last_hb = 0.0
        import time as _time

        while not self._stop.is_set():
            mono = _time.monotonic()
            if mono - last_hb >= self.heartbeat_interval:
                with contextlib.suppress(Exception):
                    await self.heartbeat_once()
                last_hb = mono
            with contextlib.suppress(Exception):
                await self.claim_once()
            self._wakeup.clear()
            wait_stop = loop.create_task(self._stop.wait())
            wait_wake = loop.create_task(self._wakeup.wait())
            done, pending = await asyncio.wait(
                {wait_stop, wait_wake}, timeout=self.poll_interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for p in pending:
                p.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await p
        ws_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ws_task
        if self.running_tasks:
            _log(f"aguardando {len(self.running_tasks)} task(s) ativa(s)…")
            await asyncio.wait(list(self.running_tasks.values()), timeout=30)
        await self.deregister_all()
        _log("ryu daemon stopped")


# ── Self-update do CLI (ryu update — multica cmd_update.go) ───────────
def detect_install_method() -> tuple[str, list[str]]:
    """Auto-detecta como o ryu foi instalado e devolve (método, comando)."""
    exe = sys.executable or ""
    pkg_dir = Path(__file__).resolve().parent
    repo_root = pkg_dir.parent.parent  # src/ryu -> src -> raiz
    if (repo_root / ".git").exists() and (repo_root / "pyproject.toml").exists():
        return "git", ["git", "-C", str(repo_root), "pull", "--ff-only"]
    if "pipx" in exe:
        return "pipx", ["pipx", "upgrade", "ryu"]
    if os.environ.get("UV_TOOL_DIR") or "/uv/tools/" in exe:
        return "uv", ["uv", "tool", "upgrade", "ryu"]
    return "pip", [exe or "python3", "-m", "pip", "install", "--upgrade", "ryu"]


def self_update() -> tuple[str, int, str]:
    method, cmd = detect_install_method()
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        output = (out.stdout or "") + (out.stderr or "")
        rc = out.returncode
        if method == "git" and rc == 0:
            pip = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", str(Path(__file__).resolve().parent.parent.parent)],
                capture_output=True, text=True, timeout=600,
            )
            output += "\n" + (pip.stdout or "") + (pip.stderr or "")
            rc = pip.returncode
        return method, rc, output[-2000:]
    except Exception as e:  # noqa: BLE001
        return method, 1, str(e)


def run_daemon(profile: str | None = None) -> None:
    asyncio.run(Daemon(profile).run())


if __name__ == "__main__":
    run_daemon(os.environ.get("RYU_PROFILE") or None)
