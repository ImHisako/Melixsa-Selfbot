import asyncio
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from Cogs.core.log_tools import BatchWriteError, LogWriter


class ArchiveTests(unittest.TestCase):
    def test_inactive_monitors_expire_when_retention_is_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            active = root / "group_-1.txt"
            active.write_text('{"id":1}\n')
            os.utime(active, (time.time() - 3 * 86_400,) * 2)
            writer = LogWriter(root)
            writer._cleanup_files(max_bytes=1000, backups=5, retention_days=0)
            self.assertTrue(active.exists())
            writer._cleanup_files(max_bytes=1000, backups=5, retention_days=1)
            self.assertFalse(active.exists())
            self.assertFalse(list(root.glob("group_-1.txt.*")))

    def test_size_rotation_limits_backups_and_keeps_valid_json_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "group_-1.txt"
            for index in range(6):
                LogWriter._write_batch([(path, {"text": "😀" * 10, "id": index}, False)], max_bytes=100, backups=2)
            archives = list(path.parent.glob(path.name + ".*"))
            self.assertEqual(len(archives), 2)
            records = [json.loads(line) for f in archives + [path] for line in f.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(sorted(item["id"] for item in records), [3, 4, 5])

    def test_retention_excludes_pending_and_operational_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "stalk_1.txt"
            archive = root / "stalk_1.txt.123"
            archive.write_text("old")
            os.utime(archive, (time.time() - 3 * 86_400,) * 2)
            pending = root / "pending-123.json"
            pending.write_text("[]")
            operational = root / "melixsa.log.1"
            operational.write_text("diagnostics")
            LogWriter(root)._cleanup_files(max_bytes=100, backups=5, retention_days=1)
            self.assertFalse(archive.exists())
            self.assertTrue(pending.exists())
            self.assertTrue(operational.exists())

    def test_partial_batch_failure_retries_only_unwritten_records(self):
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder) / "group_-1.txt"
            bad = Path(folder) / "stalk_1.txt"
            batch = [(good, {"id": 1}, False), (bad, {"id": 2}, False), (good, {"id": 3}, False)]
            original = Path.open
            def open_file(path, *args, **kwargs):
                if path == bad:
                    raise OSError("disk error")
                return original(path, *args, **kwargs)
            with patch.object(Path, "open", open_file):
                with self.assertRaises(BatchWriteError) as error:
                    LogWriter._write_batch(batch)
            self.assertEqual(error.exception.pending, batch[1:])
            LogWriter._write_batch(error.exception.pending)
            self.assertEqual([json.loads(line)["id"] for line in good.read_text().splitlines()], [1, 3])

    def test_failed_append_rolls_back_partial_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "group_-1.txt"
            path.write_text('{"id":1}\n')
            original = Path.open
            class PartialWrite:
                def __enter__(self):
                    self.file = original(path, "a+b")
                    return self
                def __exit__(self, *args): self.file.close()
                def __getattr__(self, key): return getattr(self.file, key)
                def write(self, data):
                    self.file.write(data[:4])
                    self.file.flush()
                    raise OSError("full")
            with patch.object(Path, "open", return_value=PartialWrite()):
                with self.assertRaises(BatchWriteError):
                    LogWriter._write_batch([(path, {"id": 2}, False)])
            self.assertEqual(path.read_text(), '{"id":1}\n')


class WriterRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_source_stays_durable_until_records_are_written(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "pending-1.json"
            source.write_text(json.dumps([{"file": "group_-1.txt", "record": {"id": 1}}]))
            writer = LogWriter(root, retry_delay=0.01, close_timeout=0.02)
            def fail(batch, **kwargs): raise BatchWriteError(OSError("full"), batch)
            with patch.object(writer, "_write_batch", side_effect=fail):
                await writer.start()
                await asyncio.sleep(0.01)
                self.assertTrue(source.exists())
                await writer.close()
            self.assertEqual(len(list(root.glob("pending-*.json"))), 1)
            recovered = LogWriter(root)
            await recovered.start()
            await asyncio.wait_for(recovered.queue.join(), 2)
            await recovered.close()
            self.assertEqual(json.loads((root / "group_-1.txt").read_text())["id"], 1)
            self.assertFalse(list(root.glob("pending-*.json")))

    async def test_temporary_failure_retains_queue_and_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            writer = LogWriter(root, retry_delay=0.01)
            original = writer._write_batch
            attempts = []
            def write(batch, **kwargs):
                attempts.append(1)
                if len(attempts) == 1:
                    raise BatchWriteError(OSError("full"), batch)
                return original(batch, **kwargs)
            with patch.object(writer, "_write_batch", side_effect=write):
                await writer.start()
                await writer.submit(root / "group_-1.txt", {"id": 1}, echo=False)
                await asyncio.wait_for(writer.queue.join(), 2)
                self.assertEqual(writer.failures, 1)
                self.assertEqual(writer.pending_count, 0)
                self.assertEqual(writer.written, 1)
                await writer.close()

    async def test_shutdown_spools_failed_batch_and_next_start_replays_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            writer = LogWriter(root, retry_delay=0.01, close_timeout=0.03)
            def fail(batch, **kwargs): raise BatchWriteError(OSError("full"), batch)
            with patch.object(writer, "_write_batch", side_effect=fail):
                await writer.start()
                for index in range(3):
                    await writer.submit(root / "group_-1.txt", {"id": index}, echo=False)
                await writer.close()
            self.assertEqual(len(list(root.glob("pending-*.json"))), 1)
            recovered = LogWriter(root)
            await recovered.start()
            await asyncio.wait_for(recovered.queue.join(), 2)
            await recovered.close()
            records = [json.loads(line)["id"] for line in (root / "group_-1.txt").read_text().splitlines()]
            self.assertEqual(records, [0, 1, 2])
            self.assertFalse(list(root.glob("pending-*.json")))

    async def test_malformed_spool_is_retained_and_does_not_escape_log_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            spool = root / "pending-1.json"
            spool.write_text(json.dumps([{"file": "../escaped.txt", "record": {}}]))
            writer = LogWriter(root)
            await writer.start()
            await writer.close()
            self.assertTrue(spool.exists())
            self.assertEqual(writer.failures, 1)
            self.assertEqual(writer.written, 0)


if __name__ == "__main__":
    unittest.main()
