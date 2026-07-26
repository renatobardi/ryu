"""Hub de eventos realtime — in-memory, nó único (mesma taxonomia do multica)."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket

# Taxonomia de eventos (atualizar ao publicar um evento novo):
# - issue:created|updated|deleted|reaction, comment:created|updated|reaction
# - task:queued|running|progress|completed|failed|cancelled, agent:status
# - chat:message|done|cancel_finalized|session_read|session_updated|session_deleted
# - inbox:new|unarchived, autopilot:run_done, squad:evaluated
# - workspace:updated|deleted, member:added|updated|removed, invitation:created|accepted|
#   declined|revoked, project:created|updated|deleted
# - runtime:registered|models_done|update_done, github_pr:updated, vcs_pr:updated


class Hub:
    def __init__(self) -> None:
        self._conns: dict[str, set[WebSocket]] = defaultdict(set)  # workspace_id -> conns
        self._lock = asyncio.Lock()

    async def connect(self, workspace_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._conns[workspace_id].add(ws)

    async def disconnect(self, workspace_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._conns[workspace_id].discard(ws)

    async def publish(self, workspace_id: str, event: str, data: dict) -> None:
        msg = json.dumps({"event": event, "data": data}, default=str)
        dead = []
        for ws in list(self._conns.get(workspace_id, ())):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(workspace_id, ws)


hub = Hub()
