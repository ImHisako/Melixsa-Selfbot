"""Archivi dei messaggi: rotazione, ritentativi e recupero all'arresto."""
from __future__ import annotations

import asyncio
import json
import inspect
from pathlib import Path
import re
import time

from . import console_tools, persistence_tools

DEFAULTS = dict(max_bytes=10_000_000, backups=5, retention_days=0)
RECORD_FILE = re.compile(r"(?:group_-?\d+|stalk_\d+)\.txt\Z")


class BatchWriteError(OSError):
    def __init__(self, error, pending):
        super().__init__(str(error))
        self.pending = pending


class LogWriter:
    def __init__(self, directory: Path | None = None, *, settings=None, retry_delay=2, close_timeout=5):
        self.directory = directory
        self.settings = settings or (lambda: DEFAULTS.copy())
        self.retry_delay = retry_delay
        self.close_timeout = close_timeout
        self.queue = asyncio.Queue(maxsize=5000)
        self.task = None
        self._pending = []
        self.last_error = ""
        self.failures = 0
        self.written = 0
        self.closing = False
        self.disk_lock = asyncio.Lock()
        self.recovery_task = None
        self.recovery_sources = set()

    @property
    def pending_count(self):
        return self.queue.qsize() + len(self._pending)

    async def start(self):
        if self.directory is not None:
            self.directory.mkdir(parents=True, exist_ok=True)
        self.closing = False
        await self.cleanup()
        self.task = asyncio.create_task(self._run(), name="melixsa-logs")
        if self.directory is not None:
            for spool in sorted(self.directory.glob("pending-*.json")):
                try:
                    records = await asyncio.to_thread(self._read_spool, spool)
                    for path, record, echo in records:
                        await self.submit(path, record, echo=echo)
                    self.recovery_sources.add(spool)
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    self._problem(f"Recupero log {spool.name}: {type(exc).__name__}")
            if self.recovery_sources:
                self.recovery_task = asyncio.create_task(self._finish_recovery())

    async def _delete_recovery_sources(self):
        for spool in list(self.recovery_sources):
            try:
                await asyncio.to_thread(spool.unlink, missing_ok=True)
            except OSError as exc:
                self._problem(f"Archivio recuperato ma non rimovibile: {exc}")
            else:
                self.recovery_sources.discard(spool)

    async def _finish_recovery(self):
        await self.queue.join()
        await self._delete_recovery_sources()

    def _read_spool(self, path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Archivio di recupero non valido")
        records = []
        for item in raw:
            if not isinstance(item, dict) or not RECORD_FILE.fullmatch(str(item.get("file", ""))) or not isinstance(item.get("record"), dict):
                raise ValueError("Record di recupero non valido")
            records.append((self.directory / item["file"], item["record"], False))
        return records

    async def submit(self, path, record, *, echo=True):
        if self.closing:
            raise RuntimeError("Archivio log in chiusura")
        await self.queue.put((path, record.copy(), echo))

    def _problem(self, detail):
        self.last_error = console_tools.clean(detail)
        self.failures += 1
        # Un errore persistente non deve riempire il log a ogni ritentativo.
        if self.failures == 1 or self.failures % 30 == 0:
            console_tools.event("Error", self.last_error, error=True)

    def _complete(self, count):
        self.written += count
        for _ in range(count):
            self.queue.task_done()

    async def _settings(self):
        settings = self.settings()
        return await settings if inspect.isawaitable(settings) else settings

    async def _flush(self):
        batch = self._pending
        try:
            settings = await self._settings()
            async with self.disk_lock:
                warnings = await asyncio.to_thread(self._write_batch, batch, **settings)
        except BatchWriteError as exc:
            self._complete(len(batch) - len(exc.pending))
            self._pending = exc.pending
            self._problem(f"Scrittura log sospesa, record conservati: {exc}")
        else:
            self._complete(len(batch))
            self._pending = []
            self.last_error = ""
            for warning in warnings:
                self._problem(warning)

    async def _run(self):
        while True:
            if not self._pending:
                try:
                    self._pending = [await asyncio.wait_for(self.queue.get(), timeout=60)]
                except asyncio.TimeoutError:
                    await self.cleanup()
                    continue
                while len(self._pending) < 256:
                    try:
                        self._pending.append(self.queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
            # Un arresto attende la scrittura in thread prima di salvare la coda.
            flush = asyncio.create_task(self._flush())
            try:
                await asyncio.shield(flush)
            except asyncio.CancelledError:
                await flush
                raise
            if self._pending:
                await asyncio.sleep(self.retry_delay)

    async def close(self):
        self.closing = True
        if self.recovery_task is not None:
            self.recovery_task.cancel()
            await asyncio.gather(self.recovery_task, return_exceptions=True)
        if self.task is not None:
            try:
                await asyncio.wait_for(self.queue.join(), timeout=self.close_timeout)
            except asyncio.TimeoutError:
                pass
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        while not self.queue.empty():
            self._pending.append(self.queue.get_nowait())
        if self._pending and self.directory is not None:
            spool = self.directory / f"pending-{time.time_ns()}.json"
            payload = [{"file": path.name, "record": record} for path, record, _ in self._pending]
            try:
                await asyncio.to_thread(persistence_tools.atomic_write, spool, json.dumps(payload, ensure_ascii=False))
            except OSError as exc:
                self._problem(f"Impossibile salvare {len(payload)} record pendenti: {exc}")
            else:
                console_tools.event("Event", f"{len(payload)} record log salvati per il prossimo avvio")
                for _ in self._pending:
                    self.queue.task_done()
                self._pending = []
                await self._delete_recovery_sources()
        elif not self._pending:
            await self._delete_recovery_sources()

    async def cleanup(self):
        if self.directory is None or not self.directory.exists():
            return
        try:
            settings = await self._settings()
            async with self.disk_lock:
                await asyncio.to_thread(self._cleanup_files, **settings)
        except OSError as exc:
            self._problem(f"Pulizia archivi log non completata: {exc}")

    def _cleanup_files(self, *, max_bytes, backups, retention_days):
        bases = set()
        for path in self.directory.iterdir():
            name = path.name.split(".txt", 1)[0] + ".txt"
            if RECORD_FILE.fullmatch(name):
                bases.add(self.directory / name)
        for path in bases:
            self._rotate(path, max_bytes, retention_days, 0)
            self.prune(path, backups, retention_days)

    @staticmethod
    def _rotate(path, max_bytes, retention_days, incoming):
        if not path.exists() or not path.stat().st_size:
            return
        size_limit = path.stat().st_size + incoming > max_bytes
        # Con scadenza attiva, chiudi almeno ogni giorno il file in uso.
        age_limit = retention_days and int(path.stat().st_mtime // 86_400) < int(time.time() // 86_400)
        if size_limit or age_limit:
            archive = path.with_name(f"{path.name}.{time.time_ns()}")
            path.replace(archive)

    @staticmethod
    def prune(path, backups, retention_days):
        archives = sorted((p for p in path.parent.glob(path.name + ".*")
                           if p.name[len(path.name) + 1:].isdigit()), key=lambda p: int(p.name.rsplit(".", 1)[1]), reverse=True)
        for index, archive in enumerate(archives):
            expired = retention_days and time.time() - archive.stat().st_mtime > retention_days * 86_400
            if index >= backups or expired:
                archive.unlink()

    @staticmethod
    def _write_batch(batch, *, max_bytes=10_000_000, backups=5, retention_days=0):
        touched = set()
        for index, (path, record, echo) in enumerate(batch):
            try:
                payload = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                LogWriter._rotate(path, max_bytes, retention_days, len(payload))
                with path.open("a+b") as output:
                    output.seek(0, 2)
                    offset = output.tell()
                    try:
                        output.write(payload)
                        output.flush()
                    except OSError:
                        output.seek(offset)
                        output.truncate()
                        raise
            except OSError as exc:
                raise BatchWriteError(exc, batch[index:]) from exc
            touched.add(path)
            if echo:
                chat = record.get("chat_name") or record.get("chat_title") or "Chat senza nome"
                user = record.get("name") or (f"@{record['username']}" if record.get("username") else record.get("sender_chat_title") or "Utente senza nome")
                if record.get("event") in {"name_changed", "username_changed", "photo_changed", "online", "offline"}:
                    console_tools.event("Stalk", f"{record['event']} | user={user} | {record.get('old_value')} → {record.get('new_value')}")
                else:
                    console_tools.event("Message", f"{record.get('event')} | chat={chat} | user={user} | {record.get('text') or record.get('media')}")
        warnings = []
        for path in touched:
            try:
                LogWriter.prune(path, backups, retention_days)
            except OSError as exc:
                warnings.append(f"Pulizia archivi log non completata: {exc}")
        return warnings
