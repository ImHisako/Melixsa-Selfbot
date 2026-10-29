import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pyrogram import enums, raw
from pyrogram.errors import FloodWait, ReactionInvalid, PremiumAccountRequired

from Cogs.core import autoreact_tools
from Cogs.core import runtime as selfbot


def message(user_id=99, chat_id=10, *, text="ciao", media=None, service=None):
    return SimpleNamespace(
        id=123, chat=SimpleNamespace(id=chat_id, type=enums.ChatType.PRIVATE),
        from_user=SimpleNamespace(id=user_id), text=text, media=media, service=service,
    )


def client_with_reactions(*, premium=True, custom=False):
    async def invoke(query, **kwargs):
        if isinstance(query, raw.functions.messages.GetAvailableReactions):
            return SimpleNamespace(reactions=[] if custom else [
                SimpleNamespace(reaction=emoji, inactive=False) for emoji in autoreact_tools.EMOJIS
            ])
        if isinstance(query, raw.functions.messages.SearchCustomEmoji):
            return SimpleNamespace(document_id=[111 if query.emoticon == "🖤" else 222])
        return True
    return SimpleNamespace(
        get_me=AsyncMock(return_value=SimpleNamespace(is_premium=premium)),
        invoke=AsyncMock(side_effect=invoke),
        resolve_peer=AsyncMock(return_value=raw.types.InputPeerSelf()),
    )


class AutoReactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_premium_error_explains_saved_messages_only(self):
        for chat_id in (99, 10):
            reactor = autoreact_tools.AutoReactor()
            reactor.reactions = [raw.types.ReactionEmoji(emoticon="❤")]
            reactor.resolved_emojis = ("❤️",)
            client = client_with_reactions(premium=False)
            client.invoke.side_effect = PremiumAccountRequired()
            await reactor.react(client, message(chat_id=chat_id), lambda: True, emojis=("❤️",))
            self.assertIn("PREMIUM_ACCOUNT_REQUIRED", reactor.last_error)
            self.assertEqual("Messaggi salvati" in reactor.last_error, chat_id == 99)

    async def test_selected_count_controls_sends_and_refreshes_cache(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions()
        selected = ("👍", "❤️", "🔥")
        async def invoke(query, **kwargs):
            if isinstance(query, raw.functions.messages.GetAvailableReactions):
                return SimpleNamespace(reactions=[SimpleNamespace(reaction=emoji, inactive=False) for emoji in selected])
            return True
        client.invoke.side_effect = invoke
        await reactor.react(client, message(), lambda: True, emojis=selected[:1])
        sends = [call.args[0] for call in client.invoke.call_args_list if isinstance(call.args[0], raw.functions.messages.SendReaction)]
        self.assertEqual([[r.emoticon for r in query.reaction] for query in sends], [["👍"]])
        client.invoke.reset_mock()
        await reactor.react(client, message(), lambda: True, emojis=selected)
        sends = [call.args[0] for call in client.invoke.call_args_list if isinstance(call.args[0], raw.functions.messages.SendReaction)]
        self.assertEqual([[r.emoticon for r in query.reaction] for query in sends], [["👍"], ["👍", "❤️"], list(selected)])
        self.assertEqual(reactor.resolved_emojis, selected)

    async def test_variation_selector_uses_server_standard_emoji(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions()
        client.invoke.return_value = SimpleNamespace(reactions=[SimpleNamespace(reaction="❤", inactive=False)])
        client.invoke.side_effect = None
        reactions = await reactor.prepare(client, emojis=("❤️",))
        self.assertEqual(reactions[0].emoticon, "❤")
        client.invoke.assert_awaited_once()

    async def test_reactions_are_sent_in_order_preserving_the_first(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions()
        await reactor.react(client, message(), lambda: True)
        sends = [call for call in client.invoke.call_args_list
                 if isinstance(call.args[0], raw.functions.messages.SendReaction)]
        self.assertEqual(len(sends), 2)
        self.assertEqual([r.emoticon for r in sends[0].args[0].reaction], ["🖤"])
        query = sends[1].args[0]
        self.assertEqual(query.msg_id, 123)
        self.assertEqual([r.emoticon for r in query.reaction], ["🖤", "🦇"])
        self.assertEqual(sends[0].kwargs["sleep_threshold"], 0)

    async def test_custom_emojis_are_resolved_and_cached(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions(custom=True)
        await reactor.react(client, message(), lambda: True)
        await reactor.react(client, message(), lambda: True)
        self.assertEqual([r.document_id for r in reactor.reactions], [111, 222])
        searches = [call.args[0] for call in client.invoke.call_args_list
                    if isinstance(call.args[0], raw.functions.messages.SearchCustomEmoji)]
        self.assertEqual([q.emoticon for q in searches], ["🖤", "🦇"])
        client.get_me.assert_not_awaited()

    async def test_activation_does_not_require_premium_precheck(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions(premium=False)
        await reactor.prepare(client)
        self.assertEqual(len(reactor.reactions), 2)
        client.get_me.assert_not_awaited()

    async def test_complete_pair_must_be_resolvable(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions(custom=True)
        client.invoke.side_effect = [SimpleNamespace(reactions=[]), SimpleNamespace(document_id=[111]), SimpleNamespace(document_id=[])]
        with self.assertRaisesRegex(ValueError, "🦇"):
            await reactor.prepare(client)
        self.assertIsNone(reactor.reactions)

    async def test_flood_wait_does_not_sleep_or_retry_immediately(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions()
        await reactor.prepare(client)
        client.invoke.reset_mock()
        client.invoke.side_effect = FloodWait(30)
        with patch("Cogs.core.autoreact_tools.time.monotonic", return_value=100):
            await reactor.react(client, message(), lambda: True)
            await reactor.react(client, message(chat_id=20), lambda: True)
        client.invoke.assert_awaited_once()
        self.assertEqual(reactor.retry_after, 130)
        self.assertIn("30", reactor.last_error)

    async def test_rejected_chat_does_not_block_other_chats(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions()
        await reactor.prepare(client)
        client.invoke.reset_mock()
        client.invoke.side_effect = [ReactionInvalid(), ReactionInvalid(), True, True]
        await reactor.react(client, message(chat_id=10), lambda: True)
        await reactor.react(client, message(chat_id=10), lambda: True)
        await reactor.react(client, message(chat_id=20), lambda: True)
        self.assertEqual(client.invoke.await_count, 4)
        self.assertIn("REACTION_INVALID", reactor.last_error)

    async def test_second_rejection_keeps_the_confirmed_first_reaction(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions(premium=False)
        await reactor.prepare(client)
        client.invoke.reset_mock()
        client.invoke.side_effect = [True, PremiumAccountRequired()]
        await reactor.react(client, message(), lambda: True)
        self.assertEqual(client.invoke.await_count, 2)
        self.assertIn("🦇: PREMIUM_ACCOUNT_REQUIRED", reactor.last_error)
        self.assertIn("Confermate: 🖤", reactor.last_error)

    async def test_first_rejection_still_tries_second_alone(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions()
        await reactor.prepare(client)
        client.invoke.reset_mock()
        client.invoke.side_effect = [ReactionInvalid(), True]
        await reactor.react(client, message(), lambda: True)
        second = client.invoke.call_args_list[1].args[0]
        self.assertEqual([r.emoticon for r in second.reaction], ["🦇"])
        self.assertIn("Confermate: 🦇", reactor.last_error)

    async def test_off_and_service_messages_send_nothing(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions()
        await reactor.react(client, message(), lambda: False)
        await reactor.react(client, message(service=True), lambda: True)
        client.get_me.assert_not_awaited()
        client.invoke.assert_not_awaited()

    async def test_switching_off_during_resolution_cancels_send(self):
        reactor = autoreact_tools.AutoReactor()
        client = client_with_reactions()
        await reactor.prepare(client)
        client.invoke.reset_mock()
        enabled = True
        async def resolve(chat_id):
            nonlocal enabled
            enabled = False
            return raw.types.InputPeerSelf()
        client.resolve_peer.side_effect = resolve
        await reactor.react(client, message(), lambda: enabled)
        client.invoke.assert_not_awaited()


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_configure_list_count_and_save_then_use_selected_reactions(self):
        state = selfbot.MonitorState(autoreact=True, prefix=">")
        with patch.object(selfbot, "state", state), patch.object(state, "save") as save, \
             patch.object(selfbot.auto_reactor, "prepare", new_callable=AsyncMock), \
             patch.object(selfbot.auto_reactor, "react", new_callable=AsyncMock) as react, \
             patch.object(selfbot, "respond", new_callable=AsyncMock) as respond:
            await selfbot.handle_command(None, message(), "autoreact", "emoji 👍 ❤️ 🔥")
            await selfbot.handle_command(None, message(), "autoreact", "count 1")
            self.assertEqual(state.autoreact_emojis, ("👍", "❤️", "🔥"))
            self.assertEqual(state.autoreact_count, 1)
            self.assertEqual(save.call_count, 2)
            self.assertIn("Reazioni per messaggio » 👍\n", respond.call_args.args[1])
            await selfbot.process_message(None, message(), 99)
            self.assertEqual(react.call_args.kwargs["emojis"], ("👍",))
            await selfbot.handle_command(None, message(), "autoreact", "count 3")
            await selfbot.handle_command(None, message(), "autoreact", "emoji 🖤")
            self.assertEqual(state.autoreact_count, 1)

    async def test_invalid_configuration_and_failed_save_preserve_preferences(self):
        state = selfbot.MonitorState()
        original = state.autoreact_emojis, state.autoreact_count
        with patch.object(selfbot, "state", state), patch.object(state, "save") as save, \
             patch.object(selfbot.auto_reactor, "prepare", new_callable=AsyncMock):
            for argument in ("count 0", "count 3", "count 4", "emoji", "emoji 👍 👍", "emoji ❤ ❤️", "emoji test", "emoji 👍 ❤️ 🔥 🖤"):
                with self.assertRaises(ValueError):
                    await selfbot.handle_command(None, message(), "autoreact", argument)
            save.assert_not_called()
            save.side_effect = OSError("disk error")
            with self.assertRaises(OSError):
                await selfbot.handle_command(None, message(), "autoreact", "emoji 👍")
            self.assertEqual((state.autoreact_emojis, state.autoreact_count), original)

    async def test_only_own_new_text_and_media_trigger_reactions(self):
        state = selfbot.MonitorState(autoreact=True)
        with patch.object(selfbot, "state", state), patch.object(selfbot.auto_reactor, "react", new_callable=AsyncMock) as react:
            await selfbot.process_message(None, message(), 99)
            await selfbot.process_message(None, message(text=None, media="photo"), 99)
            self.assertEqual(react.await_count, 2)
            await selfbot.process_message(None, message(user_id=100), 99)
            self.assertEqual(react.await_count, 2)
            state.autoreact = False
            await selfbot.process_message(None, message(), 99)
            self.assertEqual(react.await_count, 2)

    async def test_command_toggle_status_and_custom_prefix(self):
        state = selfbot.MonitorState(prefix="!")
        with patch.object(selfbot, "state", state), \
             patch.object(state, "save") as save, \
             patch.object(selfbot.auto_reactor, "prepare", new_callable=AsyncMock) as prepare, \
             patch.object(selfbot, "respond", new_callable=AsyncMock) as respond:
            await selfbot.handle_command(None, message(), "autoreact", "on")
            self.assertTrue(state.autoreact)
            prepare.assert_awaited_once_with(None, refresh=True, emojis=autoreact_tools.EMOJIS)
            self.assertIn("!autoreact on|off", respond.call_args.args[1])
            await selfbot.handle_command(None, message(), "autoreact", "off")
            self.assertFalse(state.autoreact)
            self.assertEqual(save.call_count, 2)
            await selfbot.handle_command(None, message(), "autoreact", "")
            self.assertEqual(save.call_count, 2)
            self.assertIn("!autoreact", selfbot.help_text("!", "fun"))

    async def test_failed_activation_does_not_enable_or_save(self):
        state = selfbot.MonitorState()
        with patch.object(selfbot, "state", state), patch.object(state, "save") as save, \
             patch.object(selfbot.auto_reactor, "prepare", new_callable=AsyncMock, side_effect=ValueError("Emoji non disponibile")):
            with self.assertRaisesRegex(ValueError, "Emoji non disponibile"):
                await selfbot.handle_command(client_with_reactions(premium=False), message(), "autoreact", "on")
            self.assertFalse(state.autoreact)
            save.assert_not_called()


class PersistenceTests(unittest.TestCase):
    def test_emoji_configuration_survives_restart_and_invalid_values_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            with patch.object(selfbot, "STATE_FILE", state_file), patch.object(selfbot, "DATA_DIR", Path(directory)):
                state = selfbot.MonitorState(autoreact=True, autoreact_emojis=("👍", "❤️", "🔥"), autoreact_count=1)
                state.save()
                loaded = selfbot.MonitorState.load()
                self.assertEqual(loaded.autoreact_emojis, state.autoreact_emojis)
                self.assertEqual(loaded.autoreact_count, 1)
                for bad in ({"autoreact_emojis": None}, {"autoreact_emojis": [1]}, {"autoreact_count": 99}):
                    state_file.write_text(json.dumps(bad), encoding="utf-8")
                    loaded = selfbot.MonitorState.load()
                    self.assertEqual(loaded.autoreact_emojis, autoreact_tools.EMOJIS)
                    self.assertEqual(loaded.autoreact_count, 2)

    def test_default_legacy_state_and_saved_toggle(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            with patch.object(selfbot, "STATE_FILE", state_file), patch.object(selfbot, "DATA_DIR", Path(directory)):
                self.assertFalse(selfbot.MonitorState.load().autoreact)
                state_file.write_text(json.dumps({"prefix": "!", "surveillance": [1], "stalk": [2]}), encoding="utf-8")
                state = selfbot.MonitorState.load()
                self.assertFalse(state.autoreact)
                state.autoreact = True
                state.save()
                loaded = selfbot.MonitorState.load()
                self.assertTrue(loaded.autoreact)
                self.assertEqual((loaded.prefix, loaded.surveillance, loaded.stalk), ("!", {1}, {2}))


if __name__ == "__main__":
    unittest.main()
