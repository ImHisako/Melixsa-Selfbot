# Melixsa Desktop

[Installazione in italiano](../README.it.md#installazione-windows) · [English quick start](../README.md#installation-on-windows) · [Riferimento comandi (inglese)](../docs/REFERENCE.md)

Interfaccia desktop Windows per il motore Python di Melixsa, con chat, automazioni,
monitoraggio e impostazioni condivise con i comandi Telegram.

Per l’uso da terminale su Android consulta la [guida Termux](../docs/TERMUX.md).

## Avvio rapido

1. Completa **i punti 1 e 2 della [guida di installazione](../README.it.md#installazione-windows)**: ambiente Python, dipendenze e credenziali nel `.env`.
2. Se `melixsa-ui.exe` e `Apri MelixsaUI.cmd` sono già nella cartella principale, passa al punto successivo. Altrimenti [scarica la build Windows](#scaricare-la-build-windows-pronta).
3. Chiudi un eventuale Melixsa avviato da `run.cmd` e apri **Apri MelixsaUI.cmd**.
4. Premi **Collega Telegram / Connect Telegram** nella Home. Al primo accesso inserisci numero, codice e password di verifica in due passaggi, se richiesta.

Per usare la build pronta **non servono Node.js, Rust o i Build Tools C++**.
Servono Windows x64, WebView2 e il Python del progetto. La sessione salvata in
`data/melixsa.session` viene riutilizzata; le credenziali API restano nel backend.

## Scaricare la build Windows pronta

1. Nella pagina GitHub del progetto apri **Actions → Build MelixsaUI (Windows)**.
2. Scegli una compilazione riuscita della stessa versione del sorgente e scarica **MelixsaUI-Windows-x64** da **Artifacts**.
3. Estrai **tutti i file dello ZIP nella cartella principale di Melixsa**, accanto a `Cogs`, `MelixsaUI`, `.venv` e `selfbot.py`.
4. Apri **Apri MelixsaUI.cmd** e collega Telegram dalla Home.

Il pacchetto contiene l’eseguibile, il launcher, le istruzioni e `SHA256SUMS.txt`.
Il backend Python va preparato una volta con la guida principale; non è incorporato
nell’eseguibile. Conserva sul dispositivo il tuo `.env` e la cartella `data/`.

Il [workflow](../.github/workflows/build-melixsa-ui.yml) parte ai push e alle pull request
che modificano la UI o il workflow. Se è presente nel branch predefinito, puoi
avviarlo da **Run workflow**. Se non è disponibile una build pronta, puoi usare
`run.cmd` oppure compilare localmente.

## Anteprima nel browser

Con **Node.js 24**, apri **Anteprima UI.cmd** da questa cartella. Il launcher installa
le dipendenze JavaScript se mancano e apre l’anteprima nel browser.

Puoi vedere la UI e cambiare lingua e icona. L’accesso a Telegram e alle chat reali
richiede l’app desktop. Per la sola anteprima non servono Python o compilatori C++.

## Compilazione locale

Questo percorso serve a chi sviluppa o vuole generare il proprio eseguibile.
Richiede il backend Python configurato, **Node.js 24, Rust, Microsoft C++ Build Tools
con Desktop development with C++ e Windows SDK, e WebView2**.

- **Sviluppo:** apri **Avvia Melixsa.cmd** da questa cartella. Le dipendenze JavaScript vengono installate se mancano.
- **Distribuzione:** dalla cartella `MelixsaUI`, esegui:

  ```powershell
  node scripts/run.mjs install
  node scripts/run.mjs desktop:build
  ```

L’eseguibile viene creato in `src-tauri/target/release/melixsa-ui.exe`. Per preparare
il pacchetto completo, sempre da questa cartella:

```powershell
.\scripts\package-windows.ps1 -Destination ..\dist\MelixsaUI-Windows-x64
```

Estrai i file del pacchetto nella cartella principale per usarli con il backend.
Aggiornare i soli sorgenti non cambia la UI incorporata in un eseguibile già compilato.

## Personalizzazione

La UI è disponibile in **italiano e inglese**. Il selettore nella barra superiore o in
**Impostazioni > Generali > Lingua** cambia subito testi, guida, login, notifiche e
formati di date e numeri. La scelta è salvata sul dispositivo e funziona anche
nell’anteprima browser; al primo avvio si usa l’inglese per un browser in inglese,
altrimenti l’italiano. Se l’archiviazione locale non è disponibile, la scelta vale
per la sessione corrente. I messaggi AFK, i nomi e i contenuti Telegram mantengono
il testo originale, così come le esportazioni JSON e i dettagli tecnici non riconosciuti.

In **Impostazioni > Generali > Icona dell’app** puoi scegliere tra **Melixsa**, con
la luna e le stelle originali, ed **E-Girl**, con l’immagine inclusa nel progetto.
La scelta aggiorna subito il logo della UI, l’icona della scheda browser e quella
della finestra desktop. Viene salvata sul dispositivo e riapplicata alla riapertura;
funziona anche offline e nell’anteprima, senza collegare Telegram.
Se l’archiviazione locale non è disponibile, la scelta vale per l’apertura corrente.
L’icona del file `.exe` e dei collegamenti di Windows segue la build installata.

La finestra desktop si apre massimizzata per adattarsi all’area disponibile dello
schermo; il launcher **Apri MelixsaUI.cmd** richiede questa modalità anche per
l’eseguibile già installato. Anche riducendola, le pagine restano scorrevoli e il
menu laterale ha uno scorrimento indipendente, con guida e account accessibili in basso.

## Pagine

- **Chat:** conversazioni principali e archiviate (private, bot, gruppi e canali),
  ricerca e filtri, cronologia Telegram e invio di testo dal proprio account.
  Il composer offre stili Unicode come Fraktur e Full Width, con anteprima dal vivo.
- **Home:** nome, username, foto profilo e ID letti da Telegram; durata della sessione;
  controlli rapidi e conteggi reali di gruppi e ricerche. Prima del collegamento viene
  mostrato lo stato scollegato. Il profilo sincronizzato viene conservato localmente
  in `data/desktop-profile.json` per le aperture successive.
- **Automazioni:** autoreact con selezione di 1–3 emoji e numero di reazioni;
  AFK e messaggio personalizzato; protezione dei nuovi accessi; notifiche degli errori.
- **Comandi:** catalogo completo diviso nelle categorie del selfbot, con ricerca per
  nome, alias, descrizione e sintassi, dettagli d’uso e copia del comando o del menu
  di categoria con il prefisso corrente. Stelle e filtro Preferiti salvano scorciatoie locali.
- **Surveillance:** attivazione e arresto del monitoraggio dei gruppi; scelta dalle
  ultime 200 chat Telegram oppure tramite username/ID; elenco ricercabile e lettore
  dei registri con filtro per modifiche, ricerca testuale ed esportazione della vista.
- **Stalk:** attivazione e arresto per username o ID utente, elenco ricercabile delle
  persone seguite e consultazione dei registri locali con gruppo di provenienza,
  filtro modifiche, ricerca ed esportazione della vista in JSON.
- **Impostazioni:** prefisso, eliminazione risposte, modalità minimale, preferenze console,
  dimensione dei log, copie di backup e conservazione.
- **Attività:** ultimi 80 eventi della sessione desktop, ricerca, filtro errori ed esportazione JSON.

Le impostazioni persistenti vengono salvate atomicamente in `data/state.json` con i
meccanismi di backup esistenti. AFK vale per la sessione corrente, come nel motore Python.
Modifiche ai comandi Telegram e agli interruttori convergono sullo stesso stato; la UI si
aggiorna ogni 3 secondi. La chiusura dell'app arresta il motore e attende lo svuotamento dei log.
La modalità desktop non avvia automaticamente SoundCloud e non invia il suo pannello di
connessione nei Messaggi salvati. SoundCloud rimane disponibile tramite i comandi Telegram.

### Usare Chat

Collega Telegram dalla Home e apri **Chat**. L’elenco include conversazioni principali
e archiviate, senza un limite totale di 200: **Carica altre chat** prosegue a blocchi
di 60. Ricerca e filtri Tutte/Gruppi/Private/Canali si applicano alle conversazioni
già caricate. **Aggiorna chat** ricarica l’elenco da Telegram.

Le foto profilo di persone, bot, gruppi e canali compaiono nell’elenco,
nell’intestazione della conversazione e accanto ai messaggi. Un clic sulla foto
apre la versione ingrandita; chiudi con il pulsante, con Escape o cliccando fuori.
Se la foto è assente, privata o non disponibile, vengono mostrate le iniziali.
Le miniature visibili si caricano in background, con al massimo tre download
contemporanei e una cache in memoria di 512 profili. La cache viene svuotata alla
disconnessione. I cambi e le rimozioni delle foto invalidano la miniatura precedente;
i profili non aggiornati dalla cronologia vengono ricontrollati dopo cinque minuti.
Gli errori temporanei applicano una pausa prima del nuovo tentativo; una foto non
disponibile non interrompe la lettura o l’invio dei messaggi.

Seleziona una conversazione per leggere gli ultimi 50 messaggi; **Messaggi precedenti**
carica altri blocchi di 50. La finestra recente si aggiorna ogni 5 secondi, incluse
modifiche e cancellazioni, mentre la pagina è aperta. Un errore sospende l’aggiornamento
fino a **Riprova**. Foto, video e documenti sono indicati con il tipo di allegato e
l’eventuale didascalia; questa sezione non scarica né invia file multimediali.

Scrivi nel composer e scegli **Stile del testo**: Normale, Fraktur, Zalgo, Squared,
Circled, Bold Italic, Full Width, Strikethrough, Invisible Separator o Undetected.
L’anteprima mostra il testo effettivo; il contatore controlla il limite di 4096 unità
UTF-16 dopo la trasformazione, incluse emoji e segni combinanti. L’invio usa testo
letterale, senza interpretare Markdown o HTML. Gli stili agiscono sui messaggi
scritti in questa sezione; i comandi e le automazioni esistenti mantengono il loro testo.

Premi **Invia messaggio** oppure **Ctrl+Invio** (Cmd+Invio su Mac). Invio da solo
va a capo. Le bozze rimangono separate per conversazione durante la permanenza
nella pagina e sono conservate in caso di errore; un invio fallito non viene ripetuto
automaticamente dalla UI. Telegram applica i permessi di scrittura e i propri limiti.
Contenuti e bozze restano in memoria, senza una nuova cache locale dello storico.
L’apertura della cronologia non segna automaticamente i messaggi come letti.

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
Durante la sessione desktop restano visibili anche i gruppi appena fermati.
Caricare i gruppi disponibili non li aggiunge automaticamente al monitoraggio.
Il pulsante cestino rimuove un gruppo dall’elenco e ferma il monitoraggio. Dopo la
conferma elimina anche tutti i suoi registri locali, compresi gli archivi ruotati;
la rimozione è disponibile anche offline e non può essere annullata.

### Cercare i comandi e salvare scorciatoie

Apri **Comandi** dalla sidebar o dal pulsante di ricerca nella barra superiore.
**Ctrl+K** (anche **Cmd+K** su Mac) apre la pagina e porta il cursore sulla ricerca.
Puoi cercare nomi, alias, categorie, descrizioni e argomenti in italiano o inglese,
anche includendo il prefisso attuale. I filtri di categoria e Preferiti si combinano
con la ricerca; Escape nel campo cancella il testo cercato.

La stella salva un comando nei Preferiti del dispositivo. Il pulsante copia usa il
prefisso corrente delle impostazioni; anche gli alias e i menu delle categorie sono
copiabili. Gli argomenti tra `<...>` e `[...]` sono segnaposto da compilare quando
incolli il comando in Telegram. Se gli appunti non sono disponibili, seleziona la
sintassi e usa Ctrl+C. I nomi dei comandi e le opzioni letterali rimangono invariati.

L’app desktop legge il catalogo centrale dell’help senza collegare Telegram o
eseguire comandi. L’anteprima usa una copia inclusa, disponibile anche se il motore
non risponde. Dopo aver modificato il catalogo Python, rigenera questa copia dalla
cartella principale del progetto:

```powershell
.\.venv\Scripts\python.exe MelixsaUI/scripts/export-command-catalog.py
```

I test verificano che la copia sia aggiornata e che tutte le categorie, descrizioni,
sintassi e istruzioni abbiano una traduzione inglese.

### Usare Stalk

Apri **Stalk** nella sidebar, inserisci `@username` oppure un ID utente positivo e
premi **Attiva Stalk** mentre Telegram è connesso. Il pannello usa lo stesso elenco
persistente dei comandi `stalk`, `unstalk` e `stalklist`; le modifiche ai comandi
appaiono automaticamente nella UI. Nomi e foto profilo vengono caricati in background
da Telegram anche per gli utenti già presenti. La cache delle immagini dura cinque
minuti e viene invalidata quando il motore rileva un cambio di foto.
La foto compare nell’elenco, nel profilo selezionato e accanto ai messaggi; se non è
disponibile vengono mostrate le iniziali. Offline restano disponibili i profili già
caricati nella sessione e i nomi ricavati dai registri; in assenza di un nome si usa l’ID.

Seleziona un utente per leggere i nuovi messaggi e le modifiche già registrati nei
gruppi visibili al tuo account, oltre ai cambi di nome, username e foto profilo e
agli stati online/offline espliciti. I messaggi indicano il gruppo di provenienza;
i cambi del profilo mostrano i valori precedenti e successivi. Puoi cercare negli
eventi, filtrarli per tipo ed esportare la vista in JSON.
La lettura include gli archivi ruotati ed è limitata a 100 eventi e 2 MB, con
aggiornamento ogni 5 secondi. Non viene scaricato lo storico precedente.

Il monitoraggio è nel motore Python e continua anche con questa pagina chiusa.
Gli aggiornamenti Telegram sono affiancati da un controllo dei profili ogni 30
secondi: l’orario dei cambi rilevati dal controllo indica quando sono stati osservati.
La prima lettura del profilo all’avvio o alla riattivazione stabilisce un riferimento,
senza generare cambiamenti fittizi. “Recentemente” o uno stato nascosto non sono
interpretati come offline. La copertura dipende dagli aggiornamenti che Telegram
rende disponibili al tuo account. I cambi di foto registrano l’identificatore della
foto visibile; le immagini precedenti non vengono archiviate.

Puoi fermare un utente e leggere i registri anche offline. Fermarlo conserva i file;
durante la sessione desktop resta nell’elenco anche senza registri. Attivarlo richiede
Telegram connesso. Stalk e Surveillance restano indipendenti.
Il pulsante cestino rimuove una persona dall’elenco e ferma Stalk. Dopo la conferma
elimina anche tutti i suoi registri locali, compresi gli archivi ruotati. Funziona
anche offline; la rimozione non può essere annullata.

## Comandi di sviluppo

Da questa cartella:

```powershell
node scripts/run.mjs install
node scripts/run.mjs dev
node scripts/run.mjs build
node scripts/run.mjs test
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
  catalog/          Catalogo generato dei comandi per l’anteprima
  hooks/            Stato, sincronizzazione e operazioni
  i18n/             Catalogo italiano/inglese, preferenza locale e formati
  lib/              Contratto con il bridge Tauri
  pages/            Home, Chat, Comandi, Automazioni, Surveillance, Stalk, Impostazioni, Attività
  tokens.css        Colori, font e variabili del tema
  styles.css        Layout responsive, componenti e animazioni
  viewport.css      Scorrimento e adattamento alle finestre ridotte
  types.ts          Modelli TypeScript
src-tauri/          Shell Rust, configurazione Tauri e icone
backend/           Bridge JSON, chat, foto profilo e monitoraggio
public/            Icone e risorse incluse nella UI
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
concorrenza fra processi, AFK, profilo Telegram, Surveillance, Stalk e isolamento del protocollo. Usano directory
temporanee e client simulati; non collegano l'account reale.

La compilazione nativa locale richiede il linker MSVC (`link.exe`) fornito dai
Build Tools C++. Per eseguire una build Windows già compilata bastano il backend
Python del progetto e WebView2; i compilatori servono soltanto a chi genera l’eseguibile.
Le modifiche ai sorgenti della UI richiedono una nuova build desktop.
