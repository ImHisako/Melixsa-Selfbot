"""Controlli desktop dello stalk esistente e lettura dei relativi registri locali."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re

from Cogs.core import runtime
from Cogs.core.instance_tools import InstanceLock
from MelixsaUI.backend.surveillance import MAX_RECORDS, log_files, read_records, text


LOG_NAME = re.compile(r"stalk_([1-9][0-9]*)\.txt(?:\.([0-9]+))?\Z")


def user_id(value) -> int:
    if type(value) is int:
        result = value
    elif isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,18}", value):
        result = int(value)
    else:
        raise ValueError("Inserisci un ID utente positivo valido oppure @username.")
    if not 0 < result < 2**63:
        raise ValueError("ID utente non valido.")
    return result


def stalk_files():
    return log_files(runtime.LOG_DIR, pattern=LOG_NAME, parse_id=user_id)


class StalkService:
    def __init__(self, bridge):
        self.bridge = bridge
        self.metadata = {}
        self.log_labels = {}

    @property
    def connected(self):
        return self.bridge.connection == "connected" and self.bridge.client is not None

    async def active_ids(self):
        if self.bridge.connection not in {"connected", "connecting"}:
            runtime.state = runtime.MonitorState.load()
        async with runtime.state_lock:
            return set(runtime.state.stalk)

    async def overview(self):
        active = await self.active_ids()
        return await asyncio.to_thread(self._overview, active)

    def _overview(self, active):
        files = stalk_files()
        users = []
        for target in active | set(files) | set(self.metadata):
            logs = files.get(target, [])
            last_update = max((item[2].st_mtime for item in logs), default=0)
            if logs and self.log_labels.get(target, (None, {}))[0] != last_update:
                latest = read_records(logs, target, identity_field="user_id", limit=1, budget=65536)["records"]
                self.log_labels[target] = (last_update, latest[0] if latest else {})
            record = self.log_labels.get(target, (None, {}))[1]
            metadata = self.metadata.get(target, {})
            users.append({
                "id": str(target), "name": metadata.get("name") or record.get("sender") or "",
                "username": metadata.get("username", record.get("username", "")),
                "enabled": target in active,
                "log_bytes": sum(item[2].st_size for item in logs), "log_files": len(logs),
                "last_update": datetime.fromtimestamp(last_update, timezone.utc).isoformat() if last_update else None,
            })
        users.sort(key=lambda item: (not item["enabled"], item["name"].casefold(), item["id"]))
        return {"users": users, "active_count": len(active), "log_bytes": sum(item["log_bytes"] for item in users)}

    async def set_enabled(self, params):
        enabled = params.get("enabled")
        if type(enabled) is not bool:
            raise ValueError("Indica se attivare o fermare il monitoraggio.")
        if self.bridge.connection in {"connecting", "login_phone", "login_code", "login_password"}:
            raise ValueError("Completa o annulla il collegamento prima di modificare Stalk.")
        query = params.get("user")
        if enabled:
            if not self.connected:
                raise ValueError("Collega Telegram per attivare Stalk.")
            if isinstance(query, str) and re.fullmatch(r"@[A-Za-z0-9_]{1,32}", query.strip()):
                target = query.strip()
            else:
                target = user_id(query)
            try:
                user = await asyncio.wait_for(self.bridge.client.get_users(target), timeout=15)
            except asyncio.TimeoutError as exc:
                raise ValueError("Telegram non ha risposto. Riprova ad aggiungere l’utente.") from exc
            target_id = user_id(user.id)
            if getattr(user, "is_self", False):
                raise ValueError("Melixsa non registra i messaggi del proprio account.")
            if getattr(user, "is_deleted", False):
                raise ValueError("Questo account Telegram è stato eliminato.")
            metadata = {
                "name": text(" ".join(filter(None, (user.first_name, user.last_name)))),
                "username": text(user.username, 64),
            }
        else:
            target_id = user_id(query)
            metadata = self.metadata.get(target_id, {})

        async def save():
            async with runtime.state_transaction():
                if enabled:
                    runtime.state.stalk.add(target_id)
                else:
                    runtime.state.stalk.discard(target_id)

        if self.bridge.connection == "connected":
            await save()
        else:
            with InstanceLock(runtime.DATA_DIR / "runtime.lock"):
                runtime.state = runtime.MonitorState.load()
                await save()
        # Keep stopped users visible for this desktop session, even without log files.
        self.metadata[target_id] = metadata
        action = "attivato" if enabled else "fermato"
        self.bridge.record(f"Monitoraggio Stalk dell’utente {target_id} {action}.", "Stalk")
        return {**await self.overview(), "changed_id": str(target_id)}

    async def logs(self, params):
        target = user_id(params.get("user_id"))
        active = await self.active_ids()
        return await asyncio.to_thread(self._logs, target, active)

    def _logs(self, target, active):
        files = stalk_files()
        if target not in active and target not in files and target not in self.metadata:
            raise ValueError("Questo utente non è presente in Stalk.")
        result = read_records(files.get(target, []), target, identity_field="user_id")
        return {"user_id": str(target), "limit": MAX_RECORDS, **result}
