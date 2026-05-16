import asyncio

from . import scheduler


async def work_loop(queue: asyncio.Queue) -> None:
    """Pull job IDs from the queue and execute them (simulated with a short sleep)."""
    while True:
        job_id = await queue.get()
        try:
            scheduler.mark_running(job_id)
            await asyncio.sleep(2)  # simulate work
            scheduler.mark_completed(job_id)
        finally:
            queue.task_done()
