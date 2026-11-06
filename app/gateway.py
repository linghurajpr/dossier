from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable


class ComintyGateway:
    def __init__(self) -> None:
        self.client = None
        self.context = None

    async def open(self) -> None:
        from cominty_sdk import AsyncCominty

        self.context = AsyncCominty()
        self.client = await self.context.__aenter__()

    async def close(self) -> None:
        if self.context is not None:
            await self.context.__aexit__(None, None, None)
            self.context = self.client = None

    async def call(
        self,
        agent_id: str,
        message: str,
        files: list[Path],
        previous_run: object | None,
        before_call: Callable[[], Awaitable[None]],
    ) -> tuple[str, object | None]:
        if self.client is None:
            raise RuntimeError("Cominty client is not open")
        uploaded = [await self.client.chat.upload_file(path) for path in files]
        file_ids = [item.id for item in uploaded]
        if previous_run is not None:
            await before_call()
            try:
                run = await self.client.chat.send(
                    previous_run.thread.id, agent_id=agent_id, message=message
                )
            except Exception as exc:
                fallback = (
                    f"{message}\nYour previous reply was invalid: "
                    f"{type(exc).__name__}: {exc}. Reply with valid JSON only."
                )
                await before_call()
                run = await self.client.chat.start(
                    agent_id=agent_id, message=fallback, file_ids=file_ids
                )
        else:
            await before_call()
            run = await self.client.chat.start(
                agent_id=agent_id, message=message, file_ids=file_ids
            )
        return await asyncio.wait_for(run.text(), timeout=120), run
