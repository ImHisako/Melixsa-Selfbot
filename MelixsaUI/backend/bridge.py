"""Protocollo JSON su stdio. Il motore Telegram rimane nel suo event loop asyncio."""
from __future__ import annotations

import asyncio
import base64
from collections import deque
from dataclasses import asdict
from datetime import datetime
import io
import json
import logging
from pathlib import Path
import sys
import time

PROTOCOL = sys.stdout
if __name__ == "__main__":
    sys.stdout = sys.stderr

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Cogs.core import autoreact_tools, config_tools, console_tools, persistence_tools, runtime
from Cogs.core.instance_tools import InstanceLock
from MelixsaUI.backend.surveillance import SurveillanceService


class ActivityHandler(logging.Handler):
    def __init__(self, bridge):
        super().__init__(logging.INFO)
        self.bridge = bridge

    def emit(self, record):
        if record.name == "melixsa":
            self.bridge.record(
                console_tools.clean(record.getMessage()),
                getattr(record, "category", "Melixsa"),
                "error" if record.levelno >= logging.ERROR else "info",
            )


class DesktopBridge:
    def __init__(self):
        self.client = None
        self.login_client = None
        self.login_lock = None
        self.phone = ""
        self.phone_code_hash = ""
        self.task = None
        self.stop_event = asyncio.Event()
        self.connection = "offline"
        self.started = None
        self.last_error = ""
        self.events = deque(maxlen=80)
        self.sequence = 0
        self.profile_path = runtime.DATA_DIR / "desktop-profile.json"
        self.profile = None
        self.surveillance = SurveillanceService(self)
        self.handler = ActivityHandler(self)
        console_tools.logger.addHandler(self.handler)
        try:
            cached = json.loads(self.profile_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and isinstance(cached.get("name"), str):
                self.profile = {key: cached.get(key) for key in ("id", "name", "username", "photo", "premium")}
        except (OSError, ValueError, TypeError):
            pass
        self.record("Il tuo spazio è pronto. Collega Telegram per avviare Melixsa.", "Desktop")

    def record(self, message, category="Desktop", level="info"):
        self.sequence += 1
        self.events.append({
            "id": self.sequence,
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "category": category,
            "message": message[:500],
            "level": level,
        })

    def snapshot(self):
        if self.connection not in {"connected", "connecting"}:
            runtime.state = runtime.MonitorState.load()
        saved = asdict(runtime.state)
        keys = ("prefix", "delete_after", "autoreact", "autoreact_emojis", "autoreact_count",
                "minimal_mode", "anti_login_enabled", "error_notify", "log_max_bytes",
                "log_backups", "log_retention_days", "console")
        return {
            "settings": {key: saved[key] for key in keys},
            "afk": {"enabled": runtime.afk.active, "message": runtime.afk.message},
            "profile": self.profile,
            "connection": self.connection,
            "last_error": self.last_error,
            "session_available": (runtime.DATA_DIR / "melixsa.session").is_file(),
            "credentials_available": self.credentials_available(),
            "uptime": int(time.monotonic() - self.started) if self.started else 0,
            "stats": {
                "groups": len(runtime.state.surveillance),
                "users": len(runtime.state.stalk),
                "commands": len(runtime.COMMANDS - runtime.CATEGORY_COMMANDS),
                "jobs": sum(job.status in runtime.jobs_tools.ACTIVE for job in runtime.osint_jobs.jobs.values()),
            },
            "events": list(reversed(self.events)),
        }

    @staticmethod
    def credentials_available():
        import os
        try:
            saved = config_tools.read_values((ROOT / ".env").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            saved = {}
        return all(os.environ.get(key) or saved.get(key) for key in config_tools.CREDENTIAL_KEYS)

    async def update_settings(self, values):
        if self.connection in {"connecting", "login_phone", "login_code", "login_password"}:
            raise ValueError("Completa o annulla il collegamento prima di modificare le impostazioni.")
        if self.connection == "connected":
            return await self._update_settings(values)
        # Read, validate and save under the same cross-process lock.
        with InstanceLock(runtime.DATA_DIR / "runtime.lock"):
            runtime.state = runtime.MonitorState.load()
            return await self._update_settings(values)

    async def _update_settings(self, values):
        if not isinstance(values, dict) or not values:
            raise ValueError("Nessuna impostazione da aggiornare.")
        booleans = {"autoreact", "minimal_mode", "anti_login_enabled", "error_notify"}
        integers = {"delete_after": (0, 3600), "autoreact_count": (1, 3),
                    "log_max_bytes": (65536, 1_000_000_000), "log_backups": (1, 100),
                    "log_retention_days": (0, 3650)}
        allowed = booleans | set(integers) | {"prefix", "autoreact_emojis", "console", "afk"}
        if set(values) - allowed:
            raise ValueError("Impostazione non riconosciuta.")
        patch = {}
        for key, value in values.items():
            if key in booleans:
                if type(value) is not bool:
                    raise ValueError("Il valore deve essere un booleano.")
            elif key in integers:
                low, high = integers[key]
                if type(value) is not int or not low <= value <= high:
                    raise ValueError(f"{key}: scegli un numero da {low} a {high}.")
            elif key == "prefix":
                if not runtime.valid_prefix(value):
                    raise ValueError("Il prefisso deve essere un singolo simbolo, per esempio / oppure !.")
            elif key == "autoreact_emojis":
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    raise ValueError("Elenco emoji non valido.")
                value = autoreact_tools.parse_emojis(" ".join(value))
            elif key == "console":
                if not isinstance(value, dict) or set(value) - set(console_tools.CONSOLE_DEFAULTS) or any(type(item) is not bool for item in value.values()):
                    raise ValueError("Preferenze console non valide.")
                value = {**runtime.state.console, **value}
            elif key == "afk":
                if self.connection != "connected":
                    raise ValueError("Collega Telegram per configurare AFK nella sessione corrente.")
                if not isinstance(value, dict) or set(value) - {"enabled", "message"} or type(value.get("enabled")) is not bool:
                    raise ValueError("Configurazione AFK non valida.")
                text = value.get("message", runtime.afk.message)
                if not isinstance(text, str) or len(text.encode("utf-16-le")) // 2 > 3000:
                    raise ValueError("Messaggio AFK: massimo 3000 caratteri UTF-16.")
                continue
            patch[key] = value
        emojis = patch.get("autoreact_emojis", runtime.state.autoreact_emojis)
        if "autoreact_count" in patch and patch["autoreact_count"] > len(emojis):
            raise ValueError("Il numero di reazioni supera le emoji selezionate.")
        if "autoreact_emojis" in patch:
            patch.setdefault("autoreact_count", min(runtime.state.autoreact_count, len(emojis)))
        async def save():
            async with runtime.state_transaction():
                for key, value in patch.items():
                    setattr(runtime.state, key, value)
        await save()
        if "afk" in values:
            afk = values["afk"]
            if afk["enabled"]:
                runtime.afk.enable(afk.get("message", runtime.afk.message))
            else:
                runtime.afk.disable()
                if "message" in afk:
                    runtime.afk.message = afk["message"] or runtime.afk_tools.DEFAULT_MESSAGE
        console_tools.configure(runtime.state.console)
        if "anti_login_enabled" in patch:
            runtime.anti_login.wakeup.set()
        self.record("Impostazioni aggiornate e salvate.", "Impostazioni")
        return self.snapshot()

    async def refresh_profile(self, me=None):
        if self.client is None:
            raise ValueError("Collega Telegram per aggiornare il profilo.")
        me = me or await self.client.get_me()
        photo = None
        if me.photo:
            try:
                stream = await self.client.download_media(me.photo.small_file_id, in_memory=True)
                if isinstance(stream, io.BytesIO) and stream.getbuffer().nbytes <= 2_000_000:
                    photo = "data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
            except Exception:
                self.record("Foto profilo non disponibile; puoi riprovare ad aggiornarla.", "Profilo")
        self.profile = {
            "id": me.id, "name": " ".join(filter(None, (me.first_name, me.last_name))) or "Il tuo account",
            "username": me.username or "", "photo": photo, "premium": bool(getattr(me, "is_premium", False)),
        }
        try:
            await asyncio.to_thread(persistence_tools.atomic_write, self.profile_path, json.dumps(self.profile, ensure_ascii=False))
        except OSError:
            self.record("Profilo aggiornato. Impossibile salvare la cache locale.", "Profilo")
        return self.snapshot()

    async def on_ready(self, client, me):
        self.client = client
        self.connection = "connected"
        self.started = time.monotonic()
        self.last_error = ""
        self.record("Telegram collegato. Melixsa è attiva.", "Connessione")
        await self.refresh_profile(me)

    async def run_runtime(self):
        try:
            await runtime.main(control=self)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = console_tools.clean(str(exc))[:300]
            self.record(self.last_error, "Connessione", "error")
            self.connection = "error"
        finally:
            self.client = None
            self.started = None
            runtime.afk.disable()
            if self.connection != "error":
                self.connection = "offline"

    async def connect(self):
        if self.task and not self.task.done():
            return self.snapshot()
        if self.login_client:
            return self.snapshot()
        self.login_lock = InstanceLock(runtime.DATA_DIR / "runtime.lock")
        self.login_lock.__enter__()
        try:
            api_id, api_hash = config_tools.load_credentials(ROOT / ".env")
            # Configure redaction before any Telegram request can generate a log.
            console_tools.setup(runtime.LOG_DIR, secrets=(api_hash,))
            from pyrogram import Client
            self.login_client = Client("melixsa", api_id=api_id, api_hash=api_hash, workdir=str(runtime.DATA_DIR))
            self.connection = "connecting"
            authorized = await self.login_client.connect()
            if authorized:
                await self.start_runtime()
            else:
                self.connection = "login_phone"
        except BaseException:
            await self.close_login()
            self.connection = "offline"
            raise
        return self.snapshot()

    async def close_login(self):
        try:
            if self.login_client and self.login_client.is_connected:
                await self.login_client.disconnect()
        finally:
            self.login_client = None
            if self.login_lock:
                self.login_lock.__exit__(None, None, None)
                self.login_lock = None
            self.phone = self.phone_code_hash = ""

    async def start_runtime(self):
        await self.close_login()
        runtime.state = runtime.MonitorState.load()
        self.stop_event = asyncio.Event()
        self.connection = "connecting"
        self.task = asyncio.create_task(self.run_runtime(), name="melixsa-desktop")

    async def login_phone(self, params):
        if self.connection != "login_phone" or not self.login_client:
            raise ValueError("Apri prima la connessione Telegram.")
        phone = params.get("phone", "").strip()
        if not phone.startswith("+") or not phone[1:].isdigit() or not 7 <= len(phone) <= 17:
            raise ValueError("Inserisci il numero completo di prefisso internazionale, per esempio +39…")
        sent = await self.login_client.send_code(phone)
        self.phone, self.phone_code_hash = phone, sent.phone_code_hash
        self.connection = "login_code"
        return self.snapshot()

    async def login_code(self, params):
        if self.connection != "login_code" or not self.login_client:
            raise ValueError("Richiedi prima il codice Telegram.")
        from pyrogram.errors import SessionPasswordNeeded
        try:
            user = await self.login_client.sign_in(self.phone, self.phone_code_hash, params.get("code", "").strip())
            if not getattr(user, "id", None):
                raise ValueError("Usa un account Telegram già registrato.")
        except SessionPasswordNeeded:
            self.connection = "login_password"
        else:
            await self.start_runtime()
        return self.snapshot()

    async def login_password(self, params):
        if self.connection != "login_password" or not self.login_client:
            raise ValueError("La sessione non richiede una password.")
        await self.login_client.check_password(params.get("password", ""))
        await self.start_runtime()
        return self.snapshot()

    async def disconnect(self):
        await self.close_login()
        if self.task and not self.task.done():
            self.stop_event.set()
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=10)
            except asyncio.TimeoutError:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
        runtime.afk.disable()
        self.connection = "offline"
        self.last_error = ""
        self.record("Melixsa arrestata. La sessione Telegram resta salvata.", "Connessione")
        return self.snapshot()

    async def dispatch(self, method, params):
        if not isinstance(params, dict):
            raise ValueError("Parametri non validi.")
        if method == "surveillance_overview":
            return await self.surveillance.overview()
        if method == "surveillance_chats":
            return await self.surveillance.chats()
        if method == "surveillance_set":
            return await self.surveillance.set_enabled(params)
        if method == "surveillance_logs":
            return await self.surveillance.logs(params)
        if method == "snapshot":
            return self.snapshot()
        if method == "update_settings":
            return await self.update_settings(params)
        if method == "refresh_profile":
            return await self.refresh_profile()
        if method in {"login_phone", "login_code", "login_password"}:
            return await getattr(self, method)(params)
        if method == "connect":
            return await self.connect()
        if method in {"disconnect", "shutdown"}:
            return await self.disconnect()
        raise ValueError("Operazione non disponibile.")

    async def close(self):
        try:
            await self.disconnect()
        finally:
            console_tools.logger.removeHandler(self.handler)


async def serve():
    protocol = PROTOCOL
    # Only protocol JSON goes to stdout; banners and third-party prints go to stderr.
    sys.stdout = sys.stderr
    bridge = DesktopBridge()
    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            method = ""
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("Richiesta non valida.")
                method = request.get("method", "")
                result = await bridge.dispatch(method, request.get("params", {}))
                response = {"result": result}
            except Exception as exc:
                # Telegram error text can contain login arguments. Return only its public type.
                if type(exc).__module__.startswith("pyrogram"):
                    message = f"Telegram: {type(exc).__name__}. Controlla i dati e riprova."
                else:
                    message = console_tools.clean(str(exc))[:400]
                response = {"error": message}
            protocol.write(json.dumps(response, ensure_ascii=True) + "\n")
            protocol.flush()
            if method == "shutdown":
                break
    finally:
        await bridge.close()


if __name__ == "__main__":
    # Import warnings from Kurigram must also stay outside the protocol stream.
    asyncio.run(serve())
