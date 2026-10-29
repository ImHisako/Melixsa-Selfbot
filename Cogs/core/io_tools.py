"""Operazioni locali in thread con completamento protetto dalle cancellazioni."""
from __future__ import annotations

import asyncio

async def local_io(function, *args):
    """Una scrittura in thread termina prima di rilasciare il lock, anche se annullata."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise
