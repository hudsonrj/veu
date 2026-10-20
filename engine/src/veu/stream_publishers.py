"""Publica mission/pulse/sideboard no bus periodicamente (SSE /stream)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from veu.bus import bus

log = logging.getLogger("veu.stream_publishers")

_task: asyncio.Task[None] | None = None


async def _loop(
    *,
    pulse_fn: Callable[[], dict[str, Any]],
    mission_fn: Callable[[], dict[str, Any]],
    sideboard_fn: Callable[[], Any],
    interval: float = 8.0,
) -> None:
    while True:
        try:
            try:
                pulse = pulse_fn()
                bus.publish(
                    "pulse",
                    {"ok": bool(pulse.get("ok", True)), "kernel": True},
                    full=None,
                )
            except Exception as e:  # noqa: BLE001
                log.debug("pulse publish: %s", e)

            try:
                mission = mission_fn()
                bus.publish(
                    "mission",
                    {
                        "job_counts": mission.get("job_counts"),
                        "projects": len(mission.get("projects") or []),
                    },
                    full=None,
                )
            except Exception as e:  # noqa: BLE001
                log.debug("mission publish: %s", e)

            try:
                side = sideboard_fn()
                if side is not None:
                    bus.publish(
                        "sideboard",
                        {"refreshed": True},
                        full=None,
                    )
            except Exception as e:  # noqa: BLE001
                log.debug("sideboard publish: %s", e)

            try:
                from veu import briefing as veu_briefing

                veu_briefing.tick_schedule()
            except Exception as e:  # noqa: BLE001
                log.debug("briefing tick: %s", e)

        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.debug("publish loop: %s", e)

        await asyncio.sleep(interval)


def start(
    *,
    pulse_fn: Callable[[], dict[str, Any]],
    mission_fn: Callable[[], dict[str, Any]],
    sideboard_fn: Callable[[], Any],
) -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(
        _loop(pulse_fn=pulse_fn, mission_fn=mission_fn, sideboard_fn=sideboard_fn),
        name="veu-stream-publishers",
    )


def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
