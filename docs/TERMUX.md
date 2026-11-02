# Melixsa su Android con Termux

[README italiano](../README.it.md) · [English README](../README.md) · [Riferimento comandi](REFERENCE.md)

Questa guida avvia il **motore Python da terminale**: usi Melixsa inviando comandi
in Telegram. L’interfaccia desktop Windows, gli eseguibili `.exe` e i launcher
`.cmd` non fanno parte di questo percorso. Non servono Node.js, Rust o i Build Tools Windows.

## 1. Installa Termux

Usa un dispositivo con **Android 7 o successivo** e una versione aggiornata di
Termux da [F-Droid](https://f-droid.org/packages/com.termux/) oppure dalle
[release ufficiali](https://github.com/termux/termux-app/releases).
Se usi plugin Termux, installali dallo stesso canale dell’app: le firme dei diversi
canali non sono intercambiabili. Vedi le [istruzioni ufficiali di installazione](https://github.com/termux/termux-app/blob/master/README.md#installation).

Servono una connessione Internet e le credenziali del tuo account Telegram
ottenute da [my.telegram.org](https://my.telegram.org): **API ID** e **API hash**.

## 2. Prepara Python e gli strumenti di compilazione

Apri Termux ed esegui, confermando le richieste del gestore pacchetti:

```bash
pkg update
pkg upgrade
pkg install git python python-pip python-ensurepip-wheels nano \
  clang make ndk-sysroot libjpeg-turbo zlib
```

`python-pip` e `python-ensurepip-wheels` forniscono gli strumenti Python e quelli
per creare l’ambiente virtuale, come previsto dal [pacchetto Python di Termux](https://github.com/termux/termux-packages/blob/master/packages/python/build.sh).
Clang e le librerie di sviluppo servono quando le dipendenze native vengono
compilate sul telefono: il progetto include [TgCrypto](https://github.com/Mayuri-Chan/tgcrypto/blob/master/setup.py)
e Pillow, che documenta i [prerequisiti per Android/Termux](https://pillow.readthedocs.io/en/stable/installation/building-from-source.html#android).

Per aggiornare il `pip` fornito da Termux usa `pkg upgrade`, non
`pip install --upgrade pip`: Termux [blocca l’autoaggiornamento](https://github.com/termux/termux-packages/blob/master/packages/python-pip/install_py_preventing_pip_from_installing.patch)
del proprio pacchetto.

## 3. Scarica Melixsa e installa le dipendenze

```bash
cd ~
git clone https://github.com/ImHisako/Melixsa-Selfbot.git
cd Melixsa-Selfbot
python -m venv .venv
.venv/bin/python -m pip install setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
```

Se hai già clonato il progetto, entra nella cartella esistente e salta il comando
`git clone`. Crea l’ambiente sul telefono: la `.venv` di Windows non è riutilizzabile.

Conserva il progetto nella home di Termux, come nell’esempio, anziché in
`/sdcard` o nella cartella Download condivisa: lo storage esterno ha restrizioni
su esecuzione e funzionalità del filesystem. Vedi il [layout ufficiale del filesystem](https://github.com/termux/termux-packages/wiki/Termux-file-system-layout).
Per questa procedura non serve `termux-setup-storage`.

La prima installazione può compilare alcuni moduli. Aspetta che il comando termini
senza errori, poi verifica:

```bash
.venv/bin/python -m pip check
.venv/bin/python -c "import pyrogram, tgcrypto, aiohttp; from PIL import Image; print('Dipendenze principali disponibili')"
```

Non serve attivare l’ambiente virtuale: tutti gli esempi chiamano direttamente
`.venv/bin/python`. Mantieni le versioni previste da [requirements.txt](../requirements.txt).

## 4. Inserisci le credenziali Telegram

Dalla cartella `~/Melixsa-Selfbot`:

```bash
if [ ! -e .env ]; then cp .env.example .env; fi
nano .env
```

Sostituisci i valori di esempio con i tuoi e salva:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_with_your_api_hash
```

L’ID deve essere numerico; l’hash deve contenere 32 caratteri esadecimali. Gli altri
campi sono facoltativi. Il comando di copia conserva un `.env` già presente.
In nano salva con **Ctrl+O**, premi **Invio** e chiudi con **Ctrl+X**.
Non serve un token BotFather.

Prima del primo collegamento da Termux, ferma un eventuale Melixsa già attivo sul
PC. La protezione anti-login è attiva di default: se devi aggiungere un dispositivo
mentre un’altra istanza è attiva, usa prima `/anti-login off` da quell’istanza.

## 5. Avvia Melixsa e accedi

```bash
cd ~/Melixsa-Selfbot
.venv/bin/python selfbot.py
```

Al primo accesso segui le richieste nella console: numero con prefisso internazionale,
codice Telegram e password della verifica in due passaggi, se richiesta.
La sessione viene salvata in `data/` e riutilizzata agli avvii successivi.

Apri Telegram e invia **`/help` nei Messaggi salvati**. Da quel momento puoi usare
i comandi nelle chat in cui il tuo account dispone dei permessi necessari.

## Uso quotidiano

Per riavviare Melixsa dopo aver riaperto Termux bastano:

```bash
cd ~/Melixsa-Selfbot
.venv/bin/python selfbot.py
```

Per fermarlo premi **Ctrl+C nella console** e attendi il completamento dell’arresto.
Il monitoraggio e le automazioni funzionano mentre il processo è in esecuzione.
Usa una sola istanza di Melixsa alla volta per evitare risposte duplicate.

| Comando Telegram | Utilizzo |
| --- | --- |
| `/help` | Menu dei comandi |
| `/help <comando>` | Istruzioni per un comando |
| `/status` | Stato e impostazioni |
| `/doctor` | Diagnostica locale |
| `/surveillance` / `/sustop` | Avviare / fermare il monitoraggio del gruppo corrente |
| `/stalk @username` / `/unstalk @username` | Avviare / fermare il monitoraggio di un utente |
| `/afk <messaggio>` / `/back` | Attivare / disattivare le risposte AFK |
| `/deleteafter 0` | Conservare le normali risposte ai comandi |

Il prefisso iniziale è `/`. Per gli altri comandi consulta l’help in Telegram
oppure il [riferimento completo](REFERENCE.md).

## Sessione persistente con tmux

Se vuoi staccarti dal terminale senza chiudere la sua sessione, installa tmux:

```bash
pkg install tmux
tmux new -s melixsa
```

Dentro la nuova sessione avvia il selfbot:

```bash
cd ~/Melixsa-Selfbot
.venv/bin/python selfbot.py
```

Per staccarti premi **Ctrl+B**, rilascia i tasti, poi premi **D**. Per rientrare:

```bash
tmux attach -t melixsa
```

Per arrestare Melixsa rientra nella sessione e premi **Ctrl+C**.

Facoltativamente, prima dell’avvio puoi usare:

```bash
termux-wake-lock
```

Quando hai terminato e fermato Melixsa:

```bash
termux-wake-unlock
```

Il [wake lock](https://github.com/termux/termux-tools/blob/master/scripts/termux-wake-lock.in)
evita la sospensione della CPU; tmux conserva la sessione del terminale. Nessuno dei
due impedisce ad Android di terminare Termux, né riavvia Melixsa dopo un riavvio del
telefono. Termux documenta queste [limitazioni dei processi in background](https://github.com/termux/termux-app/blob/master/README.md).

## Aggiornare il progetto

Ferma prima Melixsa con **Ctrl+C**, poi:

```bash
cd ~/Melixsa-Selfbot
git pull --ff-only
pkg update
pkg upgrade
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python selfbot.py
```

Se Git segnala modifiche locali o una divergenza, risolvila prima di proseguire.
Conserva `.env` e `data/`: non vanno cancellati durante l’aggiornamento.

Se l’aggiornamento di Termux cambia la versione principale o secondaria di Python
e la `.venv` non funziona più, rinomina la vecchia cartella `.venv` e ripeti la sua
creazione e l’installazione delle dipendenze del punto 3. Mantieni `.env` e `data/`.

## Problemi comuni

| Problema | Cosa fare |
| --- | --- |
| `pkg` non trova pacchetti o il mirror non risponde | Esegui `termux-change-repo`, scegli un mirror disponibile e ripeti `pkg update` e `pkg upgrade` |
| Errore relativo a `ensurepip` durante la creazione della `.venv` | Installa `python-ensurepip-wheels` e `python-pip`, poi ripeti `python -m venv .venv` |
| `Installing pip is forbidden` | Aggiorna i pacchetti con `pkg upgrade`; non aggiornare il pip di Termux tramite pip |
| `Failed building wheel` per TgCrypto, Pillow o aiohttp | Verifica di aver installato gli strumenti del punto 2 e leggi il primo errore di compilazione; poi ripeti l’installazione dei requirements |
| Errore su JPEG, zlib o `Python.h` | Verifica `pkg install python clang ndk-sysroot libjpeg-turbo zlib` e riprova nella home di Termux |
| Compilazione di Pillow terminata per memoria insufficiente | Riprova con `MAX_CONCURRENCY=1 .venv/bin/python -m pip install --no-cache-dir -r requirements.txt` |
| `Permission denied` o errore sui link della `.venv` | Sposta il sorgente nella home di Termux e ricrea lì l’ambiente |
| Un messaggio propone `.venv\Scripts\python.exe` | È un suggerimento per Windows: su Termux usa `.venv/bin/python` |
| API ID o hash non validi | Modifica `.env` con i valori reali di my.telegram.org |
| Il nuovo accesso viene terminato | Ferma l’altra istanza o disattiva la sua protezione con `/anti-login off` prima del login |
| `Melixsa è già in esecuzione` | Rientra con `tmux attach -t melixsa` e ferma il processo prima di aprirne un altro |
| Melixsa si ferma quando cambi app o spegni lo schermo | Controlla i limiti di risparmio energetico e dei processi in background di Android; tmux e wake lock non garantiscono l’esecuzione continua |

### SoundCloud

All’avvio da terminale può comparire il pannello WebNowPlaying. Può restare
scollegato mentre usi le altre funzioni. I controlli SoundCloud richiedono un
browser compatibile con WebNowPlaying **sullo stesso dispositivo**: l’adapter
ascolta solo su `127.0.0.1`, quindi Termux non controlla automaticamente il browser
del PC.

## File locali e verifica

Credenziali e sessione rimangono nel `.env` e in `data/`; l’ambiente Python è in
`.venv/`. Non caricare questi file nel repository o in cartelle pubbliche.

La procedura è basata sul motore Python del progetto e sulla documentazione
ufficiale collegata. Sono stati verificati sintassi degli esempi Bash e
collegamenti del progetto; resta da eseguire il collaudo su un dispositivo Android.
