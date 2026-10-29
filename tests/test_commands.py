import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pyrogram import enums
from pyrogram.types import Chat, Message, User

from Cogs.core import runtime as selfbot


class CommandDeletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_delayed_deletions_keep_each_command_and_chat_name(self):
        first = SimpleNamespace(id=20, chat=SimpleNamespace(id=99), delete=AsyncMock())
        second = SimpleNamespace(id=21, chat=SimpleNamespace(id=-100123, title="Gruppo amici"), delete=AsyncMock())
        with patch.object(selfbot, "state", selfbot.MonitorState(delete_after=1)), \
             patch.object(selfbot.asyncio, "sleep", new_callable=AsyncMock), \
             patch.object(selfbot.console_tools, "event") as log:
            for sent, command, name in ((first, "help", "Messaggi salvati"), (second, "whois", "Gruppo amici")):
                token = selfbot.command_context.set((command, sent.chat.id, name))
                try:
                    selfbot.schedule_delete(sent)
                finally:
                    selfbot.command_context.reset(token)
            await asyncio.gather(*list(selfbot.delete_tasks))
        first.delete.assert_awaited_once()
        second.delete.assert_awaited_once()
        self.assertIsNone(selfbot.command_context.get())
        self.assertEqual([call.args[1] for call in log.call_args_list], [
            "Comando help cancellato | chat=Messaggi salvati",
            "Comando whois cancellato | chat=Gruppo amici",
        ])

    async def test_command_logs_use_chat_title_and_provide_context_to_handler(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-100123, type=enums.ChatType.SUPERGROUP, title="Gruppo amici"),
            from_user=SimpleNamespace(id=99), text=">help", delete=AsyncMock(),
        )
        async def handle(*args):
            self.assertEqual(selfbot.command_context.get(), ("help", -100123, "Gruppo amici"))
        with patch.object(selfbot, "state", selfbot.MonitorState(prefix=">")), \
             patch.object(selfbot, "handle_command", new_callable=AsyncMock, side_effect=handle), \
             patch.object(selfbot.console_tools, "event") as log:
            await selfbot.process_message(None, message, 99)
        self.assertTrue(all("chat=Gruppo amici" in call.args[1] for call in log.call_args_list))
        self.assertIsNone(selfbot.command_context.get())

    async def test_delete_before_execution_then_send_codeblock_in_same_topic(self):
        order = []
        async def delete(*args, **kwargs):
            order.append("delete")
            return True
        async def execute(*args, **kwargs):
            self.assertEqual(order, ["delete"])
            order.append("execute")
            return "Brano: esempio"
        sent = SimpleNamespace(id=20)
        async def send(*args, **kwargs):
            self.assertEqual(order, ["delete", "execute"])
            order.append("send")
            return sent
        client = SimpleNamespace(delete_messages=AsyncMock(side_effect=delete), send_message=AsyncMock(side_effect=send))
        message = Message(
            client=client, id=10, text=">scnp", message_thread_id=7,
            chat=Chat(id=-100123, type=enums.ChatType.SUPERGROUP),
            from_user=User(id=99),
        )
        with patch.object(selfbot, "state", selfbot.MonitorState(prefix=">", autoreact=True)), \
             patch.object(selfbot.soundcloud, "execute", new_callable=AsyncMock, side_effect=execute), \
             patch.object(selfbot, "schedule_delete") as schedule, \
             patch.object(selfbot.auto_reactor, "react", new_callable=AsyncMock) as react:
            await selfbot.process_message(client, message, 99)
            schedule.assert_called_once_with(sent)
            react.assert_not_awaited()
        self.assertEqual(order, ["delete", "execute", "send"])
        kwargs = client.send_message.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], -100123)
        self.assertEqual(kwargs["message_thread_id"], 7)
        self.assertIsNone(kwargs["reply_parameters"])
        entity, = kwargs["entities"]
        self.assertEqual(entity.type, enums.MessageEntityType.PRE)
        self.assertEqual(entity.language, "ini")

    async def test_timer_off_does_not_disable_immediate_command_deletion(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=10, type=enums.ChatType.PRIVATE),
            from_user=SimpleNamespace(id=99), text=">help", delete=AsyncMock(),
        )
        with patch.object(selfbot, "state", selfbot.MonitorState(prefix=">", delete_after=0)), \
             patch.object(selfbot, "handle_command", new_callable=AsyncMock) as handle, \
             patch.object(selfbot, "schedule_delete") as schedule:
            await selfbot.process_message(None, message, 99)
            message.delete.assert_awaited_once()
            handle.assert_awaited_once_with(None, message, "help", "")
            schedule.assert_not_called()

    async def test_other_people_normal_text_and_unknown_commands_are_not_deleted(self):
        with patch.object(selfbot, "state", selfbot.MonitorState(prefix=">")), \
             patch.object(selfbot, "handle_command", new_callable=AsyncMock) as handle:
            for sender, text in ((100, ">scnp"), (99, "ciao"), (99, ">sconosciuto"), (99, "/scnp")):
                message = SimpleNamespace(
                    chat=SimpleNamespace(id=10, type=enums.ChatType.PRIVATE),
                    from_user=SimpleNamespace(id=sender), text=text, delete=AsyncMock(),
                )
                await selfbot.process_message(None, message, 99)
                message.delete.assert_not_awaited()
            handle.assert_not_awaited()

    async def test_recovery_command_and_failed_deletion_still_execute(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=10, type=enums.ChatType.PRIVATE),
            from_user=SimpleNamespace(id=99), text="/prefix /", delete=AsyncMock(side_effect=RuntimeError("cannot delete")),
        )
        with patch.object(selfbot, "state", selfbot.MonitorState(prefix=">")), \
             patch.object(selfbot, "handle_command", new_callable=AsyncMock) as handle:
            await selfbot.process_message(None, message, 99)
            message.delete.assert_awaited_once()
            handle.assert_awaited_once_with(None, message, "prefix", "/")

    async def test_command_failure_is_logged_without_sending_error_to_chat(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=10, type=enums.ChatType.PRIVATE),
            from_user=SimpleNamespace(id=99), text=">scnp", delete=AsyncMock(),
            answer=AsyncMock(return_value=SimpleNamespace(id=20)),
        )
        with patch.object(selfbot, "state", selfbot.MonitorState(prefix=">")), \
             patch.object(selfbot, "handle_command", new_callable=AsyncMock, side_effect=ValueError("offline")), \
             patch.object(selfbot, "schedule_delete") as schedule, \
             patch.object(selfbot.console_tools, "event") as log:
            await selfbot.process_message(None, message, 99)
            message.answer.assert_not_awaited()
            schedule.assert_not_called()
            self.assertTrue(any(call.args[0] == "Error" and "offline" in call.args[1] for call in log.call_args_list))


if __name__ == "__main__":
    unittest.main()
