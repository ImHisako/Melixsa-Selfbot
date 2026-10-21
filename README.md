# Melixsa Selfbot

A modular Telegram client for personal account automation, group monitoring, public-source research, and local SoundCloud playback control. Melixsa runs on [Kurigram](https://github.com/kurigram-org/kurigram) and authenticates through your Telegram user account.

Commands are available to the account owner and authorized users. Monitoring configuration, access permissions, and selected preferences persist across restarts. The current command menus and most runtime messages are in Italian; this README documents the application in English.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Command basics](#command-basics)
- [Access control](#access-control)
- [Monitoring](#monitoring)
- [Utilities and account tools](#utilities-and-account-tools)
- [Public-source research](#public-source-research)
- [SoundCloud and lyrics](#soundcloud-and-lyrics)
- [Account automation](#account-automation)
- [Diagnostics and recovery](#diagnostics-and-recovery)
- [Local data and GitHub uploads](#local-data-and-github-uploads)
- [Project structure](#project-structure)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Credits](#credits)

## Features

- **Telegram command interface:** category menus, command help, configurable prefixes, and automatic response deletion.
- **Access control:** authorize users and manage shared commands individually or by category.
- **Monitoring:** record new group messages and edits, with separate group and user logs, rotation, and retention controls.
- **Research:** public email, username, domain, IP, phone, Telegram profile, image metadata, and geolocation tools.
- **Utilities:** notes, polls, text transformations, password generation, profile management, and group administration.
- **Automation:** private-chat AFK replies, reactions to outgoing messages, and protection against new logins.
- **SoundCloud:** control a local browser player through WebNowPlaying and deliver synchronized lyrics to a chat.
- **Operations:** local diagnostics, atomic state updates, backup recovery, queued log writes, and cancellable research jobs.

## Requirements

- Python **3.10 or later**.
- A Telegram user account and API credentials from [my.telegram.org](https://my.telegram.org).
- Internet access for Telegram and the external services used by individual commands.
- Windows for the included `run.cmd` launcher and the installation commands below.

Dependencies are listed in [requirements.txt](requirements.txt). These include `tgcrypto-pyrofork`, which provides the `tgcrypto` module used by Kurigram for cryptographic acceleration. A separate BotFather token is not required.

Optional features require a WebNowPlaying browser extension for SoundCloud, a contact URL or email for LRCLIB lyrics, or your own API key for GeoSeeer analysis.

## Installation

### 1. Create the environment

Download or clone the project, open **Command Prompt** in its root directory, and run:

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
```

Create the virtual environment on each machine where you install a fresh copy of Melixsa.

### 2. Configure Telegram

For a fresh installation, copy the configuration template:

```bat
copy .env.example .env
```

If `.env` already exists, edit that file instead. Replace the following placeholders with your credentials from my.telegram.org:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_with_your_api_hash
```

The API ID must be a valid positive numeric ID; the API hash must contain 32 hexadecimal characters. Leave optional integration fields empty until you configure them.

### 3. Launch Melixsa

From Command Prompt:

```bat
run.cmd
```

From PowerShell:

```powershell
.\run.cmd
```

On first launch, follow the Telegram prompts for your phone number, login code, and two-step verification password, if enabled. The session is stored in `data/` and reused on subsequent launches.

Send `/help` in **Saved Messages** to open the command menu. Stop the application normally with `Ctrl+C` in the terminal.

**Startup behavior:** anti-login protection is enabled by default. The SoundCloud adapter also starts automatically and sends its connection panel to Saved Messages. SoundCloud can remain disconnected while you use other features.

## Configuration

Melixsa reads `.env` from the project root. Non-empty process environment variables take precedence over values in that file.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `TELEGRAM_API_ID` | Yes | None | Telegram application API ID |
| `TELEGRAM_API_HASH` | Yes | None | Telegram application API hash |
| `WEBNOWPLAYING_PORT` | No | `8976` | Local adapter port; integers from `1024` to `65535` |
| `GEOSEEER_API_KEY` | For `/geosint` | Unset | GeoSeeer media analysis key |
| `LRCLIB_CLIENT_CONTACT` | For `/sclyrics on` | Unset | Your project URL or contact email, included in the LRCLIB client identifier |
| `OSINT_INCLUDE_ADULT` | No | `0` | Set to `1` to include adult-category sites in username scans |

You can also supply Telegram credentials in the terminal. In Command Prompt:

```bat
set "TELEGRAM_API_ID=123456"
set "TELEGRAM_API_HASH=replace_with_your_api_hash"
run.cmd
```

In PowerShell:

```powershell
$env:TELEGRAM_API_ID = "123456"
$env:TELEGRAM_API_HASH = "replace_with_your_api_hash"
.\run.cmd
```

Replace placeholders before running either example. Valid Telegram credentials supplied through the environment are saved to `.env` for future launches. Missing or invalid credentials do not overwrite saved values. Restart Melixsa after configuration changes.

Set `NO_COLOR` in the process environment to disable console colors. This terminal setting is not loaded from `.env`.

## Command basics

The default prefix is `/`, used throughout this README. Open `/help`, a category such as `/tools`, or `/help <command>` for detailed syntax.

| Menu | Contents |
| --- | --- |
| `/admin` | User information and group administration |
| `/abuse` | Owner-only repeated-message commands |
| `/animated` | Text animations |
| `/fun` | GIF interactions, games, and automatic reactions |
| `/text` | Formatting, transformations, encodings, and hashes |
| `/misc` | Client information, profile tools, and AFK |
| `/mass` | Group and user monitoring |
| `/tools` | Calculator, passwords, notes, and polls |
| `/osint` | Public-source research |
| `/soundcloud` | Playback controls and lyrics |
| `/settings` | Configuration, permissions, diagnostics, and console options |

Aliases include `/h` and `/?` for help, `/profile` for Misc, and `/sc` for SoundCloud.

### Prefix and response deletion

`/prefix !` changes the prefix globally: commands become `!help`, `!status`, and so on. The prefix accepts one printable symbol and persists across restarts. The owner can always use `/prefix /` to restore `/`.

Recognized commands sent by the owner are deleted immediately, before execution. Authorized users' command messages remain in the chat. Responses are sent as new messages in the same chat and forum topic.

`/deleteafter 40` sets the response lifetime to 40 seconds, the default. Values range from `0` to `3600`; `0` keeps responses. Each response retains the timer active when it was sent. Melixsa must remain running for scheduled deletion to occur.

GeoSeeer result panels, automatic AFK replies, anti-login notifications, optional error notifications, and messages generated by `/spam` are retained. Ordinary messages and unrecognized commands are not deleted. Most execution errors are recorded in the terminal and operational log; use `/doctor` or the relevant status command to inspect problems.

## Access control

The owner can authorize other Telegram users:

```text
/access add @username
/access remove @username
/access list
/access allow admin
/access block admin
/access allow whois
/access allow soundcloud
```

`add` and `remove` also accept a numeric ID or a reply. `allow` and `block` accept a command, category, or category alias such as `mass` or `sc`.

By default, authorized users can use commands outside **Settings**, **Abuse**, **SoundCloud**, and **Misc**; help is included. SoundCloud and Misc can be enabled explicitly. Settings and Abuse remain owner-only, except for help.

Shared command permissions apply to all authorized users. Menus show only commands available to the requester. Permissions persist across restarts; moderation still requires the relevant Telegram administrator permissions.

## Monitoring

| Command | Behavior |
| --- | --- |
| `/surveillance` | Record new messages from other participants in the current group |
| `/sustop` | Stop monitoring the current group |
| `/stalk @username` | Monitor that user's new messages across groups visible to your account |
| `/unstalk @username` | Stop monitoring that user globally |
| `/monitorlist` | List monitored users and groups with available names, usernames, and IDs |
| `/stalklist` | List monitored users |
| `/sulist` | List monitored groups |
| `/status` | Show settings, current-group monitoring, and globally monitored users |
| `/whois @username` | Show user information available through Telegram |
| `/chatinfo` | Show current-group information |

`/surveillance`, `/sustop`, and `/chatinfo` require a group. `/stalk` and `/unstalk` also accept a numeric ID or a reply. Listing commands work in private chats and Saved Messages.

Group and user monitoring are independent. `/stalk` applies across all visible groups; `/unstalk` stops it everywhere. `/surveillance` applies only to the group where it was enabled.

Monitoring begins when enabled and does not download history. It records group messages and edits, excludes your own messages and service messages, and does not record private-chat conversations or download monitored media.

Records are UTF-8 JSON lines in `data/logs/group_<ID>.txt` and `data/logs/stalk_<USER_ID>.txt`. They contain timestamps, chat/message identifiers, available sender information, text or captions, and media types. Edits use the `edited` event. Monitoring configuration is restored after restarting.

## Utilities and account tools

Use built-in help for individual arguments and aliases.

| Category | Commands |
| --- | --- |
| Fun | `hug`, `kiss`, `pat`, `slap`, `tickle`, `feed`, `bite`, `shoot`, `iq`, `gay`, `love`, `dick`, `boobs`, `8ball`, `slot`, `coinflip`, `dice`, `choose`, `joke`, `dadjoke` |
| Animated | `cathi`, `flop`, `poof`, `boom`, `tableflip`, `unflip`, `warning` |
| Text | `ascii`, `reverse`, `vape`, `zalgo`, `bold`, `italic`, `spoiler`, `underline`, `strike`, `indent`, `indent_title`, `indent_footer`, `indent_all` |
| Encoding and hashes | `encode_base64`, `decode_base64`, `encode_leet`, `decode_leet`, `encode_md5`, `encode_sha1`, `encode_sha224`, `encode_sha256`, `encode_sha384`, `encode_sha512` |
| Tools | `calc`, `passgen`, `note`, `editnote`, `delnote`, `shownote`, `sendnote`, `notes`, `poll`, `cpoll` |
| Admin | `whois`, `chatinfo`, `kick`, `ban`, `unban`, `mute`, `unmute`, `slowmode`, `removeslowmode`, `guildname` |
| Misc | `uptime`, `about`, `ping`, `name`, `bio`, `avatar`, `afk`, `back`, `afkstatus` |
| Abuse | `spam`, `spamstop` |

```text
/choose pizza | sushi | pasta
/ascii Melixsa
/spoiler A surprise
/calc (12 + 3) * 4
/note ideas A new project idea
/shownote ideas
/poll Where should we go? | Rome | Milan
/name First name | Last name
```

- **Notes:** stored in `data/notes.json`, with up to 100 notes, 64-character names, and 3,000-character bodies. Display commands publish notes in the current chat.
- **Passwords:** `passgen` uses a cryptographic generator and accepts lengths from 8 to 128. The generated value is sent to the selected chat.
- **Text:** most transformations accept an argument or replied-to text up to 1,500 characters; ASCII banners accept up to 60. Formatting uses native Telegram entities. Hashes are digests, and leet decoding is approximate.
- **Polls:** separate a question and 2–10 options with `|`. `poll` is anonymous; `cpoll` creates a non-anonymous group poll.
- **Moderation:** `kick` removes a member and lifts the ban so they can rejoin. `unmute` restores current group defaults. Slow mode accepts `0`, `10`, `30`, `60`, `300`, `900`, or `3600` seconds.
- **Latency:** `ping` measures MTProto round-trip time with a five-second timeout, excluding response delivery.
- **Entertainment:** GIF interactions use nekos.best with a text fallback. Random scores and ASCII results are fictional. Animations update one message at two-second intervals, with one animation per chat.
- **Repeated messages:** owner-only `spam` accepts text, a count of 1–100, and an interval of 0–3600 seconds. One sequence runs per chat; `spamstop` stops it. Rate limits or rejected sends stop delivery. Generated messages remain in the chat.

## Public-source research

Use direct commands or `/osint <subcommand> <value>`. Research starts only when an authorized command is issued.

| Command | Purpose |
| --- | --- |
| `/username <name>` | Scan public sites using WhatsMyName indicators and attach a complete TXT report |
| `/email <address>` | MX, public Gravatar data, registrations detected by holehe, and known breach information |
| `/breach <email>` | Known breach names through XposedOrNot, without passwords |
| `/phone <+number>` | Number validity, region, original carrier, type, time zones, and formats |
| `/phone IT <number>` | Parse a national number using an explicit ISO region |
| `/namesearch <full name>` | Generate username candidates and public search queries |
| `/domain <domain>` | WHOIS, DNS, SPF/DMARC, certificate-derived subdomains, and links |
| `/dns <domain> [type]` | Query `A`, `AAAA`, `MX`, `TXT`, `NS`, or `CNAME`; defaults to `A` |
| `/rdap <domain>` | Public domain registration data |
| `/ssl <domain>` | Public TLS certificate on port 443 |
| `/subdomains <domain>` | Names published in certificate transparency records |
| `/harvester <domain>` | Public DNS and subdomain summary |
| `/ip <address>` | Approximate public-IP location, network information, and indexed Shodan InternetDB data |
| `/myip` | Return the fixed loopback value `127.0.0.1` |
| `/telegram <@username or t.me/...>` | Public Telegram web-profile information |
| `/dorks <text>` | Search queries and links |
| `/imageosint` | Replied-to image research and manual reverse-image-search links |
| `/exif` | Available image metadata and GPS information |
| `/forwardinfo` | Sender information Telegram exposes for a forwarded message |
| `/autoosint [value]` | Detect input type and select a lookup; also accepts a reply |
| `/osintall <value>` | Primary lookup and related follow-up lookups |

`/osint name Jane Doe` invokes name research; direct `/name` edits your profile. `/whois` inspects a Telegram user, while `/rdap` inspects a domain registration.

### Jobs and limits

Extended lookups return a job ID and run in the background, one at a time. At most **10 jobs** can be active or queued. Each running job has a **10-minute timeout**, including report delivery; queue waiting time is excluded.

```text
/osintjobs
/osintcancel 12
```

The owner can inspect and cancel all jobs. Authorized users can manage only their own jobs in the current chat, if those commands are enabled. Jobs and their history do not survive a restart. Basic direct lookups and GeoSeeer analysis do not use this queue.

Cancellation stops queued or active jobs and associated subprocesses. External requests already received cannot be withdrawn; work in a thread may finish without publishing results. Reports already sent remain subject to the response deletion timer.

WhatsMyName data is cached in `data/osint/wmn-data.json` and refreshed after seven days. Scans allow up to 20 concurrent requests with a 12-second per-site timeout. Adult-category sites are excluded unless `OSINT_INCLUDE_ADULT=1`. Email registration checks omit password-recovery checks.

### Results and media handling

Username matches require verification, IP locations are approximate, and carrier data may reflect the original carrier. Generated links do not confirm account registration. Service failures are distinguished from negative results. IP lookups read indexed data without active port scanning.

Forward information respects what Telegram exposes. EXIF analysis reads up to the first 1 MiB of a Telegram file in memory; original image documents usually preserve more metadata than compressed photos. Standard EXIF and image-research tools do not upload images to analysis services; reverse-image-search links are used manually.

Email, username, domain, and IP lookups contact external providers. Results do not expose private Telegram phone numbers or breach passwords.

### GeoSeeer analysis

Set `GEOSEEER_API_KEY` in `.env`, restart, and reply to supported media with `/geosint`.

Supported input includes photos, videos, animations, image/video documents up to **20 MiB**, or a message with one HTTP/HTTPS media URL. Media is downloaded into memory and sent to GeoSeeer in `fast` mode; URLs are passed to the service for analysis.

Results contain the complete returned JSON, split into messages if needed. Successful result panels are retained regardless of `deleteafter`. Analysis can take several minutes and consume credits; failed requests are not retried automatically. This integration sends selected media or its URL to an external service.

## SoundCloud and lyrics

### Connect WebNowPlaying

The browser and Melixsa must run on the **same computer**.

1. Install the [WebNowPlaying Firefox extension](https://addons.mozilla.org/en-US/firefox/addon/webnowplaying/).
2. Select **Add custom adapter** in the extension, set port **8976**, and enable it.
3. Open SoundCloud, start a track, and keep the tab open.
4. Use `/scconnect` to inspect the connection and `/scnp` to display the track.

The adapter uses WebNowPlaying revision 3 and listens on `127.0.0.1` only. To change ports, set `WEBNOWPLAYING_PORT` in `.env`, configure the same port in the extension, and restart.

| Command | Action |
| --- | --- |
| `/scnp` | Track, artist, album, playback state, position, duration, and volume |
| `/scplay`, `/scpause`, `/sctoggle` | Resume, pause, or toggle playback |
| `/scnext`, `/scprev` | Move through the SoundCloud queue |
| `/scvolume [0-100]` | Display or set volume |
| `/scseek <seconds or mm:ss>` | Seek within the track; `hh:mm:ss` is also accepted |
| `/screpeat <off\|all\|one>` | Set repeat mode |
| `/scshuffle [on\|off\|toggle]` | Set or toggle shuffle |
| `/sclike [on\|off\|toggle]` | Add or remove a like using the browser's account |
| `/scplayers` | List tabs; `*` marks the selected player |
| `/scselect <ID\|auto>` | Select a player or automatic selection |
| `/scconnect` | Connection details and adapter startup |

The `/soundcloud` and `/sc` menus accept subcommands such as `/soundcloud np` and `/soundcloud volume 50`.

Automatic selection prefers a playing SoundCloud tab with nonzero volume, then the most recently active tab. Manual selection lasts until the tab closes or Melixsa restarts. Choose tracks and manage the queue in SoundCloud itself. Actions depend on the player and extension; timed-out commands are not repeated automatically.

### Synchronized lyrics

Set `LRCLIB_CLIENT_CONTACT` to your actual project URL or contact email, restart, and use:

```text
/sclyrics on
/sclyrics status
/sclyrics off
```

`on` selects the current chat and topic as the destination, waiting for a player if needed. Only one destination is active; enabling lyrics elsewhere moves delivery there. `off` stops delivery from any chat. Lyrics start disabled after every restart.

The LRCLIB integration sends track metadata and your configured client contact to retrieve timestamped lyrics. Lines are sent separately, follow `deleteafter`, and track pauses and playback position. Passed lines are skipped, messages are spaced at least three seconds apart, and tracks without synchronized lyrics are skipped.

Temporary service failures use bounded retries with backoff and respect longer `Retry-After` values. Telegram FloodWait or delivery failures stop lyrics; inspect `/sclyrics status` for details.

## Account automation

### Anti-login protection

Anti-login is **enabled by default** and uses the existing Kurigram session:

```text
/anti-login status
/anti-login off
/anti-login on
```

`antilogin` is an alias; `enable`/`disable` are accepted. The enabled state persists across restarts.

Melixsa treats sessions present at startup as trusted and preserves its own session. While enabled, it checks every 30 seconds and attempts to terminate sessions outside that baseline. It also attempts to invalidate login codes explicitly identified in Telegram service messages from account `777000`, recognizing supported Italian, English, Spanish, and Russian phrases.

To add your own device, turn protection off before signing in, then restart Melixsa to include that device in the trusted baseline before re-enabling protection. If the initial session list cannot be read, termination stays suspended; inspect the status and use `/anti-login on` to retry initialization.

Session controls remain subject to Telegram restrictions, including the fresh-session restriction handled by Melixsa. Protection can interrupt legitimate logins and cannot guarantee every new login is prevented. Successful actions generate retained Saved Messages notifications; errors are logged locally. Login codes and their message bodies are not copied into those notifications or logs.

### AFK replies

```text
/afk Away right now; I will reply when I return.
/afkstatus
/back
```

`/afk` enables private-chat replies with an optional message and GIF. `/back`, also available as `/unafk`, disables AFK and reports elapsed time. Normal outgoing messages do not disable it.

AFK applies to new private messages from people, excluding bots, Saved Messages, service messages, and groups. Each person receives at most one reply every **six hours**. Repeating `/afk` updates the message, restarts the timer, and resets recipients. AFK starts **off after every restart**.

Custom messages accept up to 3,000 UTF-16 units. Long replies may use separate GIF and text messages; rejected GIFs fall back to text. Automatic replies remain in the chat. FloodWait suspends delivery; skipped messages are not replayed.

### Automatic reactions

```text
/autoreact emoji 👍 ❤️ 🔥
/autoreact count 1
/autoreact on
/autoreact
/autoreact off
```

Choose one to three distinct emojis and how many of the first emojis to use. The count cannot exceed the list. Settings persist across restarts; reactions are initially disabled.

Reactions apply to your new outgoing messages in private chats and groups, including media. Commands, edits, service messages, history, and messages generated by `/spam` are excluded. Disabling the feature leaves existing reactions intact.

Telegram determines available reactions and counts for your account and each chat. Rejections appear in the terminal and feature status; restrictions pause or skip delivery without replaying missed messages.

## Diagnostics and recovery

### Health and console commands

| Command | Purpose |
| --- | --- |
| `/doctor` | Inspect local connections, configuration format, backups, logs, jobs, integrations, and recent errors |
| `/errornotify [on\|off]` | Generic Saved Messages error notifications; defaults to off |
| `/console` | Redisplay the banner and settings |
| `/clear` | Clear the local terminal display |
| `/debug-mode [on\|off]` | Toggle technical Telegram and WebNowPlaying details; defaults to off |
| `/minimal-mode [on\|off]` | Show command syntax without descriptions; defaults to off |
| `/timestamp <on\|off>` | Console timestamps |
| `/spacers <on\|off>` | Console separators |
| `/pgradient <on\|off>` | Console log colors |
| `/lgradient <on\|off>` | Banner colors |

`doctor` does not call external services or reveal credential values. Error notifications are generic, retained, and limited to one per minute. Console settings persist across restarts.

The operational log, `data/logs/melixsa.log`, rotates at **2 MB** with **three backups**. It records command names, chat labels, timings, and events. Normal response bodies, command arguments, generated passwords, and received private-message content are not copied into this log. Monitoring logs separately contain group-message data.

### Monitoring-log retention

```text
/logconfig
/logconfig size 10000000
/logconfig backups 5
/logconfig days 7
```

| Option | Default | Accepted range |
| --- | --- | --- |
| `size` | `10000000` bytes per active file | `65536`–`1000000000` |
| `backups` | `5` closed archives per monitor | `1`–`100` |
| `days` | `0`, time-based expiry disabled | `0`–`3650` |

Limits apply to group and user logs, including stopped monitors. Time-based retention also rotates files at the UTC day boundary. Reducing limits can delete archives. Recovery files named `pending-*.json` are excluded from cleanup. The operational log uses separate rotation settings.

### State and write recovery

Settings are saved atomically to `data/state.json`, with a validated backup at `data/state.json.bak`. If the primary file is missing or invalid, Melixsa attempts the backup. If neither works, it starts with defaults and no authorized users or active monitors. Damaged files are preserved as `state.json.corrupt-<number>` when repaired. Failed setting writes restore previous in-memory values.

Monitoring logs use a background writer with a **5,000-record queue**, plus the active batch. Failed writes retain unfinished records for retry. During normal shutdown, records pending after five seconds are saved as `data/logs/pending-<number>.json` for recovery at next launch. Forced shutdown can lose in-memory records; interruption recovery can produce duplicates.

## Local data and GitHub uploads

Keep these files and directories local:

| Path or pattern | Reason |
| --- | --- |
| `.env` and `.env.*`, except `.env.example` | Credentials and local configuration |
| `data/` | Telegram session, state, notes, monitoring records, logs, and cache |
| `*.session`, `*.session-*`, `*.session.*` | Telegram authentication files and sidecars |
| `.venv/`, `venv/`, `env/`, `ENV/` | Machine-specific Python environments |
| `__pycache__/`, `*.pyc`, tool caches | Generated bytecode and tooling data |
| Logs, temporary files, build output, editor settings | Generated or machine-specific files |

The included [.gitignore](.gitignore) excludes these files. [.env.example](.env.example) is intended for publication and should contain placeholders only. Source code, tests, dependency declarations, documentation, and third-party notices can be shared.

For manual GitHub uploads, exclude local files yourself. `.gitignore` is applied by Git when adding files; it does not remove tracked files or erase earlier commits.

Protect the Telegram session alongside credentials: it authenticates your account. Logs and notes can contain personal information. Use monitoring only where you are authorized to record messages, and control access to the local data directory.

## Project structure

```text
Melixsa Selfbot/
├── selfbot.py                 # Entry point and environment fallback
├── run.cmd                    # Windows launcher
├── Cogs/
│   ├── runtime.py             # Shared state and Telegram lifecycle
│   ├── catalog.py             # Categories, syntax, help, and aliases
│   ├── commands/              # Telegram command handlers
│   ├── config_tools.py        # Configuration and credentials
│   ├── persistence_tools.py   # Atomic writes and backups
│   ├── log_tools.py           # Queued writes, rotation, and recovery
│   ├── jobs_tools.py          # Research queue and cancellation
│   ├── error_tools.py         # Optional error notifications
│   ├── console_tools.py       # Banner and operational logging
│   ├── luna_tools.py          # Utility, entertainment, and profile helpers
│   ├── autoreact_tools.py     # Outgoing-message reactions
│   ├── afk_tools.py           # Private-chat AFK replies
│   ├── anti_login_tools.py    # Login-code and session controls
│   ├── osint_tools.py         # Basic public-source lookups
│   ├── osint_features.py      # Extended reports and media research
│   ├── osint_extras/          # Adapted research backends
│   ├── geosint_tools.py       # GeoSeeer client
│   ├── soundcloud_tools.py    # WebNowPlaying adapter
│   └── lyrics_tools.py        # LRCLIB integration
├── tests/                     # Automated verification
├── data/                      # Local runtime data; excluded from Git
├── .env                       # Local credentials; excluded from Git
├── .env.example               # Shareable configuration template
├── .gitignore
├── requirements.txt
├── README.md
└── THIRD_PARTY_NOTICES.txt
```

Handlers use shared services from `Cogs`. Start through `run.cmd` or `selfbot.py`; individual modules are not entry points. Configuration and data paths are resolved relative to the project location.

## Development

Run the existing test suite from the project root:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers routing, permissions, configuration, monitoring, persistence, recovery, integrations, and automation with local fixtures and mocks; Telegram login is not required.

After updating the project, install changed dependencies and restart:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
run.cmd
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Missing virtual environment | Create `.venv` and install requirements using the installation commands |
| Import errors | Install requirements with `.venv\Scripts\python.exe`, then use `run.cmd` |
| Invalid Telegram credentials | Replace placeholders; verify the numeric ID and 32-character hexadecimal hash |
| Commands do not respond | Check prefix, permissions, chat context, and terminal output; the owner can restore `/` with `/prefix /` |
| Responses disappear | Inspect `/deleteafter`; use `0` to retain ordinary responses |
| No SoundCloud player | Keep the tab open, enable the custom adapter, and match its port to `WEBNOWPLAYING_PORT` |
| Adapter port unavailable | Choose another port in `.env` and the extension, then restart |
| Lyrics do not start | Set `LRCLIB_CLIENT_CONTACT`, inspect `/sclyrics status`, and check track availability |
| GeoSeeer errors | Inspect logs for key, credit, rate-limit, or API-access errors; requests are not retried automatically |
| New device login interrupted | Disable anti-login before signing in, then restart to refresh trusted sessions |
| State or log writes fail | Check directory permissions and disk space; inspect `/doctor` and retain pending recovery files |

## Credits

| Project | Contribution |
| --- | --- |
| [Kurigram](https://github.com/kurigram-org/kurigram) | Telegram client library |
| [Luna Selfbot reversed by Nas](https://github.com/ImHisako/Luna-Selfbot-Source-Code-by-Nas) | Console styling, menus, and adapted commands |
| [rehuux/selfbot](https://github.com/rehuux/selfbot) by **[Syed Rehan](https://rehuux.vercel.app)** | AFK behavior and public-source research references |
| [AbelXeon/OSINT-BOT](https://github.com/AbelXeon/OSINT-BOT) | Adapted research backends |
| [WhatsMyName by WebBreacher](https://github.com/WebBreacher/WhatsMyName) | Username-detection dataset |
| [WebNowPlaying](https://wnp.keifufu.dev/creating-adapters/getting-started) | Browser playback integration |
| [LRCLIB](https://lrclib.net/docs) | Timestamped lyrics |
| [nekos.best](https://docs.nekos.best/getting-started/api-endpoints.html) | GIF interactions |

Attributions and included third-party license terms are preserved in [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt). Retain those notices when redistributing the corresponding code. These notices describe third-party components and do not establish a single project-wide license for Melixsa.
