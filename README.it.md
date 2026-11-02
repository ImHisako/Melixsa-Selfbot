# Melixsa Selfbot

[English](README.md) · **Italiano**

Client Telegram per il tuo account personale, con interfaccia desktop Windows e comandi utilizzabili in Telegram. Include chat, stili Unicode, automazioni, monitoraggio dei gruppi, ricerche su fonti pubbliche e controlli SoundCloud.

**Su Android:** segui la [guida Termux](docs/TERMUX.md) per installare e usare il motore da terminale. La procedura Windows qui sotto riguarda il PC.

## Installazione Windows

Servono **Python 3.10 o successivo**, un account Telegram e il tuo API ID e API hash ottenuti da [my.telegram.org](https://my.telegram.org). Per l’app desktop servono anche **Windows x64 e Microsoft Edge WebView2 Runtime**.

La build desktop pronta usa l’ambiente Python del progetto. **Per eseguirla non servono Node.js, Rust o i Build Tools C++.**

### 1. Prepara il progetto

Scarica o clona il codice sorgente ed estrailo in una cartella. Apri **PowerShell in quella cartella**, dove si trovano `run.cmd` e `requirements.txt`, ed esegui:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Questo passaggio si fa una volta per computer. Puoi usare direttamente l’ambiente: non serve attivarlo con altri comandi.

### 2. Inserisci le credenziali Telegram

Nella stessa finestra PowerShell:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
notepad .env
```

Sostituisci i due valori di esempio con le tue credenziali e salva:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_with_your_api_hash
```

L’ID è numerico; l’hash contiene 32 caratteri esadecimali. Gli altri campi del `.env` sono facoltativi. Il comando di copia conserva un `.env` già presente. Melixsa usa il tuo account personale: non serve un token BotFather.

### 3. Avvia Melixsa

#### Interfaccia desktop

Se `melixsa-ui.exe` e `Apri MelixsaUI.cmd` sono già accanto a `run.cmd`, apri **Apri MelixsaUI.cmd**.

Altrimenti scarica la build Windows pronta:

1. Nella pagina GitHub del progetto apri **Actions → Build MelixsaUI (Windows)** e scegli una compilazione riuscita della stessa versione del sorgente scaricato.
2. Scarica **MelixsaUI-Windows-x64** da **Artifacts** ed estrai tutti i file nella cartella principale del progetto, accanto a `Cogs`, `MelixsaUI` e `selfbot.py`.
3. Apri **Apri MelixsaUI.cmd**, poi premi **Collega Telegram** nella Home. Se la UI è in inglese, il pulsante si chiama **Connect Telegram**.

Se non è disponibile una build, puoi usare il terminale oppure [compilare l’app sul tuo PC](#compilare-lapp-desktop).

#### Terminale

Fai doppio clic su **run.cmd**, oppure esegui dalla cartella principale:

```powershell
.\run.cmd
```

Al primo collegamento inserisci numero di telefono, codice Telegram e password di verifica in due passaggi, se richiesta. Nell’app desktop li inserisci nella UI; la modalità terminale li chiede nella console. La sessione viene salvata in `data/` e riutilizzata agli avvii successivi.

**Avvia una sola istanza alla volta:** chiudi la modalità terminale prima di collegare l’app desktop e chiudi l’app prima di avviare la modalità terminale.

## Uso quotidiano

- **Desktop:** apri `Apri MelixsaUI.cmd` e collega Telegram. Il launcher richiede l’apertura della finestra massimizzata.
- **Terminale:** apri `run.cmd`, poi invia `/help` nei **Messaggi salvati** di Telegram. Per fermarlo premi `Ctrl+C` nella console.
- **Chiusura desktop:** usa il pulsante di chiusura della finestra per fermare il motore locale.

Il prefisso predefinito dei comandi è `/`. La protezione anti-login è attiva di default; prima di accedere da un altro dispositivo Telegram usa `/anti-login off`. I dettagli sono nel [riferimento delle automazioni, in inglese](docs/REFERENCE.md#account-automation).

### Pagine della UI

| Pagina | Cosa puoi fare |
| --- | --- |
| Home | Collegare Telegram e vedere account e sessione |
| Chat | Leggere chat private, gruppi, canali e conversazioni archiviate; inviare testo con stili Unicode; vedere le foto profilo e aprirle ingrandite |
| Comandi | Cercare comandi, copiare la sintassi e salvare preferiti; `Ctrl+K` apre la ricerca |
| Automazioni | Configurare reazioni automatiche, risposte AFK, anti-login e notifiche degli errori |
| Surveillance / Stalk | Gestire il monitoraggio e leggere i registri raccolti |
| Impostazioni | Cambiare impostazioni condivise, lingua della UI e icona Melixsa / E-Girl |
| Attività | Consultare gli eventi recenti della sessione desktop |

La UI supporta italiano e inglese. Il contenuto delle chat conserva la lingua originale. Per i dettagli consulta la [guida desktop](MelixsaUI/README.md).

### Comandi Telegram utili

| Comando | Funzione |
| --- | --- |
| `/help` oppure `/help <comando>` | Menu dei comandi e istruzioni dettagliate |
| `/search <testo>` | Cercare un comando |
| `/surveillance` / `/sustop` | Avviare / fermare il monitoraggio del gruppo corrente |
| `/stalk @username` / `/unstalk @username` | Avviare / fermare il monitoraggio di un utente |
| `/afk <messaggio>` / `/back` | Attivare / disattivare le risposte AFK nelle chat private |
| `/autoreact` | Consultare le reazioni automatiche |
| `/status` | Vedere impostazioni e monitoraggi |
| `/doctor` | Eseguire la diagnostica locale |

Per permessi di accesso, ricerche, SoundCloud, backup e limiti usa `/help` in Telegram oppure il [riferimento completo dei comandi, in inglese](docs/REFERENCE.md).

## Aggiornamenti

1. Chiudi Melixsa.
2. Aggiorna i file sorgente conservando il tuo `.env` e la cartella `data/`.
3. Dalla cartella principale aggiorna le dipendenze Python:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Per la UI desktop sostituisci eseguibile e launcher con la build corrispondente al sorgente aggiornato. Le modifiche alla UI richiedono un nuovo eseguibile: sostituire solo i sorgenti non aggiorna l’interfaccia incorporata.
5. Avvia Melixsa normalmente.

## Altre modalità

### Anteprima nel browser

Con **Node.js 24** installato, apri **MelixsaUI/Anteprima UI.cmd**. Il launcher installa le dipendenze JavaScript se mancano e apre l’anteprima.

L’anteprima permette di esplorare l’interfaccia e cambiare le preferenze locali dell’aspetto. Collegare Telegram, leggere le chat reali e inviare messaggi richiede l’app desktop. Per vedere soltanto l’anteprima non serve preparare Python.

### Compilare l’app desktop

Per lo sviluppo installa **Node.js 24, Rust, Microsoft C++ Build Tools con Desktop development with C++ e Windows SDK, e WebView2**. Completa anche la preparazione di Python descritta sopra.

Apri **MelixsaUI/Avvia Melixsa.cmd** per compilare e avviare l’app di sviluppo. Le dipendenze JavaScript vengono installate se mancano.

Per una build di distribuzione, esegui dalla cartella `MelixsaUI`:

```powershell
node scripts/run.mjs install
node scripts/run.mjs desktop:build
```

L’eseguibile viene creato in `MelixsaUI/src-tauri/target/release/melixsa-ui.exe`. Per preparare gli stessi file della build scaricabile, esegui da `MelixsaUI`:

```powershell
.\scripts\package-windows.ps1 -Destination ..\dist\MelixsaUI-Windows-x64
```

Per usarli, estrai i file del pacchetto nella cartella principale del progetto. L’app desktop richiede comunque il backend Python del progetto.

## Problemi comuni

| Problema | Soluzione |
| --- | --- |
| `py` non viene riconosciuto | Installa Python e riapri PowerShell; se è disponibile `python`, usa `python -m venv .venv` |
| Mancano `.venv` o moduli Python | Ripeti il punto 1 dell’installazione nella cartella principale |
| Credenziali API non valide | Sostituisci i valori di esempio del `.env` con API ID e hash reali |
| Manca l’eseguibile desktop | Estrai la build Windows completa nella cartella principale oppure usa `run.cmd` |
| Manca WebView2 | Installa Microsoft Edge WebView2 Runtime |
| La sessione è già in uso | Chiudi l’altra istanza di Melixsa prima di ricollegare Telegram |
| `link.exe` non trovato | La compilazione locale richiede il workload C++ dei Build Tools e Windows SDK; la build pronta non li richiede |
| Non compare una modifica della UI | Usa una build desktop generata dal sorgente aggiornato |
| Le risposte scompaiono | `/deleteafter 0` conserva le normali risposte ai comandi |

## File locali

Conserva sul tuo dispositivo `.env`, `data/`, `*.session*` e `.venv/`. Contengono credenziali, sessioni dell’account, dati locali o dipendenze specifiche del computer. Il [.gitignore](.gitignore) del progetto li esclude dalle normali aggiunte a Git; escludili anche quando carichi file manualmente.

## Sviluppo e documentazione

Esegui i test del backend dalla cartella principale:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Esegui i controlli della UI dalla cartella `MelixsaUI`:

```powershell
node scripts/run.mjs test
node scripts/run.mjs build
```

- [Guida in inglese](README.md)
- [Installazione e uso su Android con Termux](docs/TERMUX.md)
- [Riferimento completo dei comandi e della configurazione, in inglese](docs/REFERENCE.md)
- [Guida desktop](MelixsaUI/README.md)
- [Workflow per la build Windows](.github/workflows/build-melixsa-ui.yml)
- [Crediti e progetti originali](docs/REFERENCE.md#credits)
