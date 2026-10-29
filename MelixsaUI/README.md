# Melixsa Desktop

Interfaccia desktop Tauri 2 + React + TypeScript per il motore Python di Melixsa.
Tema grafite e lilla, font locali, pagine modulari e impostazioni condivise con i comandi Telegram.

## Aprire subito l'anteprima

Esegui **Anteprima UI.cmd**. Serve Node.js; non serve un compilatore C++.
L'anteprima nel browser mostra il design e i moduli: connessione Telegram e salvataggi
sono disponibili nell'app desktop. Non vengono simulati salvataggi o connessioni.

## Scaricare la build da GitHub Actions

Il workflow **Build MelixsaUI (Windows)**, salvato in
`.github/workflows/build-melixsa-ui.yml`, compila la UI su un runner GitHub
**Windows x64** con gli strumenti C++ gia' disponibili.

1. Carica su GitHub le modifiche al progetto, inclusi `.github/workflows`,
   `MelixsaUI` e i lockfile `package-lock.json` e `src-tauri/Cargo.lock`.
2. Il workflow parte ai push e alle pull request che modificano la UI o il workflow.
   Per avviarlo manualmente, apri **Actions > Build MelixsaUI (Windows) > Run workflow**.
   Per vedere il pulsante manuale, il file del workflow deve essere presente nel branch predefinito.
3. Alla fine apri la run e scarica **MelixsaUI-Windows-x64** da **Artifacts**,
   oppure usa il collegamento nel riepilogo della run. L'artifact rimane disponibile per 30 giorni.
4. Estrai lo ZIP nella cartella principale di Melixsa, accanto a `Cogs`, `.venv`
   e `selfbot.py`, poi apri **Apri MelixsaUI.cmd**.

Il download contiene `melixsa-ui.exe`, il launcher, le istruzioni e l'hash SHA-256.
Per usare questa build non devi compilare nulla sul PC: servono il backend Python
del progetto gia' configurato e WebView2. La UI utilizza il `.env` e la sessione
Telegram locali. Il workflow non richiede credenziali Telegram e carica soltanto
i file di distribuzione indicati; non include un runtime Python autonomo.

## Compilare e avviare Tauri sul PC

1. Mantieni questa cartella dentro il progetto Melixsa, accanto a `Cogs`, `.venv` e `selfbot.py`.
2. Verifica che l'ambiente Python del progetto sia pronto, con `requirements.txt` installato.
3. Per compilare su Windows servono Rust, WebView2 e i **Microsoft C++ Build Tools**
   con il workload **Desktop development with C++** e Windows SDK.
   Vedi i [prerequisiti ufficiali di Tauri](https://v2.tauri.app/start/prerequisites/#windows).
4. Esegui **Avvia Melixsa.cmd**. Il primo avvio compila l'app.
5. Ferma un eventuale Melixsa avviato da `run.cmd`, poi premi **Collega Telegram** nella Home.

La sessione `data/melixsa.session` viene riutilizzata. Se non è ancora autenticata,
la UI chiede numero, codice e password a due fattori. Le credenziali API vengono lette
dal `.env` del progetto; non sono inviate al frontend. Il bridge non effettua una
registrazione di un nuovo account Telegram.

## Pagine

- **Home:** nome, username, foto profilo e ID letti da Telegram; durata della sessione;
  controlli rapidi e conteggi reali di gruppi e ricerche. Prima del collegamento viene
  mostrato lo stato scollegato. Il profilo sincronizzato viene conservato localmente
  in `data/desktop-profile.json` per le aperture successive.
- **Automazioni:** autoreact con selezione di 1–3 emoji e numero di reazioni;
  AFK e messaggio personalizzato; protezione dei nuovi accessi; notifiche degli errori.
- **Surveillance:** attivazione e arresto del monitoraggio dei gruppi; scelta dalle
  ultime 200 chat Telegram oppure tramite username/ID; elenco ricercabile e lettore
  dei registri con filtro per modifiche, ricerca testuale ed esportazione della vista.
- **Impostazioni:** prefisso, eliminazione risposte, modalità minimale, preferenze console,
  dimensione dei log, copie di backup e conservazione.
- **Attività:** ultimi 80 eventi della sessione desktop, ricerca, filtro errori ed esportazione JSON.

Le impostazioni persistenti vengono salvate atomicamente in `data/state.json` con i
meccanismi di backup esistenti. AFK vale per la sessione corrente, come nel motore Python.
Modifiche ai comandi Telegram e agli interruttori convergono sullo stesso stato; la UI si
aggiorna ogni 3 secondi. La chiusura dell'app arresta il motore e attende lo svuotamento dei log.
La modalità desktop non avvia automaticamente SoundCloud e non invia il suo pannello di
connessione nei Messaggi salvati. SoundCloud rimane disponibile tramite i comandi Telegram.

### Usare Surveillance

Collega Telegram dalla Home, apri **Surveillance** nella sidebar e usa **Carica i miei
gruppi**, oppure inserisci `@nomegruppo` o un ID negativo. Premi **Attiva Surveillance**:
il backend verifica che sia un gruppo di cui il tuo account è membro e salva il
monitoraggio nello stesso stato usato dai comandi `surveillance` e `sustop`.

Seleziona un gruppo per leggerne i registri locali, inclusi gli archivi ruotati.
La vista mostra gli ultimi 100 eventi, con un massimo di 2 MB di lettura, e si aggiorna
ogni 5 secondi. Puoi cercare nei testi e nei nomi, filtrare le modifiche ed esportare
gli eventi visualizzati in JSON. Non viene scaricato retroattivamente lo storico delle chat.

Disattivare un gruppo conserva i registri. I gruppi attivati vengono monitorati solo
mentre Telegram è connesso; i registri già presenti sono consultabili anche offline.
Durante la sessione desktop restano visibili anche i gruppi caricati o appena fermati.

## Comandi di sviluppo

Da questa cartella:

```powershell
node scripts/run.mjs install
node scripts/run.mjs dev
node scripts/run.mjs build
node scripts/run.mjs desktop
node scripts/run.mjs desktop:build
```

Il runner risolve npm accanto a Node.js e gestisce i percorsi Windows anche quando il
launcher globale npm è rimasto associato a un'installazione precedente.

`desktop:build` genera `src-tauri/target/release/melixsa-ui.exe` quando i prerequisiti sono
presenti. Questa versione usa il Python del progetto: conserva l'eseguibile dentro la
struttura del progetto oppure imposta `MELIXSA_ROOT`. Non è un installer autonomo con
Python incorporato. Le dipendenze JavaScript e Rust sono bloccate nei rispettivi lockfile.

## Struttura

```text
src/
  components/       Componenti condivisi, navigazione e login
  hooks/            Stato, sincronizzazione e operazioni
  lib/              Contratto con il bridge Tauri
  pages/            Home, Automazioni, Impostazioni, Attività
  tokens.css        Colori, font e variabili del tema
  styles.css        Layout responsive, componenti e animazioni
  types.ts          Modelli TypeScript
src-tauri/          Shell Rust, configurazione Tauri e icone
backend/bridge.py   Protocollo JSON e collegamento al runtime Python
scripts/run.mjs    Runner npm
```

Rust gestisce un solo processo Python persistente, tramite stdin/stdout JSON.
Il frontend può richiamare esclusivamente le operazioni previste; non esiste un comando
shell generico. Il processo non apre un server HTTP locale. Il lock `data/runtime.lock`
impedisce di avviare due runtime aggiornati sulla stessa sessione e di modificare lo
stato offline mentre un altro runtime lo sta usando.

## Verifiche

Dalla cartella principale di Melixsa:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

I test del bridge coprono validazione, salvataggio, rollback, preservazione degli accessi,
concorrenza fra processi, AFK, profilo Telegram e isolamento del protocollo. Usano directory
temporanee e client simulati; non collegano l'account reale.

La build del frontend e il collaudo visivo sono stati eseguiti. La compilazione nativa
locale richiede il linker MSVC (`link.exe`), assente su questo computer. Il workflow
permette di eseguirla su GitHub senza installare nuovi compilatori sul PC.
La prima run remota va verificata dopo aver caricato il progetto su GitHub.
Nome e foto reali verranno caricati al primo collegamento dall'app desktop.
