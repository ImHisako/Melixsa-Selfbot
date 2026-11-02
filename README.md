# Melixsa Selfbot

**English** · [Italiano](README.it.md)

A Telegram client for your personal account, with a Windows desktop UI and commands you can send in Telegram. Includes chats, Unicode text styles, automations, group monitoring, public-source research, and SoundCloud controls.

**On Android:** follow the [Termux guide (Italian)](docs/TERMUX.md) to install and run the Python command interface. The Windows steps below are for a PC.

## Installation on Windows

You need **Python 3.10 or later**, a Telegram account, and your API ID and API hash from [my.telegram.org](https://my.telegram.org). The desktop app also needs **Windows x64 and Microsoft Edge WebView2 Runtime**.

The ready-made desktop build uses the project's Python environment. **You do not need Node.js, Rust, or C++ Build Tools to run it.**

### 1. Prepare the project

Download or clone the source code and extract it to a folder. Open **PowerShell in that folder**, next to `run.cmd` and `requirements.txt`, and run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Do this once per computer. You can use the environment directly; no activation command is needed.

### 2. Set your Telegram credentials

In the same PowerShell window:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
notepad .env
```

Replace the two example values with your own credentials and save:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_with_your_api_hash
```

The ID is numeric; the hash has 32 hexadecimal characters. Other `.env` fields are optional. The copy command preserves an existing `.env`. Melixsa uses your personal account; no BotFather token is needed.

### 3. Start Melixsa

#### Desktop app

If `melixsa-ui.exe` and `Apri MelixsaUI.cmd` are already next to `run.cmd`, open **Apri MelixsaUI.cmd**.

Otherwise, get the ready-made Windows build:

1. On the project's GitHub page, open **Actions → Build MelixsaUI (Windows)** and select a successful run for the source version you downloaded.
2. Download **MelixsaUI-Windows-x64** from **Artifacts** and extract all its files into the project root, next to `Cogs`, `MelixsaUI`, and `selfbot.py`.
3. Open **Apri MelixsaUI.cmd**, then click **Connect Telegram** on Home. In Italian, the button is **Collega Telegram**.

If there is no available build, you can use the terminal or [build the desktop app locally](#build-the-desktop-app-yourself).

#### Terminal

Double-click **run.cmd**, or run this from the project root:

```powershell
.\run.cmd
```

On first connection, enter your phone number, Telegram code, and two-step verification password if requested. In the desktop app you enter them in the UI; terminal mode uses terminal prompts. The session is saved in `data/` and reused later.

**Run one instance at a time:** close terminal mode before connecting the desktop app, and close the desktop app before starting terminal mode.

## Everyday use

- **Desktop:** open `Apri MelixsaUI.cmd` and connect Telegram. The launcher requests a maximized window.
- **Terminal:** open `run.cmd`, then send `/help` in Telegram **Saved Messages**. Stop with `Ctrl+C` in the terminal.
- **Close desktop:** use the window's close button to stop its local engine.

Default command prefix: `/`. Anti-login protection is enabled by default; before signing in on another Telegram device, use `/anti-login off`. Details are in the [account automation reference](docs/REFERENCE.md#account-automation).

### Desktop pages

| Page | What you can do |
| --- | --- |
| Home | Connect Telegram and view your account and session |
| Chats | Read private chats, groups, channels, and archived conversations; send text with Unicode styles; view profile photos and open them larger |
| Commands | Search commands, copy syntax, and save favorites; `Ctrl+K` opens search |
| Automations | Configure automatic reactions, AFK replies, anti-login, and error notifications |
| Surveillance / Stalk | Manage monitoring and read collected logs |
| Settings | Change shared settings, UI language, and the Melixsa / E-Girl app icon |
| Activity | Read recent desktop events |

The UI supports Italian and English. Chat content stays in its original language. See the [desktop guide (Italian)](MelixsaUI/README.md) for details.

### Useful Telegram commands

| Command | Purpose |
| --- | --- |
| `/help` or `/help <command>` | Command menus and detailed help |
| `/search <text>` | Find a command |
| `/surveillance` / `/sustop` | Start / stop monitoring the current group |
| `/stalk @username` / `/unstalk @username` | Start / stop monitoring a user |
| `/afk <message>` / `/back` | Enable / disable private-chat AFK replies |
| `/autoreact` | Inspect automatic reactions |
| `/status` | View current settings and monitors |
| `/doctor` | Run local diagnostics |

For access permissions, research tools, SoundCloud, backups, and limits, use the [complete command reference](docs/REFERENCE.md) or `/help` in Telegram.

## Updating

1. Close Melixsa.
2. Update the source files while keeping your local `.env` and `data/` directory.
3. From the project root, update Python dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. For the desktop UI, replace the executable and launcher with the build matching the updated source. UI source changes require a new executable; replacing source files alone does not update the bundled interface.
5. Start Melixsa normally.

## Other ways to run

### Preview the UI in a browser

With **Node.js 24** installed, open **MelixsaUI/Anteprima UI.cmd**. It installs the JavaScript dependencies if missing and opens the preview.

Preview mode lets you inspect the interface and change local appearance preferences. Connecting Telegram, reading real chats, and sending messages require the desktop app. Python setup is not required just to view the preview.

### Build the desktop app yourself

For development, install **Node.js 24, Rust, Microsoft C++ Build Tools with Desktop development with C++ and Windows SDK, and WebView2**. Also complete the Python setup above.

Open **MelixsaUI/Avvia Melixsa.cmd** to build and start the development app. It installs the JavaScript dependencies if missing.

For a release build, run from the `MelixsaUI` folder:

```powershell
node scripts/run.mjs install
node scripts/run.mjs desktop:build
```

The executable is created at `MelixsaUI/src-tauri/target/release/melixsa-ui.exe`. To prepare the same files as the downloadable build, run from `MelixsaUI`:

```powershell
.\scripts\package-windows.ps1 -Destination ..\dist\MelixsaUI-Windows-x64
```

Extract the packaged files into the project root when using them. The desktop app still needs the project's Python backend.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `py` is not recognized | Install Python, then reopen PowerShell; if `python` is available, use `python -m venv .venv` instead |
| Missing `.venv` or Python modules | Repeat installation step 1 in the project root |
| Invalid API credentials | Replace the example values in `.env` with your real API ID and hash |
| Desktop executable missing | Extract the complete Windows build into the project root, or use `run.cmd` |
| WebView2 missing | Install Microsoft Edge WebView2 Runtime |
| Session already in use | Close the other Melixsa instance before reconnecting |
| `link.exe` not found | Local compilation needs the C++ Build Tools workload and Windows SDK; the ready-made build does not |
| A UI change is missing | Use a desktop build generated from the updated source |
| Responses disappear | `/deleteafter 0` keeps ordinary command responses |

## Local files

Keep `.env`, `data/`, `*.session*`, and `.venv/` on your device. They contain credentials, account sessions, local data, or machine-specific dependencies. The project [.gitignore](.gitignore) excludes them from normal Git additions; exclude them yourself for manual uploads.

## Development and documentation

Run backend tests from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Run UI checks from `MelixsaUI`:

```powershell
node scripts/run.mjs test
node scripts/run.mjs build
```

- [Guida italiana](README.it.md)
- [Android / Termux installation and usage (Italian)](docs/TERMUX.md)
- [Complete command and configuration reference](docs/REFERENCE.md)
- [Desktop guide (Italian)](MelixsaUI/README.md)
- [Windows build workflow](.github/workflows/build-melixsa-ui.yml)
- [Credits and upstream projects](docs/REFERENCE.md#credits)
