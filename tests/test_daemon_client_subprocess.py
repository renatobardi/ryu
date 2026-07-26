"""O daemon roda binários externos sem bloquear o event loop."""
from __future__ import annotations

import asyncio

import pytest


async def test_run_capture_returns_streams_separately():
    from ryu.daemon_client import _run_capture

    rc, out, err = await _run_capture(["python3", "-c", "print('oi')"], timeout=30)
    assert rc == 0
    assert out.strip() == "oi"
    assert err == ""


async def test_run_capture_does_not_block_event_loop():
    from ryu.daemon_client import _run_capture

    ticks = 0

    async def _ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    tick_task = asyncio.create_task(_ticker())
    await _run_capture(["python3", "-c", "import time; time.sleep(0.3)"], timeout=30)
    tick_task.cancel()
    assert ticks > 5, "event loop ficou bloqueado durante o subprocess"


async def test_run_capture_times_out():
    from ryu.daemon_client import _run_capture

    with pytest.raises(asyncio.TimeoutError):
        await _run_capture(["python3", "-c", "import time; time.sleep(5)"], timeout=0.2)
