"""Ricerche OSINT su fonti pubbliche, senza dipendenze aggiuntive."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import json
import re
import socket
import ssl
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


DNS_TYPES = {"A", "AAAA", "MX", "TXT", "NS", "CNAME"}
DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "yopmail.com", "trashmail.com", "throwawaymail.com", "fakeinbox.com",
    "getnada.com", "sharklasers.com",
}
USERNAME_SITES = {
    "GitHub": "https://github.com/{user}",
    "Instagram": "https://www.instagram.com/{user}/",
    "X": "https://x.com/{user}",
    "Reddit": "https://www.reddit.com/user/{user}",
    "Telegram": "https://t.me/{user}",
    "TikTok": "https://www.tiktok.com/@{user}",
    "Pinterest": "https://www.pinterest.com/{user}/",
}


def _json_get(url: str, *, accept: str = "application/json", timeout: int = 8) -> object:
    request = Request(url, headers={"Accept": accept, "User-Agent": "Melixsa/1.0"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise ValueError("La risposta del servizio è troppo grande.")
    return json.loads(body)


def clean_domain(value: str) -> str:
    raw = value.strip()
    if not raw or any(char.isspace() for char in raw):
        raise ValueError("Indica un dominio valido, per esempio example.com.")
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        raise ValueError("Sono ammessi solo domini o URL http/https.")
    if parsed.username or parsed.password:
        raise ValueError("Indica un dominio senza credenziali.")
    try:
        domain = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Dominio non valido.") from exc
    labels = domain.split(".")
    if len(domain) > 253 or len(labels) < 2 or not all(
        1 <= len(label) <= 63 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
        for label in labels
    ):
        raise ValueError("Dominio non valido.")
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise ValueError("Indica un dominio, non un indirizzo IP.")
    return domain


def public_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError("Indica un indirizzo IPv4 o IPv6 valido.") from exc
    if not address.is_global:
        raise ValueError("Usa un indirizzo IP pubblico.")
    return str(address)


def _short(value: object, limit: int = 100) -> str:
    result = " ".join(str(value or "—").split())
    return result[:limit] + ("…" if len(result) > limit else "")


def dns_answers(domain: str, record_type: str) -> list[str]:
    record_type = record_type.upper()
    if record_type not in DNS_TYPES:
        raise ValueError("Tipo DNS: A, AAAA, MX, TXT, NS o CNAME.")
    url = "https://cloudflare-dns.com/dns-query?" + urlencode({"name": domain, "type": record_type})
    data = _json_get(url, accept="application/dns-json")
    if not isinstance(data, dict) or data.get("Status") not in {0, 3}:
        raise RuntimeError("La ricerca DNS non è disponibile.")
    return [_short(item.get("data", "")) for item in data.get("Answer", [])[:8] if isinstance(item, dict)]


def dns_lookup(argument: str) -> str:
    parts = argument.split()
    if not parts or len(parts) > 2:
        raise ValueError("Uso: dns <dominio> [A|AAAA|MX|TXT|NS|CNAME]")
    domain = clean_domain(parts[0])
    record_type = parts[1].upper() if len(parts) == 2 else "A"
    answers = dns_answers(domain, record_type)
    return f"{domain} / {record_type}\n" + ("\n".join(answers) if answers else "Nessun record")


def email_lookup(value: str) -> str:
    email = value.strip()
    if len(email) > 254 or not re.fullmatch(r"[^@\s]{1,64}@[A-Za-z0-9.-]+", email):
        raise ValueError("Indica un indirizzo email valido.")
    domain = clean_domain(email.rsplit("@", 1)[1])
    mx = dns_answers(domain, "MX")
    temporary = "sì" if domain in DISPOSABLE_DOMAINS else "non noto"
    return f"Email » {_short(email)}\nMX » {', '.join(mx[:3]) or 'nessuno'}\nTemporanea » {temporary}"


def _site_status(site: str, template: str, username: str) -> str:
    url = template.format(user=username)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=6) as response:
            code = response.status
    except HTTPError as exc:
        code = exc.code
    except (OSError, TimeoutError):
        return f"{site} » non verificato"
    if code == 404:
        return f"{site} » 404"
    return f"{site} » HTTP {code} ({url})"


def username_lookup(value: str) -> str:
    username = value.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", username) or ".." in username or username in {".", "-"}:
        raise ValueError("Username non valido: usa lettere, numeri, _, - o .")
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        results = list(pool.map(
            lambda item: _site_status(item[0], item[1], username),
            USERNAME_SITES.items(),
        ))
    return f"Username » @{username}\n" + "\n".join(results)


def rdap_lookup(value: str) -> str:
    domain = clean_domain(value)
    data = _json_get(f"https://rdap.org/domain/{domain}", timeout=10)
    if not isinstance(data, dict):
        raise RuntimeError("Risposta RDAP non valida.")
    events = {item.get("eventAction"): item.get("eventDate") for item in data.get("events", []) if isinstance(item, dict)}
    nameservers = [item.get("ldhName", "") for item in data.get("nameservers", []) if isinstance(item, dict)]
    return "\n".join([
        f"Dominio » {domain}",
        f"Creato » {_short(events.get('registration'))}",
        f"Scade » {_short(events.get('expiration'))}",
        f"Stato » {_short(', '.join(data.get('status', [])))}",
        f"NS » {_short(', '.join(nameservers[:3]))}",
    ])


def domain_lookup(value: str) -> str:
    domain = clean_domain(value)
    lines = [f"Dominio » {domain}"]
    for record_type in ("A", "NS", "TXT"):
        try:
            answers = dns_answers(domain, record_type)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            answers = []
        lines.append(f"{record_type} » {_short(', '.join(answers[:2]))}")
    try:
        data = _json_get(f"https://rdap.org/domain/{domain}", timeout=10)
        if isinstance(data, dict):
            events = {item.get("eventAction"): item.get("eventDate") for item in data.get("events", []) if isinstance(item, dict)}
            lines.append(f"Creato » {_short(events.get('registration'))}")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
        pass
    return "\n".join(lines)


def ip_lookup(value: str) -> str:
    ip = public_ip(value)
    data = _json_get(f"https://ipwho.is/{ip}")
    if not isinstance(data, dict) or not data.get("success"):
        raise RuntimeError("Ricerca IP non disponibile.")
    connection = data.get("connection") or {}
    return "\n".join([
        f"IP » {ip}",
        f"Località » {_short(', '.join(filter(None, (data.get('city'), data.get('region'), data.get('country')))))}",
        f"ISP » {_short(connection.get('isp'))}",
        f"ASN » {_short(connection.get('asn'))}",
        f"Fuso » {_short((data.get('timezone') or {}).get('id'))}",
    ])


def my_ip() -> str:
    return "**127.0.0.1**  "


def subdomain_names(domain: str) -> list[str]:
    url = "https://crt.sh/?" + urlencode({"q": f"%.{domain}", "output": "json"})
    try:
        data = _json_get(url, timeout=12)
    except HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    if not isinstance(data, list):
        raise RuntimeError("Risposta dei certificati non valida.")
    names: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        for raw in str(item.get("name_value", "")).splitlines():
            name = raw.strip().lower().removeprefix("*.")
            if name.endswith("." + domain) and len(name) <= 253:
                names.add(name)
    return sorted(names)


def subdomains_lookup(value: str) -> str:
    domain = clean_domain(value)
    names = subdomain_names(domain)
    return f"{domain} » {len(names)} sottodomini\n" + ("\n".join(names[:12]) if names else "Nessuno trovato")


def ssl_lookup(value: str) -> str:
    domain = clean_domain(value)
    addresses = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
    public_addresses = [item[4][0] for item in addresses if ipaddress.ip_address(item[4][0]).is_global]
    if not public_addresses:
        raise ValueError("Il dominio non risolve a un IP pubblico.")
    context = ssl.create_default_context()
    with socket.create_connection((public_addresses[0], 443), timeout=8) as connection:
        with context.wrap_socket(connection, server_hostname=domain) as secure:
            cert = secure.getpeercert()
    subject = dict(part[0] for part in cert.get("subject", []))
    issuer = dict(part[0] for part in cert.get("issuer", []))
    expiry = cert.get("notAfter")
    days = int((ssl.cert_time_to_seconds(expiry) - datetime.now(timezone.utc).timestamp()) // 86400) if expiry else None
    return "\n".join([
        f"Dominio » {domain}",
        f"CN » {_short(subject.get('commonName'))}",
        f"Emittente » {_short(issuer.get('organizationName'))}",
        f"Scadenza » {_short(expiry)}",
        f"Giorni » {days if days is not None else '—'}",
    ])


def harvester_lookup(value: str) -> str:
    domain = clean_domain(value)
    lines = [f"Dominio » {domain}"]
    for record_type in ("A", "MX", "NS"):
        try:
            answers = dns_answers(domain, record_type)
            lines.append(f"{record_type} » {_short(', '.join(answers[:2]))}")
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            lines.append(f"{record_type} » non disponibile")
    try:
        names = subdomain_names(domain)
        lines.append(f"Sottodomini » {len(names)}")
        lines.extend(names[:8])
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
        lines.append("Sottodomini » non disponibili")
    return "\n".join(lines)


LOOKUPS = {
    "email": email_lookup,
    "username": username_lookup,
    "domain": domain_lookup,
    "ip": ip_lookup,
    "myip": lambda _value: my_ip(),
    "dns": dns_lookup,
    "rdap": rdap_lookup,
    "ssl": ssl_lookup,
    "subdomains": subdomains_lookup,
    "harvester": harvester_lookup,
}


def run_lookup(command: str, argument: str) -> str:
    if command != "myip" and not argument.strip():
        raise ValueError(f"Indica un valore per {command}.")
    return LOOKUPS[command](argument)
