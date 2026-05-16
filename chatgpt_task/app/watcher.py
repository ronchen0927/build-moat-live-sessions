import asyncio

from . import scheduler


async def watch_loop(queue: asyncio.Queue, interval: float = 5.0) -> None:
    """Scan for due jobs every `interval` seconds and push their IDs to the queue."""
    while True:
        for job in scheduler.find_due_jobs():
            scheduler.mark_queued(job.id)
            await queue.put(job.id)
        await asyncio.sleep(interval)
