"""Gestori dei comandi osint di Melixsa."""

from __future__ import annotations

from pyrogram.types import Message


async def handle_osint_command(message: Message, command: str, argument: str, *, client=None) -> None:
    from .. import runtime

    if command in runtime.osint_features.COMMANDS:
        async def operation(job):
            result = await runtime.osint_features.lookup(command, argument, client, message)
            job.status = "invio report"
            await runtime.osint_features.send_report(client, message, result, command, runtime.state.prefix)

        async def failed(job, exc):
            runtime.log_command_error(message, f"Ricerca #{job.id}: {exc}", title="MELIXSA / OSINT")

        requester = getattr(getattr(message, "from_user", None), "id", 0)
        job = runtime.osint_jobs.submit(command, requester, message.chat.id, operation, on_error=failed)
        try:
            ahead = sum(item.status in runtime.jobs_tools.ACTIVE for item in runtime.osint_jobs.jobs.values() if item.id < job.id)
            await runtime.respond(message, f"Ricerca #{job.id} accettata\nOperazioni davanti » {ahead}\nStato » {runtime.state.prefix}osintjobs\nAnnulla » {runtime.state.prefix}osintcancel {job.id}", title="MELIXSA / OSINT")
        except BaseException:
            runtime.osint_jobs.cancel(job.id)
            raise
        job.ready.set()
        return
    try:
        result = await runtime.asyncio.to_thread(runtime.osint_tools.run_lookup, command, argument)
    except ValueError as exc:
        runtime.log_command_error(message, exc, title=f"MELIXSA / {command.upper()}")
        return
    except Exception as exc:
        runtime.console_tools.event("Error", f"OSINT {command}: {exc}", error=True)
        return
    if command == "myip":
        sent = await message.answer(result, parse_mode=runtime.enums.ParseMode.MARKDOWN)
        if sent is not None:
            runtime.schedule_delete(sent)
        runtime.console_tools.event("Message", f"Risposta | chat={runtime.chat_name(message)} | MELIXSA / MYIP")
        return
    await runtime.respond(message, result, title=f"MELIXSA / {command.upper()}")


async def handle_jobs_command(message, command, argument):
    from .. import runtime

    restricted = runtime.shared_command_context.get()
    scope = dict(requester=getattr(getattr(message, "from_user", None), "id", 0), chat=message.chat.id) if restricted else {}
    if command == "osintcancel":
        if not argument.isascii() or not argument.isdigit():
            raise ValueError(f"Uso: {runtime.state.prefix}osintcancel <ID>")
        job = runtime.osint_jobs.cancel(int(argument), **scope)
        await runtime.respond(message, f"Annullamento richiesto per la ricerca #{job.id}. I messaggi già inviati restano in chat.", title="MELIXSA / OSINT")
        return
    if argument:
        raise ValueError(f"Uso: {runtime.state.prefix}osintjobs")
    jobs = runtime.osint_jobs.visible(**scope)
    active = [job for job in jobs if job.status in runtime.jobs_tools.ACTIVE]
    recent = sorted((job for job in jobs if job.status not in runtime.jobs_tools.ACTIVE), key=lambda job: job.finished or 0)[-5:]
    lines = [f"Ricerche attive » {len(active)}/{runtime.osint_jobs.limit}"]
    position = 0
    for job in active + recent:
        position += job.status == "in coda"
        place = f" | posizione {position}" if job.status == "in coda" else ""
        lines.append(f"#{job.id} {job.command} | {job.status} | {job.elapsed} s{place}")
    if not jobs:
        lines.append("Nessuna ricerca in questa esecuzione.")
    lines.append(f"Annulla » {runtime.state.prefix}osintcancel <ID>")
    await runtime.respond(message, "\n".join(lines), title="MELIXSA / OSINTJOBS")

