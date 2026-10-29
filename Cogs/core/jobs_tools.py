"""Coda limitata delle ricerche estese, con stato e annullamento."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import time

from . import console_tools


ACTIVE = {"in coda", "in esecuzione", "invio report", "annullamento"}


@dataclass
class Job:
    id: int
    command: str
    requester: int
    chat: int
    created: float
    status: str = "in coda"
    started: float | None = None
    finished: float | None = None
    task: asyncio.Task | None = None
    ready: asyncio.Event | None = None

    @property
    def elapsed(self):
        return max(0, int((self.finished or time.monotonic()) - (self.started or self.created)))


class JobManager:
    def __init__(self, *, limit=10, history=20, timeout=600):
        self.limit, self.history, self.timeout = limit, history, timeout
        self.jobs = OrderedDict()
        self.lock = asyncio.Lock()
        self.next_id = 1
        self.closing = False

    def visible(self, *, requester=None, chat=None):
        return [job for job in self.jobs.values()
                if requester is None or (job.requester == requester and job.chat == chat)]

    def submit(self, command, requester, chat, operation, *, on_error=None):
        if self.closing:
            raise ValueError("Ricerche in chiusura.")
        if sum(job.status in ACTIVE for job in self.jobs.values()) >= self.limit:
            raise ValueError(f"Coda piena: massimo {self.limit} ricerche. Usa osintjobs.")
        job = Job(self.next_id, command, requester, chat, time.monotonic(), ready=asyncio.Event())
        self.next_id += 1
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job, operation, on_error), name=f"osint-{job.id}")
        job.task.add_done_callback(lambda task: self._done(job, task))
        return job

    def _done(self, job, task):
        if task.cancelled():
            job.status = "annullata"
        elif task.exception() is not None:
            job.status = "fallita"
            console_tools.event("Error", f"OSINT #{job.id}: errore interno ({type(task.exception()).__name__})", error=True)
        job.finished = time.monotonic()
        # Lo storico conserva solo metadati, senza testo cercato o messaggi.
        completed = sorted((key for key, item in self.jobs.items() if item.status not in ACTIVE),
                           key=lambda key: self.jobs[key].finished or 0)
        for key in completed[:-self.history] if self.history else completed:
            self.jobs.pop(key, None)

    async def _run(self, job, operation, on_error):
        try:
            async with self.lock:
                await job.ready.wait()
                job.started = time.monotonic()
                job.status = "in esecuzione"
                try:
                    await asyncio.wait_for(operation(job), timeout=self.timeout)
                except asyncio.TimeoutError:
                    job.status = "tempo scaduto"
                    if on_error:
                        await on_error(job, TimeoutError("Tempo massimo della ricerca superato."))
                except Exception as exc:
                    job.status = "fallita"
                    if on_error:
                        await on_error(job, exc)
                else:
                    job.status = "completata"
        except asyncio.CancelledError:
            job.status = "annullata"
            raise
        finally:
            job.finished = time.monotonic()

    def cancel(self, job_id, *, requester=None, chat=None):
        job = self.jobs.get(job_id)
        if job is None or (requester is not None and (job.requester != requester or job.chat != chat)):
            raise ValueError("Ricerca non disponibile.")
        if job.status not in ACTIVE:
            raise ValueError("La ricerca è già terminata.")
        if job.status != "annullamento":
            job.status = "annullamento"
            job.task.cancel()
        return job

    async def close(self):
        self.closing = True
        tasks = []
        for job in self.jobs.values():
            if job.task is not None and not job.task.done():
                if job.status != "annullamento":
                    job.task.cancel()
                tasks.append(job.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
