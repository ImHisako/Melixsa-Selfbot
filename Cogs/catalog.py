"""Catalogo centrale: categorie, sintassi, help e alias dei comandi."""

from . import luna_tools, osint_features, osint_tools, soundcloud_tools

HELP_CATEGORIES = {
    "abuse": (
        ("spam", "<testo> <numero> <secondi>", "Invia messaggi con suffisso casuale"),
        ("spamstop", "", "Ferma gli invii nella chat corrente"),
    ),
    "admin": (
        ("chatinfo", "", "Info gruppo"),
        ("whois", "[utente]", "Info utente"),
    ),
    "animated": (),
    "fun": (
        ("autoreact", "[on|off|emoji|count]", "Configura reazioni automatiche"),
    ),
    "settings": (
        ("doctor", "", "Diagnostica servizi, configurazione ed errori"),
        ("errornotify", "[on|off]", "Avvisi brevi nei Messaggi salvati"),
        ("logconfig", "[size|backups|days valore]", "Rotazione e conservazione log"),
        ("access", "", "Menu permessi per altre persone"),
        ("status", "", "Monitor attivi"),
        ("prefix", "[simbolo]", "Cambia prefisso"),
        ("deleteafter", "[secondi]", "Timer risposte"),
        ("help", "[voce]", "Menu comandi"),
    ),
    "mass surveillance": (
        ("surveillance", "", "Avvia log gruppo"),
        ("sustop", "", "Ferma log gruppo"),
        ("stalk", "[utente]", "Segui utente"),
        ("unstalk", "[utente]", "Ferma utente"),
        ("monitorlist", "", "Elenca persone e gruppi osservati"),
        ("stalklist", "", "Elenca persone seguite"),
        ("sulist", "", "Elenca gruppi monitorati"),
    ),
    "osint": (
        ("osintjobs", "", "Stato e coda delle ricerche estese"),
        ("osintcancel", "<ID>", "Annulla una ricerca estesa"),
        ("geosint", "[in risposta]", "Analizza foto, video o URL"),
        ("email", "<email>", "Dominio e MX"),
        ("username", "<nome>", "Profili pubblici"),
        ("domain", "<dominio>", "DNS e RDAP"),
        ("ip", "<indirizzo>", "Info IP pubblico"),
        ("myip", "", "Mostra sempre 127.0.0.1"),
        ("dns", "<dominio> [tipo]", "Record DNS"),
        ("rdap", "<dominio>", "Registro dominio"),
        ("ssl", "<dominio>", "Certificato TLS"),
        ("subdomains", "<dominio>", "Sottodomini CT"),
        ("harvester", "<dominio>", "Riepilogo dominio"),
    ),
    "soundcloud": (
        ("sclyrics", "[on|off|status]", "Lyrics riga per riga in chat"),
        ("scnp", "", "Brano corrente"),
        ("scplay", "", "Riprendi canzone"),
        ("scpause", "", "Metti in pausa"),
        ("sctoggle", "", "Play / pausa"),
        ("scnext", "", "Canzone successiva"),
        ("scprev", "", "Canzone precedente"),
        ("scvolume", "[0-100]", "Mostra / cambia volume"),
        ("scseek", "<secondi|mm:ss>", "Cambia posizione"),
        ("screpeat", "<off|all|one>", "Ripetizione"),
        ("scshuffle", "[on|off|toggle]", "Riproduzione casuale"),
        ("sclike", "[on|off|toggle]", "Like al brano"),
        ("scplayers", "", "Schede SoundCloud"),
        ("scselect", "<ID|auto>", "Scegli scheda"),
        ("scconnect", "", "Collegamento WebNowPlaying"),
    ),
}
HELP_CATEGORY_ALIASES = {"mass": "mass surveillance", "masssurveillance": "mass surveillance", "sc": "soundcloud"}
HELP_DETAILS = {
    "doctor": "Diagnostica locale senza richieste ai servizi esterni: Telegram, configurazione, backup, log, ricerche, SoundCloud, lyrics, AFK, anti-login e ultimi errori. Riservato al proprietario. Non mostra credenziali.",
    "errornotify": "on/off abilita avvisi generici nei Messaggi salvati, al massimo uno al minuto. Off inizialmente. Nessun testo cercato o contenuto degli errori viene inviato negli avvisi.",
    "logconfig": "Senza argomenti mostra i limiti. size <byte> (65536-1000000000), backups <numero> (1-100), days <giorni> (0-3650). days 0 disattiva la scadenza temporale degli archivi chiusi. Limiti applicati anche agli archivi esistenti; i file pending di recupero sono esclusi.",
    "osintjobs": "Elenca ricerche estese attive e ultime cinque terminate, con ID, stato, tempo e posizione in coda. Il proprietario vede tutte; gli altri solo le proprie nella chat corrente. Coda massima di 10 operazioni, una alla volta. Le ricerche non ripartono dopo un riavvio.",
    "osintcancel": "Annulla una ricerca estesa in coda o in corso, usando l'ID di osintjobs. Il proprietario può fermarle tutte; gli altri solo le proprie nella chat corrente. I messaggi già inviati restano in chat.",
    "spam": "Testo con spazi; gli ultimi due valori sono numero (1-100) e intervallo (0-3600 secondi, anche decimali). Esempio: >spam ciao a tutti 5 0. Ogni messaggio termina con | e 5 caratteri casuali. Una sequenza per chat, nello stesso topic; messaggi conservati. Si ferma se Telegram richiede una pausa o rifiuta un invio.",
    "spamstop": "Ferma la sequenza nella chat corrente. Gli invii non ripartono al riavvio.",
    "access": "add/remove autorizza utenti; allow/block gestisce comandi e categorie. Di base esclusi settings, abuse, soundcloud e misc, con help incluso. Settings e abuse restano riservati al proprietario. Menu e help mostrano solo le categorie e i comandi abilitati. Permessi salvati per i riavvii.",
    "sclyrics": "on cerca su LRCLIB e invia le righe sincronizzate nella chat corrente; off ferma ovunque. Senza argomento mostra lo stato. Una sola chat attiva, non riparte al riavvio.",
    "geosint": "Rispondi a una foto, video o URL del media",
    "autoreact": "on/off attiva o ferma. sceglie fino a 3 emoji separate da spazi; count 1|2|3 usa le prime N della lista.",
    "surveillance": "Solo gruppi; registra i nuovi messaggi.",
    "sustop": "Solo gruppi; ferma la registrazione.",
    "chatinfo": "Solo gruppi; mostra ID, username e membri.",
    "stalk": "@username, ID o risposta; segue nei gruppi visibili.",
    "unstalk": "@username, ID o risposta; ferma il monitoraggio.",
    "monitorlist": "Mostra persone seguite con stalk e gruppi con surveillance: nomi, username e ID. Funziona anche in privato e nei Messaggi salvati. Gli elementi non più accessibili restano elencati con il loro ID.",
    "stalklist": "Mostra tutte le persone seguite con stalk, con nome, username e ID.",
    "sulist": "Mostra tutti i gruppi con surveillance attiva, con titolo, username e ID.",
    "whois": "@username, ID o risposta; mostra dati pubblici.",
    "status": "Mostra prefisso, timer e monitoraggi.",
    "prefix": "Un simbolo; /prefix / ripristina il prefisso.",
    "deleteafter": "Timer delle risposte: 0 disattiva; massimo 3600 secondi. I comandi vengono cancellati subito.",
    "help": "Apri una categoria o un comando. Alias: h, ?.",
    "email": "Controlla MX e dominio temporaneo noto.",
    "username": "Controlla le pagine pubbliche; HTTP 200 non prova che il profilo esista.",
    "domain": "Riepilogo DNS pubblico e data di registrazione RDAP.",
    "ip": "Geolocalizzazione approssimativa di un IP pubblico.",
    "myip": "Risponde sempre con 127.0.0.1 in grassetto.",
    "dns": "Tipi: A, AAAA, MX, TXT, NS, CNAME. Predefinito: A.",
    "rdap": "Mostra date, stato e nameserver pubblici.",
    "ssl": "Mostra il certificato TLS pubblico sulla porta 443.",
    "subdomains": "Legge nomi dai certificati pubblici di crt.sh.",
    "harvester": "Riepiloga DNS e sottodomini da fonti pubbliche.",
    "scnp": "Brano, artista, album, stato, tempo e volume del player SoundCloud selezionato.",
    "scplay": "Riprende il brano nella scheda SoundCloud collegata tramite WebNowPlaying.",
    "scpause": "Mette in pausa il brano nella scheda SoundCloud collegata.",
    "sctoggle": "Alterna play e pausa nella scheda SoundCloud collegata.",
    "scnext": "Passa al prossimo brano della coda SoundCloud, se disponibile.",
    "scprev": "Passa al brano precedente della coda SoundCloud, se disponibile.",
    "scvolume": "Senza valore mostra il volume; con un intero da 0 a 100 lo cambia.",
    "scseek": "Accetta secondi, mm:ss o hh:mm:ss entro la durata del brano.",
    "screpeat": "off disattiva, all ripete la coda, one ripete il brano.",
    "scshuffle": "on attiva, off disattiva; senza argomento alterna lo stato.",
    "sclike": "on aggiunge il like, off lo rimuove; senza argomento alterna. Richiede accesso a SoundCloud.",
    "scplayers": "Elenca solo i player SoundCloud; * indica la scheda controllata.",
    "scselect": "Sceglie un ID da scplayers; auto segue il player SoundCloud più attivo. Se la scheda si chiude torna automatico.",
    "scconnect": "Mostra porta e istruzioni per il Custom Adapter di WebNowPlaying sullo stesso PC del selfbot.",
}
for _category, _entries in luna_tools.CATEGORIES.items():
    HELP_CATEGORIES[_category] = HELP_CATEGORIES.get(_category, ()) + _entries
    for _name, _usage, _description in _entries:
        HELP_DETAILS[_name] = f"{_description}. Usa il prefisso corrente. Testo: argomento oppure messaggio in risposta."
HELP_CATEGORIES["settings"] += (("console", "", "Mostra banner e impostazioni console"),
                                ("clear", "", "Pulisce la console"),
                                ("debug-mode", "[on|off]", "Mostra o nasconde dettagli tecnici"),
                                ("anti-login", "[on|off|status]", "Protegge dai nuovi accessi Telegram"),
                                ("minimal-mode", "[on|off]", "Menu senza descrizioni"),
                                ("timestamp", "<on|off>", "Orario nei log console"),
                                ("spacers", "<on|off>", "Separatori nei log console"),
                                ("pgradient", "<on|off>", "Colori nei log console"),
                                ("lgradient", "<on|off>", "Colori del banner"))
for _name in ("console", "timestamp", "spacers", "pgradient", "lgradient"):
    HELP_DETAILS[_name] = "Impostazioni della console salvate per i riavvii. NO_COLOR disattiva i colori."
HELP_DETAILS["clear"] = "Pulisce la console sul computer dove gira Melixsa. Non richiede argomenti."
HELP_DETAILS["anti-login"] = "Invalidazione dei codici ricevuti da Telegram e controllo delle nuove sessioni ogni 30 s. on/off/status; alias enable/disable. Le sessioni presenti all'avvio sono autorizzate. On inizialmente, impostazione salvata. Può bloccare anche i tuoi nuovi dispositivi."
HELP_DETAILS["debug-mode"] = "Senza argomento mostra lo stato. on mostra connessioni Telegram, task e dettagli WebNowPlaying; off li nasconde. Inizialmente off, salvato per i riavvii."
HELP_DETAILS["minimal-mode"] = "on mostra nei menu solo comandi e sintassi, senza » e spiegazioni; off ripristina i dettagli. Senza argomento mostra lo stato. Inizialmente off, salvato per i riavvii."
HELP_CATEGORIES["misc"] += HELP_CATEGORIES.pop("profile") + (
    ("afk", "[messaggio]", "Attiva risposte AFK nelle chat private"),
    ("back", "", "Disattiva AFK e mostra durata"),
    ("afkstatus", "", "Mostra stato e messaggio AFK"),
)
HELP_DETAILS["afk"] = "Attiva AFK con messaggio opzionale e GIF. Solo chat private, una risposta per persona ogni 6 ore. Ripetere afk cambia messaggio e azzera durata e destinatari. Al riavvio è off."
HELP_DETAILS["back"] = "Disattiva AFK e mostra la durata dell'assenza. Alias: unafk. I normali messaggi in uscita non disattivano AFK."
HELP_DETAILS["afkstatus"] = "Mostra stato, durata, messaggio e ultimo problema di AFK."
luna_tools.ALIASES["unafk"] = "back"
luna_tools.ALIASES["antilogin"] = "anti-login"
HELP_CATEGORY_ALIASES["profile"] = "misc"
HELP_CATEGORIES = {category: HELP_CATEGORIES[category] for category in (
    "admin", "abuse", "animated", "fun", "text", "misc", "mass surveillance",
    "tools", "osint", "soundcloud", "settings",
)}
CATEGORY_COMMANDS = set(HELP_CATEGORIES) | set(HELP_CATEGORY_ALIASES)
HELP_CATEGORIES["osint"] += (
    ("phone", "<+numero|regione numero>", "Numero, paese, operatore e formati"),
    ("namesearch", "<nome cognome>", "Varianti username e ricerche pubbliche"),
    ("breach", "<email>", "Breach noti, senza password"),
    ("telegram", "<@username|t.me/...>", "Profilo Telegram pubblico"),
    ("dorks", "<testo>", "Query di ricerca avanzata"),
    ("imageosint", "[in risposta]", "Ricerca inversa ed EXIF del file"),
    ("exif", "[in risposta]", "Metadati e GPS dell'immagine"),
    ("forwardinfo", "[in risposta]", "Autore visibile dell'inoltro"),
    ("autoosint", "[valore o risposta]", "Rileva il tipo e avvia la ricerca"),
    ("osintall", "<valore>", "Ricerche correlate per il valore"),
)
for _name, _usage, _description in HELP_CATEGORIES["osint"]:
    if _name in osint_features.COMMANDS:
        HELP_DETAILS[_name] = f"{_description}. Report da AbelXeon/OSINT-BOT, con link e allegati quando disponibili."
HELP_DETAILS["username"] = "Scansione asincrona del dataset WhatsMyName con indicatori delle pagine. Possibili falsi positivi; report completo TXT."
HELP_DETAILS["dick"] = "Rispondi a un messaggio oppure indica @username o ID. Mostra un disegno 8=D, con da 1 a 13 simboli =."
HELP_DETAILS["boobs"] = "Rispondi a un messaggio oppure indica @username o ID. Mostra due disegni (.) (.), con da 0 a 13 spazi su ciascun lato del punto. Gli spazi vengono conservati."
HELP_DETAILS["email"] = "MX, Gravatar pubblico, registrazioni rilevate da holehe e breach noti XposedOrNot. Nessuna password restituita."
HELP_DETAILS["domain"] = "WHOIS, DNS, SPF/DMARC e sottodomini pubblicati nei certificati, con link di approfondimento."
HELP_DETAILS["ip"] = "Solo IP pubblici: geolocalizzazione approssimativa e dati già indicizzati da Shodan InternetDB. Nessuna scansione attiva delle porte."
OSINT_COMMANDS = set(osint_tools.LOOKUPS) | osint_features.COMMANDS
SOUNDCLOUD_COMMANDS = soundcloud_tools.COMMANDS
COMMANDS = {name for entries in HELP_CATEGORIES.values() for name, _, _ in entries} | {"h", "?"} | CATEGORY_COMMANDS | set(luna_tools.ALIASES)
MAX_DELETE_AFTER = 3600
