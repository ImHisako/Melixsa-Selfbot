import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums

from Cogs.core import runtime
from Cogs.core.jobs_tools import JobManager
from Cogs.osint import handle_osint_command, handle_jobs_command


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_acknowledgement_keeps_submission_order(self):
        manager = JobManager()
        self.addAsyncCleanup(manager.close)
        order = []
        async def operation(job): order.append(job.id)
        one = manager.submit("email", 10, 1, operation)
        two = manager.submit("email", 10, 1, operation)
        two.ready.set()
        for _ in range(4): await asyncio.sleep(0)
        self.assertEqual(order, [])
        one.ready.set()
        await asyncio.gather(one.task, two.task)
        self.assertEqual(order, [one.id, two.id])

    async def test_bounded_queue_runs_one_at_a_time_and_tracks_history(self):
        manager = JobManager(limit=2, history=1)
        self.addAsyncCleanup(manager.close)
        entered, release = asyncio.Event(), asyncio.Event()
        order = []
        async def first(job):
            order.append(1)
            entered.set()
            await release.wait()
        async def second(job): order.append(2)
        one = manager.submit("email", 10, 1, first)
        two = manager.submit("username", 20, 1, second)
        one.ready.set()
        two.ready.set()
        await asyncio.wait_for(entered.wait(), 1)
        self.assertEqual(one.status, "in esecuzione")
        self.assertEqual(two.status, "in coda")
        with self.assertRaises(ValueError): manager.submit("email", 10, 1, second)
        release.set()
        await asyncio.gather(one.task, two.task)
        self.assertEqual(order, [1, 2])
        self.assertEqual(two.status, "completata")
        self.assertGreaterEqual(two.elapsed, 0)
        self.assertEqual(list(manager.jobs), [two.id])

    async def test_queued_and_running_cancellation_cleanup_and_scope(self):
        manager = JobManager()
        self.addAsyncCleanup(manager.close)
        entered, cleaned = asyncio.Event(), asyncio.Event()
        async def operation(job):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        one = manager.submit("email", 10, 1, operation)
        two = manager.submit("username", 20, 1, AsyncMock())
        one.ready.set()
        two.ready.set()
        await asyncio.wait_for(entered.wait(), 1)
        with self.assertRaises(ValueError): manager.cancel(one.id, requester=20, chat=1)
        with self.assertRaises(ValueError): manager.cancel(one.id, requester=10, chat=2)
        manager.cancel(two.id, requester=20, chat=1)
        manager.cancel(one.id)
        await asyncio.gather(one.task, two.task, return_exceptions=True)
        self.assertTrue(cleaned.is_set())
        self.assertEqual(one.status, "annullata")
        self.assertEqual(two.status, "annullata")

    async def test_cancel_before_task_starts_is_recorded(self):
        manager = JobManager()
        operation = AsyncMock()
        job = manager.submit("email", 10, 1, operation)
        manager.cancel(job.id)
        await asyncio.gather(job.task, return_exceptions=True)
        self.assertEqual(job.status, "annullata")
        operation.assert_not_awaited()

    async def test_timeout_failure_and_shutdown_are_distinct(self):
        manager = JobManager(timeout=0.02)
        failed = AsyncMock()
        async def slow(job): await asyncio.Event().wait()
        job = manager.submit("email", 10, 1, slow, on_error=failed)
        job.ready.set()
        await job.task
        self.assertEqual(job.status, "tempo scaduto")
        failed.assert_awaited_once()
        operation = AsyncMock(side_effect=ValueError("invalid"))
        job = manager.submit("email", 10, 1, operation, on_error=failed)
        job.ready.set()
        await job.task
        self.assertEqual(job.status, "fallita")
        job = manager.submit("email", 10, 1, slow)
        await manager.close()
        self.assertEqual(job.status, "annullata")
        with self.assertRaises(ValueError): manager.submit("email", 10, 1, slow)


class JobCommandTests(unittest.IsolatedAsyncioTestCase):
    def message(self, user=10, chat=1):
        return SimpleNamespace(chat=SimpleNamespace(id=chat, type=enums.ChatType.PRIVATE), from_user=SimpleNamespace(id=user))

    async def test_handler_acknowledges_before_work_and_delivers_to_original_message(self):
        manager = JobManager()
        self.addAsyncCleanup(manager.close)
        message = self.message()
        order = []
        async def acknowledge(*args, **kwargs): order.append("ack")
        async def lookup(*args):
            self.assertEqual(order, ["ack"])
            order.append("lookup")
            return "report"
        with patch.object(runtime, "osint_jobs", manager), patch.object(runtime, "respond", new_callable=AsyncMock, side_effect=acknowledge) as respond, \
             patch.object(runtime.osint_features, "lookup", new_callable=AsyncMock, side_effect=lookup), \
             patch.object(runtime.osint_features, "send_report", new_callable=AsyncMock) as send:
            await handle_osint_command(message, "email", "test@example.com", client="client")
            job = manager.jobs[1]
            await job.task
            send.assert_awaited_once_with("client", message, "report", "email", runtime.state.prefix)
            self.assertIn("#1", respond.call_args.args[1])
            self.assertEqual(job.status, "completata")

    async def test_failed_ack_prevents_lookup(self):
        manager = JobManager()
        self.addAsyncCleanup(manager.close)
        with patch.object(runtime, "osint_jobs", manager), patch.object(runtime, "respond", new_callable=AsyncMock, side_effect=OSError("send error")), \
             patch.object(runtime.osint_features, "lookup", new_callable=AsyncMock) as lookup:
            with self.assertRaises(OSError): await handle_osint_command(self.message(), "email", "test@example.com")
            await asyncio.gather(manager.jobs[1].task, return_exceptions=True)
            lookup.assert_not_awaited()

    async def test_list_and_cancel_hide_other_users_and_chats(self):
        manager = JobManager()
        self.addAsyncCleanup(manager.close)
        one = manager.submit("email", 10, 1, AsyncMock())
        manager.submit("username", 20, 1, AsyncMock())
        manager.submit("breach", 10, 2, AsyncMock())
        token = runtime.shared_command_context.set(True)
        try:
            with patch.object(runtime, "osint_jobs", manager), patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
                await handle_jobs_command(self.message(), "osintjobs", "")
                text = respond.call_args.args[1]
                self.assertIn("email", text)
                self.assertNotIn("username", text)
                self.assertNotIn("breach", text)
                with self.assertRaises(ValueError): await handle_jobs_command(self.message(), "osintcancel", "2")
                await handle_jobs_command(self.message(), "osintcancel", str(one.id))
        finally:
            runtime.shared_command_context.reset(token)


if __name__ == "__main__":
    unittest.main()
