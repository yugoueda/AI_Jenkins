import argparse
import asyncio
import contextlib
import logging
import os
import time
from pathlib import Path

from .agent.dispatcher import dispatch
from .webhook.queue import (
    claim_next_waiting_job,
    complete_job,
    recover_stale_jobs,
)


HEARTBEAT_PATH = Path(os.getenv("WORKER_HEARTBEAT_PATH", "/tmp/ai-worker-heartbeat"))


async def heartbeat_loop() -> None:
    interval = float(os.getenv("WORKER_HEARTBEAT_INTERVAL_SECONDS", "5"))
    while True:
        HEARTBEAT_PATH.touch()
        await asyncio.sleep(interval)


async def process_once() -> bool:
    job = claim_next_waiting_job()
    if job is None:
        return False

    logging.info(
        "Job started: job_id=%s event_type=%s mr=%s",
        job["job_id"],
        job["event_type"],
        job["mr_id"],
    )
    try:
        await dispatch(job)
    except Exception:
        logging.exception("Job failed: job_id=%s", job["job_id"])
        complete_job(job["job_id"], succeeded=False)
    else:
        complete_job(job["job_id"], succeeded=True)
        logging.info(
            "Job completed: job_id=%s event_type=%s mr=%s",
            job["job_id"],
            job["event_type"],
            job["mr_id"],
        )
    return True


async def run_forever() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    recovered = recover_stale_jobs()
    if recovered:
        logging.warning("Recovered %d stale PROCESSING job(s) as FAILED", recovered)

    heartbeat_task = asyncio.create_task(heartbeat_loop())
    try:
        poll_interval = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2"))
        while True:
            processed = await process_once()
            if not processed:
                await asyncio.sleep(poll_interval)
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task


def healthcheck() -> int:
    max_age = float(os.getenv("WORKER_HEALTH_MAX_AGE_SECONDS", "30"))
    try:
        age = time.time() - HEARTBEAT_PATH.stat().st_mtime
    except FileNotFoundError:
        return 1
    return 0 if age <= max_age else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()

    if args.healthcheck:
        return healthcheck()
    if args.once:
        asyncio.run(process_once())
        return 0
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
